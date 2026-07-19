# 中间件

`app/middlewares/` 集中管理 CORS、GZip 和 JWT 中间件。默认启用 CORS 与 GZip；JWT 校验实现已
提供，但需要显式注册。

## 默认状态

| 中间件 | 默认状态 | 注册入口 | 说明 |
| --- | --- | --- | --- |
| CORS | 启用 | `register_cors_middleware()` | 包裹完整应用栈 |
| GZip | 启用 | `register_gzip_middleware()` | 压缩符合条件的响应 |
| JWT | 关闭 | `register_jwt_middleware()` | 校验 Bearer Token 并写入 `request.state` |

主程序的注册顺序是：

```text
全局异常处理器 -> 限流异常处理器与应用状态 -> 中间件 -> 路由
```

接口限流由路由函数上的 `@rate_limit(...)` 异步装饰器执行，不是 ASGI 中间件，因此不出现在下面的
中间件请求链中。

## 执行顺序

当前默认请求链：

```text
请求：CORS -> GZip -> Router
响应：Router -> GZip -> CORS
```

启用 JWT 后：

```text
请求：CORS -> GZip -> JWT -> Router
响应：Router -> JWT -> GZip -> CORS
```

CORS 是唯一的最外层包装，因此合法预检请求可在进入 JWT 前处理，正常响应和未处理异常生成的
500 响应也使用同一份跨域配置。

## 为什么 CORS 使用特殊注册方式

Starlette 默认把 `ServerErrorMiddleware` 放在普通用户中间件之外。如果直接通过
`app.add_middleware(CORSMiddleware, ...)` 注册 CORS，最外层服务器错误生成的 500 响应不会再
经过 CORS。

本项目在首次 ASGI 调用前延迟包装 `build_middleware_stack()`，用一层 `CORSMiddleware` 包住
完整内部栈，同时保持导出的对象仍是 `FastAPI`。因此：

- CORS 必须在应用启动和首次请求前注册。
- 不得再添加第二层 `CORSMiddleware`。
- CORS 注册后、应用启动前仍可继续注册路由、异常处理器和其他用户中间件。

对应行为由 `tests/test_cors_outer_middleware.py` 覆盖。

## 配置

配置位于 [`config/middleware_config.py`](../../config/middleware_config.py)，由进程环境变量覆盖。
配置类不会自行读取根目录 `.env`；本地可使用
`uv run --env-file .env.local ...`，Docker 则由 Compose 注入。

| 变量 | 默认值 | 约束与说明 |
| --- | --- | --- |
| `CORS_ALLOW_ORIGINS` | `["*"]` | 允许来源；生产环境应使用明确域名 |
| `CORS_ALLOW_CREDENTIALS` | `false` | 为 `true` 时拒绝通配来源 |
| `CORS_ALLOW_METHODS` | `["*"]` | 允许的 HTTP 方法 |
| `CORS_ALLOW_HEADERS` | `["*"]` | 允许的请求头 |
| `GZIP_MINIMUM_SIZE` | `1000` | 普通非流式响应触发压缩的最小字节数 |
| `JWT_SECRET_KEY` | 无，必填 | 至少 32 个字符 |
| `JWT_ALGORITHM` | `HS256` | JWT 校验算法 |
| `JWT_ACCESS_TOKEN_EXPIRE_HOUR` | `24` | 供 Token 签发业务使用的建议有效期 |
| `JWT_PUBLIC_PATHS` | 见下方 | 跳过 JWT 校验的路径列表 |

列表环境变量必须使用 JSON 字符串：

```dotenv
CORS_ALLOW_ORIGINS="[\"https://app.example.com\",\"https://admin.example.com\"]"
CORS_ALLOW_CREDENTIALS=true
JWT_PUBLIC_PATHS="[\"/docs\",\"/redoc\",\"/openapi.json\",\"/favicon.ico\",\"/health\"]"
```

即使 JWT 中间件未注册，`JWT_SECRET_KEY` 仍是启动必填项，因为聚合 `Settings` 会初始化并校验
`JWTSettings`。

默认公开路径为：

```text
/docs
/redoc
/openapi.json
/favicon.ico
/health
/api/auth/login
/api/auth/register
```

最后两个路径只是预留白名单，模板没有实现登录或注册接口。

## CORS

实现位于 [`cors.py`](cors.py)，使用 FastAPI 的 `CORSMiddleware`。

- 自动处理浏览器 `OPTIONS` 预检请求。
- 生产环境不应长期使用 `CORS_ALLOW_ORIGINS=["*"]`。
- `CORS_ALLOW_CREDENTIALS=true` 与通配来源组合会在配置阶段被拒绝。
- CORS 只决定浏览器是否允许跨域读取响应，不替代认证、授权或 CSRF 防护。

## GZip

实现位于 [`gzip.py`](gzip.py)，使用 FastAPI / Starlette 的 `GZipMiddleware`。客户端需要发送
`Accept-Encoding: gzip`。

当前锁定版本的行为：

- 普通非流式响应仅在响应体不小于 `GZIP_MINIMUM_SIZE` 时压缩。
- 流式响应由 Starlette 的流式压缩路径处理，不应把该阈值理解为完全相同的约束。
- 已设置 `Content-Encoding` 的响应不会重复压缩。
- `text/event-stream` 不会被 GZip 压缩。

压缩会消耗 CPU；阈值需要结合响应大小与负载评估，不是通用的性能最优值。

## JWT

实现位于 [`jwt_auth.py`](jwt_auth.py)。它只完成请求级 Token 校验，不包含：

- 登录或注册
- Token 签发与刷新
- 用户加载
- 角色和权限判断
- Token 撤销或黑名单

### 校验契约

受保护请求必须携带：

```http
Authorization: Bearer <token>
```

Token 必须：

- 使用配置的密钥与算法通过签名校验。
- 包含有效的 `exp`。
- 包含非空字符串 `sub`。

成功后写入：

```python
from fastapi import APIRouter, Request

from app.schemas.response import ResponseSchema

router = APIRouter()


@router.get("/profile")
async def get_profile(request: Request) -> ResponseSchema:
    """读取 JWT 中间件写入的认证上下文。"""
    user_id: str = request.state.user_id
    payload: dict[str, object] = request.state.jwt_payload
    return ResponseSchema.ok(data={"user_id": user_id, "claims": payload})
```

真实项目通常应再封装认证依赖，在依赖中加载用户和校验权限，避免业务 Router 直接读取原始 claims。

### 公开路径规则

`JWT_PUBLIC_PATHS` 会在配置阶段：

- 去除首尾空格和末尾 `/`
- 去重
- 拒绝空路径、根路径以及不以 `/` 开头的值

匹配采用“路径自身或路径段子路径”规则：

- `/docs` 匹配 `/docs` 和 `/docs/oauth2-redirect`
- `/docs` 不匹配 `/docs-private`

公开路径范围过宽会绕过整段鉴权，应按最小权限配置。

### 启用 JWT

在 [`__init__.py`](__init__.py) 恢复导入与注册：

```python
from fastapi import FastAPI

from app.middlewares.cors import register_cors_middleware
from app.middlewares.gzip import register_gzip_middleware
from app.middlewares.jwt_auth import register_jwt_middleware


def register_middlewares(app: FastAPI) -> None:
    """按由内到外的顺序注册中间件。"""
    register_jwt_middleware(app)
    register_gzip_middleware(app)
    register_cors_middleware(app)
```

启用前应先实现 Token 签发、用户状态校验、权限策略和密钥轮换方案，并确保 Swagger 所需的
`/docs` 与 `/openapi.json` 都在公开路径中。

### 鉴权失败

缺少、过期或无效 Token 时，中间件直接调用统一错误构造器，返回 HTTP 401、业务码 `1001`。
中间件层不能依赖抛出 `BizException` 进入业务异常处理器，原因见
[异常处理文档](../exceptions/README.md#中间件中的错误)。

## 扩展中间件

新增中间件时：

1. 在 `app/middlewares/` 创建独立文件。
2. 提供带类型提示的 `register_xxx_middleware(app: FastAPI) -> None`。
3. 明确它相对 JWT、GZip、异常处理器和 CORS 的位置。
4. 在 `register_middlewares()` 中注册；`register_cors_middleware(app)` 保持最后调用。
5. 为正常响应、异常响应、预检请求和顺序补充测试。

普通 `app.add_middleware()` 遵循后注册先执行的栈规则；修改顺序时应以请求与响应两个方向分别
验证，不能只根据函数调用顺序猜测。

[返回项目 README](../../README.md)
