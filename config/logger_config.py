import logging

from pydantic_settings import BaseSettings, SettingsConfigDict


class LoggerSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file_encoding="utf-8")
    LOG_LEVEL: int = logging.INFO  # 从环境变量读取，默认 INFO
    LOG_RETENTION: str = "14 days"
    LOG_ROTATION_TIME: str = "00:00"


__all__ = ["LoggerSettings"]
