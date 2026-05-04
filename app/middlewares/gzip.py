"""
GZip 压缩中间件

使用 FastAPI 内置的 GZipMiddleware，对客户端支持的响应内容自动进行 GZip 压缩，
减少网络传输体积，提升接口响应速度。
配置项位于 config/middleware_config.py 的 GZipSettings，可通过环境变量覆盖。
"""

from fastapi import FastAPI
from fastapi.middleware.gzip import GZipMiddleware

from app.core.log import log
from config.settings import get_settings


def register_gzip_middleware(app: FastAPI) -> None:
    """
    注册 GZip 压缩中间件。

    仅对响应体大小 >= minimum_size（字节）的响应进行压缩，
    避免对小响应引入不必要的 CPU 开销。
    客户端需在请求头携带 Accept-Encoding: gzip 才会触发压缩。
    """
    gzip = get_settings().gzip

    app.add_middleware(GZipMiddleware, minimum_size=gzip.GZIP_MINIMUM_SIZE) # type: ignore[arg-type]
    log.info(f"🧩 GZip 中间件已注册 | minimum_size={gzip.GZIP_MINIMUM_SIZE} bytes")


__all__ = ["register_gzip_middleware"]

