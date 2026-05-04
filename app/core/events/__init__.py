from contextlib import asynccontextmanager

from fastapi import FastAPI

from .shutdown import shutdown
from .startup import startup


@asynccontextmanager
async def lifespan(app: FastAPI):
    await startup()
    yield
    await shutdown()


__all__ = ["lifespan"]
