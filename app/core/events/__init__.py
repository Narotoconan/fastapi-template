from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.core.log import log
from config.settings import get_settings

from .shutdown import shutdown
from .startup import startup


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    """管理应用生命周期，并确保退出时释放数据库和缓存资源。"""
    await startup()
    settings = get_settings()
    log.info(f"✅ 应用启动完成 | name={settings.app.APP_NAME} | version={settings.app.APP_VERSION}")
    try:
        yield
    finally:
        await shutdown()


__all__ = ["lifespan"]
