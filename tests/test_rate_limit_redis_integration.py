import asyncio
import os
from collections.abc import Awaitable
from typing import cast
from uuid import uuid4

import pytest
from limits import parse
from limits.aio.strategies import FixedWindowRateLimiter
from redis.asyncio import BlockingConnectionPool, Redis

from app.core.rate_limit.rate_limiter import _create_rate_limit_storage

_TEST_REDIS_URL = os.getenv("TEST_REDIS_URL")


@pytest.mark.skipif(
    _TEST_REDIS_URL is None,
    reason="仅在显式提供 TEST_REDIS_URL 时运行真实 Redis 冒烟测试",
)
def test_two_async_redis_limiters_share_atomic_counter() -> None:
    """两个独立连接池应共享原子计数，并只清理本测试创建的唯一键。"""
    redis_url = cast(str, _TEST_REDIS_URL)

    async def run_case() -> None:
        pool_one = BlockingConnectionPool.from_url(
            redis_url,
            max_connections=2,
            timeout=1.0,
            socket_connect_timeout=1.0,
            socket_timeout=1.0,
            decode_responses=True,
        )
        pool_two = BlockingConnectionPool.from_url(
            redis_url,
            max_connections=2,
            timeout=1.0,
            socket_connect_timeout=1.0,
            socket_timeout=1.0,
            decode_responses=True,
        )
        storage_one = _create_rate_limit_storage(pool_one)
        storage_two = _create_rate_limit_storage(pool_two)
        limiter_one = FixedWindowRateLimiter(storage_one)
        limiter_two = FixedWindowRateLimiter(storage_two)
        inspector = Redis(connection_pool=pool_one)
        rate_limit_item = parse("3/minute")
        identifiers = (
            f"rate-limit-smoke:{uuid4().hex}",
            "192.0.2.10",
            "tests.real_redis_endpoint",
        )
        redis_key = f"LIMITS:{rate_limit_item.key_for(*identifiers)}"

        try:
            attempts = [
                (limiter_one if index % 2 == 0 else limiter_two).hit(
                    rate_limit_item,
                    *identifiers,
                )
                for index in range(8)
            ]
            allowed_results = await asyncio.gather(*attempts)
            stored_count = await cast(Awaitable[str | None], inspector.get(redis_key))
            remaining_ttl = await inspector.ttl(redis_key)

            assert sum(allowed_results) == 3
            assert stored_count is not None
            assert int(stored_count) == 8
            assert 0 < remaining_ttl <= rate_limit_item.get_expiry()
        finally:
            try:
                await inspector.delete(redis_key)
            finally:
                await inspector.aclose()
                await asyncio.gather(pool_one.aclose(), pool_two.aclose())

    asyncio.run(run_case())
