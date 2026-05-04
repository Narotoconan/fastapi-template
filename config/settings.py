from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings

from .app_config import AppSettings
from .cache_config import CacheSettings
from .database_config import DatabaseSettings
from .logger_config import LoggerSettings
from .middleware_config import CORSSettings, GZipSettings, JWTSettings


class Settings(BaseSettings):
    app: AppSettings = Field(default_factory=AppSettings)
    logger: LoggerSettings = Field(default_factory=LoggerSettings)
    database: DatabaseSettings = Field(default_factory=DatabaseSettings)
    cache: CacheSettings = Field(default_factory=CacheSettings)
    cors: CORSSettings = Field(default_factory=CORSSettings)
    gzip: GZipSettings = Field(default_factory=GZipSettings)
    jwt: JWTSettings = Field(default_factory=JWTSettings)


@lru_cache
def get_settings() -> Settings:
    return Settings()


__all__ = ["get_settings"]
