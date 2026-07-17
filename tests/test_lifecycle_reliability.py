import asyncio
import importlib

import pytest
from fastapi import FastAPI

from app.core import events as events_module

shutdown_module = importlib.import_module("app.core.events.shutdown")


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
    """数据库清理失败不得阻断 Redis 清理和日志队列排空。"""
    cleanup_calls: list[str] = []
    error_messages: list[str] = []

    async def failing_database_cleanup() -> None:
        cleanup_calls.append("database")
        raise RuntimeError("模拟数据库关闭失败")

    async def cache_cleanup() -> None:
        cleanup_calls.append("cache")

    async def log_cleanup() -> None:
        cleanup_calls.append("log")

    monkeypatch.setattr(shutdown_module, "db_disconnect", failing_database_cleanup)
    monkeypatch.setattr(shutdown_module, "close_cache", cache_cleanup)
    monkeypatch.setattr(shutdown_module, "complete_log", log_cleanup)
    monkeypatch.setattr(shutdown_module.log, "error", error_messages.append)

    asyncio.run(shutdown_module.shutdown())

    assert cleanup_calls == ["database", "cache", "log"]
    assert len(error_messages) == 1
    assert "数据库" in error_messages[0]
    assert "RuntimeError" in error_messages[0]
