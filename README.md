# FastAPI Template

> 基于 **FastAPI + Python 3.12** 的后端项目模板，集成异步数据库、Redis 缓存、接口限流、JWT 鉴权中间件实现、统一响应/异常处理等常用基础设施，开箱即用。

---

## 目录

- [技术栈](#技术栈)
- [项目结构](#项目结构)
- [快速开始](#快速开始)
- [Docker 运行](#docker-运行)
- [环境变量配置](#环境变量配置)
- [核心模块](#核心模块)
  - [统一响应格式](#统一响应格式)
  - [异常处理](#异常处理)
  - [JWT 鉴权](#jwt-鉴权)
  - [Redis 缓存](#redis-缓存)
  - [接口速率限制](#接口速率限制)
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
| Web 框架 | FastAPI 0.138+ |
| ASGI 服务器 | Uvicorn 0.49+ |
| ORM | SQLAlchemy 2.0（全异步） |
| 数据库驱动 | asyncpg 0.31+（PostgreSQL） |
| 缓存 | redis-py 8.0+（异步客户端） |
| 接口限流 | SlowAPI + Redis |
| 鉴权 | PyJWT 2.13+（HS256） |
| 配置管理 | Pydantic-Settings（读取进程环境变量） |
| 日志 | Loguru |
| 包管理 | [uv](https://docs.astral.sh/uv/) |
| 代码检查/格式化 | [Ruff](https://docs.astral.sh/ruff/) |
| 静态类型检查/语言服务器 | [ty](https://docs.astral.sh/ty/) |

---

## 项目结构

```
fastapi-template/
├── main.py                    # 应用入口（配置 → 日志 → FastAPI 按序初始化）
├── Dockerfile                 # 多阶段生产镜像
├── compose.yaml               # API 容器编排（连接外部 PostgreSQL / Redis）
├── .dockerignore              # Docker 构建上下文忽略规则
├── .env.docker.example        # Docker 环境变量示例
├── pyproject.toml             # 项目元数据 & Ruff / ty 配置
├── uv.lock                    # uv 锁定文件
├── tests/                     # 测试用例
├── app/
│   ├── api/                   # 路由层（APIRouter）
│   ├── core/
│   │   ├── cache/             # Redis 异步缓存模块
│   │   ├── database/          # PostgreSQL 异步引擎（SQLAlchemy 2.0）
│   │   ├── events/            # 生命周期钩子（startup / shutdown）
│   │   ├── rate_limit/        # SlowAPI Redis 接口限流
│   │   └── log/               # Loguru 封装
│   ├── dependencies/          # FastAPI 依赖注入（分页、DB Session 等）
│   ├── enums/                 # 业务枚举常量
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
    ├── middleware_config.py   # CORS / GZip / JWT 配置
    └── rate_limit_config.py   # 接口速率限制配置
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

仓库提供 `.env.example` 作为配置示例。当前配置类默认读取**进程环境变量**；如果希望直接读取根目录 `.env`，需要在配置类中显式设置 `env_file=".env"`，或由 IDE、部署平台、启动脚本先加载环境变量。`DB_PASSWORD` 与 `JWT_SECRET_KEY` 没有代码默认值，启动前必须显式配置。

最小配置示例：

```dotenv
# 数据库
DB_HOST=localhost
DB_PORT=5432
DB_USER=postgres
DB_PASSWORD=your_password
DB_DATABASE=postgres
DB_POOL_SIZE=5
DB_MAX_OVERFLOW=10
DB_POOL_RECYCLE=300
DB_POOL_TIMEOUT=30
DB_COMMAND_TIMEOUT=60
DB_CONNECT_TIMEOUT=30

# Redis
REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_DB=0
REDIS_PASSWORD=

# 接口速率限制（默认关闭）
RATE_LIMIT_ENABLED=false
RATE_LIMIT_DEFAULT=100/minute

# JWT（必填，至少 32 个字符）
JWT_SECRET_KEY=replace-with-a-strong-random-secret
```

启动前请确保 PostgreSQL 与 Redis 可连接；应用启动生命周期会执行数据库 `SELECT 1` 和 Redis `PING`。

### 3. 启动服务

```bash
uv run uvicorn main:app --reload
```

| 地址 | 说明 |
|------|------|
| http://localhost:8000/docs | Swagger UI 交互文档 |
| http://localhost:8000/redoc | ReDoc 文档 |
| http://localhost:8000/openapi.json | OpenAPI Schema |
| http://localhost:8000/health | PostgreSQL 与 Redis 健康状态 |

---

## Docker 运行

项目提供生产型多阶段镜像和只运行 API 的 Compose 编排。PostgreSQL 与 Redis 使用外部已有服务，不会由 Compose 创建；应用启动时会将两者作为强依赖进行连接检查。

### 1. 创建 Docker 环境变量文件

```powershell
Copy-Item .env.docker.example .env.docker
```

必须在 `.env.docker` 中填写：

```dotenv
API_PORT=宿主机对外端口，例如8000
DB_HOST=容器可访问的PostgreSQL地址
DB_PASSWORD=至少6个字符的数据库密码
REDIS_HOST=容器可访问的Redis地址
JWT_SECRET_KEY=至少32个字符的强随机密钥
```

密码或密钥包含 `$`、`${...}`、空格、`#` 等特殊字符时，应使用单引号包裹，例如 `DB_PASSWORD='实际密码'`，避免 Compose 将其插值或截断。

外部 Redis 开启认证时还需要取消 `REDIS_PASSWORD` 的注释并填写密码；未开启认证时保持该配置为注释状态。`.env.docker` 已加入 `.gitignore`，不得提交真实凭据。

Compose 通过服务级 `env_file` 将 `.env.docker` 中已启用的配置注入 API 容器；保持注释的非必填项不会进入容器，由 `config/` 中的代码默认值接管。需要覆盖可选配置时，取消对应注释并修改值即可。列表类型必须使用 JSON 字符串格式，例如：

```dotenv
CORS_ALLOW_ORIGINS="[\"https://admin.example.com\",\"https://app.example.com\"]"
JWT_PUBLIC_PATHS="[\"/docs\",\"/health\"]"
```

如果 PostgreSQL 或 Redis 运行在 Docker 宿主机上，`DB_HOST` / `REDIS_HOST` 可填写 `host.docker.internal`；Compose 已为 Linux Docker Engine 配置对应的 `host-gateway` 映射。远程服务则填写容器网络能够访问的内网域名或 IP，不能填写 `localhost`，因为容器中的 `localhost` 指向 API 容器自身。

### 2. 准备日志目录

Compose 不会自动创建日志目录，避免 Linux 上自动生成的 root 目录导致镜像内 UID `10001` 无法写入。Linux 宿主机首次启动前执行：

```bash
mkdir -p logs
sudo chown 10001:10001 logs
```

Windows Docker Desktop 只需创建目录，无需调整所有者：

```powershell
New-Item -ItemType Directory -Force logs
```

### 3. 构建并启动

启动前应确认外部 PostgreSQL 与 Redis 已运行，并且配置的地址、端口和凭据可以从 API 容器网络访问。还应确认当前 Shell 中没有无意保留的 `API_PORT`、`DB_HOST`、`DB_PASSWORD`、`REDIS_HOST` 或 `JWT_SECRET_KEY`，因为 Shell 同名变量的优先级高于 `--env-file`。

```bash
docker compose --env-file .env.docker config -q
docker compose --env-file .env.docker up --build -d
docker compose --env-file .env.docker ps
```

`config -q` 只校验最终 Compose 配置，不打印展开后的环境变量。命令行的 `--env-file` 为 Compose 的端口映射和必填项校验提供变量，服务级 `env_file` 则将同一文件中的应用配置注入容器，两者用途不同。Compose 只启动 API 容器，宿主机对外端口由必填的 `API_PORT` 决定；容器内部固定监听 `8000`，不会创建、停止或删除外部 PostgreSQL/Redis。应用文件日志映射到根目录 `logs/`。

### 4. 检查与停止

```bash
docker compose --env-file .env.docker logs -f api
docker compose --env-file .env.docker down
```

健康检查接口：

```text
GET http://localhost:<API_PORT>/health
```

PostgreSQL 和 Redis 均正常时返回 HTTP 200，任一外部关键依赖不可用时返回 HTTP 503。`docker compose down` 只停止并删除 API 容器，不影响外部 PostgreSQL 和 Redis。

---

## 环境变量配置

所有配置均通过 **Pydantic-Settings** 管理，默认读取进程环境变量；除明确标记为必填的敏感配置外，未提供环境变量时使用代码内默认值。配置类自身未设置 Pydantic 的 `env_file`，因此不会直接读取根目录 `.env`；Docker 运行时由 Compose 的服务级 `env_file` 将 `.env.docker` 注入进程环境。

### 数据库

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `DB_HOST` | `localhost` | PostgreSQL 主机地址 |
| `DB_PORT` | `5432` | 端口 |
| `DB_USER` | `postgres` | 用户名 |
| `DB_PASSWORD` | 无，必填 | PostgreSQL 密码，不允许空字符串 |
| `DB_DATABASE` | `postgres` | 数据库名 |
| `DB_POOL_SIZE` | `5` | 单个应用进程的常驻连接池大小，必须大于 0 |
| `DB_MAX_OVERFLOW` | `10` | 单个应用进程允许临时创建的额外连接数，必须大于等于 0 |
| `DB_POOL_RECYCLE` | `300` | 连接回收周期（秒），`-1` 表示禁用回收 |
| `DB_POOL_TIMEOUT` | `30` | 从连接池获取连接的最长等待时间（秒） |
| `DB_COMMAND_TIMEOUT` | `60` | asyncpg 命令执行超时（秒） |
| `DB_CONNECT_TIMEOUT` | `30` | asyncpg 建立连接超时（秒） |

### Redis 缓存

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `REDIS_HOST` | `localhost` | 主机地址 |
| `REDIS_PORT` | `6379` | 端口 |
| `REDIS_DB` | `0` | 数据库编号 |
| `REDIS_PASSWORD` | `None` | 认证密码（可选） |
| `REDIS_MAX_CONNECTIONS` | `10` | 连接池最大连接数 |
| `REDIS_TIMEOUT` | `5` | 连接超时（秒） |
| `REDIS_PREFIX` | `template` | 项目级键前缀，多项目共享 Redis 实例时用于数据隔离 |

### 日志

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `LOG_LEVEL` | `20` | 日志级别，使用 Python logging 的数值级别（`20` 为 INFO） |
| `LOG_RETENTION` | `14 days` | 日志文件保留周期 |
| `LOG_ROTATION_TIME` | `00:00` | 日志文件轮转时间 |

### 接口速率限制

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `RATE_LIMIT_ENABLED` | `false` | 是否启用显式声明的接口限流 |
| `RATE_LIMIT_DEFAULT` | `100/minute` | `@rate_limit()` 未传入额度时使用的默认值 |

### JWT 鉴权

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `JWT_SECRET_KEY` | 无，必填 | JWT 签名密钥，至少 32 个字符 |
| `JWT_ALGORITHM` | `HS256` | 签名算法 |
| `JWT_ACCESS_TOKEN_EXPIRE_HOUR` | `24` | Token 有效期（小时） |
| `JWT_PUBLIC_PATHS` | `/docs`, `/redoc`, `/openapi.json`, `/favicon.ico`, `/health`, `/api/auth/login`, `/api/auth/register` | 跳过鉴权的公开路径（前缀匹配） |

### 中间件

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `CORS_ALLOW_ORIGINS` | `["*"]` | 允许的跨域来源，生产环境应填写具体域名 |
| `CORS_ALLOW_CREDENTIALS` | `false` | 是否允许携带 Cookie / 凭据；启用时不能继续使用 `["*"]` 作为来源 |
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
  "data": [...],
  "pagination": {
    "page": 1, "page_size": 10, "total": 56,
    "total_pages": 6, "has_next": true, "has_prev": false
  }
}
```

> 实现见 [`app/schemas/response.py`](app/schemas/response.py) 和 [`app/dependencies/pagination.py`](app/dependencies/pagination.py)

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
raise BizException(ErrorCode.FAIL, message="余额不足") # HTTP 200, code=99999
```

| 异常类 | HTTP 状态码 | 业务 code | 场景 |
|--------|------------|-----------|------|
| `BizException` | 200（可自定义） | 自定义（默认 `99999`） | 通用业务异常基类 |
| `AuthException` | 401 | `1001` | 未登录 / Token 失效 |
| `ForbiddenException` | 403 | `1002` | 权限不足 |
| `NotFoundException` | 404 | `3001` | 资源不存在 |
| `ParamsException` | 422 | `2001` | 参数校验失败 |

Pydantic 参数校验错误由全局处理器**自动拦截**，无需手动处理。处理器会取第一条校验错误转换为中文 `message`，`result` 默认返回空对象。

> 详见 [`app/exceptions/README.md`](app/exceptions/README.md)

---

### JWT 鉴权

项目已提供 `JWTAuthMiddleware` 实现和 JWT 配置；但当前 `app/middlewares/__init__.py` 默认只注册 CORS 与 GZip，JWT 中间件处于未启用状态。

如需全局启用 JWT Bearer Token 验证，请在 `app/middlewares/__init__.py` 中导入并调用 `register_jwt_middleware(app)`，启用后非公开路径验证失败会返回统一格式 `401`。

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

通过环境变量注入 `JWT_PUBLIC_PATHS`，或直接修改 `config/middleware_config.py` 的默认列表。

> 实现见 [`app/middlewares/jwt_auth.py`](app/middlewares/jwt_auth.py)，注册入口见 [`app/middlewares/__init__.py`](app/middlewares/__init__.py)

---

### Redis 缓存

缓存模块已集成到应用生命周期，启动/关闭时自动连接/断开，并内置 **30 秒心跳保活**与自动重连机制。

**基本操作：**

```python
from app.core.cache import get_redis_manager

redis = get_redis_manager()

await redis.set("user:1", {"name": "张三"}, ex=3600)  # 设置（自动添加项目前缀）
user = await redis.get("user:1")                        # 获取（自动反序列化）
await redis.delete("user:1")                            # 删除
await redis.hset("user:profile:1", {"name": "张三"}, ex=120)  # Hash 操作
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

# 实际键名: template:user:profile:{user_id}
await redis.hset(f"{RedisPrefixes.USER_PROFILE}:{user_id}", data, ex=120)
```

> 详见 [`app/core/cache/README.md`](app/core/cache/README.md)

---

### 接口速率限制

接口限流默认关闭，仅对显式添加 `@rate_limit()` 的接口生效。限流按客户端 IP 和接口分别计数，
使用独立的 SlowAPI Redis 连接；Redis 故障时记录错误并放行请求。

```python
from fastapi import APIRouter, Request

from app.core.rate_limit import rate_limit

router = APIRouter()


@router.get("/orders")
@rate_limit()
async def get_orders(request: Request):
    """使用 RATE_LIMIT_DEFAULT 配置的额度。"""
    ...


@router.post("/orders")
@rate_limit("10/minute")
async def create_order(request: Request):
    """为单个接口指定额度。"""
    ...
```

> SlowAPI 要求路由装饰器位于 `@rate_limit()` 上方，且被限流的接口必须显式接收名为 `request` 的 `Request` 参数。

---

### 数据库

基于 **SQLAlchemy 2.0 全异步**，通过 FastAPI 依赖注入获取 `AsyncSession`，连接池参数已预调优。

**定义模型：**

```python
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base_model import BaseModel  # 内含 created_at、updated_at 公共字段


class User(BaseModel):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(nullable=False)
    email: Mapped[str] = mapped_column(unique=True)
```

**在路由中注入 Session：**

```python
from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies.db import get_db
from app.exceptions import NotFoundException
from app.schemas.response import ResponseSchema

DBSessionDep = Annotated[AsyncSession, Depends(get_db)]


@router.get("/users/{user_id}")
async def get_user(user_id: int, db: DBSessionDep) -> ResponseSchema:
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

当前默认启用 CORS 与 GZip；JWT 中间件实现已提供但未默认注册。

默认中间件执行顺序（请求方向）：

```
请求进入  →  CORS  →  GZip  →  路由处理器
响应返回  ←  CORS  ←  GZip  ←  路由处理器
```

启用 JWT 后，请求方向为 `CORS → GZip → JWT 鉴权 → 路由处理器`。

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
async def get_order(order_id: int) -> ResponseSchema:
    """查询单个订单"""
    return ResponseSchema.ok(data={"id": order_id})

__all__ = ["router_order"]
```

**Step 2**：在 `app/api/__init__.py` 的 `register_router()` 中注册：

```python
from fastapi import APIRouter, FastAPI

from app.api.demo import router_demo
from app.api.order import router_order


def register_router(app: FastAPI) -> None:
    router = APIRouter()
    router.include_router(router_demo)
    router.include_router(router_order)

    app.include_router(router)
```

如需统一 `/api` 前缀，可在最后一行改为 `app.include_router(router, prefix="/api")`。

---

## 代码规范

项目使用 [Ruff](https://docs.astral.sh/ruff/) 进行代码检查与格式化，并使用 [ty](https://docs.astral.sh/ty/) 进行静态类型检查与语言服务器支持，目标版本 Python 3.12。

```bash
# 检查
uv run ruff check .

# 格式化
uv run ruff format .

# 静态类型检查
uv run ty check
```

| 规则 | 要求 |
|------|------|
| `T201` | 禁止 `print()`，使用 `log.*` 替代 |
| `TID251` | 禁止 `import logging`，使用 `from app.core.log import log` |
| `I` (isort) | import 分组排序：标准库 → 第三方 → 项目内部（`app` / `config`） |
| `UP` (pyupgrade) | 遵循 Python 3.12 新写法（如 `X \| Y` 联合类型） |
| `B` (bugbear) | 避免常见 Bug 模式 |
| `ty` | 检查类型推断、返回值、属性访问与导入解析等静态类型问题 |

> ⚠️ 所有提交代码必须通过 `ruff check` 检查，不得引入新的 Lint 错误。
> `ty` 当前按 warning 方式接入，用于持续观察类型诊断；新增代码应尽量避免引入新的明显类型问题。

### ty 语言服务器

本项目将 `ty` 固定为 dev 依赖，建议编辑器使用项目虚拟环境中的版本：

- PyCharm 2025.3+：在 `Python | Tools | ty` 中启用，并选择 Interpreter mode。
- VS Code：安装官方 ty 扩展；如需保留其他 Python 语言服务，可按团队约定关闭 ty 的语言服务能力，仅保留类型检查。
- 其他支持 LSP 的编辑器：使用 `uv run ty server` 接入。

---

## License

Apache-2.0
