"""
Cache module - Redis 异步缓存管理
"""

from app.core.cache.decorators import cache
from app.core.cache.prefixes import RedisPrefixes
from app.core.cache.redis import RedisManager, get_redis_manager


async def init_cache() -> None:
    """初始化缓存模块 - 在应用启动时调用"""
    redis_manager = get_redis_manager()
    await redis_manager.connect()


async def close_cache() -> None:
    """关闭缓存模块 - 在应用关闭时调用"""
    redis_manager = get_redis_manager()
    await redis_manager.disconnect()


__all__ = ["RedisManager", "RedisPrefixes", "cache", "close_cache", "get_redis_manager", "init_cache"]
