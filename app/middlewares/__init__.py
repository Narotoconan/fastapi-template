"""
中间件注册入口

当前默认仅注册 CORS 与 GZip，JWT 实现已提供但默认未启用。
CORS 包裹完整 FastAPI 栈；启用 JWT 后，请求顺序为：CORS → GZip → JWT。
其余用户中间件仍遵循 add_middleware 后注册先执行的栈规则。
"""

from fastapi import FastAPI

from app.middlewares.cors import register_cors_middleware
from app.middlewares.gzip import register_gzip_middleware

# from app.middlewares.jwt_auth import register_jwt_middleware


def register_middlewares(app: FastAPI) -> None:
    """
    一键注册所有中间件。

    当前默认请求处理顺序：CORS → GZip → 路由处理器。
    如需启用 JWT，应显式导入并恢复下方注册调用。CORS 必须最后调用，
    它会延迟包裹应用启动前完成注册的异常处理器和用户中间件，确保兜底 500 响应也带跨域头；
    路由、中间件和异常处理器仍可在应用启动前继续注册。
    """
    # register_jwt_middleware(app)   # 最内层：JWT 鉴权
    register_gzip_middleware(app)  # 用户中间层：GZip 压缩
    register_cors_middleware(app)  # 完整应用栈最外层：CORS 跨域


__all__ = ["register_middlewares"]
