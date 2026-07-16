"""Cache decorators for simple function result caching"""

import functools
import hashlib
import inspect
import json
import math
from collections.abc import Awaitable, Callable, Mapping
from typing import ParamSpec, TypeVar, cast

from app.core.cache.redis import get_redis_manager

P = ParamSpec("P")
R = TypeVar("R")
_CACHE_MISS = object()


def cache(
    key_prefix: str = "", ttl: int | None = None
) -> Callable[[Callable[P, Awaitable[R]]], Callable[P, Awaitable[R]]]:
    """支持 TTL 的异步函数结果缓存装饰器。

    通过单次 GET 和进程内唯一哨兵区分缓存未命中与命中 None，
    避免 EXISTS 与 GET 之间键过期造成的竞态。
    """

    def decorator(func: Callable[P, Awaitable[R]]) -> Callable[P, Awaitable[R]]:
        if not inspect.iscoroutinefunction(func):
            raise RuntimeError("Cache decorator only supports async functions")

        @functools.wraps(func)
        async def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
            cache_key = _generate_cache_key(func, key_prefix, args, kwargs)
            redis_manager = get_redis_manager()

            cached_value = await redis_manager.get(cache_key, default=_CACHE_MISS)
            if cached_value is not _CACHE_MISS:
                return cast(R, cached_value)

            result = await func(*args, **kwargs)
            await redis_manager.set(cache_key, result, ex=ttl)
            return result

        return wrapper

    return decorator


def _generate_cache_key(
    func: Callable[..., Awaitable[object]], prefix: str, args: tuple[object, ...], kwargs: Mapping[str, object]
) -> str:
    """根据函数完整身份和规范化绑定参数生成稳定的 SHA-256 缓存键。"""
    signature = inspect.signature(func)
    bound_arguments = signature.bind(*args, **kwargs)
    bound_arguments.apply_defaults()
    cache_key_arguments = dict(bound_arguments.arguments)
    receiver_identity = _extract_receiver_identity(signature, cache_key_arguments)
    key_payload: dict[str, object] = {"arguments": cache_key_arguments}
    if receiver_identity is not None:
        key_payload["receiver_type"] = receiver_identity
    normalized_arguments = _normalize_cache_key_value(key_payload, path="call")
    serialized_arguments = json.dumps(
        normalized_arguments,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    arguments_hash = hashlib.sha256(serialized_arguments.encode("utf-8")).hexdigest()
    function_module = getattr(func, "__module__", type(func).__module__)
    function_qualname = getattr(func, "__qualname__", type(func).__qualname__)
    function_identity = f"{function_module}.{function_qualname}"
    key_namespace = f"{prefix}:{function_identity}" if prefix else function_identity
    return f"cache:{key_namespace}:{arguments_hash}"


def _extract_receiver_identity(
    signature: inspect.Signature,
    arguments: dict[str, object],
) -> str | None:
    """将实例/类方法接收者转换为稳定类型标识，不读取运行时对象状态。"""
    first_parameter = next(iter(signature.parameters.values()), None)
    if first_parameter is None or first_parameter.name not in {"self", "cls"}:
        return None
    if first_parameter.name not in arguments:
        return None

    receiver = arguments.pop(first_parameter.name)
    receiver_type = receiver if isinstance(receiver, type) else type(receiver)
    return f"{receiver_type.__module__}.{receiver_type.__qualname__}"


def _normalize_cache_key_value(value: object, *, path: str) -> object:
    """将受支持的参数值转换为无歧义、可确定序列化的 JSON 结构。"""
    value_type = type(value)
    if value is None or value_type in (str, bool, int):
        return value

    if value_type is float:
        float_value = cast(float, value)
        if not math.isfinite(float_value):
            raise TypeError(f"缓存键参数 {path} 不支持非有限浮点数")
        return float_value

    if value_type is list:
        list_value = cast(list[object], value)
        return {
            "type": "list",
            "items": [
                _normalize_cache_key_value(item, path=f"{path}[{index}]") for index, item in enumerate(list_value)
            ],
        }

    if value_type is tuple:
        tuple_value = cast(tuple[object, ...], value)
        return {
            "type": "tuple",
            "items": [
                _normalize_cache_key_value(item, path=f"{path}[{index}]") for index, item in enumerate(tuple_value)
            ],
        }

    if value_type is dict:
        dict_value = cast(dict[object, object], value)
        string_items: list[tuple[str, object]] = []
        for key, item in dict_value.items():
            if type(key) is not str:
                raise TypeError(f"缓存键参数 {path} 的字典键必须是字符串")
            string_items.append((key, item))
        return {
            "type": "dict",
            "items": [
                [key, _normalize_cache_key_value(item, path=f"{path}.{key}")]
                for key, item in sorted(string_items, key=lambda pair: pair[0])
            ],
        }

    raise TypeError(f"缓存键参数 {path} 不支持类型 {value_type.__name__}，请仅使用稳定的基础数据类型")


__all__ = ["cache"]
