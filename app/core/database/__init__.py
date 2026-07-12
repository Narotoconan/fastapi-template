from sqlalchemy import text

from app.core.log import log
from config.settings import get_settings

from .postgresql import AsyncPgSql, Base

settings = get_settings()

_pgsql = AsyncPgSql(
    host=settings.database.DB_HOST,
    port=settings.database.DB_PORT,
    user=settings.database.DB_USER,
    password=settings.database.DB_PASSWORD,
    database=settings.database.DB_DATABASE,
    pool_size=settings.database.DB_POOL_SIZE,
    max_overflow=settings.database.DB_MAX_OVERFLOW,
    pool_recycle=settings.database.DB_POOL_RECYCLE,
    pool_timeout=settings.database.DB_POOL_TIMEOUT,
    command_timeout=settings.database.DB_COMMAND_TIMEOUT,
    connect_timeout=settings.database.DB_CONNECT_TIMEOUT,
)

AsyncSessionLocal = _pgsql.AsyncSessionLocal


async def db_health_check() -> bool:
    """执行轻量查询检查数据库连接是否可用。"""
    session = AsyncSessionLocal()
    try:
        query_result = await session.execute(text("SELECT 1"))
        return query_result.scalar_one() == 1
    finally:
        await session.close()
        await AsyncSessionLocal.remove()


async def db_first_connection() -> None:
    """在应用启动阶段验证数据库连接。"""
    if not await db_health_check():
        raise RuntimeError("数据库健康检查未返回预期结果")
    log.info("✅ 数据库 连接成功")


async def db_disconnect() -> None:
    """关闭数据库连接。"""
    await _pgsql.disconnect()
    log.info("✅ 数据库 已断开连接")


__all__ = ["AsyncSessionLocal", "Base", "db_disconnect", "db_first_connection", "db_health_check"]
