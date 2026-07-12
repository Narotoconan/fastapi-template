from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from .shutdown import shutdown
from .startup import startup


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    """管理应用生命周期，并确保退出时释放数据库和缓存资源。"""
    await startup()
    try:
        yield
    finally:
        await shutdown()


__all__ = ["lifespan"]
