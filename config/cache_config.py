from pydantic_settings import BaseSettings, SettingsConfigDict


class CacheSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file_encoding="utf-8")
    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = 6379
    REDIS_DB: int = 0
    REDIS_PASSWORD: str | None = None
    REDIS_MAX_CONNECTIONS: int = 10
    REDIS_TIMEOUT: int = 5

    # Redis 键前缀 - 手动配置，用于区分多个项目在同一 Redis 实例中的数据
    # 示例: "anda_erp", "shop_system", "blog_platform"
    REDIS_PREFIX: str = "anda_erp"


__all__ = ["CacheSettings"]
