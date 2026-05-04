"""
CORS 跨域中间件

使用 FastAPI 内置的 CORSMiddleware，统一处理浏览器跨域预检（OPTIONS）请求。
配置项位于 config/middleware_config.py 的 CORSSettings，可通过环境变量覆盖。
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.log import log
from config.settings import get_settings


def register_cors_middleware(app: FastAPI) -> None:
    """
    注册 CORS 跨域中间件。

    CORS 中间件应位于最外层，确保所有请求（包括预检 OPTIONS）
    在进入鉴权等内层逻辑之前就获得正确的跨域响应头。
    """
    cors = get_settings().cors

    app.add_middleware(
        CORSMiddleware,  # type: ignore[arg-type]
        allow_origins=cors.CORS_ALLOW_ORIGINS,
        allow_credentials=cors.CORS_ALLOW_CREDENTIALS,
        allow_methods=cors.CORS_ALLOW_METHODS,
        allow_headers=cors.CORS_ALLOW_HEADERS,
    )
    log.info(
        "🧩 CORS 中间件已注册 | allow_origins={} allow_credentials={}",
        cors.CORS_ALLOW_ORIGINS,
        cors.CORS_ALLOW_CREDENTIALS,
    )


__all__ = ["register_cors_middleware"]

