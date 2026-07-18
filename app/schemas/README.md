# Schema 模型与统一响应

`app/schemas/` 负责请求校验、响应建模、公共序列化约定和 JSON API 的统一外层结构。
业务接口应优先返回明确的 Pydantic Schema，再由 `ResponseSchema` 或
`PageResponseSchema` 组装成功响应。

## 文件职责

| 文件 | 职责 |
| --- | --- |
| [`base_schema.py`](base_schema.py) | 公共 Pydantic 基类与枚举、日期时间序列化约定 |
| [`response.py`](response.py) | 普通响应、分页响应与分页元信息 |
| [`demo_schema.py`](demo_schema.py) | Demo 请求/响应模型；其中部分仅作扩展示例 |
| [`health_schema.py`](health_schema.py) | 健康检查的真实响应模型 |
| [`__init__.py`](__init__.py) | 导出公共 Schema 与响应类型 |

当前使用情况：

- `UserSearch`：`GET /demo/search` 的 Query 模型。
- `UserSearchResponse`：`GET /demo/list` 的分页元素类型。
- `HealthCheckResult`：`GET /health` 的实际业务结果。
- `UserCreate`、`UserResponse`：展示枚举用法，当前没有对应业务路由。

## `BaseSchema` 公共约定

所有业务请求和响应模型都应继承 `BaseSchema`：

```python
from datetime import datetime

from pydantic import ConfigDict, Field

from app.schemas.base_schema import BaseSchema


class OrderResponse(BaseSchema):
    """订单详情响应。"""

    model_config = ConfigDict(from_attributes=True)

    id: int = Field(description="订单 ID")
    order_no: str = Field(description="订单号")
    created_at: datetime = Field(description="创建时间")
```

### 枚举

`BaseSchema` 配置了 `use_enum_values=True`。枚举字段通过校验后以 `.value` 参与 API JSON 输出，
FastAPI 也会把合法枚举值写入 OpenAPI。

需要注意：

- Python 对象中的默认枚举值不一定会在普通 `model_dump()` 时提前转换，因为 Pydantic 默认不校验
  默认值。
- 对外契约应以 API JSON 或 `model_dump(mode="json")` 为准。
- 如果业务代码要求默认值在 Python dump 中也始终转换，可在具体字段使用
  `Field(..., validate_default=True)`，并补充测试。

枚举定义与扩展方式见 [枚举模块文档](../enums/README.md)。

### 日期时间

明确声明为 `datetime` 的 Schema 字段在 JSON 中输出为：

```text
YYYY-MM-DD HH:MM:SS
```

例如 `2026-07-16 08:30:45`。不要把裸 `datetime`、ORM 对象或包含敏感字段的任意字典直接放入
`ResponseSchema.result`；`result` 的类型是 `Any`，无法提供稳定字段约束，也可能绕过项目的日期
时间格式。应先转换为明确响应 Schema。

### ORM 转换

`BaseSchema` 没有全局启用 `from_attributes=True`。需要从 ORM 对象构造响应时，推荐在具体响应模型中
显式配置：

```python
from pydantic import ConfigDict

from app.schemas.base_schema import BaseSchema


class UserResponse(BaseSchema):
    """用户公开信息。"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str


user_response = UserResponse.model_validate(user_orm)
```

也可以在单次转换时调用：

```python
user_response = UserResponse.model_validate(user_orm, from_attributes=True)
```

响应模型只声明允许公开的字段，避免密码哈希、Token 或内部状态被意外返回或写入缓存。

## 请求 Schema

请求模型负责字段类型、范围和 OpenAPI 描述：

```python
from pydantic import Field

from app.enums import GenderEnum
from app.schemas.base_schema import BaseSchema


class UserCreate(BaseSchema):
    """创建用户请求。"""

    username: str = Field(min_length=3, max_length=20, description="用户名")
    gender: GenderEnum = Field(description="性别")
```

复杂 GET 查询可以使用 Pydantic Query 模型：

```python
from typing import Annotated

from fastapi import APIRouter, Query

from app.schemas.demo_schema import UserSearch
from app.schemas.response import ResponseSchema

router = APIRouter()


@router.get("/users/search")
async def search_users(params: Annotated[UserSearch, Query()]) -> ResponseSchema:
    """按查询条件搜索用户。"""
    return ResponseSchema.ok(data=params.model_dump(mode="json"))
```

需要数据库或外部服务才能完成的语义校验应放在依赖或 service 中，不要塞进纯 Pydantic 字段校验器。

## 普通成功响应

```python
from app.schemas.response import ResponseSchema


def build_user_response() -> ResponseSchema:
    """构造用户成功响应。"""
    return ResponseSchema.ok(
        data={"id": 1, "name": "示例用户"},
        message="获取成功",
    )
```

响应体：

```json
{
  "code": 0,
  "message": "获取成功",
  "result": {
    "id": 1,
    "name": "示例用户"
  }
}
```

`ResponseSchema.ok(data=None)` 会把 `result` 规范为 `{}`。`ResponseSchema.fail()` 虽然可用，
但业务代码不应手工拼装失败响应；请抛出项目异常，让全局处理器统一生成。

## 分页响应

优先使用 `PageDep` 接收分页 Query 参数：

| 参数 / 属性 | 约束或含义 |
| --- | --- |
| `page` | 从 1 开始 |
| `page_size` | 1～100，默认 10 |
| `offset` | `(page - 1) * page_size` |
| `limit` | 等于 `page_size` |

```python
from fastapi import APIRouter

from app.dependencies.pagination import PageDep
from app.schemas.demo_schema import UserSearchResponse
from app.schemas.response import PageResponseSchema

router = APIRouter()


@router.get("/users")
async def list_users(
    pagination: PageDep,
) -> PageResponseSchema[UserSearchResponse]:
    """分页返回用户。"""
    users = [
        {
            "name": "示例用户",
            "email": "user@example.com",
            "date": "2026-07-16 08:30:45",
        }
    ]
    return PageResponseSchema.ok(
        data=users,
        total=1,
        page=pagination.page,
        page_size=pagination.page_size,
    )
```

响应体：

```json
{
  "code": 0,
  "message": "success",
  "result": {
    "data": [
      {
        "name": "示例用户",
        "email": "user@example.com",
        "date": "2026-07-16 08:30:45"
      }
    ],
    "pagination": {
      "page": 1,
      "page_size": 10,
      "total": 1,
      "total_pages": 1,
      "has_next": false,
      "has_prev": false
    }
  }
}
```

`PageResponseSchema[T].ok()` 根据 `total` 和 `page_size` 计算总页数。Repository 应分别返回当前页
数据和总记录数，Router 不应自行编写复杂查询。

## 文件与流式响应

文件下载不使用 JSON 外层包装，直接返回 FastAPI / Starlette Response：

```python
import io

from fastapi.responses import FileResponse, StreamingResponse


async def export_csv() -> StreamingResponse:
    """导出内存中的 CSV。"""
    content = "id,name\n1,示例用户".encode("utf-8-sig")
    return StreamingResponse(
        io.BytesIO(content),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=users.csv"},
    )


async def download_report() -> FileResponse:
    """下载已有报告文件。"""
    return FileResponse(
        path="/data/reports/report.pdf",
        media_type="application/pdf",
        filename="report.pdf",
    )
```

下载失败等错误场景仍应抛出项目异常，保持统一错误响应。

## 错误响应

业务层只抛出异常：

```python
from app.exceptions import BizException, ErrorCode, NotFoundException

raise NotFoundException(message="订单不存在")
# HTTP 404 -> {"code": 3001, "message": "订单不存在", "result": {}}

raise BizException(ErrorCode.FAIL, message="库存不足")
# 默认 HTTP 200 -> {"code": 99999, "message": "库存不足", "result": {}}
```

FastAPI / Pydantic 参数错误会自动转换为 HTTP 422、业务码 `2001`，`message` 使用第一条中文错误，
`result` 为 `{}`。详细规则见 [异常处理文档](../exceptions/README.md)。

## 新增 Schema 检查清单

- 继承 `BaseSchema`，并使用有业务含义的类名。
- 使用 `Field` 声明范围、默认值和 OpenAPI 描述。
- 请求、响应模型分离，响应模型只公开允许返回的字段。
- ORM 响应明确配置 `from_attributes=True`。
- 日期时间字段显式声明为 `datetime`，不要依赖 `Any` 容器的隐式编码。
- 分页接口使用 `PageDep` 和 `PageResponseSchema[T]`。
- JSON 失败响应交给全局异常处理器。

[返回项目 README](../../README.md)
