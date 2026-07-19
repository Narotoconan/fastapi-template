import asyncio
import importlib

import pytest
from fastapi import FastAPI

from app.core import events as events_module

shutdown_module = importlib.import_module("app.core.events.shutdown")
startup_module = importlib.import_module("app.core.events.startup")


def test_lifespan_runs_shutdown_when_startup_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    """启动流程中途失败时也必须进入统一清理阶段。"""
    lifecycle_calls: list[str] = []

    async def failing_startup() -> None:
        lifecycle_calls.append("startup")
        raise RuntimeError("模拟初始化失败")

    async def mock_shutdown() -> None:
        lifecycle_calls.append("shutdown")

    monkeypatch.setattr(events_module, "startup", failing_startup)
    monkeypatch.setattr(events_module, "shutdown", mock_shutdown)

    async def run_case() -> None:
        async with events_module.lifespan(FastAPI()):
            pytest.fail("启动失败后不应进入应用运行阶段")

    with pytest.raises(RuntimeError, match="模拟初始化失败"):
        asyncio.run(run_case())

    assert lifecycle_calls == ["startup", "shutdown"]


def test_shutdown_continues_after_individual_cleanup_failures(monkeypatch: pytest.MonkeyPatch) -> None:
    """限流清理失败不得阻断缓存、数据库和日志资源的后续清理。"""
    cleanup_calls: list[str] = []
    error_messages: list[str] = []

    async def failing_rate_limit_cleanup() -> None:
        cleanup_calls.append("rate_limit")
        raise RuntimeError("模拟限流连接池关闭失败")

    async def cache_cleanup() -> None:
        cleanup_calls.append("cache")

    async def database_cleanup() -> None:
        cleanup_calls.append("database")

    async def log_cleanup() -> None:
        cleanup_calls.append("log")

    monkeypatch.setattr(shutdown_module, "close_rate_limiter", failing_rate_limit_cleanup)
    monkeypatch.setattr(shutdown_module, "close_cache", cache_cleanup)
    monkeypatch.setattr(shutdown_module, "db_disconnect", database_cleanup)
    monkeypatch.setattr(shutdown_module, "complete_log", log_cleanup)
    monkeypatch.setattr(shutdown_module.log, "error", error_messages.append)

    asyncio.run(shutdown_module.shutdown())

    assert cleanup_calls == ["rate_limit", "cache", "database", "log"]
    assert len(error_messages) == 1
    assert "接口限流" in error_messages[0]
    assert "RuntimeError" in error_messages[0]


def test_startup_initializes_dependencies_in_order(monkeypatch: pytest.MonkeyPatch) -> None:
    """启动时应先准备数据库和业务缓存，再初始化限流专用 Redis 连接。"""
    startup_calls: list[str] = []

    async def database_startup() -> None:
        startup_calls.append("database")

    async def cache_startup() -> None:
        startup_calls.append("cache")

    async def rate_limit_startup() -> None:
        startup_calls.append("rate_limit")

    monkeypatch.setattr(startup_module, "db_first_connection", database_startup)
    monkeypatch.setattr(startup_module, "init_cache", cache_startup)
    monkeypatch.setattr(startup_module, "init_rate_limiter", rate_limit_startup)

    asyncio.run(startup_module.startup())

    assert startup_calls == ["database", "cache", "rate_limit"]
