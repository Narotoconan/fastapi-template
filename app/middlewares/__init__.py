"""
中间件注册入口

中间件执行顺序（请求进入时）：CORS → GZip → JWT
FastAPI/Starlette 采用栈结构管理中间件，add_middleware 的调用顺序与实际处理顺序相反：
最后调用 add_middleware 的中间件位于最外层（最先处理请求）。
因此注册顺序为：JWT（最内层）→ GZip → CORS（最外层）。
"""

from fastapi import FastAPI

from app.middlewares.cors import register_cors_middleware
from app.middlewares.gzip import register_gzip_middleware
from app.middlewares.jwt_auth import register_jwt_middleware


def register_middlewares(app: FastAPI) -> None:
    """
    一键注册所有中间件。

    最终请求处理顺序：CORS → GZip → JWT → 路由处理器
    注册调用顺序（与处理顺序相反）：
        1. register_jwt_middleware   —— 最内层，紧邻路由
        2. register_gzip_middleware  —— 中间层，负责响应压缩
        3. register_cors_middleware  —— 最外层，处理跨域预检
    """
    # register_jwt_middleware(app)   # 第三层（最内层）：JWT 鉴权
    register_gzip_middleware(app)  # 第二层：GZip 压缩
    register_cors_middleware(app)  # 第一层（最外层）：CORS 跨域


__all__ = ["register_middlewares"]

