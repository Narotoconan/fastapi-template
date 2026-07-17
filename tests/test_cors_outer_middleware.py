from collections.abc import Awaitable, Callable
from types import SimpleNamespace

import pytest
from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient

import app.exceptions.handlers as handlers_module
import app.middlewares.cors as cors_module
import app.middlewares.gzip as gzip_module
from app.exceptions import ErrorCode, register_exception_handlers
from app.middlewares import register_middlewares
from config.middleware_config import CORSSettings, GZipSettings

_ALLOWED_ORIGIN = "https://client.example.com"


@pytest.fixture
def cors_app(monkeypatch: pytest.MonkeyPatch) -> FastAPI:
    """创建仅含测试路由且由单层全局 CORS 包裹的应用。"""
    cors_settings = CORSSettings(
        CORS_ALLOW_ORIGINS=[_ALLOWED_ORIGIN],
        CORS_ALLOW_METHODS=["GET"],
        CORS_ALLOW_HEADERS=["X-Request-ID"],
    )
    gzip_settings = GZipSettings()
    monkeypatch.setattr(cors_module, "get_settings", lambda: SimpleNamespace(cors=cors_settings))
    monkeypatch.setattr(gzip_module, "get_settings", lambda: SimpleNamespace(gzip=gzip_settings))
    monkeypatch.setattr(cors_module.log, "info", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(handlers_module.log, "error", lambda *_args, **_kwargs: None)

    app = FastAPI()
    register_exception_handlers(app)
    register_middlewares(app)

    @app.middleware("http")
    async def late_middleware(
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        """验证 CORS 注册不会提前冻结后续用户中间件。"""
        response = await call_next(request)
        response.headers["X-Late-Middleware"] = "enabled"
        return response

    class LateError(Exception):
        """验证 CORS 注册后新增异常处理器仍会进入内部栈。"""

    @app.exception_handler(LateError)
    async def late_error_handler(_request: Request, _exc: LateError) -> JSONResponse:
        return JSONResponse(status_code=418, content={"handled": True})

    @app.get("/ok")
    async def ok_endpoint() -> dict[str, str]:
        """返回正常响应。"""
        return {"status": "ok"}

    @app.get("/unhandled")
    async def unhandled_endpoint() -> None:
        """触发由 ServerErrorMiddleware 处理的未捕获异常。"""
        raise RuntimeError("sensitive internal detail")

    @app.get("/late-error")
    async def late_error_endpoint() -> None:
        """触发在 CORS 注册后新增的异常处理器。"""
        raise LateError

    return app


def test_cors_wraps_normal_response_once(cors_app: FastAPI) -> None:
    """外层 CORS 建好后注册的正常路由应带单个来源头，app 仍为 FastAPI。"""
    assert isinstance(cors_app, FastAPI)
    assert cors_app.middleware_stack is None
    assert all(middleware.cls is not CORSMiddleware for middleware in cors_app.user_middleware)

    response = TestClient(cors_app).get("/ok", headers={"Origin": _ALLOWED_ORIGIN})

    assert isinstance(cors_app.middleware_stack, CORSMiddleware)
    assert response.status_code == 200
    assert response.headers.get_list("Access-Control-Allow-Origin") == [_ALLOWED_ORIGIN]
    assert response.headers["X-Late-Middleware"] == "enabled"


def test_cors_handles_preflight_request(cors_app: FastAPI) -> None:
    """最外层 CORS 应直接处理合法的浏览器预检请求。"""
    response = TestClient(cors_app).options(
        "/ok",
        headers={
            "Origin": _ALLOWED_ORIGIN,
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "X-Request-ID",
        },
    )

    assert response.status_code == 200
    assert response.headers.get_list("Access-Control-Allow-Origin") == [_ALLOWED_ORIGIN]
    assert "GET" in response.headers["Access-Control-Allow-Methods"]


def test_cors_wraps_unhandled_server_error(cors_app: FastAPI) -> None:
    """ServerErrorMiddleware 生成的统一 500 响应也必须带 CORS 头。"""
    response = TestClient(cors_app, raise_server_exceptions=False).get(
        "/unhandled",
        headers={"Origin": _ALLOWED_ORIGIN},
    )

    assert response.status_code == 500
    assert response.headers.get_list("Access-Control-Allow-Origin") == [_ALLOWED_ORIGIN]
    assert response.json() == {
        "code": ErrorCode.INTERNAL_ERROR,
        "message": "系统内部错误，请稍后重试",
        "result": {},
    }
    assert "sensitive internal detail" not in response.text


def test_cors_registration_keeps_late_exception_handlers_effective(cors_app: FastAPI) -> None:
    """首次请求前后注册的异常处理器都必须进入被 CORS 包裹的内部栈。"""
    response = TestClient(cors_app, raise_server_exceptions=False).get(
        "/late-error",
        headers={"Origin": _ALLOWED_ORIGIN},
    )

    assert response.status_code == 418
    assert response.json() == {"handled": True}
    assert response.headers.get_list("Access-Control-Allow-Origin") == [_ALLOWED_ORIGIN]
    assert response.headers["X-Late-Middleware"] == "enabled"
