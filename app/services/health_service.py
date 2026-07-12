from app.core.cache import get_redis_manager
from app.core.database import db_health_check
from app.core.log import log
from app.exceptions import ServiceUnavailableException
from app.schemas.health_schema import HealthCheckResult, HealthStatus


class HealthService:
    """检查应用关键基础设施依赖。"""

    async def check(self) -> HealthCheckResult:
        """依次检查 PostgreSQL 与 Redis，任一异常均视为服务不可用。"""
        checks: dict[str, HealthStatus] = {
            "database": "unhealthy",
            "redis": "unhealthy",
        }

        try:
            if await db_health_check():
                checks["database"] = "healthy"
        except Exception as exc:
            log.warning(f"数据库健康检查失败 | error_type={type(exc).__name__}")

        try:
            if await get_redis_manager().ping():
                checks["redis"] = "healthy"
        except Exception as exc:
            log.warning(f"Redis 健康检查失败 | error_type={type(exc).__name__}")

        if "unhealthy" in checks.values():
            raise ServiceUnavailableException(
                message="关键依赖不可用",
                result={"status": "unhealthy", "checks": checks},
            )

        return HealthCheckResult(status="healthy", checks=checks)


health_service = HealthService()

__all__ = ["HealthService", "health_service"]
