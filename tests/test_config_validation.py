import pytest
from pydantic import ValidationError

from config.cache_config import CacheSettings
from config.database_config import DatabaseSettings
from config.logger_config import LoggerSettings
from config.middleware_config import CORSSettings, GZipSettings, JWTSettings
from config.rate_limit_config import RateLimitSettings

_JWT_SECRET = "test-jwt-secret-key-with-32-characters"


@pytest.mark.parametrize(
    ("field_name", "invalid_value"),
    [
        ("REDIS_PORT", 0),
        ("REDIS_PORT", 65536),
        ("REDIS_DB", -1),
        ("REDIS_MAX_CONNECTIONS", 0),
        ("REDIS_TIMEOUT", 0),
        ("REDIS_COMMAND_TIMEOUT", 0),
        ("REDIS_HOST", "   "),
        ("REDIS_PREFIX", "   "),
    ],
)
def test_cache_settings_reject_invalid_boundaries(field_name: str, invalid_value: object) -> None:
    """Redis 配置应在启动阶段拒绝无法正常工作的边界值。"""
    with pytest.raises(ValidationError):
        CacheSettings.model_validate({field_name: invalid_value})


def test_cache_settings_keep_defaults() -> None:
    """新增校验不应改变 Redis 配置的默认行为。"""
    settings = CacheSettings()

    assert settings.REDIS_PORT == 6379
    assert settings.REDIS_DB == 0
    assert settings.REDIS_MAX_CONNECTIONS == 10
    assert settings.REDIS_TIMEOUT == 5.0
    assert settings.REDIS_COMMAND_TIMEOUT == 5.0
    assert settings.REDIS_PREFIX == "template"


@pytest.mark.parametrize(
    ("field_name", "invalid_value"),
    [
        ("DB_PORT", 0),
        ("DB_PORT", 65536),
        ("DB_HOST", "   "),
        ("DB_USER", "   "),
        ("DB_DATABASE", "   "),
    ],
)
def test_database_settings_reject_invalid_boundaries(field_name: str, invalid_value: object) -> None:
    """数据库配置应拒绝非法端口和空白连接标识。"""
    with pytest.raises(ValidationError):
        DatabaseSettings.model_validate({"DB_PASSWORD": "test-password", field_name: invalid_value})


def test_middleware_settings_reject_invalid_combinations() -> None:
    """中间件配置应拒绝框架无法安全执行的参数组合。"""
    with pytest.raises(ValidationError, match="CORS 允许凭据时不能使用通配来源"):
        CORSSettings(CORS_ALLOW_ORIGINS=["*"], CORS_ALLOW_CREDENTIALS=True)

    with pytest.raises(ValidationError):
        GZipSettings(GZIP_MINIMUM_SIZE=-1)

    with pytest.raises(ValidationError):
        JWTSettings(JWT_SECRET_KEY=_JWT_SECRET, JWT_ACCESS_TOKEN_EXPIRE_HOUR=0)


def test_cors_credentials_accept_specific_origins() -> None:
    """凭据跨域在配置具体来源时应保持可用。"""
    settings = CORSSettings(
        CORS_ALLOW_ORIGINS=["https://admin.example.com"],
        CORS_ALLOW_CREDENTIALS=True,
    )

    assert settings.CORS_ALLOW_CREDENTIALS is True


def test_rate_limit_expression_is_validated_only_when_enabled() -> None:
    """关闭限流时保留旧行为，启用时才校验默认额度表达式。"""
    disabled_settings = RateLimitSettings(RATE_LIMIT_ENABLED=False, RATE_LIMIT_DEFAULT="invalid")
    enabled_settings = RateLimitSettings(
        RATE_LIMIT_ENABLED=True,
        RATE_LIMIT_DEFAULT="100/minute; 1000/hour",
    )

    assert disabled_settings.RATE_LIMIT_DEFAULT == "invalid"
    assert enabled_settings.RATE_LIMIT_DEFAULT == "100/minute; 1000/hour"

    with pytest.raises(ValidationError, match="必须是有效的限流表达式"):
        RateLimitSettings(RATE_LIMIT_ENABLED=True, RATE_LIMIT_DEFAULT="invalid")

    with pytest.raises(ValidationError, match="请求次数必须大于 0"):
        RateLimitSettings(RATE_LIMIT_ENABLED=True, RATE_LIMIT_DEFAULT="0/minute")


@pytest.mark.parametrize(
    "field_name",
    [
        "RATE_LIMIT_REDIS_MAX_CONNECTIONS",
        "RATE_LIMIT_REDIS_POOL_TIMEOUT",
        "RATE_LIMIT_REDIS_CONNECT_TIMEOUT",
        "RATE_LIMIT_REDIS_COMMAND_TIMEOUT",
    ],
)
def test_rate_limit_redis_settings_reject_non_positive_values(field_name: str) -> None:
    """限流专用 Redis 连接池参数必须为正数。"""
    with pytest.raises(ValidationError):
        RateLimitSettings.model_validate({field_name: 0})


def test_rate_limit_redis_settings_keep_safe_defaults() -> None:
    """异步限流连接池与故障策略应保持小型项目的保守默认值。"""
    settings = RateLimitSettings()

    assert settings.RATE_LIMIT_FAIL_OPEN is True
    assert settings.RATE_LIMIT_REDIS_MAX_CONNECTIONS == 5
    assert settings.RATE_LIMIT_REDIS_POOL_TIMEOUT == 0.2
    assert settings.RATE_LIMIT_REDIS_CONNECT_TIMEOUT == 1.0
    assert settings.RATE_LIMIT_REDIS_COMMAND_TIMEOUT == 0.5


@pytest.mark.parametrize("invalid_level", [-1, -10])
def test_logger_settings_reject_negative_level(invalid_level: int) -> None:
    """日志级别不能低于 Loguru 支持的最小数值。"""
    with pytest.raises(ValidationError):
        LoggerSettings(LOG_LEVEL=invalid_level)


@pytest.mark.parametrize("invalid_retention", ["", "invalid", "0 days", "-1 days"])
def test_logger_settings_reject_invalid_retention(invalid_retention: str) -> None:
    """日志保留期应是 Loguru 支持的正数时长。"""
    with pytest.raises(ValidationError):
        LoggerSettings(LOG_RETENTION=invalid_retention)


@pytest.mark.parametrize("invalid_rotation", ["", "invalid", "25:00", "0 seconds", "-1 days"])
def test_logger_settings_reject_invalid_rotation(invalid_rotation: str) -> None:
    """日志轮转规则应有效且不能使用可能反复触发的非正数间隔。"""
    with pytest.raises(ValidationError):
        LoggerSettings(LOG_ROTATION_TIME=invalid_rotation)


@pytest.mark.parametrize("valid_rotation", ["00:00", "daily", "10 MB", "1 day"])
def test_logger_settings_accept_loguru_rotation_forms(valid_rotation: str) -> None:
    """校验应继续接受 Loguru 已公开支持的轮转表达式。"""
    settings = LoggerSettings(LOG_ROTATION_TIME=valid_rotation)

    assert settings.LOG_ROTATION_TIME == valid_rotation
