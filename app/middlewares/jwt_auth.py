"""
JWT 鉴权中间件

对每个请求自动进行 JWT Token 验证，通过后将解析出的 payload 挂载到
request.state，下层路由和依赖项可直接读取。

公开路径（无需鉴权）通过 JWTSettings.JWT_PUBLIC_PATHS 配置，采用前缀匹配。

响应格式统一由 app.exceptions.handlers.build_error_response 构建，
与全局异常处理器共享同一套结构，确保错误输出一致。
"""

from collections.abc import Callable

import jwt
from fastapi import FastAPI
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp

from app.core.log import log
from app.exceptions import build_error_response
from app.exceptions.errors import ErrorCode
from config.settings import get_settings


class JWTAuthMiddleware(BaseHTTPMiddleware):
    """
    JWT 鉴权中间件。

    请求处理流程：
        1. 判断请求路径是否在公开路径列表中，若是则跳过鉴权直接放行。
        2. 从请求头 Authorization 中提取 Token。
        3. 使用配置的密钥和算法对 Token 进行解码验证。
        4. 验证通过后，将 payload 挂载至 request.state.jwt_payload，
           sub 字段挂载至 request.state.user_id。
        5. 验证失败则通过 build_error_response 返回统一格式的 401 响应。

    注意：中间件层无法抛出 BizException/AuthException 触发业务异常处理器，
    因为 ExceptionMiddleware（业务异常处理器所在层）位于用户中间件的内层，
    中间件抛出的异常只会向外传播至 ServerErrorMiddleware，最终返回 500。
    因此鉴权失败时必须主动构造响应并 return，不能依赖异常机制。
    """

    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)
        self._jwt_settings = get_settings().jwt

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """中间件核心处理逻辑"""
        # 公开路径跳过鉴权
        if self._is_public_path(request.url.path):
            return await call_next(request)

        # 提取 Bearer Token
        token = self._extract_bearer_token(request)
        if token is None:
            client = request.client.host if request.client else "unknown"
            log.warning(f"JWT 鉴权失败: 缺少 Token | path={request.url.path} client={client}")
            return build_error_response(
                http_status=401,
                code=ErrorCode.UNAUTHORIZED,
                message="缺少认证 Token，请在请求头携带 Authorization: Bearer <token>",
            )

        # 解码并验证 Token
        try:
            payload: dict = jwt.decode(
                token,
                self._jwt_settings.JWT_SECRET_KEY,
                algorithms=[self._jwt_settings.JWT_ALGORITHM],
            )
        except jwt.ExpiredSignatureError:
            log.warning(f"JWT 鉴权失败: Token 已过期 | path={request.url.path}")
            return build_error_response(
                http_status=401,
                code=ErrorCode.UNAUTHORIZED,
                message="Token 已过期，请重新登录",
            )
        except jwt.InvalidTokenError as exc:
            log.warning(f"JWT 鉴权失败: Token 无效 | path={request.url.path} error={exc}")
            return build_error_response(
                http_status=401,
                code=ErrorCode.UNAUTHORIZED,
                message="Token 无效，请重新登录",
            )

        # 将解析结果挂载到 request.state，供下层依赖项使用
        request.state.jwt_payload = payload
        request.state.user_id = payload.get("sub")

        return await call_next(request)

    def _is_public_path(self, path: str) -> bool:
        """
        判断请求路径是否属于公开路径（前缀匹配）。

        示例: /docs/oauth2-redirect 会匹配公开路径 /docs。
        """
        return any(path.startswith(public) for public in self._jwt_settings.JWT_PUBLIC_PATHS)

    @staticmethod
    def _extract_bearer_token(request: Request) -> str | None:
        """
        从 Authorization 请求头中提取 Bearer Token。

        返回 Token 字符串；若请求头不存在或格式不符则返回 None。
        """
        authorization: str = request.headers.get("Authorization", "")
        if not authorization.startswith("Bearer "):
            return None
        return authorization[len("Bearer "):]


def register_jwt_middleware(app: FastAPI) -> None:
    """
    注册 JWT 鉴权中间件。

    JWT 中间件应位于最内层（紧邻路由），确保 CORS 预检请求、GZip 压缩
    等外层逻辑不受鉴权影响。
    """
    jwt_settings = get_settings().jwt
    app.add_middleware(JWTAuthMiddleware)
    log.info(f"🧩 JWT 鉴权中间件已注册 | algorithm={jwt_settings.JWT_ALGORITHM} public_paths={jwt_settings.JWT_PUBLIC_PATHS}")


__all__ = ["JWTAuthMiddleware", "register_jwt_middleware"]

