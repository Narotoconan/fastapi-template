from fastapi import APIRouter

from app.schemas.response import ResponseSchema
from app.services.health_service import health_service

router_health = APIRouter(tags=["健康检查"])


@router_health.get("/health", summary="服务健康检查", include_in_schema=False)
async def health_check_api() -> ResponseSchema:
    """返回应用及关键依赖的健康状态，供容器编排和负载均衡器探测。"""
    health_result = await health_service.check()
    return ResponseSchema.ok(data=health_result)


__all__ = ["router_health"]
