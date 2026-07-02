# 缓存与限流规范

在使用 Redis 缓存、缓存装饰器、业务缓存键、接口限流时读取本文件。

## Redis 使用位置

- 查询类缓存优先放在 service 层，由 service 决定缓存命中、失效和回源。
- repository 只负责数据库访问，不直接依赖 Redis。
- router 不处理缓存细节，只调用 service。

## 基本用法

```python
from app.core.cache import RedisPrefixes, get_redis_manager


async def get_user_profile(user_id: int) -> dict[str, object]:
    """从 Redis 读取用户资料缓存。"""
    redis_manager = get_redis_manager()
    cache_key = f"{RedisPrefixes.USER_PROFILE}:{user_id}"
    return await redis_manager.hgetall(cache_key)
```

## 缓存装饰器

只读、入参稳定、返回值可序列化的查询可以使用 `@cache(...)`。不要把 `AsyncSession`、`Request`、ORM 对象等不稳定对象作为被缓存函数入参。

```python
from app.core.cache import cache


@cache(key_prefix="item:category-options", ttl=3600)
async def get_item_category_options() -> list[dict[str, int | str]]:
    """读取商品分类选项缓存。"""
    return [
        {"label": "默认分类", "value": 1},
    ]
```

使用装饰器前确认：

- 不缓存包含密码、Token、密钥等敏感字段的数据。
- TTL 明确，不使用永久缓存承载易变业务数据。
- 写操作成功后有对应的缓存删除或覆盖策略。

## 缓存失效

写操作应在事务成功后处理缓存失效，避免数据库回滚但缓存已被更新。

```python
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.cache import get_redis_manager
from app.repositories.item_repo import item_repository
from app.schemas.item_schema import ItemResponse, ItemUpdate


async def update_item(session: AsyncSession, item_id: int, payload: ItemUpdate) -> ItemResponse:
    """更新商品并清理详情缓存。"""
    async with session.begin():
        item = await item_repository.update(session, item_id, payload)

    redis_manager = get_redis_manager()
    await redis_manager.delete(f"item:detail:{item_id}")
    return ItemResponse.model_validate(item)
```

## 限流装饰器

`@rate_limit(...)` 用于需要显式限流的接口。FastAPI route 装饰器必须在 `@rate_limit(...)` 上方，接口必须接收名为 `request` 的 `Request` 参数。

```python
from fastapi import APIRouter, Request

from app.core.rate_limit import rate_limit

router_item = APIRouter(prefix="/items", tags=["商品管理"])


@router_item.post("", summary="创建商品")
@rate_limit("10/minute")
async def create_item_api(request: Request, payload: ItemCreate, db: DBSessionDep) -> ResponseSchema:
    """创建商品。"""
    item = await item_service.create_item(db, payload)
    return ResponseSchema.ok(data=item.model_dump(), message="创建成功")
```

注意：

- 未标注 `@rate_limit(...)` 的接口不受限流影响。
- 配置关闭时，标注的接口也不会访问限流存储。
- Redis 限流存储异常时项目按 fail-open 处理，记录日志并放行请求。
