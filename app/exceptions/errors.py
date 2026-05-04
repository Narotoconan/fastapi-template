"""
业务错误码枚举 & 自定义异常

错误码规范:
    0       : 成功
    -1      : 通用失败
    1xxx    : 认证/授权相关（前端需跳转登录或显示无权限）
    2xxx    : 参数校验相关（前端需提示用户修正输入）
    3xxx    : 资源相关（前端需提示资源状态）
    4xxx    : 第三方服务相关（前端提示稍后重试）
    5xxx    : 系统内部错误（前端提示服务器繁忙）

设计原则: 错误码的粒度以「前端是否需要差异化处理」为准，
         服务端内部的 DB/Cache/Timeout 等细节通过日志区分，不透传给前端。
"""

from enum import IntEnum


class ErrorCode(IntEnum):
    """业务错误码"""

    # 通用
    SUCCESS = 0
    FAIL = 99999  # 通用失败兜底（无法归类到具体分段时使用）

    # 认证/授权 1xxx
    UNAUTHORIZED = 1001  # 未登录或 Token 失效 → 前端跳转登录页
    FORBIDDEN = 1002  # 已登录但无权限 → 前端显示无权限提示

    # 参数校验 2xxx
    PARAMS_INVALID = 2001  # 参数不合法 → 前端表单错误提示

    # 资源 3xxx
    NOT_FOUND = 3001  # 资源不存在 → 前端显示 404
    ALREADY_EXISTS = 3002  # 资源已存在 → 前端提示"已存在"（注册、创建场景）

    # 第三方服务 4xxx
    THIRD_PARTY_ERROR = 4001  # 第三方调用失败（含超时）→ 前端提示稍后重试

    # 系统 5xxx
    INTERNAL_ERROR = 5001  # 系统内部错误（含 DB/Cache）→ 前端提示服务器繁忙


# 错误码 -> 默认消息映射
_ERROR_MESSAGES: dict[int, str] = {
    ErrorCode.SUCCESS: "success",
    ErrorCode.FAIL: "操作失败，请稍后重试",
    ErrorCode.UNAUTHORIZED: "未登录或登录已过期",
    ErrorCode.FORBIDDEN: "权限不足",
    ErrorCode.PARAMS_INVALID: "参数校验失败",
    ErrorCode.NOT_FOUND: "资源不存在",
    ErrorCode.ALREADY_EXISTS: "资源已存在",
    ErrorCode.THIRD_PARTY_ERROR: "第三方服务异常，请稍后重试",
    ErrorCode.INTERNAL_ERROR: "系统内部错误，请稍后重试",
}


def get_error_message(code: int) -> str:
    """根据错误码获取默认消息"""
    return _ERROR_MESSAGES.get(code, "未知错误")


class BizException(Exception):
    """
    业务异常基类

    用法:
        raise BizException(ErrorCode.NOT_FOUND)
        raise BizException(ErrorCode.PARAMS_INVALID, message="邮箱格式不正确")
        raise BizException(ErrorCode.FAIL, message="自定义错误", http_status=400)
    """

    def __init__(
        self,
        code: int | ErrorCode = ErrorCode.FAIL,
        *,
        message: str | None = None,
        http_status: int = 200,
        result: dict | None = None,
    ):
        self.code = int(code)
        self.message = message or get_error_message(self.code)
        self.http_status = http_status
        self.result = result or {}
        super().__init__(self.message)


class AuthException(BizException):
    """认证/授权异常"""

    def __init__(
        self,
        code: int | ErrorCode = ErrorCode.UNAUTHORIZED,
        *,
        message: str | None = None,
    ):
        super().__init__(code, message=message, http_status=401)


class ForbiddenException(BizException):
    """权限不足异常"""

    def __init__(self, *, message: str | None = None):
        super().__init__(ErrorCode.FORBIDDEN, message=message, http_status=403)


class NotFoundException(BizException):
    """资源不存在异常"""

    def __init__(self, *, message: str | None = None):
        super().__init__(ErrorCode.NOT_FOUND, message=message, http_status=404)


class ParamsException(BizException):
    """参数校验异常"""

    def __init__(self, *, message: str | None = None):
        super().__init__(ErrorCode.PARAMS_INVALID, message=message, http_status=422)


__all__ = [
    "AuthException",
    "BizException",
    "ErrorCode",
    "ForbiddenException",
    "NotFoundException",
    "ParamsException",
    "get_error_message",
]
