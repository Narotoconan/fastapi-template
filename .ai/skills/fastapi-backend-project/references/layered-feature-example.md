# Router / Service / Repository 示例

本文件用于新增或重塑一个完整业务功能时按需读取。示例以 `item` 资源为名，落地时按真实业务替换模型、字段、权限和错误消息。

## 目录

- [结构约定](#结构约定)
- [1. Schema](#1-schema)
- [2. Repository](#2-repository)
- [3. Service](#3-service)
- [4. Router](#4-router)
- [5. Route Registration](#5-route-registration)
- [6. Implementation Notes](#6-implementation-notes)

## 结构约定

- `app/api/item.py`：路由层，只做参数接收、依赖注入、调用 service、组装统一响应。
- `app/services/item_service.py`：业务层，处理业务规则、权限、事务边界和跨 repository 编排。
- `app/repositories/item_repo.py`：数据访问层，只处理 SQLAlchemy 查询与持久化。
- `app/schemas/item_schema.py`：请求、查询、响应 schema。
- `app/models/item.py`：SQLAlchemy ORM 模型，示例中仅引用，不在本文件展开。

## 1. Schema

`app/schemas/item_schema.py`

```python
from pydantic import ConfigDict, Field

from app.schemas.base_schema import BaseSchema


class ItemCreate(BaseSchema):
    """创建商品请求体。"""

    name: str = Field(..., min_length=1, max_length=100, description="商品名称")
    price: int = Field(..., ge=0, description="商品价格，单位分")


class ItemSearch(BaseSchema):
    """商品列表查询条件。"""

    name: str | None = Field(default=None, min_length=1, max_length=100, description="商品名称，模糊匹配")


class ItemResponse(BaseSchema):
    """商品响应体。"""

    model_config = ConfigDict(from_attributes=True)

    id: int = Field(description="商品ID")
    name: str = Field(description="商品名称")
    price: int = Field(description="商品价格，单位分")


__all__ = ["ItemCreate", "ItemResponse", "ItemSearch"]
```

## 2. Repository

`app/repositories/item_repo.py`

```python
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.item import Item
from app.repositories.base_repo import BaseRepository
from app.schemas.item_schema import ItemCreate, ItemSearch


class ItemRepository(BaseRepository):
    """商品数据访问。"""

    async def get_by_id(self, session: AsyncSession, item_id: int) -> Item | None:
        """按 ID 查询商品。"""
        statement = select(Item).where(Item.id == item_id)
        result = await session.execute(statement)
        return result.scalar_one_or_none()

    async def get_by_name(self, session: AsyncSession, name: str) -> Item | None:
        """按名称查询商品。"""
        statement = select(Item).where(Item.name == name)
        result = await session.execute(statement)
        return result.scalar_one_or_none()

    async def list_items(
        self,
        session: AsyncSession,
        search: ItemSearch,
        *,
        offset: int,
        limit: int,
    ) -> tuple[list[Item], int]:
        """分页查询商品列表和总数。"""
        filters = []
        if search.name:
            filters.append(Item.name.ilike(f"%{search.name}%"))

        list_statement = select(Item).where(*filters).order_by(Item.id.desc()).offset(offset).limit(limit)
        count_statement = select(func.count()).select_from(select(Item.id).where(*filters).subquery())

        list_result = await session.execute(list_statement)
        count_result = await session.execute(count_statement)
        return list(list_result.scalars().all()), count_result.scalar_one()

    async def create(self, session: AsyncSession, payload: ItemCreate) -> Item:
        """创建商品记录，事务提交由 service 控制。"""
        item = Item(**payload.model_dump())
        session.add(item)
        await session.flush()
        await session.refresh(item)
        return item


item_repository = ItemRepository()

__all__ = ["ItemRepository", "item_repository"]
```

## 3. Service

`app/services/item_service.py`

```python
from sqlalchemy.ext.asyncio import AsyncSession

from app.exceptions import BizException, ErrorCode, NotFoundException
from app.repositories.item_repo import item_repository
from app.schemas.item_schema import ItemCreate, ItemResponse, ItemSearch


class ItemService:
    """商品业务逻辑。"""

    async def get_item(self, session: AsyncSession, item_id: int) -> ItemResponse:
        """查询商品详情，不存在时抛出统一资源异常。"""
        item = await item_repository.get_by_id(session, item_id)
        if item is None:
            raise NotFoundException(message=f"商品 {item_id} 不存在")
        return ItemResponse.model_validate(item)

    async def list_items(
        self,
        session: AsyncSession,
        search: ItemSearch,
        *,
        offset: int,
        limit: int,
    ) -> tuple[list[ItemResponse], int]:
        """分页查询商品列表。"""
        items, total = await item_repository.list_items(session, search, offset=offset, limit=limit)
        return [ItemResponse.model_validate(item) for item in items], total

    async def create_item(self, session: AsyncSession, payload: ItemCreate) -> ItemResponse:
        """创建商品并校验名称唯一性。"""
        async with session.begin():
            exists = await item_repository.get_by_name(session, payload.name)
            if exists is not None:
                raise BizException(ErrorCode.ALREADY_EXISTS, message=f"商品名称 {payload.name} 已存在")

            item = await item_repository.create(session, payload)

        return ItemResponse.model_validate(item)


item_service = ItemService()

__all__ = ["ItemService", "item_service"]
```

## 4. Router

`app/api/item.py`

```python
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.rate_limit import rate_limit
from app.dependencies.db import get_db
from app.dependencies.pagination import PageDep
from app.schemas.item_schema import ItemCreate, ItemResponse, ItemSearch
from app.schemas.response import PageResponseSchema, ResponseSchema
from app.services.item_service import item_service

DBSessionDep = Annotated[AsyncSession, Depends(get_db)]

router_item = APIRouter(prefix="/items", tags=["商品管理"])


@router_item.get("/{item_id}", summary="获取商品详情")
async def get_item_api(item_id: int, db: DBSessionDep) -> ResponseSchema:
    """获取商品详情。"""
    item = await item_service.get_item(db, item_id)
    return ResponseSchema.ok(data=item.model_dump())


@router_item.get("", summary="分页查询商品")
@rate_limit("30/minute")
async def list_items_api(
    request: Request,
    db: DBSessionDep,
    pagination: PageDep,
    search: Annotated[ItemSearch, Query()],
) -> PageResponseSchema[ItemResponse]:
    """分页查询商品列表。"""
    items, total = await item_service.list_items(
        db,
        search,
        offset=pagination.offset,
        limit=pagination.limit,
    )
    return PageResponseSchema.ok(data=items, total=total, page=pagination.page, page_size=pagination.page_size)


@router_item.post("", summary="创建商品")
async def create_item_api(payload: ItemCreate, db: DBSessionDep) -> ResponseSchema:
    """创建商品。"""
    item = await item_service.create_item(db, payload)
    return ResponseSchema.ok(data=item.model_dump(), message="创建成功")


__all__ = ["router_item"]
```

## 5. Route Registration

`app/api/__init__.py`

```python
from fastapi import APIRouter, FastAPI

from app.api.demo import router_demo
from app.api.item import router_item


def register_router(app: FastAPI) -> None:
    router = APIRouter()
    router.include_router(router_demo)
    router.include_router(router_item)

    app.include_router(router)


__all__ = ["register_router"]
```

## 6. Implementation Notes

- 若查询条件变复杂，仍保持分页在 `PageDep`，筛选条件放 `ItemSearch`。
- 写操作事务放在 service，repository 不执行 `commit()` / `rollback()`。
- 更复杂的查询、事务、关联加载和原生 SQL 示例见 `database-async-sqlalchemy.md`。
- `ItemResponse.model_validate(item)` 依赖 `ConfigDict(from_attributes=True)`。
- 错误类型选择见 `error-handling.md`。
- 测试和验证命令见 `testing-validation.md`。
