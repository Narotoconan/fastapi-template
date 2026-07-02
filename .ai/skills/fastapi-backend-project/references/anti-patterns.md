# 常见反模式

在 review、重构、修复不规范实现时读取本文件。

## 分层反模式

错误：router 中写复杂业务和 SQL，并把空列表当成资源不存在。

```python
@router.get("/items")
async def list_items(db: DBSessionDep) -> ResponseSchema:
    statement = select(Item).where(Item.status == 1).order_by(Item.id.desc())
    result = await db.execute(statement)
    items = result.scalars().all()
    if not items:
        raise NotFoundException(message="商品不存在")
    return ResponseSchema.ok(data=items)
```

正确：router 调 service，service 调 repository。

```python
@router.get("/items")
async def list_items(db: DBSessionDep, pagination: PageDep) -> PageResponseSchema[ItemResponse]:
    """分页查询商品。"""
    items, total = await item_service.list_items(db, ItemSearch(), offset=pagination.offset, limit=pagination.limit)
    return PageResponseSchema.ok(data=items, total=total, page=pagination.page, page_size=pagination.page_size)
```

列表查询没有数据时应返回空列表和 `total=0`，不要抛 `NotFoundException`。

## 异步反模式

- 在 async 函数中使用同步 `Session`。
- 在 async 函数中调用 `time.sleep()`、同步 HTTP 请求、大文件同步读写。
- 忘记 `await session.execute(...)`。
- 把同一个 `AsyncSession` 并发传入多个 `asyncio.gather(...)` 任务。

## 异常反模式

错误：

```python
from fastapi import HTTPException

raise HTTPException(status_code=404, detail="商品不存在")
```

正确：

```python
from app.exceptions import NotFoundException

raise NotFoundException(message=f"商品 {item_id} 不存在")
```

## 日志反模式

错误：

```python
import logging

print(payload)
logging.info("created")
log.exception("failed")
```

正确：

```python
from app.core.log import log

log.info(f"商品 {item_id} 创建成功")
log.error(f"商品创建失败: error_type={type(exc).__name__}")
```

## 响应反模式

- 单个 JSON 接口绕过 `ResponseSchema` / `PageResponseSchema`。
- 业务失败手动返回 `ResponseSchema.fail(...)`，导致异常链路不统一。
- 分页接口返回普通列表，丢失 `pagination` 元信息。
- 文件下载强行包进 JSON 响应。

## 数据访问反模式

- repository 内部 `commit()` / `rollback()`，导致 service 无法控制事务边界。
- 使用字符串拼接原生 SQL。
- 查询列表后循环逐条查询关联数据造成 N+1。
- repository 依赖 FastAPI `Request`、`Depends` 或返回 `ResponseSchema`。
