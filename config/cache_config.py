from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class CacheSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file_encoding="utf-8", hide_input_in_errors=True)
    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = Field(default=6379, ge=1, le=65535)
    REDIS_DB: int = Field(default=0, ge=0)
    REDIS_PASSWORD: str | None = None
    REDIS_MAX_CONNECTIONS: int = Field(default=10, ge=1)
    REDIS_TIMEOUT: float = Field(default=5.0, gt=0)
    REDIS_COMMAND_TIMEOUT: float = Field(default=5.0, gt=0)

    # Redis 键前缀 - 手动配置，用于区分多个项目在同一 Redis 实例中的数据
    # 示例: "anda_erp", "shop_system", "blog_platform"
    REDIS_PREFIX: str = "template"

    @field_validator("REDIS_HOST", "REDIS_PREFIX")
    @classmethod
    def validate_non_empty_string(cls, value: str) -> str:
        """拒绝仅包含空白字符的 Redis 主机和键前缀配置。"""
        if not value.strip():
            raise ValueError("Redis 主机和键前缀不能为空")
        return value


__all__ = ["CacheSettings"]
