"""
中间件相关配置

包含 CORS、GZip、JWT 三个中间件的可配置项。
所有字段均可通过环境变量覆盖（Pydantic-Settings 自动读取）。
"""

from pydantic_settings import BaseSettings


class CORSSettings(BaseSettings):
    """CORS 跨域中间件配置"""

    # 允许的来源列表，生产环境应替换为具体域名
    CORS_ALLOW_ORIGINS: list[str] = ["*"]
    # 是否允许携带 Cookie/Authorization 等凭据
    CORS_ALLOW_CREDENTIALS: bool = True
    # 允许的 HTTP 方法
    CORS_ALLOW_METHODS: list[str] = ["*"]
    # 允许的请求头
    CORS_ALLOW_HEADERS: list[str] = ["*"]


class GZipSettings(BaseSettings):
    """GZip 压缩中间件配置"""

    # 触发压缩的响应体最小字节数，小于该值的响应不压缩
    GZIP_MINIMUM_SIZE: int = 1000


class JWTSettings(BaseSettings):
    """JWT 鉴权中间件配置"""

    # 签名密钥，生产环境务必通过环境变量 JWT_SECRET_KEY 注入强随机值
    JWT_SECRET_KEY: str = "change-me-in-production-use-env-var"
    # 签名算法
    JWT_ALGORITHM: str = "HS256"
    # Access Token 有效期（小时），默认 24 小时
    JWT_ACCESS_TOKEN_EXPIRE_HOUR: int = 24
    # 不需要 JWT 鉴权的公开路径列表（前缀匹配）
    JWT_PUBLIC_PATHS: list[str] = [
        "/docs",
        "/redoc",
        "/openapi.json",
        "/favicon.ico",
        "/health",
        "/api/auth/login",
        "/api/auth/register",
    ]


__all__ = ["CORSSettings", "GZipSettings", "JWTSettings"]
