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


def db_first_connection():
    log.info("✅ 数据库 连接成功")


async def db_disconnect():
    await _pgsql.disconnect()
    log.info("✅ 数据库 已断开连接")


__all__ = ["AsyncSessionLocal", "Base", "db_disconnect", "db_first_connection"]
