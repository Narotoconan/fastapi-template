# SQLAlchemy 异步使用规范

在编写 model、repository 查询、service 事务、关联加载、原生 SQL 或修复数据库相关问题时读取本文件。

## 目录

- [项目会话模型](#项目会话模型)
- [Repository 查询模式](#repository-查询模式)
- [Result 取值选择](#result-取值选择)
- [Service 事务边界](#service-事务边界)
- [Repository 写入模式](#repository-写入模式)
- [避免 N+1 查询](#避免-n1-查询)
- [原生 SQL](#原生-sql)
- [并发与 Session 安全](#并发与-session-安全)
- [禁止写法](#禁止写法)

## 项目会话模型

- 路由通过 `DBSessionDep = Annotated[AsyncSession, Depends(get_db)]` 获取请求级 `AsyncSession`。
- `app/dependencies/db.py` 会在请求异常时 `rollback()`，并在 finally 中 `close()` 与 `AsyncSessionLocal.remove()`。
- service 接收已解析的 `AsyncSession`，不使用 `Depends`。
- repository 方法显式接收 `session: AsyncSession`，不创建 session，不提交事务。
- 不要在异步调用链中使用同步 `Session`、`session.query(...)` 或阻塞 I/O。

```python
from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies.db import get_db

DBSessionDep = Annotated[AsyncSession, Depends(get_db)]
```

## Repository 查询模式

单条查询：

```python
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.item import Item
from app.repositories.base_repo import BaseRepository


class ItemRepository(BaseRepository):
    """商品数据访问。"""

    async def get_by_id(self, session: AsyncSession, item_id: int) -> Item | None:
        """按 ID 查询商品。"""
        statement = select(Item).where(Item.id == item_id)
        result = await session.execute(statement)
        return result.scalar_one_or_none()
```

列表和总数：

```python
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.base_repo import BaseRepository


class ItemRepository(BaseRepository):
    """商品数据访问。"""

    async def list_items(
        self,
        session: AsyncSession,
        *,
        keyword: str | None,
        offset: int,
        limit: int,
    ) -> tuple[list[Item], int]:
        """分页查询商品列表和总数。"""
        filters = []
        if keyword:
            filters.append(Item.name.ilike(f"%{keyword}%"))

        list_statement = select(Item).where(*filters).order_by(Item.id.desc()).offset(offset).limit(limit)
        count_statement = select(func.count()).select_from(select(Item.id).where(*filters).subquery())

        list_result = await session.execute(list_statement)
        count_result = await session.execute(count_statement)
        return list(list_result.scalars().all()), count_result.scalar_one()
```

存在性检查：

```python
from sqlalchemy import exists, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.base_repo import BaseRepository


class ItemRepository(BaseRepository):
    """商品数据访问。"""

    async def exists_by_name(self, session: AsyncSession, name: str) -> bool:
        """判断商品名称是否存在。"""
        statement = select(exists().where(Item.name == name))
        result = await session.execute(statement)
        return result.scalar_one()
```

## Result 取值选择

- `scalar_one_or_none()`：期望 0 或 1 条，适合按唯一键查询。
- `scalar_one()`：期望必须且只能 1 条，适合 `count()`、`exists()` 等确定返回一行的查询。
- `scalars().all()`：返回 ORM 对象列表。
- `first()`：只取第一行但不保证唯一，除非业务上明确允许。

## Service 事务边界

写操作由 service 控制事务。进入 `async with session.begin():` 后再执行属于本次写事务的查询和写入，避免先查询触发 SQLAlchemy autobegin 后再开启事务。

```python
from sqlalchemy.ext.asyncio import AsyncSession

from app.exceptions import BizException, ErrorCode, NotFoundException
from app.repositories.item_repo import item_repository
from app.schemas.item_schema import ItemCreate, ItemResponse


async def create_item(session: AsyncSession, payload: ItemCreate) -> ItemResponse:
    """创建商品并校验名称唯一性。"""
    async with session.begin():
        exists = await item_repository.exists_by_name(session, payload.name)
        if exists:
            raise BizException(ErrorCode.ALREADY_EXISTS, message=f"商品名称 {payload.name} 已存在")

        item = await item_repository.create(session, payload)

    return ItemResponse.model_validate(item)


async def update_item_price(session: AsyncSession, item_id: int, price: int) -> ItemResponse:
    """更新商品价格。"""
    async with session.begin():
        item = await item_repository.get_by_id(session, item_id)
        if item is None:
            raise NotFoundException(message=f"商品 {item_id} 不存在")

        item.price = price
        await session.flush()
        await session.refresh(item)

    return ItemResponse.model_validate(item)
```

事务规则：

- `async with session.begin():` 正常退出时提交，异常退出时回滚。
- repository 不调用 `commit()` / `rollback()`。
- 需要拿到数据库生成的主键、默认值或触发器字段时，用 `await session.flush()` 后再按需 `await session.refresh(obj)`。
- 读接口通常不需要显式 `session.begin()`。

## Repository 写入模式

```python
from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.base_repo import BaseRepository


class ItemRepository(BaseRepository):
    """商品数据访问。"""

    async def create(self, session: AsyncSession, payload: ItemCreate) -> Item:
        """创建商品记录，提交由 service 控制。"""
        item = Item(**payload.model_dump())
        session.add(item)
        await session.flush()
        await session.refresh(item)
        return item

    async def delete_by_id(self, session: AsyncSession, item_id: int) -> bool:
        """按 ID 删除商品，返回是否删除成功。"""
        item = await self.get_by_id(session, item_id)
        if item is None:
            return False

        await session.delete(item)
        await session.flush()
        return True
```

## 避免 N+1 查询

需要关联对象时，在 repository 里显式声明加载策略。优先用 `selectinload` 处理一对多或多对多，避免循环查询。

```python
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.repositories.base_repo import BaseRepository


class ItemRepository(BaseRepository):
    """商品数据访问。"""

    async def get_with_tags(self, session: AsyncSession, item_id: int) -> Item | None:
        """查询商品并预加载标签。"""
        statement = select(Item).options(selectinload(Item.tags)).where(Item.id == item_id)
        result = await session.execute(statement)
        return result.scalar_one_or_none()
```

## 原生 SQL

优先使用 SQLAlchemy 表达式。确需原生 SQL 时，必须使用参数绑定，不要拼接用户输入。

```python
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def count_items_by_status(session: AsyncSession, status: int) -> int:
    """使用参数绑定统计商品数量。"""
    statement = text("SELECT COUNT(*) FROM items WHERE status = :status")
    result = await session.execute(statement, {"status": status})
    return result.scalar_one()
```

## 并发与 Session 安全

- `AsyncSession` 是请求/任务级对象，不要把同一个 session 传入多个并发任务。
- 不要这样写：`await asyncio.gather(repo.get_a(session), repo.get_b(session))`。
- 如果确实需要并发数据库任务，应为每个任务创建独立 session，并确认事务边界和连接池容量。
- 多数业务接口优先顺序执行查询，保持事务语义清晰。

## 禁止写法

- `from sqlalchemy.orm import Session` 用在异步链路。
- `session.query(Model)`。
- repository 内部 `await session.commit()` 或 `await session.rollback()`。
- 字符串拼接原生 SQL。
- 查询列表后在循环里逐条查关联数据。
- 捕获数据库异常后吞掉，或把数据库内部错误细节返回给前端。
