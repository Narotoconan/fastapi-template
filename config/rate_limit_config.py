from pydantic_settings import BaseSettings


class RateLimitSettings(BaseSettings):
    """接口速率限制配置。"""

    RATE_LIMIT_ENABLED: bool = False
    RATE_LIMIT_DEFAULT: str = "100/minute"


__all__ = ["RateLimitSettings"]
