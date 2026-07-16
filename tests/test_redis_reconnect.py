import asyncio
from typing import cast

import pytest
from redis.asyncio import Redis

import app.core.cache.redis as redis_module
from app.core.cache.redis import RedisManager, _create_connection_pool
from config.cache_config import CacheSettings


@pytest.fixture
def redis_manager(monkeypatch: pytest.MonkeyPatch) -> RedisManager:
    """提供不连接真实 Redis 且状态隔离的连接管理器。"""
    manager = RedisManager()
    monkeypatch.setattr(manager, "_pool", None)
    monkeypatch.setattr(manager, "_client", None)
    monkeypatch.setattr(manager, "_heartbeat_task", None)
    monkeypatch.setattr(manager, "_connection_lock", asyncio.Lock())
    monkeypatch.setattr(manager, "_heartbeat_interval", 0)
    monkeypatch.setattr(manager, "_reconnect_count", 0)
    monkeypatch.setattr(manager, "_reconnect_interval", 0)

    monkeypatch.setattr(redis_module.log, "debug", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(redis_module.log, "info", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(redis_module.log, "warning", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(redis_module.log, "error", lambda *_args, **_kwargs: None)
    return manager


def test_connection_pool_uses_separate_connect_and_command_timeouts() -> None:
    """连接建立和命令读写应分别使用对应的超时配置。"""
    cache_settings = CacheSettings(REDIS_TIMEOUT=2.5, REDIS_COMMAND_TIMEOUT=4.5)

    pool = _create_connection_pool(cache_settings)

    assert pool.connection_kwargs["socket_connect_timeout"] == 2.5
    assert pool.connection_kwargs["socket_timeout"] == 4.5


def test_connect_publishes_client_only_after_ping_and_serializes_concurrent_calls(
    redis_manager: RedisManager,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """并发连接只能初始化一次，PING 完成前不得暴露未验证的客户端。"""

    class FakePool:
        disconnected = False

        async def disconnect(self) -> None:
            self.disconnected = True

    class BlockingRedisClient:
        def __init__(self) -> None:
            self.ping_started = asyncio.Event()
            self.release_ping = asyncio.Event()
            self.closed = False

        async def ping(self) -> bool:
            self.ping_started.set()
            await self.release_ping.wait()
            return True

        async def close(self) -> None:
            self.closed = True

    pool = FakePool()
    client = BlockingRedisClient()
    client_create_count = 0

    def create_client(*, connection_pool: object) -> BlockingRedisClient:
        nonlocal client_create_count
        assert connection_pool is pool
        client_create_count += 1
        return client

    monkeypatch.setattr(redis_module, "_create_connection_pool", lambda _settings: pool)
    monkeypatch.setattr(redis_module.redis, "Redis", create_client)

    async def run_case() -> None:
        first_connect = asyncio.create_task(redis_manager.connect())
        second_connect = asyncio.create_task(redis_manager.connect())
        await client.ping_started.wait()

        assert redis_manager._client is None
        assert redis_manager._pool is None

        client.release_ping.set()
        await asyncio.gather(first_connect, second_connect)

        assert redis_manager._client is client
        assert redis_manager._pool is pool
        assert client_create_count == 1
        await redis_manager.disconnect()

    asyncio.run(run_case())
    assert client.closed is True
    assert pool.disconnected is True


def test_failed_ping_cleans_local_resources_without_publishing_state(
    redis_manager: RedisManager,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """PING 失败时应清理局部连接，且管理器始终保持未连接状态。"""

    class FakePool:
        disconnected = False

        async def disconnect(self) -> None:
            self.disconnected = True

    class FailingRedisClient:
        closed = False

        async def ping(self) -> bool:
            raise ConnectionError("模拟 Redis 不可达")

        async def close(self) -> None:
            self.closed = True

    pool = FakePool()
    client = FailingRedisClient()
    monkeypatch.setattr(redis_module, "_create_connection_pool", lambda _settings: pool)
    monkeypatch.setattr(redis_module.redis, "Redis", lambda **_kwargs: client)

    with pytest.raises(ConnectionError, match="模拟 Redis 不可达"):
        asyncio.run(redis_manager.connect())

    assert redis_manager._client is None
    assert redis_manager._pool is None
    assert client.closed is True
    assert pool.disconnected is True


def test_disconnect_waits_for_heartbeat_cancellation(redis_manager: RedisManager) -> None:
    """disconnect 返回前必须等待心跳任务的 finally 清理完成。"""

    async def run_case() -> None:
        heartbeat_finished = asyncio.Event()

        async def heartbeat() -> None:
            try:
                await asyncio.Event().wait()
            finally:
                await asyncio.sleep(0)
                heartbeat_finished.set()

        heartbeat_task = asyncio.create_task(heartbeat())
        redis_manager._heartbeat_task = heartbeat_task
        await asyncio.sleep(0)

        await redis_manager.disconnect()

        assert heartbeat_task.done()
        assert heartbeat_finished.is_set()
        assert redis_manager._heartbeat_task is None

    asyncio.run(run_case())


def test_disconnect_does_not_cancel_current_heartbeat_task(redis_manager: RedisManager) -> None:
    """心跳任务内部触发清理时不得取消自身并中断后续异步流程。"""

    async def run_case() -> None:
        current_task = asyncio.current_task()
        assert current_task is not None
        redis_manager._heartbeat_task = current_task

        await redis_manager.disconnect()

        assert current_task.cancelling() == 0
        assert redis_manager._heartbeat_task is None

    asyncio.run(run_case())


def test_reconnect_retries_until_connection_succeeds(
    redis_manager: RedisManager,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """临时连接失败时应继续按上限重试并在成功后重置计数。"""
    connection_attempts = 0

    async def connect_after_two_failures() -> None:
        nonlocal connection_attempts
        connection_attempts += 1
        if connection_attempts < 3:
            raise ConnectionError("模拟 Redis 暂时不可用")

    monkeypatch.setattr(redis_manager, "connect", connect_after_two_failures)

    assert asyncio.run(redis_manager._reconnect()) is True
    assert connection_attempts == 3
    assert redis_manager._reconnect_count == 0


def test_reconnect_stops_after_maximum_attempts(
    redis_manager: RedisManager,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """持续连接失败时应在达到配置上限后停止重试。"""
    connection_attempts = 0
    monkeypatch.setattr(redis_manager, "_max_reconnect_attempts", 3)

    async def always_fail_to_connect() -> None:
        nonlocal connection_attempts
        connection_attempts += 1
        raise ConnectionError("模拟 Redis 持续不可用")

    monkeypatch.setattr(redis_manager, "connect", always_fail_to_connect)

    assert asyncio.run(redis_manager._reconnect()) is False
    assert connection_attempts == 3
    assert redis_manager._reconnect_count == 3


def test_heartbeat_clears_finished_task_reference(redis_manager: RedisManager) -> None:
    """心跳循环自然结束后应清除任务引用，以便后续重新启动。"""

    async def run_case() -> None:
        heartbeat_task = asyncio.create_task(redis_manager._heartbeat_loop())
        redis_manager._heartbeat_task = heartbeat_task

        await heartbeat_task

        assert redis_manager._heartbeat_task is None

    asyncio.run(run_case())


def test_heartbeat_reconnects_without_cancelling_itself(
    redis_manager: RedisManager,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """心跳失败后应进入重连流程，并继续运行到连接状态明确结束。"""
    reconnect_calls = 0

    class FailingRedisClient:
        async def ping(self) -> bool:
            raise ConnectionError("模拟心跳失败")

    async def reconnect_once() -> bool:
        nonlocal reconnect_calls
        reconnect_calls += 1
        redis_manager._client = None
        return True

    monkeypatch.setattr(redis_manager, "_reconnect", reconnect_once)

    async def run_case() -> None:
        redis_manager._client = cast(Redis, FailingRedisClient())
        heartbeat_task = asyncio.create_task(redis_manager._heartbeat_loop())
        redis_manager._heartbeat_task = heartbeat_task

        await heartbeat_task

        assert heartbeat_task.cancelled() is False
        assert redis_manager._heartbeat_task is None

    asyncio.run(run_case())
    assert reconnect_calls == 1
