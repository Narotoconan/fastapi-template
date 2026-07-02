# 错误处理规范

在新增业务规则、权限判断、参数语义校验、中间件错误响应时读取本文件。

## 异常选择

`AuthException`、`ForbiddenException`、`NotFoundException`、`ParamsException` 都继承自 `BizException`。优先使用这些语义化子类，不是为了区分“业务异常/非业务异常”，而是为了让 HTTP 状态码、业务错误码和前端处理语义更准确。无法归入明确语义的业务失败，再直接使用 `BizException(...)`。

| 场景 | 使用 |
| --- | --- |
| 未登录、Token 缺失、Token 失效 | `AuthException(message="请先登录")` |
| 已登录但无权限 | `ForbiddenException(message="仅管理员可操作")` |
| 资源不存在 | `NotFoundException(message=f"商品 {item_id} 不存在")` |
| 请求参数格式已通过 Pydantic，但跨字段或查询范围等参数语义非法 | `ParamsException(message="开始时间不能晚于结束时间")` |
| 资源已存在、库存不足、余额不足、状态不允许等业务失败 | `BizException(ErrorCode.ALREADY_EXISTS, message="资源已存在")` 或 `BizException(ErrorCode.FAIL, message="...")` |
| 未捕获系统错误 | 不吞异常，让全局 handler 返回 `ErrorCode.INTERNAL_ERROR` |

## 参数错误与业务失败边界

- 字段级约束优先放在 Pydantic schema，例如 `price: int = Field(..., gt=0)`。
- 跨字段参数约束使用 `ParamsException`，例如开始时间不能晚于结束时间。
- 已持久化资源的业务状态不满足操作前置条件，使用 `BizException`，例如商品未设置价格不能发布、库存不足、订单已关闭不能取消。

## Service 层示范

```python
from app.exceptions import BizException, ErrorCode, ForbiddenException, NotFoundException


async def publish_item(session: AsyncSession, item_id: int, current_user_id: int) -> ItemResponse:
    """发布商品并校验业务状态。"""
    async with session.begin():
        item = await item_repository.get_by_id(session, item_id)
        if item is None:
            raise NotFoundException(message=f"商品 {item_id} 不存在")

        if item.owner_id != current_user_id:
            raise ForbiddenException(message="只能发布自己的商品")

        if item.price <= 0:
            raise BizException(ErrorCode.FAIL, message="商品价格必须大于 0 后才能发布")

        if item.status == ItemStatus.PUBLISHED:
            raise BizException(ErrorCode.FAIL, message="商品已发布，无需重复操作")

        item = await item_repository.update_status(session, item_id, ItemStatus.PUBLISHED)

    return ItemResponse.model_validate(item)
```

## Router 层不要手动构造失败响应

错误写法：

```python
return ResponseSchema.fail(message="商品不存在", code=ErrorCode.NOT_FOUND)
```

正确写法：

```python
raise NotFoundException(message=f"商品 {item_id} 不存在")
```

全局异常处理器会统一生成：

```json
{"code": 3001, "message": "商品 1 不存在", "result": {}}
```

## Middleware 错误响应

中间件层无法总是依赖 FastAPI route 异常处理流程。需要直接返回统一格式时，使用 `build_error_response(...)`。

```python
from fastapi import status

from app.exceptions import ErrorCode, build_error_response


return build_error_response(
    http_status=status.HTTP_401_UNAUTHORIZED,
    code=ErrorCode.UNAUTHORIZED,
    message="请先登录",
)
```

## 日志原则

- 业务异常可用 `log.warning(...)` 记录必要上下文。
- 系统异常用 `log.error(...)`，但不要向前端透传 DB、Redis、第三方错误细节。
- 日志只写可定位的信息，例如 `path`、资源 ID、错误类型；不要写密码、Token、密钥、手机号、身份证号。
