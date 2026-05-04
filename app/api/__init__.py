from fastapi import APIRouter, FastAPI

from app.api.demo import router_demo


def register_router(app: FastAPI):
    router = APIRouter()
    router.include_router(router_demo)

    app.include_router(router)


__all__ = ["register_router"]
