"""
统一响应模型

使用方式:
    # 成功响应
    return ResponseSchema(result={"id": 1, "name": "test"})

    # 成功响应(快捷方式)
    return ResponseSchema.ok(data={"id": 1}, message="操作成功")

    # 分页响应
    return PageResponseSchema.ok(items=user_list, total=100, page=1, page_size=10)

    # 错误响应(通常由异常处理器自动构建，无需手动使用)
    return ResponseSchema.fail(message="参数错误", code=-1)
"""

from typing import Any, TypeVar

from pydantic import Field

from app.schemas.base_schema import BaseSchema

T = TypeVar("T")


# ==================== 基础响应模型 ====================


class ResponseSchema(BaseSchema):
    """统一响应格式"""

    code: int = Field(default=0, description="业务状态码, 0=成功, 非0=失败")
    message: str = Field(default="success", description="响应消息")
    result: Any = Field(default={}, description="响应数据")

    @classmethod
    def ok(cls, *, data: Any = None, message: str = "success") -> "ResponseSchema":
        """构建成功响应"""
        return cls(code=0, message=message, result=data if data is not None else {})

    @classmethod
    def fail(cls, *, message: str = "error", code: int = -1, result: Any = None) -> "ResponseSchema":
        """构建失败响应"""
        return cls(code=code, message=message, result=result if result is not None else {})


# ==================== 分页响应模型 ====================


class PageInfo(BaseSchema):
    """分页元信息"""

    page: int = Field(description="当前页码")
    page_size: int = Field(description="每页条数")
    total: int = Field(description="总记录数")
    total_pages: int = Field(description="总页数")
    has_next: bool = Field(description="是否有下一页")
    has_prev: bool = Field(description="是否有上一页")


class PageResult[T](BaseSchema):
    """分页数据载体"""

    data: list[T] = Field(default_factory=list, description="数据列表")
    pagination: PageInfo = Field(description="分页信息")


class PageResponseSchema[T](BaseSchema):
    """分页响应格式"""

    code: int = Field(default=0, description="业务状态码")
    message: str = Field(default="success", description="响应消息")
    result: PageResult[T] = Field(description="分页响应数据")

    @classmethod
    def ok(
        cls,
        *,
        data: list[Any],
        total: int,
        page: int = 1,
        page_size: int = 10,
        message: str = "success",
    ) -> "PageResponseSchema":
        """构建分页成功响应"""
        total_pages = (total + page_size - 1) // page_size if page_size > 0 else 0
        pagination = PageInfo(
            page=page,
            page_size=page_size,
            total=total,
            total_pages=total_pages,
            has_next=page < total_pages,
            has_prev=page > 1,
        )
        return cls(
            code=0,
            message=message,
            result=PageResult(data=data, pagination=pagination),
        )


__all__ = [
    "PageInfo",
    "PageResponseSchema",
    "PageResult",
    "ResponseSchema",
]
