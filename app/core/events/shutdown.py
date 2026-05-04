from app.core.cache import close_cache
from app.core.database import db_disconnect


async def shutdown():
    await db_disconnect()
    await close_cache()


__all__ = ["shutdown"]
