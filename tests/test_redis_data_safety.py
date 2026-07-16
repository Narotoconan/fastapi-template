import asyncio
import builtins
from collections.abc import Mapping
from typing import Any, cast

import pytest
from redis.asyncio import Redis
from redis.exceptions import ResponseError

import app.core.cache.redis as redis_module
from app.core.cache.redis import RedisManager

SUPPORTED_VALUES: list[Any] = [
    "123",
    "true",
    "null",
    '{"legacy":"json"}',
    "",
    True,
    False,
    42,
    -7,
    3.5,
    None,
    [1, "2", False, None, {"nested": [3.5]}],
    {"name": "测试", "enabled": True, "items": [1, None]},
]


class MemoryRedisClient:
    """仅覆盖 RedisManager 数据操作的纯内存异步替身。"""

    def __init__(self, *, unlink_supported: bool = True) -> None:
        self.values: dict[str, str] = {}
        self.hashes: dict[str, dict[str, str]] = {}
        self.lists: dict[str, list[str]] = {}
        self.sets: dict[str, builtins.set[str]] = {}
        self.unlink_supported = unlink_supported
        self.scan_calls: list[tuple[int, str | None, int | None]] = []
        self.unlink_calls: list[list[str]] = []
        self.delete_calls: list[list[str]] = []
        self._scan_snapshot: list[str] = []

    def _all_keys(self) -> builtins.set[str]:
        return set(self.values) | set(self.hashes) | set(self.lists) | set(self.sets)

    def _drop_key(self, key: str) -> bool:
        existed = key in self._all_keys()
        self.values.pop(key, None)
        self.hashes.pop(key, None)
        self.lists.pop(key, None)
        self.sets.pop(key, None)
        return existed

    async def set(self, key: str, value: str, ex: int | None = None) -> bool:
        del ex
        self.values[key] = value
        return True

    async def get(self, key: str) -> str | None:
        return self.values.get(key)

    async def mset(self, mapping: Mapping[str, str]) -> bool:
        self.values.update(mapping)
        return True

    async def mget(self, *keys: str) -> list[str | None]:
        return [self.values.get(key) for key in keys]

    async def hset(self, name: str, mapping: Mapping[str, str]) -> int:
        hash_values = self.hashes.setdefault(name, {})
        new_fields = sum(field not in hash_values for field in mapping)
        hash_values.update(mapping)
        return new_fields

    async def hget(self, name: str, key: str) -> str | None:
        return self.hashes.get(name, {}).get(key)

    async def hgetall(self, name: str) -> dict[str, str]:
        return self.hashes.get(name, {}).copy()

    async def lpush(self, name: str, *values: str) -> int:
        list_values = self.lists.setdefault(name, [])
        for value in values:
            list_values.insert(0, value)
        return len(list_values)

    async def rpush(self, name: str, *values: str) -> int:
        list_values = self.lists.setdefault(name, [])
        list_values.extend(values)
        return len(list_values)

    async def lrange(self, name: str, start: int, end: int) -> list[str]:
        list_values = self.lists.get(name, [])
        if end == -1:
            return list_values[start:]
        return list_values[start : end + 1]

    async def lpop(self, name: str) -> str | None:
        list_values = self.lists.get(name, [])
        return list_values.pop(0) if list_values else None

    async def rpop(self, name: str) -> str | None:
        list_values = self.lists.get(name, [])
        return list_values.pop() if list_values else None

    async def sadd(self, name: str, *members: str) -> int:
        set_values = self.sets.setdefault(name, set())
        old_size = len(set_values)
        set_values.update(members)
        return len(set_values) - old_size

    async def smembers(self, name: str) -> builtins.set[str]:
        return self.sets.get(name, set()).copy()

    async def srem(self, name: str, *members: str) -> int:
        set_values = self.sets.get(name, set())
        removed = 0
        for member in members:
            if member in set_values:
                set_values.remove(member)
                removed += 1
        return removed

    async def scan(
        self,
        cursor: int = 0,
        match: str | None = None,
        count: int | None = None,
    ) -> tuple[int, list[str]]:
        self.scan_calls.append((cursor, match, count))
        if cursor == 0:
            assert match is not None
            literal_prefix = match.removesuffix("*").replace("\\", "")
            self._scan_snapshot = sorted(key for key in self._all_keys() if key.startswith(literal_prefix))

        batch_size = count or 10
        end = min(cursor + batch_size, len(self._scan_snapshot))
        next_cursor = 0 if end >= len(self._scan_snapshot) else end
        keys = self._scan_snapshot[cursor:end]
        if next_cursor == 0:
            self._scan_snapshot = []
        return next_cursor, keys

    async def unlink(self, *keys: str) -> int:
        if not self.unlink_supported:
            raise ResponseError("unknown command 'UNLINK'")
        self.unlink_calls.append(list(keys))
        return sum(self._drop_key(key) for key in keys)

    async def delete(self, *keys: str) -> int:
        self.delete_calls.append(list(keys))
        return sum(self._drop_key(key) for key in keys)


@pytest.fixture(autouse=True)
def mute_cache_logs(monkeypatch: pytest.MonkeyPatch) -> None:
    """避免纯单元测试依赖应用日志生命周期。"""
    monkeypatch.setattr(redis_module.log, "debug", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(redis_module.log, "info", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(redis_module.log, "warning", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(redis_module.log, "error", lambda *_args, **_kwargs: None)


@pytest.fixture
def redis_manager(monkeypatch: pytest.MonkeyPatch) -> tuple[RedisManager, MemoryRedisClient]:
    """提供使用纯内存客户端且固定项目前缀的 Redis 管理器。"""
    manager = RedisManager()
    client = MemoryRedisClient()
    monkeypatch.setattr(manager, "_client", cast(Redis, client))
    monkeypatch.setattr(manager, "_redis_prefix", "template")
    return manager, client


def assert_same_value(actual: Any, expected: Any) -> None:
    """断言缓存往返后值及顶层类型均保持不变。"""
    assert type(actual) is type(expected)
    assert actual == expected


def assert_same_unordered_values(actual_values: list[Any], expected_values: list[Any]) -> None:
    """按类型和值比较 Redis Set 返回的无序成员列表。"""
    remaining_values = actual_values.copy()
    for expected in expected_values:
        matching_index = next(
            index
            for index, actual in enumerate(remaining_values)
            if type(actual) is type(expected) and actual == expected
        )
        remaining_values.pop(matching_index)
    assert remaining_values == []


def test_supported_values_round_trip_across_redis_structures(
    redis_manager: tuple[RedisManager, MemoryRedisClient],
) -> None:
    """KV、Hash、List、Set 均应保持受支持值的类型和值。"""
    manager, client = redis_manager

    async def run_case() -> None:
        for index, expected in enumerate(SUPPORTED_VALUES):
            assert await manager.set(f"value:{index}", expected) is True
            assert_same_value(await manager.get(f"value:{index}"), expected)
        assert all(
            client.values[f"template:value:{index}"].startswith(redis_module._SERIALIZATION_PREFIX)
            for index in range(len(SUPPORTED_VALUES))
        )

        batch_values = {f"batch:{index}": value for index, value in enumerate(SUPPORTED_VALUES)}
        assert await manager.mset(batch_values) is True
        actual_batch_values = await manager.mget(*batch_values)
        for actual, expected in zip(actual_batch_values, SUPPORTED_VALUES, strict=True):
            assert_same_value(actual, expected)

        hash_values = {f"field:{index}": value for index, value in enumerate(SUPPORTED_VALUES)}
        assert await manager.hset("hash", hash_values) == len(hash_values)
        actual_hash_values = await manager.hgetall("hash")
        for field, expected in hash_values.items():
            assert_same_value(actual_hash_values[field], expected)
        assert_same_value(await manager.hget("hash", "field:0"), SUPPORTED_VALUES[0])

        assert await manager.rpush("list", *SUPPORTED_VALUES) == len(SUPPORTED_VALUES)
        actual_list_values = await manager.lrange("list")
        for actual, expected in zip(actual_list_values, SUPPORTED_VALUES, strict=True):
            assert_same_value(actual, expected)

        assert await manager.sadd("set", *SUPPORTED_VALUES) == len(SUPPORTED_VALUES)
        actual_set_values = await manager.smembers("set")
        assert isinstance(actual_set_values, list)
        assert_same_unordered_values(actual_set_values, SUPPORTED_VALUES)

        removed_values = SUPPORTED_VALUES[-2:]
        assert await manager.srem("set", *removed_values) == len(removed_values)
        assert_same_unordered_values(await manager.smembers("set"), SUPPORTED_VALUES[:-2])

    asyncio.run(run_case())


def test_legacy_unversioned_values_remain_raw_strings(
    redis_manager: tuple[RedisManager, MemoryRedisClient],
) -> None:
    """升级前没有版本标记的 JSON 外观数据不得再被猜测为其他类型。"""
    manager, client = redis_manager
    legacy_values = ["123", "true", "null", '[1,"two"]', '{"name":"legacy"}']
    client.values.update({f"template:legacy:{index}": value for index, value in enumerate(legacy_values)})
    client.hashes["template:legacy-hash"] = {f"field:{index}": value for index, value in enumerate(legacy_values)}
    client.lists["template:legacy-list"] = legacy_values.copy()
    client.sets["template:legacy-set"] = set(legacy_values)

    async def run_case() -> None:
        assert await manager.mget(*(f"legacy:{index}" for index in range(len(legacy_values)))) == legacy_values
        assert await manager.hgetall("legacy-hash") == {
            f"field:{index}": value for index, value in enumerate(legacy_values)
        }
        assert await manager.lrange("legacy-list") == legacy_values
        assert set(await manager.smembers("legacy-set")) == set(legacy_values)

    asyncio.run(run_case())


def test_serialize_rejects_values_that_would_lose_type_information() -> None:
    """不支持的对象、元组和非字符串字典键必须显式失败。"""

    class UnsupportedValue:
        pass

    class StringSubclass(str):
        pass

    with pytest.raises(TypeError, match="UnsupportedValue"):
        RedisManager._serialize(UnsupportedValue())
    with pytest.raises(TypeError, match="tuple"):
        RedisManager._serialize(("would", "become", "list"))
    with pytest.raises(TypeError, match="StringSubclass"):
        RedisManager._serialize(StringSubclass("would lose its concrete type"))
    with pytest.raises(TypeError, match="字典的键必须是字符串"):
        RedisManager._serialize({1: "would become a string key"})
    with pytest.raises(ValueError, match="Out of range float values"):
        RedisManager._serialize(float("inf"))


def test_deserialization_failure_log_does_not_expose_raw_value(
    redis_manager: tuple[RedisManager, MemoryRedisClient],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """损坏的版本化载荷只能记录位置和异常类型，不能输出原始缓存内容。"""
    manager, client = redis_manager
    secret = "super-secret-token"
    corrupted_value = f"{redis_module._SERIALIZATION_PREFIX}{{{secret}"
    client.values["template:broken"] = corrupted_value
    client.hashes["template:broken-hash"] = {"field": corrupted_value}
    client.lists["template:broken-list"] = [corrupted_value]
    client.sets["template:broken-set"] = {corrupted_value}
    warning_messages: list[str] = []
    monkeypatch.setattr(redis_module.log, "warning", warning_messages.append)

    async def run_case() -> None:
        assert await manager.get("broken") == corrupted_value
        assert await manager.hgetall("broken-hash") == {"field": corrupted_value}
        assert await manager.lrange("broken-list") == [corrupted_value]
        assert await manager.smembers("broken-set") == [corrupted_value]

    asyncio.run(run_case())
    assert len(warning_messages) == 4
    assert all(secret not in message for message in warning_messages)
    assert all("error_type=JSONDecodeError" in message for message in warning_messages)


def test_clear_deletes_only_current_prefix_in_scan_batches(
    redis_manager: tuple[RedisManager, MemoryRedisClient],
) -> None:
    """clear 应分批 UNLINK 当前前缀，保留共享数据库中的其他项目数据。"""
    manager, client = redis_manager
    client.values.update({f"template:item:{index}": "value" for index in range(501)})
    client.hashes["template:hash"] = {"field": "value"}
    client.lists["template:list"] = ["value"]
    client.sets["template:set"] = {"value"}
    client.values["other:item"] = "keep"

    asyncio.run(manager.clear())

    assert not any(key.startswith("template:") for key in client._all_keys())
    assert client.values["other:item"] == "keep"
    assert len(client.scan_calls) == 2
    assert [len(keys) for keys in client.unlink_calls] == [500, 4]
    assert client.delete_calls == []


def test_clear_falls_back_to_delete_when_unlink_is_unsupported(monkeypatch: pytest.MonkeyPatch) -> None:
    """旧 Redis 不支持 UNLINK 时仅对本批前缀键回退使用 DELETE。"""
    manager = RedisManager()
    client = MemoryRedisClient(unlink_supported=False)
    client.values.update({"template:item": "delete", "other:item": "keep"})
    monkeypatch.setattr(manager, "_client", cast(Redis, client))
    monkeypatch.setattr(manager, "_redis_prefix", "template")

    asyncio.run(manager.clear())

    assert "template:item" not in client.values
    assert client.values["other:item"] == "keep"
    assert client.delete_calls == [["template:item"]]
