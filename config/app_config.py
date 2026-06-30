import os
import tomllib
from collections.abc import Mapping
from functools import lru_cache

from pydantic_settings import BaseSettings

# 项目根目录
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@lru_cache(maxsize=1)
def load_pyproject_toml() -> tuple[str, str]:
    """从 pyproject.toml 读取项目名称和版本号"""
    with open(f"{_PROJECT_ROOT}/pyproject.toml", "rb") as config_file:
        config: Mapping[str, object] = tomllib.load(config_file)
    project_config = config.get("project")
    if not isinstance(project_config, Mapping):
        return "fastapi-template", "0.1.0"
    return str(project_config.get("name", "fastapi-template")), str(project_config.get("version", "0.1.0"))


class AppSettings(BaseSettings):
    _name, _version = load_pyproject_toml()

    APP_NAME: str = _name
    APP_VERSION: str = _version
    BASE_PATH: str = _PROJECT_ROOT


__all__ = ["AppSettings"]
