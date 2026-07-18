# 项目组合模式示例

本文件补充当前模板中需要跨 Router、Service、Repository、数据库、缓存和测试共同完成的代码模式。单个 API 的参数与行为仍以 `SKILL.md` 指向的模块 README 和当前实现为准。

示例延续 `Item` 占位业务。复制时把方法合并进实际类，不要用片段覆盖已有模块；字段、缓存键、TTL、错误消息和约束名称必须按真实业务调整。

## 目录

- [分页列表的完整调用链](#分页列表的完整调用链)
- [唯一约束冲突转换](#唯一约束冲突转换)
- [Cache Aside 与写后失效](#cache-aside-与写后失效)
- [最小测试骨架](#最小测试骨架)
- [落地检查](#落地检查)

## 分页列表的完整调用链

Repository 分别执行数据查询与总数查询。新增筛选条件时，两条语句必须应用同一组条件。

```python
# app/repositories/item_repo.py
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.item import Item
from app.repositories.base_repo import BaseRepository


class ItemRepository(BaseRepository):
    """示例业务对象的数据访问。"""

    async def list_page(
        self,
        session: AsyncSession,
        *,
        offset: int,
        limit: int,
    ) -> tuple[list[Item], int]:
        """分页查询业务对象并返回独立总数。"""
        data_statement = select(Item).order_by(Item.id).offset(offset).limit(limit)
        count_statement = select(func.count(Item.id))

        item_result = await session.scalars(data_statement)
        total = await session.scalar(count_statement)
        return list(item_result.all()), total or 0
```

Service 把 ORM 对象转换为公开 Schema，不向 Router 暴露持久化对象：

```python
# app/services/item_service.py
from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.item_repo import ItemRepository
from app.schemas.item_schema import ItemResponse


class ItemService:
    """示例业务对象的业务编排。"""

    def __init__(self, repository: ItemRepository) -> None:
        self._repository = repository

    async def list_items(
        self,
        session: AsyncSession,
        *,
        offset: int,
        limit: int,
    ) -> tuple[list[ItemResponse], int]:
        """分页查询并转换公开响应字段。"""
        items, total = await self._repository.list_page(
            session,
            offset=offset,
            limit=limit,
        )
        return [ItemResponse.model_validate(item) for item in items], total
```

Router 使用 `PageDep` 解析分页 Query，并用 `PageResponseSchema` 统一组装分页元信息：

```python
# app/api/item.py
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies.db import get_db
from app.dependencies.pagination import PageDep
from app.schemas.item_schema import ItemResponse
from app.schemas.response import PageResponseSchema
from app.services.item_service import item_service

DBSessionDep = Annotated[AsyncSession, Depends(get_db)]

router_item = APIRouter(prefix="/items", tags=["条目"])


@router_item.get("", summary="分页查询条目")
async def list_items_api(
    session: DBSessionDep,
    pagination: PageDep,
) -> PageResponseSchema[ItemResponse]:
    """分页查询业务对象。"""
    items, total = await item_service.list_items(
        session,
        offset=pagination.offset,
        limit=pagination.limit,
    )
    return PageResponseSchema.ok(
        data=items,
        total=total,
        page=pagination.page,
        page_size=pagination.page_size,
    )
```

如果存在筛选条件，继续通过请求 Schema 接收，不要把业务筛选塞入 `PageDep`。

## 唯一约束冲突转换

预查询只能改善提示，最终一致性依赖具名数据库唯一约束。完整分层示例中的 `uq_items_name` 让 Service 能识别预期冲突，而不是把所有 `IntegrityError` 都误报为“已存在”。

当前 PostgreSQL + asyncpg 组合可通过 SQLSTATE 和原始驱动异常中的约束名进行识别：

```python
# app/services/item_service.py
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.exceptions import BizException, ErrorCode
from app.models.item import ITEM_NAME_UNIQUE_CONSTRAINT
from app.repositories.item_repo import ItemRepository
from app.schemas.item_schema import ItemCreate, ItemResponse


def is_named_unique_violation(
    error: IntegrityError,
    constraint_name: str,
) -> bool:
    """识别当前 asyncpg 驱动返回的具名唯一约束冲突。"""
    driver_error = getattr(error.orig, "__cause__", None)
    return (
        getattr(error.orig, "sqlstate", None) == "23505"
        and getattr(driver_error, "constraint_name", None) == constraint_name
    )


class ItemService:
    """示例业务对象的业务编排。"""

    def __init__(self, repository: ItemRepository) -> None:
        self._repository = repository

    async def create_item(
        self,
        session: AsyncSession,
        payload: ItemCreate,
    ) -> ItemResponse:
        """创建业务对象并转换预期的名称冲突。"""
        try:
            async with session.begin():
                item = await self._repository.create(
                    session,
                    name=payload.name,
                )
                response = ItemResponse.model_validate(item)
        except IntegrityError as error:
            if not is_named_unique_violation(
                error,
                ITEM_NAME_UNIQUE_CONSTRAINT,
            ):
                raise
            raise BizException(
                ErrorCode.ALREADY_EXISTS,
                message=f"条目名称 {payload.name} 已存在",
                http_status=409,
            ) from error

        return response
```

事务上下文会先回滚，再由 Service 转换异常。更换数据库或驱动后必须重新确认异常属性；不要解析完整数据库错误字符串，也不要把 SQL、参数或驱动详情返回给客户端。

## Cache Aside 与写后失效

先在 `app/core/cache/prefixes.py` 为真实业务增加稳定键前缀。以下名称只是示例：

```python
class RedisPrefixes:
    """业务模块缓存键前缀常量。"""

    ITEM_DETAIL = "item:detail"
```

只读详情可在 Service 中使用 Cache Aside。示例只对 Redis 命令执行期间的连接和超时异常降级；序列化错误或响应校验错误继续暴露，避免掩盖缺陷：

```python
# app/services/item_service.py
from redis.exceptions import ConnectionError as RedisConnectionError
from redis.exceptions import TimeoutError as RedisTimeoutError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.cache import RedisPrefixes, get_redis_manager
from app.core.log import log
from app.exceptions import NotFoundException
from app.repositories.item_repo import ItemRepository
from app.schemas.item_schema import ItemResponse

CACHE_CONNECTION_ERRORS = (RedisConnectionError, RedisTimeoutError)
ITEM_DETAIL_TTL_SECONDS = 300


class ItemService:
    """示例业务对象的业务编排。"""

    def __init__(self, repository: ItemRepository) -> None:
        self._repository = repository

    @staticmethod
    def _detail_cache_key(item_id: int) -> str:
        return f"{RedisPrefixes.ITEM_DETAIL}:{item_id}"

    async def get_item_cached(
        self,
        session: AsyncSession,
        item_id: int,
    ) -> ItemResponse:
        """优先读取缓存，Redis 命令连接或超时故障时回源数据库。"""
        redis_manager = get_redis_manager()
        cache_key = self._detail_cache_key(item_id)

        try:
            cached_item = await redis_manager.get(cache_key)
        except CACHE_CONNECTION_ERRORS as error:
            log.warning(f"读取条目缓存失败，回源数据库 | item_id={item_id} | error_type={type(error).__name__}")
            cached_item = None

        if cached_item is not None:
            return ItemResponse.model_validate(cached_item)

        item = await self._repository.get_by_id(session, item_id)
        if item is None:
            raise NotFoundException(message=f"条目 {item_id} 不存在")

        response = ItemResponse.model_validate(item)
        try:
            await redis_manager.set(
                cache_key,
                response.model_dump(mode="json"),
                ex=ITEM_DETAIL_TTL_SECONDS,
            )
        except CACHE_CONNECTION_ERRORS as error:
            log.warning(f"回填条目缓存失败 | item_id={item_id} | error_type={type(error).__name__}")

        return response
```

当前 `RedisManager` 在尚未初始化或重连耗尽后可能抛出普通 `RuntimeError`。不要把所有 `RuntimeError` 加入降级范围；如果业务要求此状态也回源，应先在缓存基础设施中定义并导出明确的“缓存不可用”异常，再由 Service 精确捕获。

写操作的 Repository 方法仍然只修改数据库对象并 `flush()`：

```python
# app/repositories/item_repo.py
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.item import Item
from app.repositories.base_repo import BaseRepository


class ItemRepository(BaseRepository):
    """示例业务对象的数据访问。"""

    async def update_name(
        self,
        session: AsyncSession,
        *,
        item_id: int,
        name: str,
    ) -> Item | None:
        """更新业务对象名称，但不提交调用方事务。"""
        item = await session.get(Item, item_id)
        if item is None:
            return None

        item.name = name
        await session.flush()
        return item
```

Service 先提交数据库事务，再失效缓存。下面的示例选择“缓存删除失败时记录错误并允许短暂不一致”；如果业务要求更强一致性，应改为可靠补偿，而不是假设抛出异常可以回滚已经提交的数据库事务：

将下面的方法合并进同一个 `ItemService`：

```python
from redis.exceptions import ConnectionError as RedisConnectionError
from redis.exceptions import TimeoutError as RedisTimeoutError
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.cache import get_redis_manager
from app.core.log import log
from app.exceptions import BizException, ErrorCode, NotFoundException
from app.models.item import ITEM_NAME_UNIQUE_CONSTRAINT
from app.schemas.item_schema import ItemResponse

CACHE_CONNECTION_ERRORS = (RedisConnectionError, RedisTimeoutError)


async def update_item_name(
    self,
    session: AsyncSession,
    *,
    item_id: int,
    name: str,
) -> ItemResponse:
    """更新业务对象，并在提交后失效详情缓存。"""
    try:
        async with session.begin():
            item = await self._repository.update_name(
                session,
                item_id=item_id,
                name=name,
            )
            if item is None:
                raise NotFoundException(message=f"条目 {item_id} 不存在")
            response = ItemResponse.model_validate(item)
    except IntegrityError as error:
        driver_error = getattr(error.orig, "__cause__", None)
        is_name_conflict = (
            getattr(error.orig, "sqlstate", None) == "23505"
            and getattr(driver_error, "constraint_name", None) == ITEM_NAME_UNIQUE_CONSTRAINT
        )
        if not is_name_conflict:
            raise
        raise BizException(
            ErrorCode.ALREADY_EXISTS,
            message=f"条目名称 {name} 已存在",
            http_status=409,
        ) from error

    try:
        await get_redis_manager().delete(self._detail_cache_key(item_id))
    except CACHE_CONNECTION_ERRORS as error:
        log.error(f"删除条目缓存失败，允许短暂不一致 | item_id={item_id} | error_type={type(error).__name__}")

    return response
```

示例内联了与创建路径相同的唯一约束判定条件，以便代码块可独立阅读；实际落地时应复用同一个
`is_named_unique_violation()` helper，避免创建与更新路径的判定逻辑发生偏移。缓存失效必须继续放在
事务成功提交之后，发生约束冲突或其他数据库异常时不得删除缓存。

提交后删除属于最终一致性方案，仍存在经典竞态：读请求缓存未命中并查到旧值，写请求随后提交并删除缓存，最后读请求又把旧值回填。强一致场景需要按业务设计版本化缓存键、带版本校验的写入或可靠补偿机制；不能把一次删除视为完整的一致性保证。

Repository 不操作缓存，也不提交事务。TTL、允许降级的异常和一致性策略必须从当前配置、README 与业务要求确认。

## 最小测试骨架

先核对 `pyproject.toml` 与现有测试；如果仍未启用异步 pytest 插件，Service 测试可以沿用仓库现有的 `asyncio.run()` 与标准库 mock：

```python
import asyncio
from unittest.mock import AsyncMock, create_autospec

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.exceptions import NotFoundException
from app.repositories.item_repo import ItemRepository
from app.services.item_service import ItemService


def test_get_item_raises_not_found() -> None:
    """Repository 返回空值时，Service 转换为项目资源异常。"""
    repository = create_autospec(ItemRepository, instance=True)
    repository.get_by_id = AsyncMock(return_value=None)
    session = create_autospec(AsyncSession, instance=True)

    with pytest.raises(NotFoundException, match="条目 42 不存在"):
        asyncio.run(ItemService(repository).get_item(session, 42))
```

API 契约测试应注册项目异常处理器，并覆盖数据库依赖，避免连接真实 PostgreSQL：

```python
from collections.abc import AsyncGenerator
from unittest.mock import create_autospec

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.item import router_item
from app.dependencies.db import get_db
from app.exceptions import register_exception_handlers
from app.schemas.item_schema import ItemResponse
from app.services.item_service import item_service


def create_item_client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    """创建只装配示例路由的测试客户端。"""

    async def override_get_db() -> AsyncGenerator[AsyncSession, None]:
        yield create_autospec(AsyncSession, instance=True)

    async def get_item(
        _session: AsyncSession,
        item_id: int,
    ) -> ItemResponse:
        return ItemResponse(id=item_id, name="示例条目")

    monkeypatch.setattr(item_service, "get_item", get_item)

    app = FastAPI()
    register_exception_handlers(app)
    app.dependency_overrides[get_db] = override_get_db
    app.include_router(router_item)
    return TestClient(app, raise_server_exceptions=False)


def test_get_item_returns_unified_response(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """详情接口返回统一成功响应。"""
    response = create_item_client(monkeypatch).get("/items/1")

    assert response.status_code == 200
    assert response.json() == {
        "code": 0,
        "message": "success",
        "result": {"id": 1, "name": "示例条目"},
    }
```

Repository 的查询、唯一约束和并发冲突应使用真实 PostgreSQL 集成测试验证；mock 只能证明调用与业务转换，不能证明 SQL 或约束行为。

## 落地检查

- 片段是否合并进现有类，而不是覆盖已实现方法。
- 分页数据与总数查询是否使用相同过滤条件和稳定排序。
- 唯一冲突是否只转换预期 SQLSTATE 与具名约束。
- 缓存键、TTL、精确降级异常、并发竞态和写后失效策略是否来自当前契约。
- Service、API 与 PostgreSQL 集成测试是否分别覆盖自己的责任边界。
