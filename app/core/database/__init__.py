from app.core.log import log
from config.settings import get_settings

from .postgresql import AsyncPgSql

settings = get_settings()

_pgsql = AsyncPgSql(
    host=settings.database.DB_HOST,
    port=settings.database.DB_PORT,
    user=settings.database.DB_USER,
    password=settings.database.DB_PASSWORD,
    database=settings.database.DB_DATABASE,
)

AsyncSessionLocal = _pgsql.AsyncSessionLocal
Base = _pgsql.Base


async def db_first_connection() -> None:
    from sqlalchemy import text
    """记录数据库启动日志。

    注意：此函数仅做日志输出，不发送实际查询验证连接可用性。
    真正的连接在首次执行 SQL 时由 SQLAlchemy 连接池建立。
    """
    session = AsyncSessionLocal()
    await session.execute(text("SELECT 1"))
    await session.close()
    await AsyncSessionLocal.remove()
    log.info("✅ 数据库 连接成功")


async def db_disconnect():
    await _pgsql.disconnect()
    log.info("✅ 数据库 已断开连接")


__all__ = ["AsyncSessionLocal", "Base", "db_disconnect", "db_first_connection"]
