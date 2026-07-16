import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import app.core.events as events_module
import app.core.log as log_module
from app.schemas.health_schema import HealthCheckResult
from app.services.health_service import health_service


def test_main_app_wires_lifespan_routes_and_exception_handlers(monkeypatch: pytest.MonkeyPatch) -> None:
    """真实应用装配应执行生命周期，并提供健康路由和统一异常响应。"""
    lifecycle_calls: list[str] = []

    async def mock_startup() -> None:
        lifecycle_calls.append("startup")

    async def mock_shutdown() -> None:
        lifecycle_calls.append("shutdown")

    async def mock_health_check() -> HealthCheckResult:
        return HealthCheckResult(
            status="healthy",
            checks={"database": "healthy", "redis": "healthy"},
        )

    monkeypatch.setattr(events_module, "startup", mock_startup)
    monkeypatch.setattr(events_module, "shutdown", mock_shutdown)
    monkeypatch.setattr(health_service, "check", mock_health_check)
    monkeypatch.setattr(log_module, "register_log", lambda: None)
    for method_name in ("info", "warning", "error", "debug"):
        monkeypatch.setattr(log_module.log, method_name, lambda *_args, **_kwargs: None)

    import main as main_module

    assert isinstance(main_module.app, FastAPI)
    with TestClient(main_module.app, raise_server_exceptions=False) as client:
        health_response = client.get("/health")
        missing_response = client.get("/__missing_route__")

    assert health_response.status_code == 200
    assert health_response.json()["result"]["status"] == "healthy"
    assert missing_response.status_code == 404
    assert missing_response.json()["code"] == 3001
    assert lifecycle_calls == ["startup", "shutdown"]
