import asyncio
import inspect
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from limits import RateLimitItem, parse, parse_many
from limits.aio.storage import Storage
from limits.aio.storage.memory import MemoryStorage
from limits.aio.storage.redis.redispy import RedispyBridge
from limits.aio.strategies import FixedWindowRateLimiter
from limits.errors import StorageError
from redis.asyncio import BlockingConnectionPool, Redis

from app.core.rate_limit import rate_limit
from app.core.rate_limit import rate_limiter as rate_limit_module
from app.exceptions import RateLimitException, register_exception_handlers
from config.rate_limit_config import RateLimitSettings
from config.settings import get_settings


@rate_limit("2/minute")
async def limited_endpoint(request: Request) -> dict[str, str]:
    """提供自定义额度的测试接口。"""
    return {"status": "ok"}


@rate_limit()
async def default_limited_endpoint(request: Request) -> dict[str, str]:
    """提供默认额度的测试接口。"""
    return {"status": "ok"}


async def unlimited_endpoint(request: Request) -> dict[str, str]:
    """提供未声明限流的测试接口。"""
    return {"status": "ok"}


def _create_request(
    path: str = "/limited",
    client_host: str = "203.0.113.10",
) -> Request:
    """创建包含稳定客户端地址的最小 ASGI 请求。"""
    return Request(
        {
            "type": "http",
            "http_version": "1.1",
            "method": "GET",
            "scheme": "http",
            "path": path,
            "raw_path": path.encode(),
            "query_string": b"",
            "headers": [],
            "client": (client_host, 12345),
            "server": ("testserver", 80),
        }
    )


@pytest.fixture(autouse=True)
def configure_limiter(monkeypatch: pytest.MonkeyPatch) -> None:
    """为每个测试使用独立异步内存策略，避免依赖真实 Redis。"""
    storage = MemoryStorage()
    strategy = FixedWindowRateLimiter(storage)
    monkeypatch.setattr(rate_limit_module.limiter, "_storage", None)
    monkeypatch.setattr(rate_limit_module.limiter, "_pool", None)
    monkeypatch.setattr(rate_limit_module.limiter, "_strategy", strategy)
    monkeypatch.setattr(rate_limit_module.limiter, "enabled", False)
    monkeypatch.setattr(rate_limit_module.limiter, "fail_open", True)
    monkeypatch.setattr(rate_limit_module.log, "info", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(rate_limit_module.log, "warning", lambda *_args, **_kwargs: None)


def create_test_client() -> TestClient:
    """创建仅包含限流测试接口的最小 FastAPI 客户端。"""
    app = FastAPI()
    register_exception_handlers(app)
    rate_limit_module.register_rate_limiter(app)
    app.add_api_route("/limited", limited_endpoint, methods=["GET"])
    app.add_api_route("/default-limited", default_limited_endpoint, methods=["GET"])
    app.add_api_route("/unlimited", unlimited_endpoint, methods=["GET"])
    return TestClient(app)


def test_rate_limit_is_disabled_by_default_and_does_not_check_storage(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """默认关闭时，显式标注接口也不访问限流存储。"""

    class UnexpectedStrategy:
        async def hit(self, *_args: Any, **_kwargs: Any) -> bool:
            raise AssertionError("关闭限流时不应访问存储")

    monkeypatch.setattr(rate_limit_module.limiter, "_strategy", UnexpectedStrategy())
    client = create_test_client()

    assert get_settings().rate_limit.RATE_LIMIT_ENABLED is False
    assert client.get("/limited").status_code == 200
    assert client.get("/limited").status_code == 200
    assert client.get("/limited").status_code == 200


def test_explicit_limit_returns_unified_429_response() -> None:
    """开启后，超过显式额度的请求返回项目统一 429 响应。"""
    rate_limit_module.limiter.enabled = True
    client = create_test_client()

    assert client.get("/limited").status_code == 200
    assert client.get("/limited").status_code == 200

    response = client.get("/limited")

    assert response.status_code == 429
    assert response.json() == {
        "code": 99999,
        "message": "请求过于频繁，请稍后重试",
        "result": {},
    }


def test_unmarked_endpoint_is_not_limited_and_default_limit_is_enforced() -> None:
    """未标注接口不受影响，默认额度会在超限时真实返回 429。"""
    rate_limit_module.limiter.enabled = True
    client = create_test_client()

    assert get_settings().rate_limit.RATE_LIMIT_DEFAULT == "100/minute"
    assert [client.get("/limited").status_code for _ in range(3)] == [200, 200, 429]
    default_limit_statuses = [client.get("/default-limited").status_code for _ in range(101)]
    assert default_limit_statuses[:100] == [200] * 100
    assert default_limit_statuses[100] == 429
    assert [client.get("/unlimited").status_code for _ in range(5)] == [200, 200, 200, 200, 200]


def test_redis_storage_failure_is_fail_open(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Redis 存储异常在 fail-open 模式下放行请求。"""

    class FailingStrategy:
        async def hit(self, *_args: Any, **_kwargs: Any) -> bool:
            raise StorageError(ConnectionError("Redis unavailable"))

    rate_limit_module.limiter.enabled = True
    monkeypatch.setattr(rate_limit_module.limiter, "_strategy", FailingStrategy())
    client = create_test_client()

    assert client.get("/limited").status_code == 200


def test_redis_storage_failure_can_fail_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """关闭 fail-open 后，Redis 存储异常应返回统一 503。"""

    class FailingStrategy:
        async def hit(self, *_args: Any, **_kwargs: Any) -> bool:
            raise StorageError(ConnectionError("Redis unavailable"))

    rate_limit_module.limiter.enabled = True
    rate_limit_module.limiter.fail_open = False
    monkeypatch.setattr(rate_limit_module.limiter, "_strategy", FailingStrategy())
    client = create_test_client()

    response = client.get("/limited")

    assert response.status_code == 503
    assert response.json() == {
        "code": 5001,
        "message": "接口限流服务暂不可用，请稍后重试",
        "result": {},
    }


def test_unexpected_strategy_error_is_not_swallowed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """程序缺陷不得被当作 Redis 故障静默放行。"""

    class BuggyStrategy:
        async def hit(self, *_args: Any, **_kwargs: Any) -> bool:
            raise RuntimeError("programming error")

    local_limiter = rate_limit_module.AsyncRateLimiter(
        enabled=True,
        fail_open=True,
        key_prefix="template:rate_limit",
    )
    monkeypatch.setattr(local_limiter, "_strategy", BuggyStrategy())

    with pytest.raises(RuntimeError, match="programming error"):
        asyncio.run(
            local_limiter.check(
                _create_request(),
                "tests.test_rate_limit.limited_endpoint",
                (parse("2/minute"),),
            )
        )


def test_cancelled_error_is_not_swallowed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """请求取消信号必须继续向上传播。"""

    class CancelledStrategy:
        async def hit(self, *_args: Any, **_kwargs: Any) -> bool:
            raise asyncio.CancelledError

    local_limiter = rate_limit_module.AsyncRateLimiter(
        enabled=True,
        fail_open=True,
        key_prefix="template:rate_limit",
    )
    monkeypatch.setattr(local_limiter, "_strategy", CancelledStrategy())

    with pytest.raises(asyncio.CancelledError):
        asyncio.run(
            local_limiter.check(
                _create_request(),
                "tests.test_rate_limit.limited_endpoint",
                (parse("2/minute"),),
            )
        )


def test_rate_limit_preserves_legacy_key_components(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """新实现应复用 SlowAPI 旧键组成，保证滚动发布期间共享计数。"""
    captured_identifiers: list[tuple[str, ...]] = []

    class CapturingStrategy:
        async def hit(
            self,
            _item: RateLimitItem,
            *identifiers: str,
            cost: int = 1,
        ) -> bool:
            assert cost == 1
            captured_identifiers.append(identifiers)
            return True

    local_limiter = rate_limit_module.AsyncRateLimiter(
        enabled=True,
        fail_open=True,
        key_prefix="template:rate_limit",
    )
    monkeypatch.setattr(local_limiter, "_strategy", CapturingStrategy())
    item = parse("2/minute")

    asyncio.run(
        local_limiter.check(
            _create_request(client_host="198.51.100.20"),
            "tests.test_rate_limit.limited_endpoint",
            (item,),
        )
    )

    identifiers = captured_identifiers[0]
    assert identifiers == (
        "template:rate_limit",
        "198.51.100.20",
        "tests.test_rate_limit.limited_endpoint",
    )
    assert (
        f"{rate_limit_module._LIMITS_STORAGE_PREFIX}:{item.key_for(*identifiers)}"
        == "LIMITS:LIMITER/template:rate_limit/198.51.100.20/"
        "tests.test_rate_limit.limited_endpoint/2/1/minute"
    )


def test_async_check_yields_control_to_event_loop(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """等待异步存储时，事件循环仍应能够调度其他协程。"""

    async def run_case() -> None:
        entered = asyncio.Event()
        release = asyncio.Event()

        class WaitingStrategy:
            async def hit(self, *_args: Any, **_kwargs: Any) -> bool:
                entered.set()
                await release.wait()
                return True

        local_limiter = rate_limit_module.AsyncRateLimiter(
            enabled=True,
            fail_open=True,
            key_prefix="template:rate_limit",
        )
        monkeypatch.setattr(local_limiter, "_strategy", WaitingStrategy())
        check_task = asyncio.create_task(
            local_limiter.check(
                _create_request(),
                "tests.test_rate_limit.limited_endpoint",
                (parse("2/minute"),),
            )
        )

        await asyncio.wait_for(entered.wait(), timeout=1)
        marker: list[str] = []
        await asyncio.sleep(0)
        marker.append("scheduled")

        assert marker == ["scheduled"]
        assert not check_task.done()

        release.set()
        await check_task

    asyncio.run(run_case())


def test_combined_limits_reject_when_later_limit_is_exhausted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """组合额度中任意一项耗尽时都必须拒绝请求。"""
    storage = MemoryStorage()
    local_limiter = rate_limit_module.AsyncRateLimiter(
        enabled=True,
        fail_open=True,
        key_prefix="template:rate_limit",
    )
    monkeypatch.setattr(local_limiter, "_strategy", FixedWindowRateLimiter(storage))
    combined_limits = tuple(parse_many("3/second; 1/minute"))
    request = _create_request()

    async def run_case() -> None:
        await local_limiter.check(request, "tests.combined_endpoint", combined_limits)
        with pytest.raises(RateLimitException):
            await local_limiter.check(request, "tests.combined_endpoint", combined_limits)

    asyncio.run(run_case())


def test_decorator_preserves_endpoint_signature() -> None:
    """装饰后仍应保留 FastAPI 依赖注入所需的原始函数签名。"""
    endpoint_signature = inspect.signature(limited_endpoint)

    assert list(endpoint_signature.parameters) == ["request"]
    assert endpoint_signature.parameters["request"].annotation is Request
    assert limited_endpoint.__name__ == "limited_endpoint"


def test_limiter_start_and_close_manage_pool(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """启用限流时应检查连接，并在关闭阶段释放客户端和专用连接池。"""

    class TrackingPool:
        def __init__(self) -> None:
            self.close_calls = 0

        async def aclose(self) -> None:
            self.close_calls += 1

    class TrackingClient:
        def __init__(self) -> None:
            self.ping_calls = 0
            self.close_calls = 0

        async def ping(self) -> bool:
            self.ping_calls += 1
            return True

        async def aclose(self) -> None:
            self.close_calls += 1

    pool = TrackingPool()
    client = TrackingClient()
    storage = MemoryStorage()
    local_limiter = rate_limit_module.AsyncRateLimiter(
        enabled=True,
        fail_open=True,
        key_prefix="template:rate_limit",
    )
    monkeypatch.setattr(rate_limit_module, "_create_rate_limit_pool", lambda *_args: pool)
    monkeypatch.setattr(rate_limit_module, "_create_rate_limit_client", lambda _pool: client)
    monkeypatch.setattr(rate_limit_module, "_create_rate_limit_storage", lambda _pool: storage)
    monkeypatch.setattr(rate_limit_module.log, "info", lambda *_args, **_kwargs: None)

    async def run_case() -> None:
        await local_limiter.start()
        assert isinstance(local_limiter._strategy, FixedWindowRateLimiter)

        await local_limiter.close()
        await local_limiter.close()

    asyncio.run(run_case())

    assert client.ping_calls == 1
    assert client.close_calls == 1
    assert pool.close_calls == 1


def test_concurrent_limiter_start_initializes_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """多个并发启动调用只能创建一套限流资源。"""

    class TrackingPool:
        def __init__(self) -> None:
            self.close_calls = 0

        async def aclose(self) -> None:
            self.close_calls += 1

    class YieldingClient:
        def __init__(self) -> None:
            self.ping_calls = 0
            self.close_calls = 0

        async def ping(self) -> bool:
            self.ping_calls += 1
            await asyncio.sleep(0)
            return True

        async def aclose(self) -> None:
            self.close_calls += 1

    pool = TrackingPool()
    client = YieldingClient()
    pool_factory_calls = 0
    local_limiter = rate_limit_module.AsyncRateLimiter(
        enabled=True,
        fail_open=True,
        key_prefix="template:rate_limit",
    )

    def create_pool(*_args: Any) -> TrackingPool:
        nonlocal pool_factory_calls
        pool_factory_calls += 1
        return pool

    monkeypatch.setattr(rate_limit_module, "_create_rate_limit_pool", create_pool)
    monkeypatch.setattr(rate_limit_module, "_create_rate_limit_client", lambda _pool: client)
    monkeypatch.setattr(rate_limit_module, "_create_rate_limit_storage", lambda _pool: MemoryStorage())
    monkeypatch.setattr(rate_limit_module.log, "info", lambda *_args, **_kwargs: None)

    async def run_case() -> None:
        await asyncio.gather(local_limiter.start(), local_limiter.start())
        await local_limiter.close()

    asyncio.run(run_case())

    assert pool_factory_calls == 1
    assert client.ping_calls == 1
    assert client.close_calls == 1
    assert pool.close_calls == 1


def test_limiter_start_failure_releases_pool(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """限流连接检查失败时不得泄漏已创建的客户端或连接池。"""

    class TrackingPool:
        def __init__(self) -> None:
            self.close_calls = 0

        async def aclose(self) -> None:
            self.close_calls += 1

    class UnavailableClient:
        def __init__(self) -> None:
            self.close_calls = 0

        async def ping(self) -> bool:
            raise ConnectionError("异步限流 Redis 连接检查失败")

        async def aclose(self) -> None:
            self.close_calls += 1

    pool = TrackingPool()
    client = UnavailableClient()
    storage = MemoryStorage()
    local_limiter = rate_limit_module.AsyncRateLimiter(
        enabled=True,
        fail_open=True,
        key_prefix="template:rate_limit",
    )
    monkeypatch.setattr(rate_limit_module, "_create_rate_limit_pool", lambda *_args: pool)
    monkeypatch.setattr(rate_limit_module, "_create_rate_limit_client", lambda _pool: client)
    monkeypatch.setattr(rate_limit_module, "_create_rate_limit_storage", lambda _pool: storage)

    with pytest.raises(ConnectionError, match="连接检查失败"):
        asyncio.run(local_limiter.start())

    assert client.close_calls == 1
    assert pool.close_calls == 1
    assert local_limiter._strategy is None
    assert local_limiter._client is None


def test_limiter_storage_construction_failure_releases_resources(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """存储适配器构造失败时也不得泄漏客户端和连接池。"""

    class TrackingPool:
        def __init__(self) -> None:
            self.close_calls = 0

        async def aclose(self) -> None:
            self.close_calls += 1

    class TrackingClient:
        def __init__(self) -> None:
            self.close_calls = 0

        async def aclose(self) -> None:
            self.close_calls += 1

    pool = TrackingPool()
    client = TrackingClient()
    local_limiter = rate_limit_module.AsyncRateLimiter(
        enabled=True,
        fail_open=True,
        key_prefix="template:rate_limit",
    )
    monkeypatch.setattr(rate_limit_module, "_create_rate_limit_pool", lambda *_args: pool)
    monkeypatch.setattr(rate_limit_module, "_create_rate_limit_client", lambda _pool: client)

    def fail_storage_creation(_pool: object) -> MemoryStorage:
        raise RuntimeError("模拟存储构造失败")

    monkeypatch.setattr(rate_limit_module, "_create_rate_limit_storage", fail_storage_creation)

    with pytest.raises(RuntimeError, match="存储构造失败"):
        asyncio.run(local_limiter.start())

    assert client.close_calls == 1
    assert pool.close_calls == 1
    assert local_limiter._strategy is None


def test_limiter_start_cancellation_is_propagated_and_cleaned(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """启动 PING 被取消时必须传播取消信号并释放局部资源。"""

    class TrackingPool:
        def __init__(self) -> None:
            self.close_calls = 0

        async def aclose(self) -> None:
            self.close_calls += 1

    class CancelledClient:
        def __init__(self) -> None:
            self.close_calls = 0

        async def ping(self) -> bool:
            raise asyncio.CancelledError

        async def aclose(self) -> None:
            self.close_calls += 1

    pool = TrackingPool()
    client = CancelledClient()
    local_limiter = rate_limit_module.AsyncRateLimiter(
        enabled=True,
        fail_open=True,
        key_prefix="template:rate_limit",
    )
    monkeypatch.setattr(rate_limit_module, "_create_rate_limit_pool", lambda *_args: pool)
    monkeypatch.setattr(rate_limit_module, "_create_rate_limit_client", lambda _pool: client)
    monkeypatch.setattr(rate_limit_module, "_create_rate_limit_storage", lambda _pool: MemoryStorage())

    with pytest.raises(asyncio.CancelledError):
        asyncio.run(local_limiter.start())

    assert client.close_calls == 1
    assert pool.close_calls == 1


def test_close_cancellation_still_closes_pool(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """客户端关闭被取消时仍必须继续释放连接池并传播取消。"""

    class TrackingPool:
        def __init__(self) -> None:
            self.close_calls = 0

        async def aclose(self) -> None:
            self.close_calls += 1

    class CancelledClient:
        async def aclose(self) -> None:
            raise asyncio.CancelledError

    pool = TrackingPool()
    local_limiter = rate_limit_module.AsyncRateLimiter(
        enabled=True,
        fail_open=True,
        key_prefix="template:rate_limit",
    )
    monkeypatch.setattr(local_limiter, "_client", CancelledClient())
    monkeypatch.setattr(local_limiter, "_pool", pool)
    monkeypatch.setattr(local_limiter, "_strategy", FixedWindowRateLimiter(MemoryStorage()))

    with pytest.raises(asyncio.CancelledError):
        asyncio.run(local_limiter.close())

    assert pool.close_calls == 1
    assert local_limiter._client is None
    assert local_limiter._pool is None


def test_disabled_limiter_does_not_create_pool(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """限流关闭时生命周期初始化不得创建额外 Redis 连接。"""
    local_limiter = rate_limit_module.AsyncRateLimiter(
        enabled=False,
        fail_open=True,
        key_prefix="template:rate_limit",
    )

    def fail_if_called(*_args: Any) -> None:
        raise AssertionError("限流关闭时不应创建连接池")

    monkeypatch.setattr(rate_limit_module, "_create_rate_limit_pool", fail_if_called)

    asyncio.run(local_limiter.start())


def test_decorator_rejects_invalid_endpoint_contracts() -> None:
    """装饰器应在导入阶段拒绝无效额度、同步接口和缺少 Request 的接口。"""
    with pytest.raises(ValueError, match="无效的接口限流表达式"):
        rate_limit("invalid")

    with pytest.raises(ValueError, match="请求次数必须大于 0"):
        rate_limit("0/minute")

    with pytest.raises(TypeError, match="仅支持 async def"):

        @rate_limit("1/minute")  # ty: ignore[invalid-argument-type] 此处刻意验证同步函数会被拒绝
        def sync_endpoint(request: Request) -> dict[str, str]:
            return {"status": "ok"}

    with pytest.raises(TypeError, match="必须声明名为 request"):

        @rate_limit("1/minute")
        async def missing_request_endpoint() -> dict[str, str]:
            return {"status": "ok"}


def test_disabled_invalid_default_keeps_previous_import_behavior(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """限流关闭时，无效默认额度不得导致使用默认装饰器的模块导入失败。"""
    rate_limit_settings = RateLimitSettings(
        RATE_LIMIT_ENABLED=False,
        RATE_LIMIT_DEFAULT="invalid",
    )
    monkeypatch.setattr(
        rate_limit_module,
        "get_settings",
        lambda: SimpleNamespace(rate_limit=rate_limit_settings),
    )

    @rate_limit()
    async def dormant_endpoint(request: Request) -> dict[str, str]:
        return {"status": "ok"}

    assert asyncio.run(dormant_endpoint(_create_request())) == {"status": "ok"}

    rate_limit_module.limiter.enabled = True
    with pytest.raises(ValueError, match="无效的接口限流表达式"):
        asyncio.run(dormant_endpoint(_create_request()))


def test_rate_limit_storage_is_async_redispy() -> None:
    """生产存储应明确使用 limits.aio 和 redis.asyncio，而不是同步客户端。"""
    settings = get_settings()
    pool = rate_limit_module._create_rate_limit_pool(settings.cache, settings.rate_limit)
    storage = rate_limit_module._create_rate_limit_storage(pool)
    client = rate_limit_module._create_rate_limit_client(pool)

    assert isinstance(storage, Storage)
    assert isinstance(storage.bridge, RedispyBridge)
    storage_client = storage.bridge.get_connection()
    assert isinstance(storage_client, Redis)
    assert isinstance(pool, BlockingConnectionPool)
    assert storage_client.connection_pool is pool
    assert client.connection_pool is pool
    assert storage.bridge.key_prefix == "LIMITS"

    async def close_resources() -> None:
        await client.aclose()
        await pool.aclose()

    asyncio.run(close_resources())
