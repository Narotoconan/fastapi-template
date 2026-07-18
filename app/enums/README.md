# 枚举模块

`app/enums/` 存放可在 Schema、Model、Service 和 Repository 间复用的业务常量。枚举值属于公开
契约或持久化契约时，应保持稳定，不能因展示顺序变化而随意重新编号。

## 当前结构

```text
app/enums/
├── __init__.py       # 公共导出
├── common.py         # 跨业务通用枚举
└── README.md
```

模板当前只内置两个 `IntEnum`：

| 枚举 | 成员 | 值 |
| --- | --- | --- |
| `GenderEnum` | `UNKNOWN` / `MALE` / `FEMALE` | `0` / `1` / `2` |
| `StatusEnum` | `DISABLED` / `ENABLED` | `0` / `1` |

推荐从包级入口导入：

```python
from app.enums import GenderEnum, StatusEnum
```

当前源码中的 Demo Schema 仍可从 `app.enums.common` 直接导入；新增公共调用优先使用包级入口，
以降低调用方对文件布局的耦合。

## 在 Schema 中使用

```python
from pydantic import Field

from app.enums import GenderEnum, StatusEnum
from app.schemas.base_schema import BaseSchema


class UserCreate(BaseSchema):
    """创建用户请求。"""

    username: str = Field(min_length=3, max_length=20)
    gender: GenderEnum
    status: StatusEnum = Field(
        default=StatusEnum.ENABLED,
        validate_default=True,
    )
```

Pydantic 会校验输入值是否属于枚举，FastAPI 会在 OpenAPI 中展示合法选项。`BaseSchema` 使用
`use_enum_values=True`，因此经过校验的字段和 API JSON 使用原始值，例如 `GenderEnum.MALE`
对外输出为 `1`。

如果业务逻辑需要比较枚举成员，建议在进入 Schema 前后明确类型边界，不要假设
`model_dump()` 返回值始终仍是枚举实例。

## 新增业务枚举

业务枚举按领域拆分。下面是扩展示例，模板当前并未内置 `order.py`：

```python
# app/enums/order.py
from enum import IntEnum, StrEnum


class OrderStatusEnum(IntEnum):
    """订单状态。"""

    PENDING = 10
    CONFIRMED = 20
    SHIPPED = 30
    COMPLETED = 40
    CANCELLED = 90


class PaymentMethodEnum(StrEnum):
    """支付方式。"""

    CARD = "card"
    BANK_TRANSFER = "bank_transfer"
```

随后更新公共导出：

```python
# app/enums/__init__.py
from app.enums.common import GenderEnum, StatusEnum
from app.enums.order import OrderStatusEnum, PaymentMethodEnum

__all__ = [
    "GenderEnum",
    "OrderStatusEnum",
    "PaymentMethodEnum",
    "StatusEnum",
]
```

调用方即可统一使用：

```python
from app.enums import OrderStatusEnum, PaymentMethodEnum
```

## `IntEnum` 与 `StrEnum`

| 类型 | 适合场景 | 示例 |
| --- | --- | --- |
| `IntEnum` | 已明确采用整数协议或整数列的状态、等级、类型 | `OrderStatusEnum.CONFIRMED.value == 20` |
| `StrEnum` | 需要可读字符串协议的渠道、来源、策略标识 | `PaymentMethodEnum.CARD.value == "card"` |

选择依据是 API 与数据库契约，而不是单纯追求“整数更高效”。枚举只定义业务常量，不会自动完成
SQLAlchemy 列类型、数据库约束或迁移。

## 持久化与兼容性

- 已进入 API、消息或数据库的枚举值不得随意改值、复用或重新编号。
- 删除成员前先确认历史数据、兼容读取和回滚策略。
- 修改持久化值必须配套数据库迁移和调用方升级。
- 状态值使用 `10 / 20 / 30` 等间隔是可选策略，适合未来可能插入中间状态的流程，但不是硬性要求。
- 状态流转规则属于 Service，不应写进枚举类作为隐式副作用。
- ORM 字段应明确选择整数列、字符串列或 SQLAlchemy Enum，并为数据库约束和索引单独设计。

## 与错误码的边界

`ErrorCode` 虽然也是 `IntEnum`，但它属于统一错误响应协议，定义在
[`app/exceptions/errors.py`](../exceptions/errors.py)。不要在 `app/enums/` 中复制或重新导出错误码；
错误码的说明见 [异常处理文档](../exceptions/README.md)。

## 新增枚举检查清单

- 使用能表达业务含义的名称，并以 `Enum` 结尾。
- 按业务域创建文件，通用枚举才放入 `common.py`。
- 为枚举和不直观的成员添加中文说明。
- 更新 `app/enums/__init__.py` 与 `__all__`。
- 同步检查 Schema、ORM、数据库迁移、缓存、消息和 API 文档。
- 为输入校验、序列化和兼容行为补充测试。

[返回项目 README](../../README.md)
