"""基于 SlowAPI 和 Redis 的接口速率限制。"""

from collections.abc import Callable
from typing import Any, cast
from urllib.parse import quote

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from app.core.log import log
from app.exceptions import ErrorCode, build_error_response
from config.cache_config import CacheSettings
from config.settings import get_settings


class FailOpenLimiter(Limiter):
    """修复 SlowAPI 存储故障放行后缺少请求状态的问题。"""

    def _check_request_limit(
        self,
        request: Request,
        endpoint_func: Callable[..., Any] | None,
        in_middleware: bool = True,
    ) -> None:
        super()._check_request_limit(request, endpoint_func, in_middleware)
        if not hasattr(request.state, "view_rate_limit"):
            request.state.view_rate_limit = None


def build_rate_limit_storage_uri(cache_settings: CacheSettings | None = None) -> str:
    """根据项目 Redis 配置构建 SlowAPI 使用的连接 URI。"""
    redis_settings = cache_settings or get_settings().cache
    password = f":{quote(redis_settings.REDIS_PASSWORD, safe='')}@" if redis_settings.REDIS_PASSWORD else ""
    return f"redis://{password}{redis_settings.REDIS_HOST}:{redis_settings.REDIS_PORT}/{redis_settings.REDIS_DB}"


def create_rate_limiter() -> Limiter:
    """创建使用独立 Redis 连接的 SlowAPI 限流器。"""
    settings = get_settings()
    return FailOpenLimiter(
        key_func=get_remote_address,
        storage_uri=build_rate_limit_storage_uri(settings.cache),
        key_prefix=f"{settings.cache.REDIS_PREFIX}:rate_limit",
        enabled=settings.rate_limit.RATE_LIMIT_ENABLED,
        swallow_errors=True,
        headers_enabled=False,
        key_style="endpoint",
    )


limiter = create_rate_limiter()


def rate_limit(limit_value: str | None = None) -> Callable[..., Any]:
    """为单个接口声明速率限制，未指定额度时使用项目默认配置。"""
    configured_limit = limit_value or get_settings().rate_limit.RATE_LIMIT_DEFAULT
    return limiter.limit(configured_limit)


async def rate_limit_exceeded_handler(request: Request, exc: Exception) -> JSONResponse:
    """将 SlowAPI 限流异常转换为项目统一响应。"""
    _exc = cast(RateLimitExceeded, exc)
    client = request.client.host if request.client else "unknown"
    log.warning(f"RateLimitExceeded | path={request.url.path} client={client} limit={_exc.detail}")
    return build_error_response(
        http_status=status.HTTP_429_TOO_MANY_REQUESTS,
        code=ErrorCode.FAIL,
        message="请求过于频繁，请稍后重试",
    )


def register_rate_limiter(app: FastAPI) -> None:
    """向 FastAPI 应用注册限流器和统一异常处理器。"""
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, rate_limit_exceeded_handler)

    settings = get_settings().rate_limit
    log.info(f"接口速率限制已注册 | enabled={settings.RATE_LIMIT_ENABLED} default={settings.RATE_LIMIT_DEFAULT}")


__all__ = [
    "build_rate_limit_storage_uri",
    "create_rate_limiter",
    "limiter",
    "rate_limit",
    "register_rate_limiter",
]
