from typing import Literal

from pydantic import Field

from app.schemas.base_schema import BaseSchema

HealthStatus = Literal["healthy", "unhealthy"]


class HealthCheckResult(BaseSchema):
    """应用及关键依赖健康状态。"""

    status: HealthStatus = Field(description="应用整体健康状态")
    checks: dict[str, HealthStatus] = Field(description="关键依赖健康状态")


__all__ = ["HealthCheckResult"]
