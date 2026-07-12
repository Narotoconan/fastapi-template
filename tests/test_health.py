import asyncio

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import app.exceptions.handlers as exception_handlers_module
import app.services.health_service as health_service_module
from app.api.health import router_health
from app.exceptions import ServiceUnavailableException, register_exception_handlers
from app.schemas.health_schema import HealthCheckResult


class HealthyRedisProbe:
    """提供健康 Redis PING 结果的测试替身。"""

    async def ping(self) -> bool:
        return True


def create_health_client() -> TestClient:
    """创建只注册健康检查路由的测试客户端。"""
    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(router_health)
    return TestClient(app, raise_server_exceptions=False)


def test_health_service_returns_healthy_when_dependencies_are_available(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """PostgreSQL 与 Redis 均可用时返回健康状态。"""

    async def healthy_database() -> bool:
        return True

    monkeypatch.setattr(health_service_module, "db_health_check", healthy_database)
    monkeypatch.setattr(health_service_module, "get_redis_manager", HealthyRedisProbe)

    health_result = asyncio.run(health_service_module.health_service.check())

    assert health_result == HealthCheckResult(
        status="healthy",
        checks={"database": "healthy", "redis": "healthy"},
    )


def test_health_service_raises_503_exception_when_database_is_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """数据库不可用时返回不包含内部异常详情的统一 503 异常。"""

    async def unavailable_database() -> bool:
        raise ConnectionError("sensitive database connection details")

    monkeypatch.setattr(health_service_module, "db_health_check", unavailable_database)
    monkeypatch.setattr(health_service_module, "get_redis_manager", HealthyRedisProbe)
    monkeypatch.setattr(health_service_module.log, "warning", lambda *_args, **_kwargs: None)

    with pytest.raises(ServiceUnavailableException) as exc_info:
        asyncio.run(health_service_module.health_service.check())

    assert exc_info.value.http_status == 503
    assert exc_info.value.message == "关键依赖不可用"
    assert exc_info.value.result == {
        "status": "unhealthy",
        "checks": {"database": "unhealthy", "redis": "healthy"},
    }
    assert "sensitive" not in exc_info.value.message


def test_health_endpoint_returns_unified_success_response(monkeypatch: pytest.MonkeyPatch) -> None:
    """健康检查接口使用项目统一成功响应。"""

    async def healthy_check() -> HealthCheckResult:
        return HealthCheckResult(
            status="healthy",
            checks={"database": "healthy", "redis": "healthy"},
        )

    monkeypatch.setattr(health_service_module.health_service, "check", healthy_check)

    response = create_health_client().get("/health")

    assert response.status_code == 200
    assert response.json() == {
        "code": 0,
        "message": "success",
        "result": {
            "status": "healthy",
            "checks": {"database": "healthy", "redis": "healthy"},
        },
    }


def test_health_endpoint_returns_unified_503_response(monkeypatch: pytest.MonkeyPatch) -> None:
    """关键依赖不可用时健康检查接口返回统一 503 响应。"""

    async def unhealthy_check() -> HealthCheckResult:
        raise ServiceUnavailableException(
            message="关键依赖不可用",
            result={
                "status": "unhealthy",
                "checks": {"database": "healthy", "redis": "unhealthy"},
            },
        )

    monkeypatch.setattr(health_service_module.health_service, "check", unhealthy_check)
    monkeypatch.setattr(exception_handlers_module.log, "warning", lambda *_args, **_kwargs: None)

    response = create_health_client().get("/health")

    assert response.status_code == 503
    assert response.json() == {
        "code": 5001,
        "message": "关键依赖不可用",
        "result": {
            "status": "unhealthy",
            "checks": {"database": "healthy", "redis": "unhealthy"},
        },
    }
