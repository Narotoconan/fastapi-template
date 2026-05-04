典型 app/enums/ 目录结构

```shell
app/enums/
├── __init__.py       # 统一对外导出
├── common.py         # ✅ 已有：跨业务通用（Gender、Status、SortOrder）
├── demo.py           # 用户域：角色、登录方式、账号类型
├── order.py          # 订单域：订单状态、支付状态、支付方式、发货方式
├── product.py        # 商品域：商品状态、计量单位、商品类型
└── finance.py        # 财务域：单据类型、币种、账单状态
```
各文件内容举例
user.py — 用户域

```python
from enum import IntEnum, StrEnum

class UserRoleEnum(IntEnum):
    """用户角色"""
    SUPER_ADMIN = 1  # 超级管理员
    ADMIN       = 2  # 管理员
    STAFF       = 3  # 普通员工
    GUEST       = 4  # 访客

class LoginTypeEnum(IntEnum):
    """登录方式"""
    PASSWORD = 1  # 账号密码
    SMS      = 2  # 短信验证码
    WECHAT   = 3  # 微信扫码
```

order.py — 订单域（状态流转最复杂的一类）
```python
from enum import IntEnum

class OrderStatusEnum(IntEnum):
    """订单状态（有明确流转方向，不要用随意整数）"""
    PENDING    = 10  # 待确认
    CONFIRMED  = 20  # 已确认
    PROCESSING = 30  # 生产中
    SHIPPED    = 40  # 已发货
    COMPLETED  = 50  # 已完成
    CANCELLED  = 99  # 已取消

class PaymentStatusEnum(IntEnum):
    """支付状态"""
    UNPAID     = 0  # 未支付
    PARTIAL    = 1  # 部分支付
    PAID       = 2  # 已支付全款
    REFUNDING  = 3  # 退款中
    REFUNDED   = 4  # 已退款

class PaymentMethodEnum(StrEnum):
    """支付方式（StrEnum 更语义化，对账时直接可读）"""
    WECHAT     = "wechat"    # 微信支付
    ALIPAY     = "alipay"    # 支付宝
    BANK       = "bank"      # 银行转账
    CASH       = "cash"      # 现金
```

product.py — 商品域
```python
from enum import IntEnum, StrEnum

class ProductUnitEnum(StrEnum):
    """计量单位"""
    PCS    = "pcs"    # 个/件
    KG     = "kg"     # 千克
    METER  = "m"      # 米
    BOX    = "box"    # 箱

class ProductTypeEnum(IntEnum):
    """商品类型"""
    STANDARD  = 1  # 标准品
    CUSTOMIZE = 2  # 定制品
    SERVICE   = 3  # 服务类
```
 
两个设计规范值得注意
规范一：状态流转用间隔值（10、20、30...），留出插入空间
```python
# ❌ 新增"生产暂停"状态时，插不进去
CONFIRMED  = 2
PROCESSING = 3
SHIPPED    = 4

# ✅ 随时可以在 30~40 之间插入 35
CONFIRMED  = 20
PROCESSING = 30
SHIPPED    = 40
```

规范二：有实际含义的标识用 StrEnum，存数据库的状态码用 IntEnum
```python
# 支付渠道对接时，字符串更直观，日志/对账不需要反查枚举
PaymentMethodEnum.WECHAT  # → "wechat"，直接可读

# 订单状态存 DB，整数更高效，查询 WHERE status = 20
OrderStatusEnum.CONFIRMED  # → 20
```

__init__.py 随之扩展
```python
from app.enums.common import GenderEnum, StatusEnum, SortOrderEnum
from app.enums.user import UserRoleEnum, LoginTypeEnum
from app.enums.order import OrderStatusEnum, PaymentStatusEnum, PaymentMethodEnum
from app.enums.product import ProductUnitEnum, ProductTypeEnum
```
原则是：按业务域拆文件，通过 __init__.py 聚合导出，调用方永远只需要 from app.enums import OrderStatusEnum，不用关心它在哪个文件里。