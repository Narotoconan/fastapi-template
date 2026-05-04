from .app_config import AppSettings
from .database_config import DatabaseSettings

APP_SETTINGS = AppSettings()
DATABASE_SETTINGS = DatabaseSettings()

__all__ = [
    "APP_SETTINGS",
    "DATABASE_SETTINGS",
]
