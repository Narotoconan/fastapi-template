# 分层功能骨架示例

本文件给出一个可按需改造的 router → service → repository 示例。代码中的 `Item` 是虚构业务对象，仅用于展示层间职责和数据流，不表示当前项目已经存在相应表、路由、字段或配置。

复制前先核对当前 `AGENTS.md`、相关模块 README、实现和测试；再替换领域命名、字段、权限、异常语义与数据库约束。

## 目录

- [建议文件](#建议文件)
- [模型](#模型)
- [请求与响应 Schema](#请求与响应-schema)
- [Repository](#repository)
- [Service](#service)
- [Router](#router)
- [路由注册](#路由注册)
- [落地检查](#落地检查)

## 建议文件

```text
app/
├── api/item.py
├── models/item.py
├── repositories/item_repo.py
├── schemas/item_schema.py
└── services/item_service.py
```

这只是常见拆分方式。若仓库当前按业务包组织或存在更近的 `AGENTS.md`，应遵循当前结构。

## 模型

模型负责持久化映射和数据库级约束。示例中的长度、唯一性和表名都是占位设计，实际值必须来自业务需求。

```python
# app/models/item.py
from sqlalchemy import String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base_model import BaseModel

ITEM_NAME_UNIQUE_CONSTRAINT = "uq_items_name"


class Item(BaseModel):
    """示例业务对象。"""

    __tablename__ = "items"
    __table_args__ = (
        UniqueConstraint(
            "name",
            name=ITEM_NAME_UNIQUE_CONSTRAINT,
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )


__all__ = ["ITEM_NAME_UNIQUE_CONSTRAINT", "Item"]
```

新增或修改模型后，应按项目当前迁移机制补充并审核迁移，不要假设应用启动会自动完成结构变更。

## 请求与响应 Schema

请求 Schema 只接收允许客户端设置的字段；响应 Schema 明确公开字段，避免直接暴露未经审查的 ORM 对象。

```python
# app/schemas/item_schema.py
from pydantic import ConfigDict, Field

from app.schemas.base_schema import BaseSchema


class ItemCreate(BaseSchema):
    """创建业务对象的请求参数。"""

    name: str = Field(min_length=1, max_length=100)


class ItemResponse(BaseSchema):
    """对外公开的业务对象字段。"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str


__all__ = ["ItemCreate", "ItemResponse"]
```

## Repository

Repository 只负责查询和持久化，不依赖 FastAPI 响应或 HTTP 异常，也不提交调用方事务。

```python
# app/repositories/item_repo.py
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.item import Item
from app.repositories.base_repo import BaseRepository


class ItemRepository(BaseRepository):
    """示例业务对象的数据访问。"""

    async def get_by_id(
        self,
        session: AsyncSession,
        item_id: int,
    ) -> Item | None:
        """按主键查询业务对象。"""
        statement = select(Item).where(Item.id == item_id)
        result = await session.execute(statement)
        return result.scalar_one_or_none()

    async def create(
        self,
        session: AsyncSession,
        *,
        name: str,
    ) -> Item:
        """写入业务对象，但不提交调用方事务。"""
        item = Item(name=name)
        session.add(item)
        await session.flush()
        return item


# 仅在当前仓库采用模块级无状态实例时保留。
item_repository = ItemRepository()

__all__ = ["ItemRepository", "item_repository"]
```

如果名称需要唯一，数据库唯一约束才是并发安全的最终保障。是否预查询、如何识别约束冲突以及转换成哪种项目异常，应依据当前数据库与异常约定决定。

模块级实例不是 FastAPI 或 SQLAlchemy 的通用要求。若当前项目改用依赖注入容器、工厂或请求级实例，应删除示例实例，并沿用实际装配方式。

## Service

Service 解释业务结果、抛出项目异常并拥有写事务边界。示例在事务退出前构造响应，避免依赖未知的提交后对象过期策略。

```python
# app/services/item_service.py
from sqlalchemy.ext.asyncio import AsyncSession

from app.exceptions import NotFoundException
from app.repositories.item_repo import ItemRepository, item_repository
from app.schemas.item_schema import ItemCreate, ItemResponse


class ItemService:
    """示例业务对象的业务编排。"""

    def __init__(self, repository: ItemRepository) -> None:
        self._repository = repository

    async def get_item(
        self,
        session: AsyncSession,
        item_id: int,
    ) -> ItemResponse:
        """查询业务对象并解释不存在语义。"""
        item = await self._repository.get_by_id(session, item_id)
        if item is None:
            raise NotFoundException(message=f"条目 {item_id} 不存在")
        return ItemResponse.model_validate(item)

    async def create_item(
        self,
        session: AsyncSession,
        payload: ItemCreate,
    ) -> ItemResponse:
        """在一个事务内创建业务对象。"""
        async with session.begin():
            item = await self._repository.create(
                session,
                name=payload.name,
            )
            response = ItemResponse.model_validate(item)

        return response


# 与上面的模块级实例策略配套；实际以当前装配代码为准。
item_service = ItemService(item_repository)

__all__ = ["ItemService", "item_service"]
```

如果一个写流程在进入 `session.begin()` 前已经通过同一会话执行了查询，需要重新设计事务入口或沿用当前已开启事务，不能机械嵌套 `begin()`。

## Router

Router 负责 HTTP 参数、依赖注入和成功响应组装。业务判断和事务留在 Service。

```python
# app/api/item.py
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies.db import get_db
from app.schemas.item_schema import ItemCreate
from app.schemas.response import ResponseSchema
from app.services.item_service import item_service

DBSessionDep = Annotated[AsyncSession, Depends(get_db)]

router_item = APIRouter(prefix="/items", tags=["条目"])


@router_item.get("/{item_id}", summary="查询条目")
async def get_item_api(
    item_id: int,
    session: DBSessionDep,
) -> ResponseSchema:
    """查询单个业务对象。"""
    item = await item_service.get_item(session, item_id)
    return ResponseSchema.ok(data=item.model_dump(mode="json"))


@router_item.post("", summary="创建条目")
async def create_item_api(
    payload: ItemCreate,
    session: DBSessionDep,
) -> ResponseSchema:
    """创建业务对象。"""
    item = await item_service.create_item(session, payload)
    return ResponseSchema.ok(data=item.model_dump(mode="json"))


__all__ = ["router_item"]
```

权限依赖、HTTP 状态码、幂等要求和审计字段均应按实际公共契约补充。不要因为示例省略，就默认接口不需要这些能力。

## 路由注册

在当前装配文件中做增量修改，保留全部既有路由：

```diff
+from app.api.item import router_item

 def register_router(app: FastAPI) -> None:
     router = APIRouter()
     # 保留已有的 include_router(...) 调用
+    router.include_router(router_item)
     app.include_router(router)
```

实际插入位置以当前代码的 import 排序和注册顺序为准，不要用该片段覆盖整个函数。

## 落地检查

- 业务字段、权限、失败语义和兼容要求是否来自真实需求，而不是示例。
- 数据库约束、索引、迁移和事务边界是否完整。
- Router 是否保持轻量，Repository 是否没有提交事务或依赖 HTTP 对象。
- 响应字段是否通过 Schema 显式筛选，序列化方式是否符合当前响应文档。
- 是否补充了 Service 规则、Repository 查询、接口行为和并发约束的相关测试。
- 是否同步更新受影响的根 README 或模块 README，并按 `AGENTS.md` 运行质量门禁。
