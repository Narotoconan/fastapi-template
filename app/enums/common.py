"""
业务枚举常量

设计原则:
    - 枚举是业务常量，独立于 Schema / Model / Service，三层均可复用
    - IntEnum  : 适合存入数据库的数字状态码（gender、status、type 等）
    - StrEnum  : 适合排序方向、字符串标识等（Python 3.11+ 原生支持）
    - 配合 BaseSchema 的 use_enum_values=True，序列化时自动提取 .value，
      无需手动转换
"""

from enum import IntEnum

# ==================== 性别 ====================


class GenderEnum(IntEnum):
    """性别"""

    UNKNOWN = 0  # 未知
    MALE = 1  # 男
    FEMALE = 2  # 女


# ==================== 通用启用/禁用状态 ====================


class StatusEnum(IntEnum):
    """通用启用/禁用状态"""

    DISABLED = 0  # 禁用
    ENABLED = 1  # 启用


__all__ = [
    "GenderEnum",
    "StatusEnum",
]
