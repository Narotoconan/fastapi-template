from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class DatabaseSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file_encoding="utf-8", hide_input_in_errors=True)
    DB_HOST: str = "localhost"
    DB_PORT: int = 5432
    DB_USER: str = "postgres"
    DB_PASSWORD: str = Field(min_length=6)
    DB_DATABASE: str = "postgres"
    DB_POOL_SIZE: int = Field(default=5, ge=1)
    DB_MAX_OVERFLOW: int = Field(default=10, ge=0)
    DB_POOL_RECYCLE: int = Field(default=300, ge=-1)
    DB_POOL_TIMEOUT: float = Field(default=30.0, gt=0)
    DB_COMMAND_TIMEOUT: float = Field(default=60.0, gt=0)
    DB_CONNECT_TIMEOUT: float = Field(default=30.0, gt=0)


__all__ = ["DatabaseSettings"]
