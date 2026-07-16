from typing import Any

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from limits.storage import MemoryStorage
from limits.strategies import FixedWindowRateLimiter

from app.core.rate_limit import rate_limit
from app.core.rate_limit import rate_limiter as rate_limit_module
from config.cache_config import CacheSettings
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


@pytest.fixture(autouse=True)
def configure_limiter(monkeypatch: pytest.MonkeyPatch) -> None:
    """为每个测试使用独立内存存储，避免依赖真实 Redis。"""
    storage = MemoryStorage()
    monkeypatch.setattr(rate_limit_module.limiter, "_storage", storage)
    monkeypatch.setattr(
        rate_limit_module.limiter,
        "_limiter",
        FixedWindowRateLimiter(storage),
    )
    monkeypatch.setattr(rate_limit_module.limiter, "enabled", False)
    monkeypatch.setattr(rate_limit_module.log, "info", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(rate_limit_module.log, "warning", lambda *_args, **_kwargs: None)


def create_test_client() -> TestClient:
    """创建仅包含限流测试接口的最小 FastAPI 客户端。"""
    app = FastAPI()
    rate_limit_module.register_rate_limiter(app)
    app.add_api_route("/limited", limited_endpoint, methods=["GET"])
    app.add_api_route("/default-limited", default_limited_endpoint, methods=["GET"])
    app.add_api_route("/unlimited", unlimited_endpoint, methods=["GET"])
    return TestClient(app)


def test_rate_limit_is_disabled_by_default_and_does_not_check_storage(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """默认关闭时，显式标注接口也不访问限流存储。"""

    def fail_if_checked(*_args: Any, **_kwargs: Any) -> None:
        raise AssertionError("关闭限流时不应访问存储")

    monkeypatch.setattr(rate_limit_module.limiter, "_check_request_limit", fail_if_checked)
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


def test_redis_failure_is_swallowed_and_request_is_allowed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Redis 存储不可用时放行请求。"""

    class FailingRateLimiter:
        def hit(self, *_args: Any, **_kwargs: Any) -> bool:
            raise ConnectionError("Redis unavailable")

    rate_limit_module.limiter.enabled = True
    monkeypatch.setattr(rate_limit_module.limiter, "_limiter", FailingRateLimiter())
    client = create_test_client()

    assert client.get("/limited").status_code == 200


def test_build_rate_limit_storage_uri_escapes_password() -> None:
    """Redis URI 会正确转义密码中的特殊字符。"""
    cache_settings = CacheSettings(
        REDIS_HOST="redis.example.com",
        REDIS_PORT=6380,
        REDIS_DB=3,
        REDIS_PASSWORD="p@ss:/ word",
    )

    assert (
        rate_limit_module.build_rate_limit_storage_uri(cache_settings)
        == "redis://:p%40ss%3A%2F%20word@redis.example.com:6380/3"
    )


def test_rate_limit_uses_project_redis_prefix() -> None:
    """限流键使用独立的项目 Redis 前缀。"""
    assert rate_limit_module.limiter._key_prefix == f"{get_settings().cache.REDIS_PREFIX}:rate_limit"
