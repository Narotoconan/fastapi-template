"""
Redis 异步连接管理器 - 轻量级设计
支持自动连接池、异步操作、JSON 序列化、连接保活
"""

import asyncio
import builtins
import json
from collections.abc import Awaitable
from typing import Any, Optional, cast

import redis.asyncio as redis
from redis.asyncio import ConnectionPool, Redis

from app.core.log import log
from config.settings import get_settings


async def _await_redis_response[ResponseT](response: Awaitable[ResponseT] | ResponseT) -> ResponseT:
    """统一等待 Redis 响应结果。

    `redis.asyncio` 的类型定义将很多命令标注为 `Awaitable[T] | T`，
    会导致 IDE 在直接 `await client.xxx()` 时误报类型告警。
    这里集中处理同步/异步联合返回，避免在业务方法中重复编写类型收窄逻辑。
    """
    if isinstance(response, Awaitable):
        return await cast(Awaitable[ResponseT], response)
    return cast(ResponseT, response)


class RedisManager:
    """Redis 异步连接管理器"""

    _instance: Optional["RedisManager"] = None
    _pool: ConnectionPool | None = None
    _client: Redis | None = None
    _heartbeat_task: asyncio.Task | None = None
    _heartbeat_interval: int = 30  # 心跳间隔（秒）
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
            pool = ConnectionPool.from_url(
                url=f"redis://:{cache_config.REDIS_PASSWORD}@{cache_config.REDIS_HOST}:{cache_config.REDIS_PORT}/{cache_config.REDIS_DB}"
                if cache_config.REDIS_PASSWORD
                else f"redis://{cache_config.REDIS_HOST}:{cache_config.REDIS_PORT}/{cache_config.REDIS_DB}",
                max_connections=cache_config.REDIS_MAX_CONNECTIONS,
                socket_connect_timeout=cache_config.REDIS_TIMEOUT,
                socket_keepalive=True,
                decode_responses=True,
            )
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
            self._start_heartbeat()

        except Exception as e:
            log.error(f"❌ Redis 连接失败: {e}")
            await self.disconnect()
            raise

    async def disconnect(self) -> None:
        """关闭 Redis 连接并停止心跳检查"""
        log.debug("开始关闭 Redis 连接...")

        # 停止心跳检查
        self._stop_heartbeat()

        client = self._client
        if client is not None:
            try:
                await _await_redis_response(client.close())
                log.debug("✅ Redis 客户端已关闭")
            except Exception as e:
                log.warning(f"⚠️ 关闭 Redis 客户端异常: {e}")
            self._client = None

        pool = self._pool
        if pool is not None:
            try:
                await _await_redis_response(pool.disconnect())
                log.debug("✅ Redis 连接池已断开")
            except Exception as e:
                log.warning(f"⚠️ Redis 连接池断开异常: {e}")
            self._pool = None

        log.info("✅ Redis 已断开连接")

    def _start_heartbeat(self) -> None:
        """启动心跳检查任务"""
        if self._heartbeat_task is not None:
            log.debug("❤️ 心跳检查已启动，跳过重复启动")
            return

        self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())
        log.info(f"❤️ Redis 心跳检查已启动 (检查间隔: {self._heartbeat_interval} 秒)")

    def _stop_heartbeat(self) -> None:
        """停止心跳检查任务"""
        if self._heartbeat_task is not None:
            self._heartbeat_task.cancel()
            self._heartbeat_task = None
            log.debug("❤️ Redis 心跳检查已停止")

    async def _heartbeat_loop(self) -> None:
        """心跳检查循环"""
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
                break
            except Exception as e:
                log.warning(f"⚠️ Redis 心跳检查失败: {e}")
                # 尝试重新连接
                try:
                    log.info("🔄 开始重连 Redis...")
                    await self.disconnect()
                    await asyncio.sleep(5)
                    log.info("🔄 尝试重新连接 Redis...")
                    await self.connect()
                    log.info("✅ Redis 重连成功")
                except Exception as reconnect_error:
                    log.error(f"❌ Redis 重连失败: {reconnect_error}")
                    self._reconnect_count += 1
                    if self._reconnect_count >= self._max_reconnect_attempts:
                        log.error("❌ 达到最大重连次数，停止重连")
                        break

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
            result = await _await_redis_response(client.set(prefixed_key, serialized_value, ex=ex))
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
            try:
                return self._deserialize(value)
            except Exception as e:
                log.warning(f"⚠️ 反序列化值失败 ({key}): {e}, 原值: {value}")
                return value
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
            return await _await_redis_response(client.delete(*prefixed_keys))
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
            return await _await_redis_response(client.exists(*prefixed_keys))
        except Exception as e:
            log.error(f"❌ 检查键存在性失败: {e}")
            raise

    async def clear(self) -> None:
        """清空当前数据库所有键"""
        try:
            client = self._require_client()
            await _await_redis_response(client.flushdb())
            log.info("✅ 已清空 Redis 数据库")
        except Exception as e:
            log.error(f"❌ 清空数据库失败: {e}")
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
            result = await _await_redis_response(client.expire(prefixed_key, ex))
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
            return await _await_redis_response(client.ttl(prefixed_key))
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
            result = await _await_redis_response(client.mset(serialized_data))

            # 如果设置了过期时间，为所有键设置过期
            if ex is not None:
                prefixed_keys = [self._get_prefixed_key(k) for k in data.keys()]
                for key in prefixed_keys:
                    await _await_redis_response(client.expire(key, ex))

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
            values = await _await_redis_response(client.mget(*prefixed_keys))
            # 对每个值进行反序列化，处理可能的异常
            result = []
            for i, v in enumerate(values):
                if v is None:
                    result.append(None)
                else:
                    try:
                        result.append(self._deserialize(v))
                    except Exception as e:
                        log.warning(f"⚠️ 反序列化批量值失败 (key[{i}]): {e}, 原值: {v}")
                        result.append(v)
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
            serialized_mapping = {k: self._serialize(v) for k, v in mapping.items()}
            result = await _await_redis_response(client.hset(prefixed_name, mapping=serialized_mapping))

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
            return self._deserialize(value) if value is not None else None
        except Exception as e:
            log.error(f"❌ 哈希获取失败 ({name}[{key}]): {e}")
            raise

    async def hgetall(self, name: str) -> dict[str, Any]:
        """获取哈希所有字段"""
        try:
            client = self._require_client()
            prefixed_name = self._get_prefixed_key(name)
            data = await _await_redis_response(client.hgetall(prefixed_name))
            # 对每个值进行反序列化，处理可能的异常
            result = {}
            for k, v in data.items():
                try:
                    result[k] = self._deserialize(v)
                except Exception as e:
                    log.warning(f"⚠️ 反序列化哈希值失败 ({name}[{k}]): {e}, 原值: {v}")
                    result[k] = v
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
            return await _await_redis_response(client.hdel(prefixed_name, *keys))
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
            result = await _await_redis_response(client.lpush(prefixed_name, *serialized_values))

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
            result = await _await_redis_response(client.rpush(prefixed_name, *serialized_values))

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
            values = await _await_redis_response(client.lrange(prefixed_name, start, end))
            # 对每个元素进行反序列化，处理可能的异常
            result = []
            for v in values:
                try:
                    result.append(self._deserialize(v))
                except Exception as e:
                    log.warning(f"⚠️ 反序列化列表元素失败: {e}, 原值: {v}")
                    result.append(v)
            return result
        except Exception as e:
            log.error(f"❌ 获取列表范围失败 ({name}[{start}:{end}]): {e}")
            raise

    async def lpop(self, name: str) -> Any:
        """从列表左端弹出值"""
        try:
            client = self._require_client()
            prefixed_name = self._get_prefixed_key(name)
            value = await _await_redis_response(client.lpop(prefixed_name))
            return self._deserialize(value) if value is not None else None
        except Exception as e:
            log.error(f"❌ 列表左弹出失败 ({name}): {e}")
            raise

    async def rpop(self, name: str) -> Any:
        """从列表右端弹出值"""
        try:
            client = self._require_client()
            prefixed_name = self._get_prefixed_key(name)
            value = await _await_redis_response(client.rpop(prefixed_name))
            return self._deserialize(value) if value is not None else None
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
            result = await _await_redis_response(client.sadd(prefixed_name, *serialized_members))

            # 如果设置了过期时间
            if ex is not None:
                await _await_redis_response(client.expire(prefixed_name, ex))

            return result
        except Exception as e:
            log.error(f"❌ 集合添加失败 ({name}): {e}")
            raise

    async def smembers(self, name: str) -> builtins.set[Any]:
        """获取集合所有成员"""
        try:
            client = self._require_client()
            prefixed_name = self._get_prefixed_key(name)
            members = await _await_redis_response(client.smembers(prefixed_name))
            # 对每个成员进行反序列化，处理可能的异常
            result = set()
            for m in members:
                try:
                    result.add(self._deserialize(m))
                except Exception as e:
                    log.warning(f"⚠️ 反序列化集合成员失败: {e}, 原值: {m}")
                    result.add(m)
            return result
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
            return await _await_redis_response(client.srem(prefixed_name, *serialized_members))
        except Exception as e:
            log.error(f"❌ 集合移除失败 ({name}): {e}")
            raise

    # ==================== 序列化/反序列化 ====================

    @staticmethod
    def _serialize(value: Any) -> str:
        """自动序列化值（JSON）

        处理规则：
        - 字符串: 直接返回
        - 布尔值: JSON 序列化（true/false）
        - 数字: 直接转字符串
        - None: "null"
        - 复杂类型: JSON 序列化
        """
        if isinstance(value, str):
            return value
        # 注意：必须在 int 之前检查 bool，因为 bool 是 int 的子类
        if isinstance(value, bool):
            # 布尔值使用 JSON 序列化以保证正确的 true/false 格式
            return json.dumps(value)
        if isinstance(value, (int, float)):
            return str(value)
        if value is None:
            return "null"
        # 复杂类型使用 JSON 序列化
        return json.dumps(value, ensure_ascii=False, default=str)

    @staticmethod
    def _deserialize(value: Any) -> Any:
        """自动反序列化值

        尝试三步反序列化：
        1. JSON 解析（布尔、数字、对象、数组等）
        2. 处理 "null" 字符串
        3. 返回原字符串（如果不是 JSON）
        """
        if not isinstance(value, str):
            return value

        # 尝试 JSON 解析
        try:
            return json.loads(value)
        except (json.JSONDecodeError, ValueError):
            # 非 JSON 字符串直接返回
            return value


# 全局单例
_redis_manager: RedisManager | None = None


def get_redis_manager() -> RedisManager:
    """获取 Redis 管理器单例"""
    global _redis_manager
    manager = _redis_manager
    if manager is None:
        manager = RedisManager()
        _redis_manager = manager
    return manager


__all__ = ["RedisManager", "get_redis_manager"]
