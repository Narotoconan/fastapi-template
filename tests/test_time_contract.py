import json
from datetime import datetime
from typing import Any, cast

import pytest
from sqlalchemy.engine import URL
from sqlalchemy.ext.asyncio import AsyncEngine

import app.core.database.postgresql as postgresql_module
from app.core.database.postgresql import DATABASE_TIMEZONE, AsyncPgSql
from app.models.base_model import BaseModel
from app.schemas.base_schema import BaseSchema


class TimestampSchema(BaseSchema):
    """用于验证公共业务时间输出格式。"""

    occurred_at: datetime


class EventSchema(BaseSchema):
    """用于验证嵌套响应模型沿用公共时间格式。"""

    event: TimestampSchema


def test_orm_timestamp_columns_use_naive_database_time() -> None:
    """ORM 公共时间列应使用数据库生成的无时区北京时间。"""
    created_at_column = BaseModel.created_at.column
    updated_at_column = BaseModel.updated_at.column

    assert created_at_column.type.timezone is False
    assert updated_at_column.type.timezone is False
    assert created_at_column.default is not None
    assert created_at_column.default.is_clause_element is True
    assert created_at_column.server_default is not None
    assert updated_at_column.default is not None
    assert updated_at_column.default.is_clause_element is True
    assert updated_at_column.server_default is not None
    assert updated_at_column.onupdate is not None
    assert updated_at_column.onupdate.is_clause_element is True


def test_database_connections_use_beijing_timezone(monkeypatch: pytest.MonkeyPatch) -> None:
    """asyncpg 连接应固定 PostgreSQL 会话为北京时间。"""
    captured_options: dict[str, Any] = {}

    def fake_create_async_engine(_url: URL, **options: Any) -> AsyncEngine:
        captured_options.update(options)
        return cast(AsyncEngine, object())

    monkeypatch.setattr(postgresql_module, "create_async_engine", fake_create_async_engine)
    AsyncPgSql(
        host="localhost",
        port=5432,
        user="postgres",
        password="test-password",
        database="postgres",
        pool_size=5,
        max_overflow=10,
        pool_recycle=300,
        pool_timeout=30,
        command_timeout=60,
        connect_timeout=30,
    )

    connect_args = cast(dict[str, Any], captured_options["connect_args"])
    assert DATABASE_TIMEZONE == "Asia/Shanghai"
    assert connect_args["server_settings"] == {"timezone": "Asia/Shanghai"}


def test_schema_formats_business_datetime() -> None:
    """明确声明的日期时间字段应输出北京时间字符串并省略微秒。"""
    source_time = datetime(2026, 7, 16, 8, 30, 45, 123000)
    schema = TimestampSchema(occurred_at=source_time)

    assert schema.occurred_at == source_time
    assert json.loads(schema.model_dump_json()) == {"occurred_at": "2026-07-16 08:30:45"}


def test_nested_schema_keeps_business_datetime_format() -> None:
    """嵌套的明确响应模型也应沿用公共时间格式。"""
    schema = EventSchema(event=TimestampSchema(occurred_at=datetime(2026, 7, 16, 8, 30)))

    assert json.loads(schema.model_dump_json()) == {"event": {"occurred_at": "2026-07-16 08:30:00"}}
