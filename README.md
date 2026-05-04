# anda-erp-alpha · FastAPI Template

> 基于 **FastAPI + Python 3.12** 的后端项目模板，集成异步数据库、Redis 缓存、JWT 鉴权、统一响应/异常处理等常用基础设施，开箱即用。

---

## 目录

- [技术栈](#技术栈)
- [项目结构](#项目结构)
- [快速开始](#快速开始)
- [环境变量配置](#环境变量配置)
- [核心模块](#核心模块)
  - [统一响应格式](#统一响应格式)
  - [异常处理](#异常处理)
  - [JWT 鉴权](#jwt-鉴权)
  - [Redis 缓存](#redis-缓存)
  - [数据库](#数据库)
  - [日志系统](#日志系统)
  - [分页依赖](#分页依赖)
  - [中间件](#中间件)
- [新增路由](#新增路由)
- [代码规范](#代码规范)

---

## 技术栈

| 类别 | 技术 |
|------|------|
| 语言 | Python 3.12 |
| Web 框架 | FastAPI 0.115+ |
| ASGI 服务器 | Uvicorn |
| ORM | SQLAlchemy 2.0（全异步） |
| 数据库驱动 | asyncpg（PostgreSQL） |
| 缓存 | Redis 5.0+（异步） |
| 鉴权 | PyJWT（HS256） |
| 配置管理 | Pydantic-Settings（支持 `.env`） |
| 日志 | Loguru |
| 包管理 | [uv](https://docs.astral.sh/uv/) |
| 代码检查/格式化 | [Ruff](https://docs.astral.sh/ruff/) |

---

## 项目结构

```
anda-erp-alpha/
├── main.py                    # 应用入口（配置 → 日志 → FastAPI 按序初始化）
├── pyproject.toml             # 项目元数据 & Ruff 配置
├── app/
│   ├── api/                   # 路由层（APIRouter）
│   ├── core/
│   │   ├── cache/             # Redis 异步缓存模块
│   │   ├── database/          # PostgreSQL 异步引擎（SQLAlchemy 2.0）
│   │   ├── events/            # 生命周期钩子（startup / shutdown）
│   │   └── log/               # Loguru 封装
│   ├── dependencies/          # FastAPI 依赖注入（分页、DB Session 等）
│   ├── exceptions/            # 自定义异常类 & 全局异常处理器
│   ├── middlewares/           # CORS / GZip / JWT 中间件
│   ├── models/                # SQLAlchemy ORM 模型基类
│   ├── repositories/          # 数据库访问层（Repository 模式）
│   ├── schemas/               # Pydantic Schema（请求体/响应体）
│   ├── scheduler/             # 定时任务（可扩展）
│   ├── services/              # 业务逻辑层
│   └── utils/                 # 工具函数（UUIDv7 等）
└── config/                    # 各模块配置，统一由 settings.py 汇总
    ├── settings.py            # 全局 Settings 入口（lru_cache 单例）
    ├── app_config.py          # 应用基础配置
    ├── cache_config.py        # Redis 配置
    ├── database_config.py     # 数据库配置
    ├── logger_config.py       # 日志配置
    └── middleware_config.py   # CORS / GZip / JWT 配置
```

---

## 快速开始

### 1. 安装依赖

```bash
# 安装 uv（若未安装）
pip install uv

# 创建虚拟环境并同步依赖
uv sync
```

### 2. 配置环境变量

在项目根目录创建 `.env` 文件并按��填写（所有配置均有默认值，最少只需配置数据库连接）：

```dotenv
# 数据库
DB_HOST=localhost
DB_PORT=5432
DB_USER=postgres
DB_PASSWORD=your_password
DB_NAME=anda_erp

# Redis
REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_PASSWORD=

# JWT（生产环境必须替换！）
JWT_SECRET_KEY=change-me-in-production-use-env-var
```

### 3. 启动服务

```bash
uv run uvicorn main:app --reload
```

| 地址 | 说明 |
|------|------|
| http://localhost:8000/docs | Swagger UI 交互文档 |
| http://localhost:8000/redoc | ReDoc 文档 |
| http://localhost:8000/openapi.json | OpenAPI Schema |

---

## 环境变量配置

所有配置均通过 **Pydantic-Settings** 管理，优先读取环境变量，其次 `.env` 文件，最后使用代码内默认值。

### 数据库

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `DB_HOST` | `localhost` | PostgreSQL 主机地址 |
| `DB_PORT` | `5432` | 端口 |
| `DB_USER` | `postgres` | 用户名 |
| `DB_PASSWORD` | — | 密码 |
| `DB_NAME` | `anda_erp` | 数据库名 |

### Redis 缓存

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `REDIS_HOST` | `localhost` | 主机地址 |
| `REDIS_PORT` | `6379` | 端口 |
| `REDIS_DB` | `0` | 数据库编号 |
| `REDIS_PASSWORD` | `None` | 认证密码（可选） |
| `REDIS_MAX_CONNECTIONS` | `10` | 连接池最大连接数 |
| `REDIS_TIMEOUT` | `5` | 连接超时（秒） |
| `REDIS_PREFIX` | `anda_erp` | 项目级键前缀，多项目共享 Redis 实例时用于数据隔离 |

### JWT 鉴权

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `JWT_SECRET_KEY` | `change-me-in-production-use-env-var` | ⚠️ 生产环境必须替换为强随机值 |
| `JWT_ALGORITHM` | `HS256` | 签名算法 |
| `JWT_ACCESS_TOKEN_EXPIRE_HOUR` | `24` | Token 有效期（小时） |
| `JWT_PUBLIC_PATHS` | `/docs`, `/redoc`, `/health` 等 | 跳过鉴权的公开路���（前缀匹配） |

### 中间件

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `CORS_ALLOW_ORIGINS` | `["*"]` | 允许的跨域来源，生产环境应填写具体域名 |
| `CORS_ALLOW_CREDENTIALS` | `true` | 是否允许携带 Cookie / 凭据 |
| `CORS_ALLOW_METHODS` | `["*"]` | 允许的 HTTP 方法 |
| `CORS_ALLOW_HEADERS` | `["*"]` | 允许的请求头 |
| `GZIP_MINIMUM_SIZE` | `1000` | 触发 GZip 压缩的响应体最小字节数 |

---

## 核心模块

### 统一响应格式

所有接口统一返回以下 JSON 结构：

```json
{ "code": 0, "message": "success", "result": { ... } }
```

```python
from app.schemas.response import ResponseSchema, PageResponseSchema

# 普通成功响应
return ResponseSchema.ok(data={"id": 1, "name": "张三"})

# 自定义消息
return ResponseSchema.ok(data=user, message="获取成功")

# 分页响应
return PageResponseSchema.ok(data=items, total=56, page=1, page_size=10)

# 文件下载（不走 JSON 包装，直接返回）
return StreamingResponse(io.BytesIO(content), media_type="text/csv", ...)
```

分页响应 `result` 结构：

```json
{
  "items": [...],
  "pagination": {
    "page": 1, "page_size": 10, "total": 56,
    "total_pages": 6, "has_next": true, "has_prev": false
  }
}
```

> 详见 [`app/schemas/README.md`](app/schemas/README.md)

---

### 异常处理

业务层只需**抛出异常**，全局处理器自动转换为统一格式响应。

```python
from app.exceptions import (
    BizException, NotFoundException, AuthException,
    ForbiddenException, ParamsException, ErrorCode,
)

raise NotFoundException(message="用户不存在")           # HTTP 404, code=3001
raise AuthException(message="请先登录")                # HTTP 401, code=1001
raise ForbiddenException(message="仅管理员可操作")     # HTTP 403, code=1002
raise BizException(ErrorCode.FAIL, message="余额不足") # HTTP 200, code=-1
```

| 异常类 | HTTP 状态码 | 业务 code | 场景 |
|--------|------------|-----------|------|
| `BizException` | 200（可自定义） | `-1` | 通用业务异常 |
| `AuthException` | 401 | `1001` | 未登录 / Token 失效 |
| `ForbiddenException` | 403 | `1002` | 权限不足 |
| `NotFoundException` | 404 | `3001` | 资源不存在 |
| `ParamsException` | 422 | `2001` | 参数校验失败 |

Pydantic 参数校验错误由全局处理器**自动拦截**，无需手动处理。

> 详见 [`app/exceptions/README.md`](app/exceptions/README.md)

---

### JWT 鉴权

中间件已全局注册，对所有非公开路径自动进行 JWT Bearer Token 验证，验证失败返回统一格式 `401`。

**生成 Token（登录接口中调用）：**

```python
from datetime import datetime, timedelta, timezone
import jwt
from config.settings import get_settings

def create_access_token(user_id: str) -> str:
    """生成 JWT Access Token"""
    cfg = get_settings().jwt
    expire = datetime.now(timezone.utc) + timedelta(hours=cfg.JWT_ACCESS_TOKEN_EXPIRE_HOUR)
    payload = {"sub": user_id, "exp": expire, "iat": datetime.now(timezone.utc)}
    return jwt.encode(payload, cfg.JWT_SECRET_KEY, algorithm=cfg.JWT_ALGORITHM)
```

**在路由中读取当前登录用户：**

```python
from starlette.requests import Request

@router.get("/profile")
async def get_profile(request: Request):
    user_id = request.state.user_id      # payload 中的 sub 字段
    payload = request.state.jwt_payload  # 完整 JWT payload dict
```

**配置公开路径（跳过鉴权）：**

在 `.env` 中追加 `JWT_PUBLIC_PATHS`，或直接修改 `config/middleware_config.py` 的默认列表。

> 详见 [`app/middlewares/README.md`](app/middlewares/README.md)

---

### Redis 缓存

缓存模块已集成到应用生命周期，启动/关闭时自动连接/断开，并内置 **30 秒心跳保活**与自动重连机制。

**基本操作：**

```python
from app.core.cache import get_redis_manager

redis = get_redis_manager()

await redis.set("user:1", {"name": "张三"}, ex=3600)  # 设置（自动添加项目前缀）
user  = await redis.get("user:1")                       # 获取（自动反序列化）
await redis.delete("user:1")                            # 删除
await redis.hset("user:profile:1", mapping, ex=120)    # Hash 操作
```

**装饰器缓存（推荐用于只读查询）：**

```python
from app.core.cache import cache

@cache(key_prefix="user", ttl=3600)
async def get_user(user_id: int):
    return await db.users.get(user_id)
```

**业务模块前缀常量（推荐）：**

```python
from app.core.cache import RedisPrefixes

# 实际键名: anda_erp:user:profile:{user_id}
await redis.hset(f"{RedisPrefixes.USER_PROFILE}:{user_id}", data, ex=120)
```

> 详见 [`app/core/cache/README.md`](app/core/cache/README.md)

---

### 数据库

基于 **SQLAlchemy 2.0 全异步**，通过 FastAPI 依赖注入获取 `AsyncSession`，连接池参数已预调优。

**定义模型：**

```python
from app.models.base_model import BaseModel  # 内含 id、created_at、updated_at 等公共字段
from sqlalchemy.orm import Mapped, mapped_column

class User(BaseModel):
    __tablename__ = "users"
    name:  Mapped[str] = mapped_column(nullable=False)
    email: Mapped[str] = mapped_column(unique=True)
```

**在路由中注入 Session：**

```python
from app.dependencies.db import DBSessionDep

@router.get("/users/{user_id}")
async def get_user(user_id: int, db: DBSessionDep):
    user = await db.get(User, user_id)
    if not user:
        raise NotFoundException(message=f"用户 {user_id} 不存在")
    return ResponseSchema.ok(data=user)
```

---

### 日志系统

基于 **Loguru** 封装，禁止直接使用 `print()` 或原生 `logging` 模块。

```python
from app.core.log import log

log.info("服务启动成功")
log.warning(f"用户 {user_id} 不存在，跳过处理")
log.error(f"数据库查询失败: {e}")
log.debug(f"请求参数: {params}")
```

- 日志文件自动按时间滚动，输出至 `logs/` 目录。
- 控制台彩色输出，文件与控制台级别可独立配置。

---

### 分页依赖

使用预置的 `PageDep` 依赖，自动解析 `page` / `page_size` 查询参数：

```python
from app.dependencies.pagination import PageDep

@router.get("/list")
async def get_list(pagination: PageDep):
    # pagination.page       当前页码（默认 1）
    # pagination.page_size  每页条数（默认 10，最大 100）
    # pagination.offset     计算好的 offset，可直接用于 SQL LIMIT/OFFSET
    ...
    return PageResponseSchema.ok(data=items, total=total,
                                 page=pagination.page, page_size=pagination.page_size)
```

---

### 中间件

中间件执行顺序（请求方向）：

```
请求进入  →  CORS  →  GZip  →  JWT 鉴权  →  路由处理器
响应返回  ←  CORS  ←  GZip  ←  JWT 鉴权  ←  路由处理器
```

**新增自定义中间件：**

1. 在 `app/middlewares/` 下新建 `your_middleware.py`，实现 `register_your_middleware(app: FastAPI) -> None`。
2. 在 `app/middlewares/__init__.py` 的 `register_middlewares()` 中按需层级调用。

---

## 新增路由

**Step 1**：在 `app/api/` 下新建路由文件，例如 `order.py`：

```python
from fastapi import APIRouter
from app.schemas.response import ResponseSchema

router_order = APIRouter(prefix="/orders", tags=["订单管理"])

@router_order.get("/{order_id}", summary="获取订单详情")
async def get_order(order_id: int):
    """查询单个订单"""
    return ResponseSchema.ok(data={"id": order_id})

__all__ = ["router_order"]
```

**Step 2**：在 `app/api/__init__.py` 的 `register_router()` 中注册：

```python
from app.api.order import router_order

def register_router(app: FastAPI) -> None:
    app.include_router(router_order, prefix="/api")
    # ...其他路由
```

---

## 代码规范

项目使用 [Ruff](https://docs.astral.sh/ruff/) 进行代码检查与格式化，目标版本 Python 3.12。

```bash
# 检查
uv run ruff check .

# 格式化
uv run ruff format .
```

| 规则 | 要求 |
|------|------|
| `T201` | 禁止 `print()`，使用 `log.*` 替代 |
| `TID251` | 禁止 `import logging`，使用 `from app.core.log import log` |
| `I` (isort) | import 分组排序：标准库 → 第三方 → 项目内部（`app` / `config`） |
| `UP` (pyupgrade) | 遵循 Python 3.12 新写法（如 `X \| Y` 联合类型） |
| `B` (bugbear) | 避免常见 Bug 模式 |

> ⚠️ 所有提交代码必须通过 `ruff check` 检查，不得引入新的 Lint 错误。

---

## License

Apache-2.0

