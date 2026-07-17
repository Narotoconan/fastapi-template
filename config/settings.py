from functools import lru_cache

from pydantic import BaseModel, ConfigDict, Field

from .app_config import AppSettings
from .cache_config import CacheSettings
from .database_config import DatabaseSettings
from .logger_config import LoggerSettings
from .middleware_config import CORSSettings, GZipSettings, JWTSettings
from .rate_limit_config import RateLimitSettings


class Settings(BaseModel):
    """聚合各模块配置，不直接从无前缀环境变量读取嵌套对象。"""

    model_config = ConfigDict(hide_input_in_errors=True)

    app: AppSettings = Field(default_factory=AppSettings)
    logger: LoggerSettings = Field(default_factory=LoggerSettings)
    database: DatabaseSettings = Field(default_factory=DatabaseSettings)
    cache: CacheSettings = Field(default_factory=CacheSettings)
    cors: CORSSettings = Field(default_factory=CORSSettings)
    gzip: GZipSettings = Field(default_factory=GZipSettings)
    jwt: JWTSettings = Field(default_factory=JWTSettings)
    rate_limit: RateLimitSettings = Field(default_factory=RateLimitSettings)


@lru_cache
def get_settings() -> Settings:
    return Settings()


__all__ = ["get_settings"]
