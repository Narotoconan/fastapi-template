# 测试与验证规范

在完成代码修改前读取本文件，按变更范围选择最小但有效的验证集。

## 目录

- [必跑质量门禁](#必跑质量门禁)
- [测试选择](#测试选择)
- [Router 测试示范](#router-测试示范)
- [Service 测试示范](#service-测试示范)
- [最终回复需要包含](#最终回复需要包含)

## 必跑质量门禁

修改 Python 代码后至少运行：

```bash
uv run ruff format <changed-python-files>
uv run ruff check <changed-python-files>
uv run ty check
```

如果改动跨多个模块或 import 影响全局，运行：

```bash
uv run ruff format .
uv run ruff check .
uv run ty check
```

不要执行：

```bash
uv run ruff check . --fix
```

## 测试选择

- 修改 router：优先增加或运行接口测试，断言 HTTP 状态码、统一响应结构、异常响应。
- 修改 service：优先覆盖业务分支、权限分支、异常分支，可 monkeypatch repository。
- 修改 repository：优先使用真实测试数据库 fixture；没有数据库 fixture 时不要伪造 repository 测试通过。
- 修改缓存、限流、外部服务：参考 `tests/test_rate_limit.py`，用内存实现或 monkeypatch 隔离真实 Redis/外部依赖。
- 只改文档或 skill：可不运行 Ruff、ty、pytest，但最终回复说明原因。

## Router 测试示范

```python
from collections.abc import AsyncGenerator
from typing import cast

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.item import router_item
from app.dependencies.db import get_db
from app.exceptions import NotFoundException, register_exception_handlers
from app.services.item_service import item_service


async def override_get_db() -> AsyncGenerator[AsyncSession, None]:
    """提供不连接真实数据库的测试会话替身。"""
    yield cast(AsyncSession, object())


def create_client() -> TestClient:
    """创建仅注册商品路由的测试客户端。"""
    app = FastAPI()
    register_exception_handlers(app)
    app.dependency_overrides[get_db] = override_get_db
    app.include_router(router_item)
    return TestClient(app)


def test_get_item_not_found(monkeypatch: pytest.MonkeyPatch) -> None:
    """商品不存在时返回统一错误格式。"""

    async def mock_get_item(_session: AsyncSession, item_id: int) -> None:
        raise NotFoundException(message=f"商品 {item_id} 不存在")

    monkeypatch.setattr(item_service, "get_item", mock_get_item)
    client = create_client()
    response = client.get("/items/999")

    assert response.status_code == 404
    assert response.json()["code"] == 3001
```

## Service 测试示范

```python
import asyncio
from typing import cast

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.exceptions import NotFoundException
from app.repositories.item_repo import item_repository
from app.services.item_service import item_service


def test_get_item_raises_not_found(monkeypatch: pytest.MonkeyPatch) -> None:
    """商品不存在时 service 抛出项目统一异常。"""

    async def mock_get_by_id(_session: AsyncSession, _item_id: int) -> None:
        return None

    monkeypatch.setattr(item_repository, "get_by_id", mock_get_by_id)

    async def run_case() -> None:
        with pytest.raises(NotFoundException):
            await item_service.get_item(cast(AsyncSession, object()), 1)

    asyncio.run(run_case())
```

## 最终回复需要包含

- 修改摘要。
- 关键文件。
- 验证命令和结果。
- 未运行的检查及原因。
- 仍存在的风险或假设。
