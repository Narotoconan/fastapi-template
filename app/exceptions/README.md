# 异常与错误响应

`app/exceptions/` 定义业务错误码、项目异常和 FastAPI 全局异常处理器。Router、Service 和
Repository 不需要手工拼装失败 JSON；业务代码抛出项目异常，处理器负责 HTTP 状态与统一响应。

## 文件职责

| 文件 | 职责 |
| --- | --- |
| [`errors.py`](errors.py) | `ErrorCode`、默认消息和项目异常 |
| [`handlers.py`](handlers.py) | 统一错误响应与全局异常处理器 |
| [`validation_i18n.py`](validation_i18n.py) | Pydantic 校验错误的中文转换 |
| [`__init__.py`](__init__.py) | 公共导出 |

## 响应契约

所有 JSON 错误响应使用相同外层结构：

```json
{
  "code": 3001,
  "message": "订单不存在",
  "result": {}
}
```

- HTTP 状态描述协议层结果。
- `code` 描述前端是否需要差异化处理的业务错误。
- `message` 面向调用方，必须安全、具体且不包含内部敏感信息。
- `result` 默认是 `{}`；只有确有公开价值时才返回结构化错误上下文。

## 内置异常

| 异常 | HTTP 状态 | 默认业务码 | 场景 |
| --- | ---: | ---: | --- |
| `BizException` | 200，可指定 | `99999` | 通用业务失败基类 |
| `AuthException` | 401 | `1001` | 未认证或 Token 失效 |
| `ForbiddenException` | 403 | `1002` | 已认证但无权限 |
| `NotFoundException` | 404 | `3001` | 资源不存在 |
| `ParamsException` | 422 | `2001` | 通过 Pydantic 后仍不满足业务参数规则 |
| `ServiceUnavailableException` | 503 | `5001` | PostgreSQL、Redis 等关键依赖不可用 |

优先使用语义明确的子类。`BizException` 默认返回 HTTP 200 是当前兼容契约，只有客户端明确采用
“HTTP 200 + 非零业务码”时才应使用；资源、认证、权限和参数错误应使用对应 4xx 异常。

## 使用示例

### 资源不存在

```python
from app.exceptions import NotFoundException


def require_order(order: object | None, order_id: int) -> object:
    """确认订单存在并返回订单。"""
    if order is None:
        raise NotFoundException(message=f"订单 {order_id} 不存在")
    return order
```

响应：

```json
{
  "code": 3001,
  "message": "订单 99 不存在",
  "result": {}
}
```

HTTP 状态为 404。

### 认证与授权

```python
from app.exceptions import AuthException, ForbiddenException

raise AuthException(message="请先登录")
# HTTP 401, code=1001

raise ForbiddenException(message="仅管理员可执行此操作")
# HTTP 403, code=1002
```

### 通用业务失败

```python
from app.exceptions import BizException, ErrorCode

raise BizException(ErrorCode.ALREADY_EXISTS)
# HTTP 200, code=3002, message="资源已存在"

raise BizException(
    ErrorCode.FAIL,
    message="库存不足，无法创建订单",
    http_status=409,
)
# HTTP 409, code=99999
```

### 关键依赖不可用

```python
from app.exceptions import ServiceUnavailableException

raise ServiceUnavailableException(
    message="关键依赖不可用",
    result={
        "status": "unhealthy",
        "checks": {
            "database": "healthy",
            "redis": "unhealthy",
        },
    },
)
```

该异常用于 `/health` 等需要公开依赖状态的场景，返回 HTTP 503、业务码 `5001`。不要把连接串、
密码、主机内部信息或原始异常文本放入 `message` / `result`。

## 错误码

| 分段 | 枚举成员 | 值 | 默认消息 |
| --- | --- | ---: | --- |
| 成功 | `SUCCESS` | `0` | `success` |
| 通用 | `FAIL` | `99999` | 操作失败，请稍后重试 |
| 认证 | `UNAUTHORIZED` | `1001` | 未登录或登录已过期 |
| 授权 | `FORBIDDEN` | `1002` | 权限不足 |
| 参数 | `PARAMS_INVALID` | `2001` | 参数校验失败 |
| 资源 | `NOT_FOUND` | `3001` | 资源不存在 |
| 资源 | `ALREADY_EXISTS` | `3002` | 资源已存在 |
| 第三方 | `THIRD_PARTY_ERROR` | `4001` | 第三方服务异常，请稍后重试 |
| 系统 | `INTERNAL_ERROR` | `5001` | 系统内部错误，请稍后重试 |

错误码粒度以调用方是否需要差异化处理为准。数据库、缓存、超时等服务端细节通过安全日志定位，
不应为每个内部异常新增对外错误码。

## 参数校验错误

FastAPI 的 `RequestValidationError` 会自动转换为：

- HTTP 422
- 业务码 `2001`
- 第一条错误的中文 `message`
- 空对象 `result`

例如缺少 `name`：

```json
{
  "code": 2001,
  "message": "name: 该字段为必填项",
  "result": {}
}
```

当前处理器不会把完整 Pydantic 错误列表返回客户端，避免暴露内部约束并减少响应噪音。合法枚举值等
约束请通过 OpenAPI 文档查看。

`ParamsException` 用于已经通过字段校验、但不满足业务语义的参数，例如结束时间早于开始时间。

## 框架与未处理异常

全局处理器还覆盖以下异常：

| 异常来源 | 行为 |
| --- | --- |
| Starlette / FastAPI `HTTPException` 4xx | 映射业务码，原样保留 `detail` 与协议响应头；调用方必须保证 detail 不含敏感信息 |
| 原生 `HTTPException` 5xx | 保留协议响应头，但隐藏原始 detail，统一返回 `5001` |
| 未处理 `Exception` | HTTP 500、业务码 `5001`，不返回原始异常文本 |

认证场景中的 `WWW-Authenticate`、服务降级中的 `Retry-After` 等响应头会在统一转换后保留。

Service 层不要随意抛出 `HTTPException`；它是 Web 框架异常，业务失败应使用本模块的项目异常。

## 注册

应用入口已完成注册：

```python
from fastapi import FastAPI

from app.exceptions import register_exception_handlers

app = FastAPI()
register_exception_handlers(app)
```

注册后会处理：

- `BizException` 及其子类
- `RequestValidationError`
- Starlette / FastAPI `HTTPException`
- 未处理 `Exception`

## 中间件中的错误

Starlette 的用户中间件位于业务异常处理层之外。中间件中直接抛出 `BizException` 不能可靠进入
业务异常处理器，因此 JWT 等中间件使用 `build_error_response()` 主动返回统一错误：

```python
from app.exceptions import ErrorCode, build_error_response

return build_error_response(
    http_status=401,
    code=ErrorCode.UNAUTHORIZED,
    message="Token 无效，请重新登录",
)
```

该函数主要供基础设施和中间件使用，普通 Service 仍应抛出项目异常。

## 新增异常检查清单

- 先判断现有 `ErrorCode` 是否已能表达调用方处理方式。
- 新异常继承 `BizException`，固定合理的 HTTP 状态和业务码。
- 消息描述可定位的业务原因，不透传原始数据库、Redis 或第三方异常。
- 只在确有公开价值时返回 `result`，并保证内容可 JSON 编码。
- 捕获底层异常时记录安全上下文，不能吞掉异常或覆盖原始取消信号。
- 同步更新测试、本 README 和调用方契约。

[返回项目 README](../../README.md)
