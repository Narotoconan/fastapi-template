"""
CORS 跨域中间件

使用 FastAPI 内置的 CORSMiddleware，统一处理浏览器跨域预检（OPTIONS）请求。
配置项位于 config/middleware_config.py 的 CORSSettings，可通过环境变量覆盖。
"""

from types import MethodType
from typing import Any, cast

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.types import ASGIApp

from app.core.log import log
from config.settings import get_settings


def register_cors_middleware(app: FastAPI) -> None:
    """
    将 CORS 注册到完整 FastAPI 中间件栈的最外层。

    Starlette 默认把 ServerErrorMiddleware 放在所有用户中间件外层；若通过
    app.add_middleware() 注册 CORS，未处理异常生成的 500 响应不会再经过 CORS。
    因此这里延迟装饰应用的中间件栈构建函数，在首次 ASGI 调用时才用
    CORSMiddleware 包裹完整内部栈。这样既保持导出的 app 为 FastAPI、保证全链路
    只有一层 CORS，也不会阻止后续在应用启动前注册路由、中间件或异常处理器。
    """
    cors = get_settings().cors

    if app.middleware_stack is not None:
        raise RuntimeError("CORS 必须在应用启动前注册")
    if getattr(app, "_outer_cors_registered", False):
        raise RuntimeError("CORS 最外层中间件不能重复注册")
    if any(middleware.cls is CORSMiddleware for middleware in app.user_middleware):
        raise RuntimeError("检测到重复的 CORS 用户中间件")

    original_stack_builder = app.build_middleware_stack

    def build_outer_cors_stack(_app: FastAPI) -> ASGIApp:
        if any(middleware.cls is CORSMiddleware for middleware in app.user_middleware):
            raise RuntimeError("检测到重复的 CORS 用户中间件")
        return CORSMiddleware(
            original_stack_builder(),
            allow_origins=cors.CORS_ALLOW_ORIGINS,
            allow_credentials=cors.CORS_ALLOW_CREDENTIALS,
            allow_methods=cors.CORS_ALLOW_METHODS,
            allow_headers=cors.CORS_ALLOW_HEADERS,
        )

    mutable_app = cast(Any, app)
    mutable_app.build_middleware_stack = MethodType(build_outer_cors_stack, app)
    mutable_app._outer_cors_registered = True
    log.info(
        f"🧩 CORS 最外层中间件已注册 | allow_origins={cors.CORS_ALLOW_ORIGINS} "
        f"allow_credentials={cors.CORS_ALLOW_CREDENTIALS}"
    )


__all__ = ["register_cors_middleware"]
