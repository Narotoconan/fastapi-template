"""Cache decorators for simple function result caching"""

import functools
import hashlib
import inspect
import json
from collections.abc import Awaitable, Callable, Mapping
from typing import ParamSpec, TypeVar, cast

from app.core.cache.redis import get_redis_manager

P = ParamSpec("P")
R = TypeVar("R")


def cache(
    key_prefix: str = "", ttl: int | None = None
) -> Callable[[Callable[P, Awaitable[R]]], Callable[P, Awaitable[R]]]:
    """支持 TTL 的异步函数结果缓存装饰器。

    使用 exists() 先行检查键是否存在，再取值，
    正确区分「缓存未命中」与「命中但函数返回值为 None」两种情况，
    避免返回 None 的函数每次均穿透缓存直接执行。
    """

    def decorator(func: Callable[P, Awaitable[R]]) -> Callable[P, Awaitable[R]]:
        if not inspect.iscoroutinefunction(func):
            raise RuntimeError("Cache decorator only supports async functions")

        @functools.wraps(func)
        async def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
            cache_key = _generate_cache_key(func, key_prefix, args, kwargs)
            redis_manager = get_redis_manager()

            # 先检查键是否存在，再取值：
            # - exists == 0：缓存未命中，执行原函数并写入缓存
            # - exists >= 1：缓存命中，直接返回（即便值本身是 None）
            if await redis_manager.exists(cache_key):
                return cast(R, await redis_manager.get(cache_key))

            result = await func(*args, **kwargs)
            await redis_manager.set(cache_key, result, ex=ttl)
            return result

        return wrapper

    return decorator


def _generate_cache_key(
    func: Callable[..., Awaitable[object]], prefix: str, args: tuple[object, ...], kwargs: Mapping[str, object]
) -> str:
    """Generate cache key from function name and parameters"""
    func_name = getattr(func, "__name__", type(func).__name__)
    key_base = f"{prefix}:{func_name}" if prefix else func_name
    params = json.dumps({"args": args, "kwargs": kwargs}, default=str, sort_keys=True)
    param_hash = hashlib.md5(params.encode()).hexdigest()[:8]
    return f"cache:{key_base}:{param_hash}"


__all__ = ["cache"]
