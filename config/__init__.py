from .app_config import AppSettings
from .database_config import DatabaseSettings

APP_SETTINGS = AppSettings()
DATABASE_SETTINGS = DatabaseSettings()  # ty: ignore[missing-argument] BaseSettings 从环境变量读取必填项

__all__ = [
    "APP_SETTINGS",
    "DATABASE_SETTINGS",
]
