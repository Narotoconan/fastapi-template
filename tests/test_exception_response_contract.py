import json
from datetime import datetime
from enum import StrEnum
from uuid import UUID

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

import app.exceptions.handlers as handlers_module
from app.exceptions import ErrorCode, build_error_response, register_exception_handlers


class FailureStage(StrEnum):
    """用于验证异常结果中枚举值的 JSON 编码。"""

    DATABASE = "database"


def test_build_error_response_encodes_supported_non_native_json_values() -> None:
    """统一异常响应应编码日期时间、UUID 和枚举等常见业务值。"""
    occurred_at = datetime(2026, 7, 16, 8, 30)
    request_id = UUID("019f660b-0bb6-7c82-9207-ea3d98549289")

    response = build_error_response(
        http_status=503,
        code=ErrorCode.INTERNAL_ERROR,
        message="关键依赖不可用",
        result={
            "occurred_at": occurred_at,
            "request_id": request_id,
            "stage": FailureStage.DATABASE,
        },
    )

    assert json.loads(bytes(response.body)) == {
        "code": ErrorCode.INTERNAL_ERROR,
        "message": "关键依赖不可用",
        "result": {
            "occurred_at": "2026-07-16 08:30:00",
            "request_id": str(request_id),
            "stage": "database",
        },
    }


@pytest.mark.parametrize(("result", "expected_result"), [(None, {}), ({}, {}), ({"items": []}, {"items": []})])
def test_build_error_response_preserves_empty_result_contract(
    result: dict[str, object] | None,
    expected_result: dict[str, object],
) -> None:
    """未提供结果时仍返回空对象，显式空值结构不应被意外替换。"""
    response = build_error_response(
        http_status=400,
        code=ErrorCode.FAIL,
        message="请求失败",
        result=result,
    )

    assert json.loads(bytes(response.body))["result"] == expected_result


def test_http_exception_preserves_protocol_headers(monkeypatch: pytest.MonkeyPatch) -> None:
    """框架 HTTP 异常转换为统一响应后应保留认证等协议头。"""
    monkeypatch.setattr(handlers_module.log, "warning", lambda *_args, **_kwargs: None)
    app = FastAPI()
    register_exception_handlers(app)

    @app.get("/protected")
    async def protected_endpoint() -> None:
        """触发带认证响应头的框架异常。"""
        raise HTTPException(
            status_code=401,
            detail="请先登录",
            headers={"WWW-Authenticate": "Bearer"},
        )

    response = TestClient(app).get("/protected")

    assert response.status_code == 401
    assert response.headers["WWW-Authenticate"] == "Bearer"
    assert response.json() == {
        "code": ErrorCode.UNAUTHORIZED,
        "message": "请先登录",
        "result": {},
    }


def test_server_http_exception_keeps_headers_but_hides_detail(monkeypatch: pytest.MonkeyPatch) -> None:
    """服务端 HTTP 异常可保留重试头，但不得向客户端泄露内部详情。"""
    sensitive_detail = "database-password=do-not-expose"
    monkeypatch.setattr(handlers_module.log, "error", lambda *_args, **_kwargs: None)
    app = FastAPI()
    register_exception_handlers(app)

    @app.get("/unavailable")
    async def unavailable_endpoint() -> None:
        """触发带重试响应头的服务端异常。"""
        raise HTTPException(
            status_code=503,
            detail=sensitive_detail,
            headers={"Retry-After": "60"},
        )

    response = TestClient(app).get("/unavailable")

    assert response.status_code == 503
    assert response.headers["Retry-After"] == "60"
    assert response.json() == {
        "code": ErrorCode.INTERNAL_ERROR,
        "message": "系统内部错误，请稍后重试",
        "result": {},
    }
    assert sensitive_detail not in response.text
