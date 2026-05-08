from app.core.cache import init_cache
from app.core.database import db_first_connection


async def startup():
    await db_first_connection()
    await init_cache()


__all__ = ["startup"]
