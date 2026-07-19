import os
import sys

_SETTINGS_ENVIRONMENT_VARIABLES = (
    "APP_NAME",
    "APP_VERSION",
    "BASE_PATH",
    "LOG_LEVEL",
    "LOG_RETENTION",
    "LOG_ROTATION_TIME",
    "DB_HOST",
    "DB_PORT",
    "DB_USER",
    "DB_PASSWORD",
    "DB_DATABASE",
    "DB_POOL_SIZE",
    "DB_MAX_OVERFLOW",
    "DB_POOL_RECYCLE",
    "DB_POOL_TIMEOUT",
    "DB_COMMAND_TIMEOUT",
    "DB_CONNECT_TIMEOUT",
    "REDIS_HOST",
    "REDIS_PORT",
    "REDIS_DB",
    "REDIS_PASSWORD",
    "REDIS_MAX_CONNECTIONS",
    "REDIS_TIMEOUT",
    "REDIS_COMMAND_TIMEOUT",
    "REDIS_PREFIX",
    "CORS_ALLOW_ORIGINS",
    "CORS_ALLOW_CREDENTIALS",
    "CORS_ALLOW_METHODS",
    "CORS_ALLOW_HEADERS",
    "GZIP_MINIMUM_SIZE",
    "JWT_SECRET_KEY",
    "JWT_ALGORITHM",
    "JWT_ACCESS_TOKEN_EXPIRE_HOUR",
    "JWT_PUBLIC_PATHS",
    "RATE_LIMIT_ENABLED",
    "RATE_LIMIT_DEFAULT",
    "RATE_LIMIT_FAIL_OPEN",
    "RATE_LIMIT_REDIS_MAX_CONNECTIONS",
    "RATE_LIMIT_REDIS_POOL_TIMEOUT",
    "RATE_LIMIT_REDIS_CONNECT_TIMEOUT",
    "RATE_LIMIT_REDIS_COMMAND_TIMEOUT",
)
_REQUIRED_TEST_ENVIRONMENT = {
    "DB_PASSWORD": "test-database-password",
    "JWT_SECRET_KEY": "test-jwt-secret-key-with-32-characters",
}
_ORIGINAL_ENVIRONMENT: dict[str, str | None] = {}


def _clear_settings_cache() -> None:
    """清理已加载的全局配置缓存，避免跨测试运行保留旧环境。"""
    settings_module = sys.modules.get("config.settings")
    get_settings = getattr(settings_module, "get_settings", None)
    if get_settings is not None:
        get_settings.cache_clear()


def pytest_configure() -> None:
    """在测试收集前隔离项目配置环境，并注入固定假凭据。"""
    _ORIGINAL_ENVIRONMENT.clear()
    for variable_name in _SETTINGS_ENVIRONMENT_VARIABLES:
        _ORIGINAL_ENVIRONMENT[variable_name] = os.environ.get(variable_name)
        os.environ.pop(variable_name, None)
    os.environ.update(_REQUIRED_TEST_ENVIRONMENT)
    _clear_settings_cache()


def pytest_unconfigure() -> None:
    """测试结束后恢复宿主机环境，并清理测试期间创建的配置缓存。"""
    _clear_settings_cache()
    for variable_name, original_value in _ORIGINAL_ENVIRONMENT.items():
        if original_value is None:
            os.environ.pop(variable_name, None)
        else:
            os.environ[variable_name] = original_value
    _ORIGINAL_ENVIRONMENT.clear()
