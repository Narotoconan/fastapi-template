"""
全局异常处理器
注册到 FastAPI app 后，所有异常会被统一拦截并转换为标准 JSON 响应格式。
"""

from typing import cast

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.log import log
from app.exceptions.errors import BizException, ErrorCode
from app.exceptions.validation_i18n import translate_validation_error


def build_error_response(
    *,
    http_status: int,
    code: int,
    message: str,
    result: dict | None = None,
) -> JSONResponse:
    """
    构建统一错误 JSON 响应。

    供异常处理器与中间件共享使用，确保全链路错误响应格式一致。
    注意：中间件层无法直接抛出 BizException 等业务异常来触发 ExceptionMiddleware，
    因此需要主动调用本函数构造响应并返回。
    """
    return JSONResponse(
        status_code=http_status,
        content={
            "code": code,
            "message": message,
            "result": result or {},
        },
    )


# ==================== 异常处理函数 ====================


async def biz_exception_handler(_request: Request, exc: Exception) -> JSONResponse:
    """业务异常处理"""
    _exc = cast(BizException, exc)
    log.warning(
        "BizException | code={} message={} path={}",
        _exc.code,
        _exc.message,
        _request.url.path,
    )
    return build_error_response(
        http_status=_exc.http_status,
        code=_exc.code,
        message=_exc.message,
        result=_exc.result,
    )


async def validation_exception_handler(_request: Request, exc: Exception) -> JSONResponse:
    """
    Pydantic / FastAPI 参数校验异常处理

    取第一条校验错误翻译为中文消息写入 message，result 返回空对象。
    多条错误时仅展示第一条，避免信息过载；完整错误列表通过日志记录。
    """
    _exc = cast(RequestValidationError, exc)
    # 过滤 Pydantic v2 默认注入的官方文档链接字段，减少日志噪音
    # 不使用 include_url=False，因为 FastAPI RequestValidationError.errors() 不支持该参数
    errors = [{k: v for k, v in e.items() if k != "url"} for e in _exc.errors()]
    first = errors[0] if errors else {}
    message = translate_validation_error(first) if first else "参数校验失败，请检查输入内容"

    log.warning("ValidationError | path={} | {}", _request.url.path, message)
    return build_error_response(
        http_status=status.HTTP_422_UNPROCESSABLE_ENTITY,
        code=ErrorCode.PARAMS_INVALID,
        message=message,
    )


async def http_exception_handler(_request: Request, exc: Exception) -> JSONResponse:
    """
    Starlette / FastAPI HTTPException 处理
    将框架原生的 HTTP 异常也转换为统一格式
    """
    _exc = cast(StarletteHTTPException, exc)
    # 映射常见 HTTP 状态码到业务错误码
    _STATUS_CODE_MAP: dict[int, int] = {
        401: ErrorCode.UNAUTHORIZED,
        403: ErrorCode.FORBIDDEN,
        404: ErrorCode.NOT_FOUND,
        405: ErrorCode.PARAMS_INVALID,
        422: ErrorCode.PARAMS_INVALID,
        429: ErrorCode.FAIL,
    }
    code = _STATUS_CODE_MAP.get(_exc.status_code, ErrorCode.FAIL)

    log.warning(
        "HTTPException | status={} detail={} path={}",
        _exc.status_code,
        _exc.detail,
        _request.url.path,
    )
    return build_error_response(
        http_status=_exc.status_code,
        code=code,
        message=str(_exc.detail) if _exc.detail else "请求失败",
    )


async def unhandled_exception_handler(_request: Request, exc: Exception) -> JSONResponse:
    """
    兜底: 未被捕获的异常
    生产环境隐藏堆栈，仅记录日志
    """
    log.exception(
        "UnhandledException | path={} error={}",
        _request.url.path,
        str(exc),
    )
    return build_error_response(
        http_status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        code=ErrorCode.INTERNAL_ERROR,
        message="系统内部错误，请稍后重试",
    )


# ==================== 注册入口 ====================


def register_exception_handlers(app: FastAPI) -> None:
    """一键注册所有异常处理器"""
    app.add_exception_handler(BizException, biz_exception_handler)
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)
    app.add_exception_handler(Exception, unhandled_exception_handler)


__all__ = ["build_error_response", "register_exception_handlers"]
