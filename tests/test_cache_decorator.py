import asyncio
import re
from typing import Any, override

import pytest

import app.core.cache.decorators as decorators_module
from app.core.cache.decorators import _generate_cache_key, cache


class MemoryCacheManager:
    """只实现装饰器所需 GET/SET 的内存缓存替身。"""

    def __init__(self) -> None:
        self.values: dict[str, Any] = {}
        self.get_calls: list[str] = []
        self.set_calls: list[tuple[str, Any, int | None]] = []

    async def get(self, key: str, default: Any = None) -> Any:
        self.get_calls.append(key)
        return self.values.get(key, default)

    async def set(self, key: str, value: Any, ex: int | None = None) -> bool:
        self.set_calls.append((key, value, ex))
        self.values[key] = value
        return True


def test_cache_uses_single_get_and_caches_none(monkeypatch: pytest.MonkeyPatch) -> None:
    """命中判断只执行一次 GET，并能正确缓存 None。"""
    cache_manager = MemoryCacheManager()
    function_calls = 0
    monkeypatch.setattr(decorators_module, "get_redis_manager", lambda: cache_manager)

    @cache(key_prefix="user", ttl=60)
    async def load_user(user_id: int) -> None:
        nonlocal function_calls
        function_calls += 1
        return None

    async def run_case() -> None:
        assert await load_user(1) is None
        assert await load_user(user_id=1) is None

    asyncio.run(run_case())

    assert function_calls == 1
    assert len(cache_manager.get_calls) == 2
    assert cache_manager.get_calls[0] == cache_manager.get_calls[1]
    assert len(cache_manager.set_calls) == 1
    assert cache_manager.set_calls[0][1:] == (None, 60)


def test_equivalent_calls_and_explicit_defaults_share_cache_key() -> None:
    """位置参数、关键字参数和显式默认值应绑定为同一调用语义。"""

    async def load_user(user_id: int, active: bool = True, *, page: int = 1) -> object:
        return user_id, active, page

    positional_key = _generate_cache_key(load_user, "user", (7,), {})
    keyword_key = _generate_cache_key(load_user, "user", (), {"user_id": 7})
    explicit_defaults_key = _generate_cache_key(
        load_user,
        "user",
        (),
        {"user_id": 7, "active": True, "page": 1},
    )
    different_page_key = _generate_cache_key(load_user, "user", (7,), {"page": 2})

    assert positional_key == keyword_key == explicit_defaults_key
    assert different_page_key != positional_key
    assert positional_key.startswith(f"cache:user:{load_user.__module__}.{load_user.__qualname__}:")
    assert re.fullmatch(r"[0-9a-f]{64}", positional_key.rsplit(":", maxsplit=1)[1])


def test_cache_key_normalizes_mapping_order_and_preserves_container_types() -> None:
    """字典顺序不影响键，但列表与元组不得共用缓存键。"""

    async def search(filters: object) -> object:
        return filters

    first_mapping_key = _generate_cache_key(search, "", ({"status": 1, "page": 2},), {})
    reordered_mapping_key = _generate_cache_key(search, "", ({"page": 2, "status": 1},), {})
    list_key = _generate_cache_key(search, "", ([1, 2],), {})
    tuple_key = _generate_cache_key(search, "", ((1, 2),), {})

    assert first_mapping_key == reordered_mapping_key
    assert list_key != tuple_key


def test_function_module_and_qualname_isolate_cache_namespaces() -> None:
    """同名函数位于不同模块或限定路径时不得产生相同缓存键。"""

    async def first(value: int) -> int:
        return value

    async def second(value: int) -> int:
        return value

    first.__module__ = "package_a.service"
    first.__qualname__ = "UserService.load"
    second.__module__ = "package_b.service"
    second.__qualname__ = "UserService.load"

    first_key = _generate_cache_key(first, "user", (1,), {})
    second_key = _generate_cache_key(second, "user", (1,), {})
    second.__module__ = first.__module__
    second.__qualname__ = "AdminService.load"
    different_qualname_key = _generate_cache_key(second, "user", (1,), {})

    assert first_key != second_key
    assert first_key != different_qualname_key


def test_cache_supports_stateless_instance_methods(monkeypatch: pytest.MonkeyPatch) -> None:
    """实例方法按接收者类型生成稳定键，不序列化 Service 实例本身。"""
    cache_manager = MemoryCacheManager()
    monkeypatch.setattr(decorators_module, "get_redis_manager", lambda: cache_manager)

    class UserService:
        calls = 0

        @cache(key_prefix="user", ttl=60)
        async def load_user(self, user_id: int) -> dict[str, int]:
            type(self).calls += 1
            return {"id": user_id}

    async def run_case() -> None:
        first_service = UserService()
        second_service = UserService()
        assert await first_service.load_user(1) == {"id": 1}
        assert await second_service.load_user(user_id=1) == {"id": 1}

    asyncio.run(run_case())

    assert UserService.calls == 1
    assert cache_manager.get_calls[0] == cache_manager.get_calls[1]


def test_cache_separates_inherited_method_keys_by_receiver_type() -> None:
    """继承同一实现的不同 Service 类型不能共享缓存命名空间。"""

    class BaseService:
        async def load(self, item_id: int) -> int:
            return item_id

    class ChildService(BaseService):
        pass

    base_key = _generate_cache_key(BaseService.load, "item", (BaseService(), 1), {})
    child_key = _generate_cache_key(BaseService.load, "item", (ChildService(), 1), {})

    assert base_key != child_key


def test_cache_supports_stateless_class_methods(monkeypatch: pytest.MonkeyPatch) -> None:
    """类方法按实际 cls 类型隔离，并保持等价调用共享缓存键。"""
    cache_manager = MemoryCacheManager()
    calls: dict[str, int] = {}
    monkeypatch.setattr(decorators_module, "get_redis_manager", lambda: cache_manager)

    class BaseService:
        @classmethod
        @cache(key_prefix="class-service", ttl=60)
        async def load(cls, item_id: int) -> dict[str, object]:
            calls[cls.__name__] = calls.get(cls.__name__, 0) + 1
            return {"service": cls.__name__, "id": item_id}

    class ChildService(BaseService):
        pass

    async def run_case() -> None:
        assert await BaseService.load(1) == {"service": "BaseService", "id": 1}
        assert await BaseService.load(item_id=1) == {"service": "BaseService", "id": 1}
        assert await ChildService.load(1) == {"service": "ChildService", "id": 1}
        assert await ChildService.load(item_id=1) == {"service": "ChildService", "id": 1}

    asyncio.run(run_case())

    assert calls == {"BaseService": 1, "ChildService": 1}
    assert len(cache_manager.set_calls) == 2


def test_cache_key_rejects_unstable_objects_without_stringifying_them() -> None:
    """不支持的对象必须明确失败，不能退化为可能包含地址的字符串。"""
    stringify_calls = 0

    class UnstableObject:
        @override
        def __str__(self) -> str:
            nonlocal stringify_calls
            stringify_calls += 1
            return "unstable"

    async def load(value: object) -> object:
        return value

    with pytest.raises(TypeError, match="UnstableObject"):
        _generate_cache_key(load, "", (UnstableObject(),), {})

    assert stringify_calls == 0


@pytest.mark.parametrize("invalid_value", [{1: "value"}, float("nan"), float("inf")])
def test_cache_key_rejects_ambiguous_or_non_standard_json_values(invalid_value: object) -> None:
    """非字符串字典键和非有限浮点数不得进入缓存键协议。"""

    async def load(value: object) -> object:
        return value

    with pytest.raises(TypeError, match="缓存键参数"):
        _generate_cache_key(load, "", (invalid_value,), {})
