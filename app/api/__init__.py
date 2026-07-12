from fastapi import APIRouter, FastAPI

from app.api.demo import router_demo
from app.api.health import router_health


def register_router(app: FastAPI) -> None:
    router = APIRouter()
    router.include_router(router_health)
    router.include_router(router_demo)

    app.include_router(router)


__all__ = ["register_router"]
