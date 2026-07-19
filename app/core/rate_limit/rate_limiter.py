"""基于 limits.aio 和 redis-py 的异步接口速率限制。"""

import asyncio
import inspect
from collections.abc import Awaitable, Callable
from functools import wraps
from typing import Any, Protocol, TypeVar, cast

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from limits import RateLimitItem, parse_many
from limits.aio.storage.redis import RedisStorage
from limits.aio.strategies import FixedWindowRateLimiter
from limits.errors import StorageError
from redis.asyncio import BlockingConnectionPool, Redis

from app.core.log import log
from app.exceptions import (
    RateLimitException,
    ServiceUnavailableException,
    build_error_response,
)
from config.cache_config import CacheSettings
from config.rate_limit_config import RateLimitSettings
from config.settings import get_settings

_LIMITS_STORAGE_PREFIX = "LIMITS"
_RATE_LIMIT_KEY_SUFFIX = "rate_limit"
_STORAGE_SCHEME_URI = "async+redis://"

EndpointT = TypeVar("EndpointT", bound=Callable[..., Awaitable[object]])


class EndpointDecorator(Protocol):
    """保持异步接口函数签名不变的装饰器协议。"""

    def __call__(self, endpoint: EndpointT, /) -> EndpointT: ...


class AsyncRateLimitStrategy(Protocol):
    """异步限流策略最小协议，便于隔离具体存储实现并开展测试。"""

    async def hit(
        self,
        item: RateLimitItem,
        *identifiers: str,
        cost: int = 1,
    ) -> bool: ...


def _create_rate_limit_pool(
    cache_settings: CacheSettings,
    rate_limit_settings: RateLimitSettings,
) -> BlockingConnectionPool:
    """创建限流专用异步连接池，避免限流流量占用业务缓存连接。"""
    return BlockingConnectionPool(
        host=cache_settings.REDIS_HOST,
        port=cache_settings.REDIS_PORT,
        db=cache_settings.REDIS_DB,
        password=cache_settings.REDIS_PASSWORD,
        max_connections=rate_limit_settings.RATE_LIMIT_REDIS_MAX_CONNECTIONS,
        timeout=rate_limit_settings.RATE_LIMIT_REDIS_POOL_TIMEOUT,
        socket_connect_timeout=rate_limit_settings.RATE_LIMIT_REDIS_CONNECT_TIMEOUT,
        socket_timeout=rate_limit_settings.RATE_LIMIT_REDIS_COMMAND_TIMEOUT,
        socket_keepalive=True,
        decode_responses=True,
    )


def _create_rate_limit_storage(pool: BlockingConnectionPool) -> RedisStorage:
    """创建使用 redis.asyncio 的 limits 异步 Redis 存储。"""
    # limits 5.8.0 的运行时 API 支持 connection_pool，但其 **options 类型未包含连接池对象。
    storage_options: dict[str, Any] = {"connection_pool": pool}
    return RedisStorage(
        _STORAGE_SCHEME_URI,
        implementation="redispy",
        key_prefix=_LIMITS_STORAGE_PREFIX,
        wrap_exceptions=True,
        **storage_options,
    )


def _create_rate_limit_client(pool: BlockingConnectionPool) -> Redis:
    """创建由限流器显式管理生命周期的异步 Redis 客户端。"""
    return Redis(connection_pool=pool)


async def _close_rate_limit_resources(
    client: Redis | None,
    pool: BlockingConnectionPool | None,
) -> None:
    """尝试释放客户端和连接池，单项失败不得阻断另一项清理。"""
    cleanup_error: BaseException | None = None

    if client is not None:
        try:
            await client.aclose()
        except BaseException as exc:
            cleanup_error = exc

    if pool is not None:
        try:
            await pool.aclose()
        except BaseException as exc:
            if cleanup_error is None:
                cleanup_error = exc
            else:
                log.warning(f"限流 Redis 客户端与连接池均清理失败: pool_error_type={type(exc).__name__}")

    if cleanup_error is not None:
        raise cleanup_error


def _parse_rate_limits(limit_value: str) -> tuple[RateLimitItem, ...]:
    """解析并校验一个或多个限流表达式。"""
    try:
        parsed_limits = tuple(parse_many(limit_value))
    except ValueError as exc:
        raise ValueError(f"无效的接口限流表达式: {limit_value}") from exc

    if not parsed_limits or any(item.amount <= 0 for item in parsed_limits):
        raise ValueError("接口限流请求次数必须大于 0")
    return parsed_limits


def _get_client_address(request: Request) -> str:
    """提取由 ASGI 服务器确认的客户端地址，不直接信任转发请求头。"""
    if request.client is None or not request.client.host:
        return "127.0.0.1"
    return request.client.host


class AsyncRateLimiter:
    """管理异步 Redis 限流策略、连接池和请求检查。"""

    def __init__(
        self,
        *,
        enabled: bool,
        fail_open: bool,
        key_prefix: str,
    ) -> None:
        self.enabled = enabled
        self.fail_open = fail_open
        self.key_prefix = key_prefix
        self._pool: BlockingConnectionPool | None = None
        self._client: Redis | None = None
        self._storage: RedisStorage | None = None
        self._strategy: AsyncRateLimitStrategy | FixedWindowRateLimiter | None = None
        self._lifecycle_lock = asyncio.Lock()

    async def start(self) -> None:
        """启用时初始化并验证限流专用 Redis 连接。"""
        if not self.enabled:
            return

        async with self._lifecycle_lock:
            if self._strategy is not None:
                return

            settings = get_settings()
            pool: BlockingConnectionPool | None = None
            client: Redis | None = None

            try:
                pool = _create_rate_limit_pool(settings.cache, settings.rate_limit)
                client = _create_rate_limit_client(pool)
                storage = _create_rate_limit_storage(pool)
                strategy = FixedWindowRateLimiter(storage)
                await client.ping()
            except BaseException:
                try:
                    await _close_rate_limit_resources(client, pool)
                except asyncio.CancelledError:
                    raise
                except Exception as cleanup_exc:
                    log.warning(f"限流 Redis 初始化失败后清理连接池异常: error_type={type(cleanup_exc).__name__}")
                raise

            self._pool = pool
            self._client = client
            self._storage = storage
            self._strategy = strategy
            log.info(
                "✅ 异步接口限流器初始化完成 | "
                f"strategy=fixed-window fail_open={self.fail_open} "
                f"max_connections={settings.rate_limit.RATE_LIMIT_REDIS_MAX_CONNECTIONS}"
            )

    async def close(self) -> None:
        """关闭限流连接池并清理运行状态，可安全重复调用。"""
        async with self._lifecycle_lock:
            client = self._client
            pool = self._pool
            self._strategy = None
            self._storage = None
            self._client = None
            self._pool = None

            if client is None and pool is None:
                return

            await _close_rate_limit_resources(client, pool)
            log.info("✅ 异步接口限流器已关闭")

    async def check(
        self,
        request: Request,
        endpoint_key: str,
        rate_limits: tuple[RateLimitItem, ...],
    ) -> None:
        """原子消费接口额度，按配置处理运行期 Redis 存储故障。"""
        if not self.enabled:
            return

        strategy = self._strategy
        if strategy is None:
            raise RuntimeError("异步接口限流器尚未初始化")

        client_address = _get_client_address(request)
        identifiers = (self.key_prefix, client_address, endpoint_key)

        try:
            for rate_limit_item in rate_limits:
                if not await strategy.hit(rate_limit_item, *identifiers):
                    raise RateLimitException(limit=str(rate_limit_item))
        except StorageError as exc:
            log.warning(
                "接口限流存储不可用 | "
                f"path={request.url.path} error_type={type(exc.storage_error).__name__} "
                f"fail_open={self.fail_open}"
            )
            if self.fail_open:
                return
            raise ServiceUnavailableException(message="接口限流服务暂不可用，请稍后重试") from exc


def create_rate_limiter() -> AsyncRateLimiter:
    """根据项目配置创建全局异步限流器。"""
    settings = get_settings()
    return AsyncRateLimiter(
        enabled=settings.rate_limit.RATE_LIMIT_ENABLED,
        fail_open=settings.rate_limit.RATE_LIMIT_FAIL_OPEN,
        key_prefix=f"{settings.cache.REDIS_PREFIX}:{_RATE_LIMIT_KEY_SUFFIX}",
    )


limiter = create_rate_limiter()


def rate_limit(limit_value: str | None = None) -> EndpointDecorator:
    """为异步接口声明速率限制，未指定额度时使用项目默认配置。"""
    rate_limit_settings = get_settings().rate_limit
    configured_limit = limit_value or rate_limit_settings.RATE_LIMIT_DEFAULT
    try:
        parsed_limits: tuple[RateLimitItem, ...] | None = _parse_rate_limits(configured_limit)
    except ValueError:
        if limit_value is not None or rate_limit_settings.RATE_LIMIT_ENABLED:
            raise
        parsed_limits = None

    def decorator(endpoint: EndpointT) -> EndpointT:
        if not inspect.iscoroutinefunction(endpoint):
            raise TypeError("@rate_limit 仅支持 async def 接口")

        endpoint_type = type(endpoint)
        endpoint_name = cast(str, getattr(endpoint, "__name__", endpoint_type.__name__))
        endpoint_module = cast(str, getattr(endpoint, "__module__", endpoint_type.__module__))
        endpoint_signature = inspect.signature(endpoint)
        request_index: int | None = None
        for index, parameter in enumerate(endpoint_signature.parameters.values()):
            if parameter.name == "request":
                request_index = index
                break
        if request_index is None:
            raise TypeError(f'接口 "{endpoint_name}" 必须声明名为 request 的 Request 参数')

        endpoint_key = f"{endpoint_module}.{endpoint_name}"

        @wraps(endpoint)
        async def async_wrapper(*args: Any, **kwargs: Any) -> object:
            request = kwargs.get("request")
            if request is None and request_index < len(args):
                request = args[request_index]
            if not isinstance(request, Request):
                raise TypeError("参数 request 必须是 starlette.requests.Request 实例")

            effective_limits = parsed_limits
            if effective_limits is None:
                effective_limits = _parse_rate_limits(configured_limit) if limiter.enabled else ()
            await limiter.check(request, endpoint_key, effective_limits)
            return await endpoint(*args, **kwargs)

        return cast(EndpointT, async_wrapper)

    return cast(EndpointDecorator, decorator)


async def rate_limit_exceeded_handler(request: Request, exc: Exception) -> JSONResponse:
    """将限流异常转换为项目统一 429 响应。"""
    rate_limit_exc = cast(RateLimitException, exc)
    client_address = _get_client_address(request)
    log.warning(f"RateLimitExceeded | path={request.url.path} client={client_address} limit={rate_limit_exc.limit}")
    return build_error_response(
        http_status=rate_limit_exc.http_status,
        code=rate_limit_exc.code,
        message=rate_limit_exc.message,
    )


async def init_rate_limiter() -> None:
    """在应用启动阶段初始化异步限流存储。"""
    await limiter.start()


async def close_rate_limiter() -> None:
    """在应用关闭阶段释放异步限流连接池。"""
    await limiter.close()


def register_rate_limiter(app: FastAPI) -> None:
    """向 FastAPI 应用注册限流器和统一异常处理器。"""
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitException, rate_limit_exceeded_handler)

    settings = get_settings().rate_limit
    log.info(
        "🧩 接口速率限制已注册 | "
        f"enabled={settings.RATE_LIMIT_ENABLED} default={settings.RATE_LIMIT_DEFAULT} "
        f"fail_open={settings.RATE_LIMIT_FAIL_OPEN}"
    )


__all__ = [
    "AsyncRateLimiter",
    "close_rate_limiter",
    "create_rate_limiter",
    "init_rate_limiter",
    "limiter",
    "rate_limit",
    "register_rate_limiter",
]
