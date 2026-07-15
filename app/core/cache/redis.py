"""
Redis 异步连接管理器 - 轻量级设计
支持自动连接池、异步操作、JSON 序列化、连接保活
"""

import asyncio
import json
from collections.abc import Awaitable, Mapping
from typing import Any, Optional, cast

import redis.asyncio as redis
from redis.asyncio import ConnectionPool, Redis
from redis.exceptions import ResponseError
from redis.typing import EncodableT

from app.core.log import log
from config.cache_config import CacheSettings
from config.settings import get_settings

_SERIALIZATION_PREFIX = "__fastapi_template_cache__:v1:"
_CLEAR_SCAN_COUNT = 500


async def _await_redis_response[ResponseT](response: Awaitable[ResponseT] | ResponseT) -> ResponseT:
    """统一等待 Redis 响应结果。

    `redis.asyncio` 的类型定义将很多命令标注为 `Awaitable[T] | T`，
    会导致 IDE 在直接 `await client.xxx()` 时误报类型告警。
    这里集中处理同步/异步联合返回，避免在业务方法中重复编写类型收窄逻辑。
    """
    if isinstance(response, Awaitable):
        return await cast(Awaitable[ResponseT], response)
    return cast(ResponseT, response)


def _create_connection_pool(cache_config: CacheSettings) -> ConnectionPool:
    """使用结构化参数创建 Redis 连接池，避免密码参与 URL 字符串拼接。"""
    return ConnectionPool(
        host=cache_config.REDIS_HOST,
        port=cache_config.REDIS_PORT,
        db=cache_config.REDIS_DB,
        password=cache_config.REDIS_PASSWORD,
        max_connections=cache_config.REDIS_MAX_CONNECTIONS,
        socket_connect_timeout=cache_config.REDIS_TIMEOUT,
        socket_keepalive=True,
        decode_responses=True,
    )


class RedisManager:
    """Redis 异步连接管理器"""

    _instance: Optional["RedisManager"] = None
    _pool: ConnectionPool | None = None
    _client: Redis | None = None
    _heartbeat_task: asyncio.Task[None] | None = None
    _heartbeat_interval: int = 30  # 心跳间隔（秒）
    _reconnect_interval: int = 5  # 重连等待间隔（秒）
    _redis_prefix: str | None = None  # Redis 键前缀
    _reconnect_count: int = 0  # 重连计数
    _max_reconnect_attempts: int = 5  # 最大重连次数

    def __new__(cls) -> "RedisManager":
        instance = cls._instance
        if instance is None:
            instance = super().__new__(cls)
            cls._instance = instance
        return instance

    def _get_prefixed_key(self, key: str) -> str:
        """获取带前缀的键名"""
        if self._redis_prefix is None:
            settings = get_settings()
            self._redis_prefix = settings.cache.REDIS_PREFIX
        return f"{self._redis_prefix}:{key}"

    def _require_client(self) -> Redis:
        """获取已初始化的 Redis 客户端。

        若外部在未建立连接时直接调用缓存读写方法，这里会抛出明确异常，
        同时也为类型检查器提供稳定的非空返回类型。
        """
        client = self._client
        if client is None:
            raise RuntimeError("Redis 客户端未初始化，请先调用 connect() 建立连接")
        return client

    @staticmethod
    def _escape_scan_pattern(value: str) -> str:
        """转义 Redis SCAN 匹配表达式中的特殊字符。"""
        special_characters = {"\\", "*", "?", "[", "]"}
        return "".join(f"\\{character}" if character in special_characters else character for character in value)

    @staticmethod
    async def _delete_scanned_keys(client: Redis, keys: list[str]) -> int:
        """优先异步释放扫描到的键，不支持 UNLINK 时回退到 DELETE。"""
        unlink = getattr(client, "unlink", None)
        if unlink is not None:
            try:
                return cast(int, await _await_redis_response(unlink(*keys)))
            except ResponseError as exc:
                if "unknown command" not in str(exc).lower():
                    raise
        return cast(int, await _await_redis_response(client.delete(*keys)))

    async def connect(self) -> None:
        """初始化 Redis 连接池并启动心跳检查"""
        if self._client is not None:
            log.debug("Redis 已连接，跳过重复连接")
            return

        settings = get_settings()
        cache_config = settings.cache

        try:
            # 前置配置检查
            log.debug(f"[Redis] 连接前配置检查 - 主机:{cache_config.REDIS_HOST}, 端口:{cache_config.REDIS_PORT}")

            # 验证基础配置
            if not cache_config.REDIS_HOST or cache_config.REDIS_PORT <= 0:
                raise ValueError("Redis 主机地址或端口配置错误")

            if cache_config.REDIS_MAX_CONNECTIONS <= 0:
                raise ValueError(f"Redis 连接池大小必须大于 0，当前值: {cache_config.REDIS_MAX_CONNECTIONS}")

            if cache_config.REDIS_TIMEOUT <= 0:
                raise ValueError(f"Redis 连接超时时间必须大于 0，当前值: {cache_config.REDIS_TIMEOUT}")

            if not cache_config.REDIS_PREFIX or not isinstance(cache_config.REDIS_PREFIX, str):
                raise ValueError(f"REDIS_PREFIX 必须是非空字符串，当前值: {cache_config.REDIS_PREFIX}")

            # 创建连接池
            log.debug(f"[Redis] 创建连接池 - 最大连接数:{cache_config.REDIS_MAX_CONNECTIONS}")
            pool = _create_connection_pool(cache_config)
            self._pool = pool

            # 创建 Redis 客户端
            log.debug("开始建立 Redis 客户端连接...")
            client = redis.Redis(connection_pool=pool)
            self._client = client

            # 测试连接
            await _await_redis_response(client.ping())
            log.info(
                f"✅ Redis 连接成功 - "
                f"主机:{cache_config.REDIS_HOST} | "
                f"端口:{cache_config.REDIS_PORT} | "
                f"数据库:{cache_config.REDIS_DB}"
            )

            # 启动心跳检查任务
            self._reconnect_count = 0
            self._start_heartbeat()

        except Exception as e:
            log.error(f"❌ Redis 连接失败: {e}")
            await self._close_connections()
            raise

    async def disconnect(self) -> None:
        """关闭 Redis 连接并停止心跳检查"""
        log.debug("开始关闭 Redis 连接...")

        # 停止心跳检查
        self._stop_heartbeat()

        await self._close_connections()
        log.info("✅ Redis 已断开连接")

    async def _close_connections(self) -> None:
        """关闭 Redis 客户端与连接池，但不改变当前心跳任务状态。"""

        client = self._client
        self._client = None
        if client is not None:
            try:
                await _await_redis_response(client.close())
                log.debug("✅ Redis 客户端已关闭")
            except Exception as e:
                log.warning(f"⚠️ 关闭 Redis 客户端异常: {e}")

        pool = self._pool
        self._pool = None
        if pool is not None:
            try:
                await _await_redis_response(pool.disconnect())
                log.debug("✅ Redis 连接池已断开")
            except Exception as e:
                log.warning(f"⚠️ Redis 连接池断开异常: {e}")

    async def ping(self) -> bool:
        """检查当前 Redis 连接是否可用。"""
        client = self._require_client()
        return cast(bool, await _await_redis_response(client.ping()))

    def _start_heartbeat(self) -> None:
        """启动心跳检查任务"""
        if self._heartbeat_task is not None:
            log.debug("❤️ 心跳检查已启动，跳过重复启动")
            return

        self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())
        log.info(f"❤️ Redis 心跳检查已启动 (检查间隔: {self._heartbeat_interval} 秒)")

    def _stop_heartbeat(self) -> None:
        """停止心跳检查任务"""
        heartbeat_task = self._heartbeat_task
        if heartbeat_task is None:
            return

        if heartbeat_task is not asyncio.current_task():
            heartbeat_task.cancel()
        self._heartbeat_task = None
        log.debug("❤️ Redis 心跳检查已停止")

    async def _reconnect(self) -> bool:
        """关闭失效连接并按上限重试，成功时继续复用当前心跳任务。"""
        await self._close_connections()

        while self._reconnect_count < self._max_reconnect_attempts:
            self._reconnect_count += 1
            current_attempt = self._reconnect_count
            log.info(f"🔄 尝试重新连接 Redis ({current_attempt}/{self._max_reconnect_attempts})...")

            await asyncio.sleep(self._reconnect_interval)
            try:
                await self.connect()
            except asyncio.CancelledError:
                raise
            except Exception as reconnect_error:
                log.error(f"❌ Redis 重连失败 ({current_attempt}/{self._max_reconnect_attempts}): {reconnect_error}")
                continue

            self._reconnect_count = 0
            log.info("✅ Redis 重连成功")
            return True

        log.error("❌ 达到最大重连次数，停止重连")
        return False

    async def _heartbeat_loop(self) -> None:
        """心跳检查循环"""
        heartbeat_task = asyncio.current_task()
        try:
            while True:
                try:
                    await asyncio.sleep(self._heartbeat_interval)

                    client = self._client
                    if client is None:
                        break

                    # 执行 ping 测试连接
                    await _await_redis_response(client.ping())
                    log.debug("❤️ Redis 心跳检查: 正常")

                except asyncio.CancelledError:
                    raise
                except Exception as e:
                    log.warning(f"⚠️ Redis 心跳检查失败: {e}")
                    if not await self._reconnect():
                        break
        finally:
            if self._heartbeat_task is heartbeat_task:
                self._heartbeat_task = None

    # ==================== Key-Value 操作 ====================

    async def set(self, key: str, value: Any, ex: int | None = None) -> bool:
        """
        设置缓存值
        :param key: 缓存键（自动添加项目前缀）
        :param value: 缓存值（自动序列化复杂类型）
        :param ex: 过期时间（秒）
        """
        try:
            client = self._require_client()
            prefixed_key = self._get_prefixed_key(key)
            serialized_value = self._serialize(value)
            result = cast(bool, await _await_redis_response(client.set(prefixed_key, serialized_value, ex=ex)))
            return result
        except Exception as e:
            log.error(f"❌ 设置缓存失败 ({key}): {e}")
            raise

    async def get(self, key: str, default: Any = None) -> Any:
        """
        获取缓存值
        :param key: 缓存键（自动添加项目前缀）
        :param default: 默认值
        """
        try:
            client = self._require_client()
            prefixed_key = self._get_prefixed_key(key)
            value = await _await_redis_response(client.get(prefixed_key))
            if value is None:
                return default
            return self._deserialize_with_fallback(value, location=f"key={key}")
        except Exception as e:
            log.error(f"❌ 获取缓存失败 ({key}): {e}")
            raise

    async def delete(self, *keys: str) -> int:
        """删除缓存"""
        if not keys:
            return 0
        try:
            client = self._require_client()
            prefixed_keys = [self._get_prefixed_key(k) for k in keys]
            return cast(int, await _await_redis_response(client.delete(*prefixed_keys)))
        except Exception as e:
            log.error(f"❌ 删除缓存失败: {e}")
            raise

    async def exists(self, *keys: str) -> int:
        """检查键是否存在"""
        if not keys:
            return 0
        try:
            client = self._require_client()
            prefixed_keys = [self._get_prefixed_key(k) for k in keys]
            return cast(int, await _await_redis_response(client.exists(*prefixed_keys)))
        except Exception as e:
            log.error(f"❌ 检查键存在性失败: {e}")
            raise

    async def clear(self) -> None:
        """分批清理当前项目前缀下的键，不影响共享 Redis 数据库中的其他项目。"""
        try:
            client = self._require_client()
            pattern = f"{self._escape_scan_pattern(self._get_prefixed_key(''))}*"
            cursor = 0
            deleted_count = 0
            while True:
                scan_result = await _await_redis_response(
                    client.scan(cursor=cursor, match=pattern, count=_CLEAR_SCAN_COUNT)
                )
                cursor, keys = cast(tuple[int, list[str]], scan_result)
                if keys:
                    deleted_count += await self._delete_scanned_keys(client, keys)
                if cursor == 0:
                    break
            log.info(f"✅ 已清理当前 Redis 前缀缓存，共删除 {deleted_count} 个键")
        except Exception as e:
            log.error(f"❌ 清理当前 Redis 前缀缓存失败: {e}")
            raise

    async def expire(self, key: str, ex: int) -> bool:
        """为指定键设置过期时间
        :param key: 缓存键（自动添加项目前缀）
        :param ex: 过期时间（秒）
        :return: 是否成功设置过期时间
        """
        try:
            client = self._require_client()
            prefixed_key = self._get_prefixed_key(key)
            result = cast(bool, await _await_redis_response(client.expire(prefixed_key, ex)))
            if result:
                log.debug(f"✅ 已为键 {key} 设置过期时间: {ex} 秒")
            else:
                log.warning(f"⚠️ 键 {key} 不存在，无法设置过期时间")
            return result
        except Exception as e:
            log.error(f"❌ 设置过期时间失败 ({key}): {e}")
            raise

    async def ttl(self, key: str) -> int:
        """获取键的剩余存活时间
        :param key: 缓存键（自动添加项目前缀）
        :return: 剩余秒数，-1 表示永久存储，-2 表示键不存在
        """
        try:
            client = self._require_client()
            prefixed_key = self._get_prefixed_key(key)
            return cast(int, await _await_redis_response(client.ttl(prefixed_key)))
        except Exception as e:
            log.error(f"❌ 获取键存活时间失败 ({key}): {e}")
            raise

    # ==================== 批量操作 ====================

    async def mset(self, data: dict[str, Any], ex: int | None = None) -> bool:
        """
        批量设置缓存
        :param data: {key: value, ...}（key自动添加项目前缀）
        :param ex: 过期时间（秒）
        """
        if not data:
            return True

        try:
            client = self._require_client()
            serialized_data = {self._get_prefixed_key(k): self._serialize(v) for k, v in data.items()}
            result = cast(bool, await _await_redis_response(client.mset(serialized_data)))

            # 如果设置了过期时间，使用 pipeline 批量发送 expire 命令，避免 N 次网络往返
            if ex is not None:
                async with client.pipeline(transaction=False) as pipe:
                    for prefixed_key in serialized_data:
                        # await 将命令入队到 pipeline 本地缓冲区，不会立即发送网络请求
                        # 真正的批量发送发生在 pipe.execute() 时
                        await pipe.expire(prefixed_key, ex)
                    await pipe.execute()

            return result
        except Exception as e:
            log.error(f"❌ 批量设置失败: {e}")
            raise

    async def mget(self, *keys: str) -> list[Any]:
        """
        批量获取缓存
        :param keys: 缓存键列表（自动添加项目前缀）
        :return: 值列表（按键顺序）
        """
        if not keys:
            return []

        try:
            client = self._require_client()
            prefixed_keys = [self._get_prefixed_key(k) for k in keys]
            values = cast(list[str | None], await _await_redis_response(client.mget(*prefixed_keys)))
            # 对每个值进行反序列化，处理可能的异常
            result: list[Any] = []
            for i, v in enumerate(values):
                if v is None:
                    result.append(None)
                else:
                    result.append(self._deserialize_with_fallback(v, location=f"key={keys[i]}, index={i}"))
            return result
        except Exception as e:
            log.error(f"❌ 批量获取失败 (keys: {keys}): {e}")
            raise

    # ==================== 哈希操作 ====================

    async def hset(self, name: str, mapping: dict[str, Any], ex: int | None = None) -> int:
        """
        设置哈希字段
        :param name: 哈希键名（自动添加项目前缀）
        :param mapping: 字段映射 {field: value, ...}
        :param ex: 过期时间（秒）
        """
        try:
            client = self._require_client()
            prefixed_name = self._get_prefixed_key(name)
            serialized_mapping: Mapping[str, EncodableT] = {
                key: self._serialize(value) for key, value in mapping.items()
            }
            result = cast(
                int,
                await _await_redis_response(
                    # ty 无法根据 redis-py 的 self 类型重载识别异步客户端，运行时返回值仍由统一适配器处理。
                    client.hset(  # ty: ignore[no-matching-overload]
                        prefixed_name,
                        mapping=serialized_mapping,
                    )
                ),
            )

            # 如果设置了过期时间
            if ex is not None:
                await _await_redis_response(client.expire(prefixed_name, ex))

            return result
        except Exception as e:
            log.error(f"❌ 哈希设置失败 ({name}): {e}")
            raise

    async def hget(self, name: str, key: str) -> Any:
        """获取哈希字段值"""
        try:
            client = self._require_client()
            prefixed_name = self._get_prefixed_key(name)
            value = await _await_redis_response(client.hget(prefixed_name, key))
            return (
                self._deserialize_with_fallback(value, location=f"key={name}, field={key}")
                if value is not None
                else None
            )
        except Exception as e:
            log.error(f"❌ 哈希获取失败 ({name}[{key}]): {e}")
            raise

    async def hgetall(self, name: str) -> dict[str, Any]:
        """获取哈希所有字段"""
        try:
            client = self._require_client()
            prefixed_name = self._get_prefixed_key(name)
            data = cast(dict[str, str], await _await_redis_response(client.hgetall(prefixed_name)))
            # 对每个值进行反序列化，处理可能的异常
            result: dict[str, Any] = {}
            for k, v in data.items():
                result[k] = self._deserialize_with_fallback(v, location=f"key={name}, field={k}")
            return result
        except Exception as e:
            log.error(f"❌ 获取哈希所有字段失败 ({name}): {e}")
            raise

    async def hdel(self, name: str, *keys: str) -> int:
        """删除哈希字段"""
        if not keys:
            return 0
        try:
            client = self._require_client()
            prefixed_name = self._get_prefixed_key(name)
            return cast(int, await _await_redis_response(client.hdel(prefixed_name, *keys)))
        except Exception as e:
            log.error(f"❌ 哈希删除失败 ({name}): {e}")
            raise

    # ==================== 列表操作 ====================

    async def lpush(self, name: str, *values: Any, ex: int | None = None) -> int:
        """从列表左端推入值
        :param name: 列表键名（自动添加项目前缀）
        :param values: 要推入的值
        :param ex: 过期时间（秒）
        """
        if not values:
            return 0
        try:
            client = self._require_client()
            prefixed_name = self._get_prefixed_key(name)
            serialized_values = [self._serialize(v) for v in values]
            result = cast(int, await _await_redis_response(client.lpush(prefixed_name, *serialized_values)))

            # 如果设置了过期时间
            if ex is not None:
                await _await_redis_response(client.expire(prefixed_name, ex))

            return result
        except Exception as e:
            log.error(f"❌ 列表左推失败 ({name}): {e}")
            raise

    async def rpush(self, name: str, *values: Any, ex: int | None = None) -> int:
        """从列表右端推入值
        :param name: 列表键名（自动添加项目前缀）
        :param values: 要推入的值
        :param ex: 过期时间（秒）
        """
        if not values:
            return 0
        try:
            client = self._require_client()
            prefixed_name = self._get_prefixed_key(name)
            serialized_values = [self._serialize(v) for v in values]
            result = cast(int, await _await_redis_response(client.rpush(prefixed_name, *serialized_values)))

            # 如果设置了过期时间
            if ex is not None:
                await _await_redis_response(client.expire(prefixed_name, ex))

            return result
        except Exception as e:
            log.error(f"❌ 列表右推失败 ({name}): {e}")
            raise

    async def lrange(self, name: str, start: int = 0, end: int = -1) -> list[Any]:
        """获取列表范围内的值"""
        try:
            client = self._require_client()
            prefixed_name = self._get_prefixed_key(name)
            values = cast(list[str], await _await_redis_response(client.lrange(prefixed_name, start, end)))
            # 对每个元素进行反序列化，处理可能的异常
            return [
                self._deserialize_with_fallback(value, location=f"key={name}, index={index}")
                for index, value in enumerate(values)
            ]
        except Exception as e:
            log.error(f"❌ 获取列表范围失败 ({name}[{start}:{end}]): {e}")
            raise

    async def lpop(self, name: str) -> Any:
        """从列表左端弹出值"""
        try:
            client = self._require_client()
            prefixed_name = self._get_prefixed_key(name)
            value = await _await_redis_response(client.lpop(prefixed_name))
            return (
                self._deserialize_with_fallback(value, location=f"key={name}, operation=lpop")
                if value is not None
                else None
            )
        except Exception as e:
            log.error(f"❌ 列表左弹出失败 ({name}): {e}")
            raise

    async def rpop(self, name: str) -> Any:
        """从列表右端弹出值"""
        try:
            client = self._require_client()
            prefixed_name = self._get_prefixed_key(name)
            value = await _await_redis_response(client.rpop(prefixed_name))
            return (
                self._deserialize_with_fallback(value, location=f"key={name}, operation=rpop")
                if value is not None
                else None
            )
        except Exception as e:
            log.error(f"❌ 列表右弹出失败 ({name}): {e}")
            raise

    # ==================== 集合操作 ====================

    async def sadd(self, name: str, *members: Any, ex: int | None = None) -> int:
        """添加集合成员
        :param name: 集合键名（自动添加项目前缀）
        :param members: 要添加的成员
        :param ex: 过期时间（秒）
        """
        if not members:
            return 0
        try:
            client = self._require_client()
            prefixed_name = self._get_prefixed_key(name)
            serialized_members = [self._serialize(m) for m in members]
            result = cast(int, await _await_redis_response(client.sadd(prefixed_name, *serialized_members)))

            # 如果设置了过期时间
            if ex is not None:
                await _await_redis_response(client.expire(prefixed_name, ex))

            return result
        except Exception as e:
            log.error(f"❌ 集合添加失败 ({name}): {e}")
            raise

    async def smembers(self, name: str) -> list[Any]:
        """以无序列表返回集合成员，使 list/dict 成员也能保持原始类型。"""
        try:
            client = self._require_client()
            prefixed_name = self._get_prefixed_key(name)
            members = cast(set[str], await _await_redis_response(client.smembers(prefixed_name)))
            return [
                self._deserialize_with_fallback(member, location=f"key={name}, index={index}")
                for index, member in enumerate(members)
            ]
        except Exception as e:
            log.error(f"❌ 获取集合成员失败 ({name}): {e}")
            raise

    async def srem(self, name: str, *members: Any) -> int:
        """移除集合成员"""
        if not members:
            return 0
        try:
            client = self._require_client()
            prefixed_name = self._get_prefixed_key(name)
            serialized_members = [self._serialize(m) for m in members]
            return cast(int, await _await_redis_response(client.srem(prefixed_name, *serialized_members)))
        except Exception as e:
            log.error(f"❌ 集合移除失败 ({name}): {e}")
            raise

    # ==================== 序列化/反序列化 ====================

    @classmethod
    def _validate_serializable_value(cls, value: Any) -> None:
        """递归校验缓存值，拒绝会在 JSON 转换中丢失类型的信息。"""
        value_type = type(value)
        if value is None or value_type in (str, bool, int, float):
            return
        if value_type in (list,):
            for item in value:
                cls._validate_serializable_value(item)
            return
        if value_type in (dict,):
            for key, item in value.items():
                if type(key) not in (str,):
                    raise TypeError("Redis 缓存字典的键必须是字符串")
                cls._validate_serializable_value(item)
            return
        raise TypeError(f"Redis 缓存不支持序列化类型: {type(value).__name__}")

    @staticmethod
    def _serialize(value: Any) -> str:
        """使用带版本标记的 JSON 协议序列化受支持的缓存值。"""
        RedisManager._validate_serializable_value(value)
        payload = json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        return f"{_SERIALIZATION_PREFIX}{payload}"

    @staticmethod
    def _deserialize(value: Any) -> Any:
        """解析当前版本缓存值；旧版无标记值保持原始字符串。"""
        if not isinstance(value, str) or not value.startswith(_SERIALIZATION_PREFIX):
            return value
        return json.loads(value.removeprefix(_SERIALIZATION_PREFIX))

    @staticmethod
    def _deserialize_with_fallback(value: Any, *, location: str) -> Any:
        """安全反序列化缓存值，失败时不在日志中暴露原始内容。"""
        try:
            return RedisManager._deserialize(value)
        except Exception as exc:
            log.warning(f"⚠️ 反序列化缓存值失败 ({location}): error_type={type(exc).__name__}")
            return value


# 全局单例
def get_redis_manager() -> RedisManager:
    """获取 Redis 管理器单例。

    RedisManager.__new__ 已通过类变量 _instance 保证全局唯一实例，
    此处直接调用构造函数即可，无需在模块层再维护额外的全局变量。
    """
    return RedisManager()


__all__ = ["RedisManager", "get_redis_manager"]
