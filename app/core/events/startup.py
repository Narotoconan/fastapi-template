from app.core.cache import init_cache
from app.core.database import db_first_connection


async def startup() -> None:
    """检查数据库与 Redis 依赖，确认应用具备对外服务条件。"""
    await db_first_connection()
    await init_cache()


__all__ = ["startup"]
