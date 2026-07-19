# FastAPI Template

一个面向 Python 3.12 的异步 FastAPI 后端模板，内置 PostgreSQL、Redis、统一响应与异常处理、
健康检查、日志、可选 JWT 鉴权和接口限流等基础能力。仓库更适合作为业务服务的起点，而不是
带完整用户系统的成品应用。

## 特性与默认状态

| 能力 | 默认状态 | 说明 |
| --- | --- | --- |
| FastAPI + Uvicorn | 启用 | 应用入口为 `main:app` |
| SQLAlchemy 2.0 + asyncpg | 启用，强依赖 | 启动时执行 PostgreSQL `SELECT 1` |
| redis-py 异步缓存 | 启用，强依赖 | 启动时执行 `PING`，包含连接池、心跳和有限重连 |
| 统一 JSON 响应与异常处理 | 启用 | 成功与失败均使用 `code / message / result` |
| CORS / GZip | 启用 | CORS 包裹完整应用栈，兜底 500 响应也可携带跨域头 |
| JWT Bearer 校验 | 已实现，默认关闭 | 仅负责校验 Token，不包含登录、注册和 Token 签发业务 |
| 异步 Redis 接口限流 | 已注册，默认关闭 | 基于 `limits.aio` 与 `redis.asyncio`，仅作用于显式添加 `@rate_limit(...)` 的接口 |
| Loguru 日志 | 启用 | 输出到控制台和 `logs/app.log` |
| 分页、枚举、模型与 Repository 基类 | 已提供 | 用于扩展业务模块 |
| Scheduler | 仅目录骨架 | 模板未内置实际定时任务 |

> [!IMPORTANT]
> `DB_PASSWORD` 和 `JWT_SECRET_KEY` 都是启动必填项。即使 JWT 中间件保持关闭，
> 聚合配置仍会校验 JWT 密钥。

## 模板边界

为避免把基础设施误认为完整业务能力，请先了解以下边界：

- 仓库不包含用户表、登录/注册接口、权限模型或 Token 签发服务。
- `JWT_PUBLIC_PATHS` 中的 `/api/auth/login`、`/api/auth/register` 只是预留白名单，
  当前没有对应路由。
- 仓库不包含 Alembic，也不会自动创建或迁移业务表。
- `compose.yaml` 只运行 API；PostgreSQL 和 Redis 需要由外部提供。
- `app/models/`、`app/repositories/`、`app/services/` 提供基础结构，业务 CRUD 需要自行实现。

## 快速开始

### 前置条件

- Python 3.12
- [uv](https://docs.astral.sh/uv/)
- 可访问的 PostgreSQL
- 可访问的 Redis

### 1. 安装依赖

```bash
uv sync --locked
```

### 2. 创建本地配置

PowerShell：

```powershell
Copy-Item .env.example .env.local
```

Linux / macOS：

```bash
cp .env.example .env.local
```

至少填写以下两项；如果数据库或 Redis 不在本机，还需同步修改它们的主机和端口：

```dotenv
DB_PASSWORD=replace-with-at-least-6-characters
JWT_SECRET_KEY=replace-with-a-random-secret-at-least-32-characters
```

配置类读取的是进程环境变量，不会自行加载根目录下的 `.env*` 文件。下面的启动命令通过
uv 显式加载 `.env.local`：

```bash
uv run --env-file .env.local uvicorn main:app --reload
```

应用会依次检查 PostgreSQL、Redis 缓存和（启用时）限流 Redis；任一依赖不可用时启动失败，这是模板的故障快速暴露策略。

### 3. 验证服务

| 地址 | 用途 |
| --- | --- |
| <http://127.0.0.1:8000/docs> | Swagger UI |
| <http://127.0.0.1:8000/redoc> | ReDoc |
| <http://127.0.0.1:8000/openapi.json> | OpenAPI Schema |
| <http://127.0.0.1:8000/health> | PostgreSQL 与 Redis 健康检查 |

`/health` 不出现在 OpenAPI 文档中。两项依赖正常时返回 HTTP 200；运行期间任一依赖异常时返回
HTTP 503、业务码 `5001`。

## 当前接口

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| `GET` | `/health` | 检查 PostgreSQL 与 Redis；不进入 OpenAPI |
| `GET` | `/demo/list` | Faker 分页响应；启用限流后额度为 `3/minute` |
| `GET` | `/demo/detail?user_id=1` | 生成演示详情并写入 Redis Hash，TTL 为 120 秒 |
| `GET` | `/demo/export` | 下载 UTF-8 CSV，不使用 JSON 响应包装 |
| `GET` | `/demo/error-demo?error_type=biz` | 演示业务、认证和未处理异常 |
| `GET` | `/demo/search` | 演示 Query Schema 与枚举校验 |

这些接口用于展示模板能力，不代表已经实现持久化的用户业务。生产项目通常应删除、替换或限制
`/demo/*`。

## 架构约定

新增正式业务模块应遵循轻量路由和三层分工：

```text
HTTP 请求
  -> CORS（最外层）
  -> GZip
  -> JWT（可选）
  -> Router：参数、依赖、权限入口、响应组装
     -> Service：业务规则、编排、事务与缓存策略
        -> Repository：SQLAlchemy 语句与持久化
           -> AsyncSession / PostgreSQL
```

- Router 不直接承载复杂查询或业务规则。
- Service 写操作在第一次数据库访问前使用 `async with session.begin():` 建立事务边界。
- Repository 接收 `AsyncSession`，不自行 `commit()` 或 `rollback()`。
- JSON API 使用 `ResponseSchema` / `PageResponseSchema`；文件与流式响应直接返回相应 Response。
- 业务失败抛出 `app.exceptions` 中的项目异常，由全局处理器统一构造错误响应。
- 每个请求使用独立 `AsyncSession`，异常或取消时会尝试回滚并可靠关闭。

`/demo/*` 为了集中展示分页、缓存、文件和异常能力，存在直接生成模拟数据或访问 Redis 的简化写法；
它不是正式业务模块的分层范例。

## 项目结构

```text
fastapi-template/
├── main.py                     # 配置、日志、应用和组件注册入口
├── app/
│   ├── api/                    # APIRouter 与接口层
│   ├── core/
│   │   ├── cache/              # Redis 管理器与缓存装饰器
│   │   ├── database/           # 异步 PostgreSQL 引擎与会话
│   │   ├── events/             # lifespan 启停与资源清理
│   │   ├── log/                # Loguru 统一入口
│   │   └── rate_limit/         # 异步 Redis 限流
│   ├── dependencies/           # 数据库、分页等请求依赖
│   ├── enums/                  # 公共与业务枚举
│   ├── exceptions/             # 错误码、项目异常和全局处理器
│   ├── middlewares/            # CORS、GZip、可选 JWT
│   ├── models/                 # SQLAlchemy 模型基类
│   ├── repositories/           # 数据访问层
│   ├── schemas/                # Pydantic 请求与响应模型
│   ├── scheduler/              # 定时任务扩展目录
│   └── services/               # 业务逻辑层
├── config/                     # 分模块 Pydantic Settings
├── tests/                      # 单元与集成测试
├── Dockerfile                  # 多阶段、非 root 运行镜像
├── compose.yaml                # 仅 API 的 Compose 编排
├── pyproject.toml              # 依赖与 Ruff / ty 配置
└── uv.lock                     # 锁定依赖
```

## 配置

完整、带注释的变量清单位于 [`.env.example`](.env.example)，Docker 专用示例位于
[`.env.docker.example`](.env.docker.example)。配置按模块拆分在 [`config/`](config/) 中，
并由 `config.settings.get_settings()` 缓存聚合。

| 配置组 | 关键项 | 说明 |
| --- | --- | --- |
| 应用 | `APP_NAME`、`APP_VERSION` | 默认从 `pyproject.toml` 读取 |
| PostgreSQL | `DB_PASSWORD` | 必填，至少 6 个字符；连接池与超时均可覆盖 |
| Redis | `REDIS_HOST`、`REDIS_PREFIX` | 默认 `localhost` / `template` |
| JWT | `JWT_SECRET_KEY` | 必填，至少 32 个字符；中间件默认仍关闭 |
| CORS / GZip | `CORS_*`、`GZIP_MINIMUM_SIZE` | CORS 列表必须使用 JSON 字符串 |
| 限流 | `RATE_LIMIT_ENABLED`、`RATE_LIMIT_DEFAULT`、`RATE_LIMIT_FAIL_OPEN`、`RATE_LIMIT_REDIS_*` | 默认关闭；独立连接池默认上限为 5 |
| 日志 | `LOG_LEVEL`、`LOG_RETENTION`、`LOG_ROTATION_TIME` | 默认 INFO、保留 14 天、每日轮转 |

注意：

- 列表类型必须使用 JSON 字符串，例如
  `CORS_ALLOW_ORIGINS="[\"https://app.example.com\"]"`。
- `CORS_ALLOW_CREDENTIALS=true` 时不能继续使用通配来源 `["*"]`，配置会在启动阶段被拒绝。
- 配置已通过 `lru_cache` 缓存；修改进程环境变量后应重启应用。
- `.env*` 已默认忽略，请勿提交真实密码、Token 或密钥。

## 核心契约

### 统一响应

普通 JSON 成功响应：

```json
{
  "code": 0,
  "message": "success",
  "result": {
    "id": 1
  }
}
```

分页响应将列表和分页元信息放在 `result` 中。错误响应保持相同外层结构并使用非零业务码；
HTTP 状态由异常类型或兼容契约决定，通用 `BizException` 默认返回 HTTP 200。详细用法见
[Schema 文档](app/schemas/README.md) 和 [异常处理文档](app/exceptions/README.md)。

### Redis 缓存

缓存键自动添加 `REDIS_PREFIX`，支持 KV、批量、Hash、List、Set、TTL、按项目前缀清理以及
异步函数结果缓存。缓存值采用带版本标记的 JSON 协议，不支持任意 Python 或 ORM 对象。

```python
from app.core.cache import RedisPrefixes, get_redis_manager

redis_manager = get_redis_manager()
await redis_manager.hset(
    f"{RedisPrefixes.USER_PROFILE}:1",
    {"name": "示例用户"},
    ex=120,
)
```

完整的序列化边界、API 和失效策略见 [Redis 缓存文档](app/core/cache/README.md)。

### 接口限流

限流默认关闭，开启后仅检查显式声明的接口。端点必须显式接收名为 `request` 的 `Request`，
并保持路由装饰器在 `@rate_limit(...)` 上方：

```python
from fastapi import APIRouter, Request

from app.core.rate_limit import rate_limit
from app.schemas.response import ResponseSchema

router = APIRouter()


@router.get("/orders")
@rate_limit("10/minute")
async def list_orders(request: Request) -> ResponseSchema:
    """返回订单列表。"""
    return ResponseSchema.ok(data=[])
```

限流使用 `limits.aio` 的固定窗口策略和 `redis.asyncio`，按客户端 IP 与端点计数。它复用项目
`REDIS_PREFIX` 进行键隔离，但拥有独立的小连接池，避免占用缓存连接；多个 worker 连接同一 Redis
时共享额度。启用后应用启动会先 `PING` 限流 Redis，连接失败即终止启动；运行期 Redis 故障则由
`RATE_LIMIT_FAIL_OPEN` 决定是否放行（默认 `true`）。高安全场景应设为 `false` 并结合网关限流。

### 数据库与时间

- SQLAlchemy 使用异步引擎、`async_sessionmaker` 和请求级 `AsyncSession`。
- PostgreSQL 会话时区固定为 `Asia/Shanghai`。
- `BaseModel.created_at / updated_at` 使用无时区 `DateTime`；默认值由 SQLAlchemy SQL 表达式
  `func.now()` 参与生成，绕过 ORM 的外部更新不会自动触发 `updated_at` 更新。
- `BaseSchema` 中明确声明的 `datetime` 字段输出为 `YYYY-MM-DD HH:MM:SS`。
- 修改 ORM 模型不会自动改变既有数据库结构，必须配套迁移方案。

## 模块文档

| 文档 | 内容 |
| --- | --- |
| [Schemas](app/schemas/README.md) | `BaseSchema`、普通/分页响应、文件响应与 ORM 转换 |
| [Enums](app/enums/README.md) | 当前枚举、扩展方式与兼容性约定 |
| [Exceptions](app/exceptions/README.md) | 错误码、异常类型、处理器与响应契约 |
| [Middlewares](app/middlewares/README.md) | CORS、GZip、JWT 和执行顺序 |
| [Redis Cache](app/core/cache/README.md) | 连接生命周期、数据类型、装饰器与 API |
| [AGENTS.md](AGENTS.md) | 本仓库的工程与协作规范 |

## 扩展业务模块

新增功能时建议按以下顺序落地：

1. 在 `app/enums/` 和 `app/schemas/` 定义稳定的业务常量与请求/响应模型。
2. 在 `app/models/` 定义 ORM，并准备独立的数据库迁移。
3. 在 `app/repositories/` 封装 SQLAlchemy 2.x 查询。
4. 在 `app/services/` 实现业务规则、事务、权限和缓存失效。
5. 在 `app/api/` 添加薄路由，并在 `app/api/__init__.py` 注册。
6. 使用项目异常表达失败，使用统一响应表达 JSON 成功结果。
7. 为关键 service、repository 和接口契约补充测试。

不要仅为统一前缀直接给整个聚合路由添加 `/api`：当前 Docker 健康探针固定访问 `/health`。
如果确需调整路由前缀，必须同步更新健康探针、JWT 公开路径、文档和测试。

## Docker 运行

Compose 只构建和运行 API 容器，PostgreSQL 与 Redis 必须已存在并可从容器网络访问。

### 1. 准备配置

```powershell
Copy-Item .env.docker.example .env.docker
```

或：

```bash
cp .env.docker.example .env.docker
```

填写 `API_PORT`、`DB_HOST`、`DB_PASSWORD`、`REDIS_HOST` 和 `JWT_SECRET_KEY`。外部服务运行在
Docker 宿主机时可使用 `host.docker.internal`；容器中的 `localhost` 指向 API 容器自身。

### 2. 准备日志目录

Linux 上运行用户固定为 UID/GID `10001`：

```bash
mkdir -p logs
sudo chown 10001:10001 logs
```

Windows Docker Desktop 只需确保 `logs/` 已存在。

### 3. 校验并启动

```bash
docker compose --env-file .env.docker config -q
docker compose --env-file .env.docker up --build -d
docker compose --env-file .env.docker ps
```

查看日志或停止：

```bash
docker compose --env-file .env.docker logs -f api
docker compose --env-file .env.docker down
```

镜像以非 root 用户运行，容器内固定监听 `8000`。默认停止预算保持
`DB 命令 60 秒 < Uvicorn 70 秒 < Compose 90 秒`，为生命周期清理预留时间。

## 开发与验证

```bash
uv run ruff format .
uv run ruff check .
uv run ty check
uv run pytest
```

真实 Redis 限流冒烟测试默认跳过，只有显式设置 `TEST_REDIS_URL` 时才会运行。该地址必须指向隔离的
测试 Redis，禁止使用生产实例；测试只会删除本次运行生成的唯一限流键：

```bash
uv run pytest tests/test_rate_limit_redis_integration.py
```

项目使用 [Ruff](https://docs.astral.sh/ruff/) 进行格式化与静态检查，使用
[ty](https://docs.astral.sh/ty/) 持续观察类型诊断，并通过 pytest 覆盖配置、安全、生命周期、
缓存、限流、数据库会话和响应契约。

业务代码统一使用：

```python
from app.core.log import log
```

禁止使用 `print()`，也不要在业务模块直接使用原生 `logging`。

## 上线前检查

- 使用密钥管理系统注入数据库密码、Redis 密码和 JWT 密钥。
- 将 CORS 来源收紧为明确域名。
- 明确是否启用 JWT，并实现真实的登录、用户加载与权限策略。
- 根据业务风险评估 `RATE_LIMIT_FAIL_OPEN`；多 worker 部署时按 worker 数评估缓存与限流两个 Redis 连接池的总连接数。
- 删除或保护 `/demo/*`，并建立数据库迁移流程。
- 根据进程数、数据库上限和实际负载重新评估连接池参数。

## License

[Apache-2.0](LICENSE)
