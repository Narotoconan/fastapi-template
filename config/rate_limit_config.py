from typing import Self

from limits import parse_many
from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class RateLimitSettings(BaseSettings):
    """接口速率限制配置。"""

    model_config = SettingsConfigDict(hide_input_in_errors=True)

    RATE_LIMIT_ENABLED: bool = False
    RATE_LIMIT_DEFAULT: str = "100/minute"

    @model_validator(mode="after")
    def validate_enabled_limit(self) -> Self:
        """启用限流时验证默认额度表达式，避免在首个请求才暴露配置错误。"""
        if not self.RATE_LIMIT_ENABLED:
            return self

        try:
            limits = parse_many(self.RATE_LIMIT_DEFAULT)
        except ValueError as exc:
            raise ValueError("启用限流时 RATE_LIMIT_DEFAULT 必须是有效的限流表达式") from exc

        if not limits or any(limit.amount <= 0 for limit in limits):
            raise ValueError("启用限流时 RATE_LIMIT_DEFAULT 的请求次数必须大于 0")
        return self


__all__ = ["RateLimitSettings"]
