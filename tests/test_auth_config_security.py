from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import jwt
import pytest
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.testclient import TestClient
from pydantic import ValidationError

import app.exceptions.handlers as handlers_module
import app.middlewares.cors as cors_module
import app.middlewares.jwt_auth as jwt_auth_module
from app.exceptions import ErrorCode, register_exception_handlers
from app.middlewares import register_middlewares
from app.middlewares.jwt_auth import JWTAuthMiddleware
from config.database_config import DatabaseSettings
from config.middleware_config import JWTSettings
from config.settings import Settings

_JWT_SECRET = "test-jwt-secret-key-with-32-characters"


def _create_jwt_app(monkeypatch: pytest.MonkeyPatch, public_paths: list[str]) -> FastAPI:
    """创建使用指定 JWT 配置的隔离测试应用。"""
    jwt_settings = JWTSettings(JWT_SECRET_KEY=_JWT_SECRET, JWT_PUBLIC_PATHS=public_paths)
    monkeypatch.setattr(jwt_auth_module, "get_settings", lambda: SimpleNamespace(jwt=jwt_settings))
    monkeypatch.setattr(jwt_auth_module.log, "warning", lambda _message: None)

    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    app.add_middleware(JWTAuthMiddleware)

    @app.get("/{requested_path:path}")
    async def echo_request_state(request: Request, requested_path: str) -> dict[str, object]:
        """返回鉴权中间件写入的请求状态。"""
        return {
            "path": requested_path,
            "user_id": getattr(request.state, "user_id", None),
        }

    return app


def test_settings_ignores_bare_environment_name_collisions(monkeypatch: pytest.MonkeyPatch) -> None:
    """顶层聚合配置不应把常见裸环境变量解析为嵌套 JSON。"""
    for variable_name in ("APP", "LOGGER", "DATABASE", "CACHE", "CORS", "GZIP", "JWT", "RATE_LIMIT"):
        monkeypatch.setenv(variable_name, "not-json")

    monkeypatch.setenv("DB_PASSWORD", "test-database-password")
    monkeypatch.setenv("JWT_SECRET_KEY", _JWT_SECRET)
    monkeypatch.setenv("DB_HOST", "database.internal")
    monkeypatch.setenv("REDIS_HOST", "redis.internal")

    settings = Settings()

    assert settings.database.DB_HOST == "database.internal"
    assert settings.cache.REDIS_HOST == "redis.internal"
    assert settings.jwt.JWT_SECRET_KEY == _JWT_SECRET


def test_default_middleware_registration_does_not_enable_jwt(monkeypatch: pytest.MonkeyPatch) -> None:
    """默认中间件注册应保留 CORS/GZip，并继续显式关闭 JWT。"""
    monkeypatch.setattr(cors_module.log, "info", lambda *_args, **_kwargs: None)
    app = FastAPI()

    register_middlewares(app)

    middleware_classes = {middleware.cls for middleware in app.user_middleware}
    assert GZipMiddleware in middleware_classes
    assert JWTAuthMiddleware not in middleware_classes
    assert CORSMiddleware not in middleware_classes
    assert app.middleware_stack is None
    assert isinstance(app.build_middleware_stack(), CORSMiddleware)


def test_sensitive_settings_hide_invalid_inputs() -> None:
    """配置校验异常文本不得包含数据库密码或 JWT 密钥原值。"""
    invalid_database_password = "db!"
    with pytest.raises(ValidationError) as database_error:
        DatabaseSettings(DB_PASSWORD=invalid_database_password)

    invalid_jwt_secret = "short-sensitive-jwt-key"
    with pytest.raises(ValidationError) as jwt_error:
        JWTSettings(JWT_SECRET_KEY=invalid_jwt_secret)

    assert invalid_database_password not in str(database_error.value)
    assert invalid_jwt_secret not in str(jwt_error.value)


@pytest.mark.parametrize("public_paths", [[""], ["   "], ["/"], [" / "], ["//"], [" /// "]])
def test_jwt_public_paths_reject_blank_and_root(public_paths: list[str]) -> None:
    """公开路径不得配置为空白或根路径，避免意外放行全站。"""
    with pytest.raises(ValidationError, match="JWT 公开路径不能为空或根路径"):
        JWTSettings(JWT_SECRET_KEY=_JWT_SECRET, JWT_PUBLIC_PATHS=public_paths)


def test_jwt_public_path_uses_path_segment_boundary(monkeypatch: pytest.MonkeyPatch) -> None:
    """公开路径仅放行自身及其路径段子路径，不放行相似前缀。"""
    app = _create_jwt_app(monkeypatch, [" /docs/ "])

    with TestClient(app) as client:
        assert client.get("/docs").status_code == 200
        assert client.get("/docs/oauth2-redirect").status_code == 200
        assert client.get("/docs-private").status_code == 401
        assert client.get("/doc").status_code == 401


def test_jwt_requires_expiration_and_non_empty_subject(monkeypatch: pytest.MonkeyPatch) -> None:
    """Token 必须同时包含有效期和非空字符串用户标识。"""
    app = _create_jwt_app(monkeypatch, [])
    expires_at = datetime.now(UTC) + timedelta(minutes=5)
    invalid_payloads: list[dict[str, object]] = [
        {"sub": "user-1"},
        {"exp": expires_at},
        {"sub": "", "exp": expires_at},
        {"sub": "   ", "exp": expires_at},
        {"sub": 1, "exp": expires_at},
        {"sub": "user-1", "exp": {}},
        {"sub": "user-1", "exp": []},
    ]

    with TestClient(app) as client:
        for payload in invalid_payloads:
            token = jwt.encode(payload, _JWT_SECRET, algorithm="HS256")
            response = client.get("/protected", headers={"Authorization": f"Bearer {token}"})
            assert response.status_code == 401

        valid_token = jwt.encode({"sub": "user-1", "exp": expires_at}, _JWT_SECRET, algorithm="HS256")
        response = client.get("/protected", headers={"Authorization": f"Bearer {valid_token}"})

    assert response.status_code == 200
    assert response.json()["user_id"] == "user-1"


def test_server_exceptions_hide_details_and_raw_error_logs(monkeypatch: pytest.MonkeyPatch) -> None:
    """服务端异常响应和日志不得包含原始异常文本。"""
    sensitive_http_detail = "database-password=do-not-expose"
    sensitive_runtime_detail = "JWT_SECRET_KEY=do-not-expose"
    error_logs: list[str] = []
    monkeypatch.setattr(handlers_module.log, "error", error_logs.append)

    app = FastAPI()
    register_exception_handlers(app)

    @app.get("/http-500")
    async def raise_http_500() -> None:
        """触发框架服务端异常。"""
        raise HTTPException(status_code=500, detail=sensitive_http_detail)

    @app.get("/unhandled")
    async def raise_unhandled_exception() -> None:
        """触发未处理异常。"""
        raise RuntimeError(sensitive_runtime_detail)

    with TestClient(app, raise_server_exceptions=False) as client:
        http_response = client.get("/http-500")
        unhandled_response = client.get("/unhandled")

    assert http_response.status_code == 500
    assert http_response.json()["code"] == ErrorCode.INTERNAL_ERROR
    assert http_response.json()["message"] == "系统内部错误，请稍后重试"
    assert sensitive_http_detail not in http_response.text
    assert unhandled_response.status_code == 500
    assert unhandled_response.json()["message"] == "系统内部错误，请稍后重试"
    assert sensitive_runtime_detail not in unhandled_response.text
    assert sensitive_http_detail not in " ".join(error_logs)
    assert sensitive_runtime_detail not in " ".join(error_logs)


def test_client_http_exception_keeps_safe_detail(monkeypatch: pytest.MonkeyPatch) -> None:
    """客户端错误继续返回既有安全 detail，避免破坏公开响应契约。"""
    warning_logs: list[str] = []
    monkeypatch.setattr(handlers_module.log, "warning", warning_logs.append)

    app = FastAPI()
    register_exception_handlers(app)

    @app.get("/missing")
    async def raise_not_found() -> None:
        """触发客户端资源不存在异常。"""
        raise HTTPException(status_code=404, detail="资源不存在")

    with TestClient(app) as client:
        response = client.get("/missing")

    assert response.status_code == 404
    assert response.json()["message"] == "资源不存在"
    assert all("资源不存在" not in log_message for log_message in warning_logs)
