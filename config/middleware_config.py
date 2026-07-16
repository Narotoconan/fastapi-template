"""
中间件相关配置

包含 CORS、GZip、JWT 三个中间件的可配置项。
所有字段均可通过环境变量覆盖（Pydantic-Settings 自动读取）。
"""

from typing import Self

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class CORSSettings(BaseSettings):
    """CORS 跨域中间件配置"""

    # 允许的来源列表，生产环境应替换为具体域名，例如 ["https://example.com"]
    CORS_ALLOW_ORIGINS: list[str] = ["*"]
    # 是否允许携带 Cookie/Authorization 等凭据
    # ⚠️ 注意：allow_credentials=True 与 allow_origins=["*"] 互斥！
    # 启用 credentials 时必须将 CORS_ALLOW_ORIGINS 设为具体域名列表，不可使用通配符 "*"
    CORS_ALLOW_CREDENTIALS: bool = False
    # 允许的 HTTP 方法
    CORS_ALLOW_METHODS: list[str] = ["*"]
    # 允许的请求头
    CORS_ALLOW_HEADERS: list[str] = ["*"]

    @model_validator(mode="after")
    def validate_credentials_with_origins(self) -> Self:
        """启用凭据时拒绝通配来源，避免产生无效或不安全的 CORS 配置。"""
        if self.CORS_ALLOW_CREDENTIALS and any(origin.strip() == "*" for origin in self.CORS_ALLOW_ORIGINS):
            raise ValueError("CORS 允许凭据时不能使用通配来源 *")
        return self


class GZipSettings(BaseSettings):
    """GZip 压缩中间件配置"""

    # 触发压缩的响应体最小字节数，小于该值的响应不压缩
    GZIP_MINIMUM_SIZE: int = Field(default=1000, ge=0)


class JWTSettings(BaseSettings):
    """JWT 鉴权中间件配置"""

    model_config = SettingsConfigDict(hide_input_in_errors=True)

    # 签名密钥必须通过环境变量注入，最少 32 个字符
    JWT_SECRET_KEY: str = Field(min_length=32)
    # 签名算法
    JWT_ALGORITHM: str = "HS256"
    # Access Token 有效期（小时），默认 24 小时
    JWT_ACCESS_TOKEN_EXPIRE_HOUR: int = Field(default=24, gt=0)
    # 不需要 JWT 鉴权的公开路径列表（精确匹配或路径段子路径匹配）
    JWT_PUBLIC_PATHS: list[str] = [
        "/docs",
        "/redoc",
        "/openapi.json",
        "/favicon.ico",
        "/health",
        "/api/auth/login",
        "/api/auth/register",
    ]

    @field_validator("JWT_PUBLIC_PATHS")
    @classmethod
    def validate_public_paths(cls, public_paths: list[str]) -> list[str]:
        """规范化公开路径，并拒绝可能放行全站的配置。"""
        normalized_paths: list[str] = []
        for public_path in public_paths:
            stripped_path = public_path.strip()
            normalized_path = stripped_path.rstrip("/")
            if not normalized_path:
                raise ValueError("JWT 公开路径不能为空或根路径")
            if not normalized_path.startswith("/"):
                raise ValueError(f"JWT 公开路径必须以 / 开头: {normalized_path}")
            normalized_paths.append(normalized_path)
        return list(dict.fromkeys(normalized_paths))


__all__ = ["CORSSettings", "GZipSettings", "JWTSettings"]
