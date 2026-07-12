import asyncio

import pytest
from fastapi import FastAPI
from pydantic import ValidationError

from app.core import events as events_module
from app.core.cache.redis import _create_connection_pool
from app.core.database.postgresql import build_database_url
from config.cache_config import CacheSettings
from config.database_config import DatabaseSettings
from config.middleware_config import JWTSettings


def test_database_password_is_required(monkeypatch: pytest.MonkeyPatch) -> None:
    """数据库密码缺失时配置初始化必须失败。"""
    monkeypatch.delenv("DB_PASSWORD", raising=False)

    with pytest.raises(ValidationError):
        DatabaseSettings()  # ty: ignore[missing-argument] 此处刻意验证缺少必填配置


def test_jwt_secret_is_required_and_has_minimum_length(monkeypatch: pytest.MonkeyPatch) -> None:
    """JWT 密钥缺失或长度不足时配置初始化必须失败。"""
    monkeypatch.delenv("JWT_SECRET_KEY", raising=False)

    with pytest.raises(ValidationError):
        JWTSettings()  # ty: ignore[missing-argument] 此处刻意验证缺少必填配置

    with pytest.raises(ValidationError):
        JWTSettings(JWT_SECRET_KEY="too-short")


def test_database_pool_settings_are_configurable() -> None:
    """数据库连接池容量可通过配置覆盖并拒绝非法值。"""
    database_settings = DatabaseSettings(
        DB_PASSWORD="test-password",
        DB_POOL_SIZE=8,
        DB_MAX_OVERFLOW=4,
        DB_POOL_RECYCLE=600,
        DB_POOL_TIMEOUT=12.5,
        DB_COMMAND_TIMEOUT=45,
        DB_CONNECT_TIMEOUT=8,
    )

    assert database_settings.DB_POOL_SIZE == 8
    assert database_settings.DB_MAX_OVERFLOW == 4
    assert database_settings.DB_POOL_RECYCLE == 600
    assert database_settings.DB_POOL_TIMEOUT == 12.5
    assert database_settings.DB_COMMAND_TIMEOUT == 45
    assert database_settings.DB_CONNECT_TIMEOUT == 8

    with pytest.raises(ValidationError):
        DatabaseSettings(DB_PASSWORD="test-password", DB_POOL_SIZE=0)

    with pytest.raises(ValidationError):
        DatabaseSettings(DB_PASSWORD="test-password", DB_POOL_TIMEOUT=0)

    with pytest.raises(ValidationError):
        DatabaseSettings(DB_PASSWORD="test-password", DB_POOL_RECYCLE=-2)


def test_database_url_preserves_password_special_characters() -> None:
    """结构化 PostgreSQL URL 应完整保留密码中的特殊字符。"""
    database_url = build_database_url(
        host="postgres",
        port=5432,
        user="app_user",
        password="p@ss:/ word",
        database="app_db",
    )

    assert database_url.password == "p@ss:/ word"
    assert database_url.host == "postgres"
    assert database_url.database == "app_db"


def test_redis_pool_preserves_password_special_characters() -> None:
    """Redis 连接池应通过独立参数接收密码，而不是拼接连接 URL。"""
    cache_settings = CacheSettings(
        REDIS_HOST="redis",
        REDIS_PORT=6379,
        REDIS_DB=2,
        REDIS_PASSWORD="p@ss:/ word",
    )

    pool = _create_connection_pool(cache_settings)

    assert pool.connection_kwargs["password"] == "p@ss:/ word"
    assert pool.connection_kwargs["host"] == "redis"
    assert pool.connection_kwargs["db"] == 2


def test_lifespan_always_runs_shutdown(monkeypatch: pytest.MonkeyPatch) -> None:
    """应用处理阶段异常时仍应执行生命周期清理逻辑。"""
    lifecycle_calls: list[str] = []

    async def mock_startup() -> None:
        lifecycle_calls.append("startup")

    async def mock_shutdown() -> None:
        lifecycle_calls.append("shutdown")

    monkeypatch.setattr(events_module, "startup", mock_startup)
    monkeypatch.setattr(events_module, "shutdown", mock_shutdown)

    async def run_case() -> None:
        async with events_module.lifespan(FastAPI()):
            raise RuntimeError("模拟应用运行异常")

    with pytest.raises(RuntimeError, match="模拟应用运行异常"):
        asyncio.run(run_case())

    assert lifecycle_calls == ["startup", "shutdown"]
