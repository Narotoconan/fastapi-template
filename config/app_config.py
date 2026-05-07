import os
import tomllib
from functools import lru_cache

from pydantic_settings import BaseSettings

# 项目根目录
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@lru_cache(maxsize=1)
def load_pyproject_toml() -> tuple[str, str]:
    """从 pyproject.toml 读取项目名称和版本号"""
    with open(f"{_PROJECT_ROOT}/pyproject.toml", "rb") as config_file:
        _config = tomllib.load(config_file)
    return _config.get("project").get("name"), _config.get("project").get("version")


class AppSettings(BaseSettings):
    _name, _version = load_pyproject_toml()

    APP_NAME: str = _name
    APP_VERSION: str = _version
    BASE_PATH: str = _PROJECT_ROOT


__all__ = ["AppSettings"]
