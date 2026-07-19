from app.core.cache import init_cache
from app.core.database import db_first_connection
from app.core.rate_limit import init_rate_limiter


async def startup() -> None:
    """检查数据库、缓存与限流依赖，确认应用具备对外服务条件。"""
    await db_first_connection()
    await init_cache()
    await init_rate_limiter()


__all__ = ["startup"]
