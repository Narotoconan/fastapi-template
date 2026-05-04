"""
分页参数依赖注入

职责分离原则：
    - Query 参数控制「怎么取」（分页、排序）
    - Body 参数描述「取什么」（筛选条件）

使用方式:

场景一：GET 接口
    from app.dependencies.pagination import PageDep

    @router.get("/list")
    async def get_list(pagination: PageDep): ...

场景二：POST 复杂查询（分页在 Query，筛选在 Body）
    from app.dependencies.pagination import PageDep
    from app.schemas.user_schema import UserSearch

    @router.post("/search")
    async def search_user(
        pagination: PageDep,
        params: UserSearch,
    ):
        # pagination.offset, pagination.limit 用于 SQL
        # params.username, params.gender 用于 WHERE 条件
        ...
"""

from typing import Annotated

from fastapi import Depends, Query

from app.schemas.base_schema import BaseSchema


class PageParams(BaseSchema):
    """分页数据载体（由 get_pagination 依赖构建，参数已由 Query 校验）"""

    page: int
    page_size: int

    @property
    def offset(self) -> int:
        """计算 SQL OFFSET"""
        return (self.page - 1) * self.page_size

    @property
    def limit(self) -> int:
        """计算 SQL LIMIT"""
        return self.page_size


async def get_pagination(
    page: int = Query(default=1, ge=1, description="页码，从1开始"),
    page_size: int = Query(default=10, ge=1, le=100, description="每页条数，最大100"),
) -> PageParams:
    """统一分页参数依赖"""
    return PageParams(page=page, page_size=page_size)


# 类型别名，路由函数直接注解使用
PageDep = Annotated[PageParams, Depends(get_pagination)]

__all__ = [
    "PageDep",
    "PageParams",
    "get_pagination",
]
