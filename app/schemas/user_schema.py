"""
用户相关 Schema

枚举使用规范:
    1. 枚举定义在 app/enums/ 下，Schema / Model / Service 三层共用，不重复定义
    2. BaseSchema 已配置 use_enum_values=True：
       - 入参校验：自动验证值是否在枚举范围内，非法值直接 422
       - 出参序列化：model_dump() / JSON 响应自动提取 .value（int/str），无需手动转换
    3. FastAPI 会根据枚举类型自动生成 OpenAPI 文档的 enum 约束，无需额外描述
"""

from pydantic import Field

from app.enums.common import GenderEnum, StatusEnum
from app.schemas.base_schema import BaseSchema

# ==================== 场景一: 枚举作为必填字段 ====================


class UserCreate(BaseSchema):
    """创建用户 - gender 为必填枚举"""

    username: str = Field(..., min_length=3, max_length=20, description="用户名")
    # 直接声明枚举类型，Pydantic 自动校验值合法性，非 0/1/2 直接 422
    gender: GenderEnum = Field(..., description="性别")
    status: StatusEnum = Field(default=StatusEnum.ENABLED, description="账户状态")


# ==================== 场景二: 枚举作为可选筛选字段 ====================


class UserSearch(BaseSchema):
    """查询用户 - 枚举字段作为可选过滤条件"""

    username: str | None = Field(default=None, min_length=1, max_length=20, description="用户名，模糊匹配")
    gender: GenderEnum | None = Field(default=None, description="性别筛选，不传则查全部")
    status: StatusEnum | None = Field(default=None, description="状态筛选，不传则查全部")


# ==================== 场景三: 枚举在响应 Schema 中使用 ====================


class UserResponse(BaseSchema):
    """用户响应体 - use_enum_values=True 保证序列化为原始值（int/str）"""

    id: int
    username: str
    # 响应中同样使用枚举类型，序列化时自动输出 .value（如 1），而非枚举成员名
    gender: GenderEnum
    status: StatusEnum


__all__ = [
    "UserCreate",
    "UserResponse",
    "UserSearch",
]
