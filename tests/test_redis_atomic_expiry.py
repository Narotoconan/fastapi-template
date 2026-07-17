import asyncio
from collections.abc import Mapping
from typing import Any, ClassVar, Self, cast

import pytest
from redis.asyncio import Redis

import app.core.cache.redis as redis_module
from app.core.cache.redis import RedisManager


class RecordingPipeline:
    """记录事务命令并返回主写命令的模拟结果。"""

    _PRIMARY_RESULTS: ClassVar[dict[str, bool | int]] = {
        "mset": True,
        "hset": 2,
        "lpush": 3,
        "rpush": 4,
        "sadd": 2,
    }

    def __init__(self, transaction: bool) -> None:
        self.transaction = transaction
        self.commands: list[tuple[str, tuple[Any, ...], dict[str, Any]]] = []
        self.executed = False

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, *_args: object) -> None:
        return None

    def mset(self, mapping: Mapping[str, str]) -> Self:
        self.commands.append(("mset", (mapping,), {}))
        return self

    def hset(self, name: str, *, mapping: Mapping[str, str]) -> Self:
        self.commands.append(("hset", (name,), {"mapping": mapping}))
        return self

    def lpush(self, name: str, *values: str) -> Self:
        self.commands.append(("lpush", (name, *values), {}))
        return self

    def rpush(self, name: str, *values: str) -> Self:
        self.commands.append(("rpush", (name, *values), {}))
        return self

    def sadd(self, name: str, *members: str) -> Self:
        self.commands.append(("sadd", (name, *members), {}))
        return self

    def expire(self, name: str, seconds: int) -> Self:
        self.commands.append(("expire", (name, seconds), {}))
        return self

    async def execute(self) -> list[bool | int]:
        self.executed = True
        primary_command = self.commands[0][0]
        return [self._PRIMARY_RESULTS[primary_command], *(True for _command in self.commands[1:])]


class PipelineRedisClient:
    """只允许通过事务 pipeline 执行带过期时间的写操作。"""

    def __init__(self) -> None:
        self.pipelines: list[RecordingPipeline] = []

    def pipeline(self, transaction: bool = True) -> RecordingPipeline:
        pipeline = RecordingPipeline(transaction)
        self.pipelines.append(pipeline)
        return pipeline


@pytest.fixture(autouse=True)
def mute_cache_logs(monkeypatch: pytest.MonkeyPatch) -> None:
    """避免缓存单元测试依赖应用日志生命周期。"""
    monkeypatch.setattr(redis_module.log, "error", lambda *_args, **_kwargs: None)


def test_writes_with_expiry_use_atomic_transactions_and_preserve_results(monkeypatch: pytest.MonkeyPatch) -> None:
    """写入与 TTL 必须在同一事务中执行，且公开返回值保持原语义。"""
    manager = RedisManager()
    client = PipelineRedisClient()
    monkeypatch.setattr(manager, "_client", cast(Redis, client))
    monkeypatch.setattr(manager, "_redis_prefix", "template")

    async def run_case() -> None:
        assert await manager.mset({"one": 1, "two": 2}, ex=60) is True
        assert await manager.hset("hash", {"one": 1, "two": 2}, ex=60) == 2
        assert await manager.lpush("left", 1, 2, 3, ex=60) == 3
        assert await manager.rpush("right", 1, 2, 3, 4, ex=60) == 4
        assert await manager.sadd("set", 1, 2, ex=60) == 2

    asyncio.run(run_case())

    assert len(client.pipelines) == 5
    assert all(pipeline.transaction is True and pipeline.executed for pipeline in client.pipelines)
    assert [command[0] for command in client.pipelines[0].commands] == ["mset", "expire", "expire"]
    assert all(
        [command[0] for command in pipeline.commands] == [primary_command, "expire"]
        for pipeline, primary_command in zip(
            client.pipelines[1:],
            ("hset", "lpush", "rpush", "sadd"),
            strict=True,
        )
    )
    assert all(
        command[1][-1] == 60 for pipeline in client.pipelines for command in pipeline.commands if command[0] == "expire"
    )
