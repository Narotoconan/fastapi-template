# app/middlewares — 中间件模块

本目录包含项目所有中间件的实现与注册逻辑。  
各中间件由 `__init__.py` 中的 `register_middlewares()` 统一管理，在 `main.py` 中一键注册。

---

## 中间件执行顺序

```
请求进入  →  CORS  →  GZip  →  JWT 鉴权  →  路由处理器
响应返回  ←  CORS  ←  GZip  ←  JWT 鉴权  ←  路由处理器
```

> **原理说明**：FastAPI/Starlette 中间件采用**栈结构**（LIFO），`add_middleware()` 的调用顺序与实际请求处理顺序**相反**。因此 `register_middlewares()` 的注册顺序为：JWT → GZip → CORS（后注册先处理）。

---

## 文件结构

```
app/middlewares/
├── __init__.py       # 注册入口，暴露 register_middlewares()
├── cors.py           # CORS 跨域中间件
├── gzip.py           # GZip 压缩中间件
├── jwt_auth.py       # JWT 鉴权中间件
└── README.md         # 本文件
```

---

## 使用方式

### 1. 在 `main.py` 中注册（已完成）

```python
from app.middlewares import register_middlewares

app = FastAPI(...)
register_middlewares(app)
```

### 2. 通过环境变量调整配置

所有配置项均位于 `config/middleware_config.py`，可通过环境变量覆盖：

| 环境变量                           | 默认值     | 说明                          |
|--------------------------------|---------|-----------------------------|
| `CORS_ALLOW_ORIGINS`           | `["*"]` | 允许的跨域来源，生产环境应填写具体域名         |
| `CORS_ALLOW_CREDENTIALS`       | `true`  | 是否允许携带 Cookie/凭据            |
| `CORS_ALLOW_METHODS`           | `["*"]` | 允许的 HTTP 方法                 |
| `CORS_ALLOW_HEADERS`           | `["*"]` | 允许的请求头                      |
| `GZIP_MINIMUM_SIZE`            | `1000`  | 触发 GZip 压缩的响应体最小字节数         |
| `JWT_SECRET_KEY`               | *(需修改)* | JWT 签名密钥，**生产环境必须通过环境变量注入** |
| `JWT_ALGORITHM`                | `HS256` | JWT 签名算法                    |
| `JWT_ACCESS_TOKEN_EXPIRE_HOUR` | `24`    | Token 有效期（小时），默认 24 小时      |
| `JWT_PUBLIC_PATHS`             | 见下方     | 跳过鉴权的公开路径列表（JSON 数组格式）      |

**.env 示例**：
```dotenv
CORS_ALLOW_ORIGINS=["https://app.example.com","https://admin.example.com"]
JWT_SECRET_KEY=your-super-secret-key-min-32-chars
JWT_PUBLIC_PATHS=["/docs","/redoc","/openapi.json","/health","/api/auth/login"]
```

---

## 各中间件详解

### CORS 中间件 (`cors.py`)

基于 `fastapi.middleware.cors.CORSMiddleware` 实现，位于**最外层**。

- 自动响应浏览器的 `OPTIONS` 预检请求，返回正确的跨域响应头
- 支持 `Access-Control-Allow-Origin`、`Access-Control-Allow-Credentials` 等完整 CORS 头

**⚠️ 生产注意事项**：`CORS_ALLOW_ORIGINS=["*"]` 仅适用于开发环境，生产环境务必配置为具体的前端域名：
```dotenv
CORS_ALLOW_ORIGINS=["https://your-frontend.com"]
```

---

### GZip 中间件 (`gzip.py`)

基于 `fastapi.middleware.gzip.GZipMiddleware` 实现，位于**中间层**。

- 当客户端请求头包含 `Accept-Encoding: gzip` 时，自动对响应体进行压缩
- 仅压缩大于 `GZIP_MINIMUM_SIZE` 字节的响应，避免对小响应引入 CPU 开销
- 对文件下载（`StreamingResponse`）同样生效

---

### JWT 鉴权中间件 (`jwt_auth.py`)

基于 `starlette.middleware.base.BaseHTTPMiddleware` 自定义实现，位于**最内层**。

**处理流程**：
1. 判断请求路径是否在 `JWT_PUBLIC_PATHS` 列表中（前缀匹配），若是则跳过鉴权
2. 从请求头 `Authorization: Bearer <token>` 提取 Token
3. 使用 PyJWT 对 Token 进行解码验证（密钥 + 算法 + 过期时间）
4. 验证通过后，将 payload 挂载到 `request.state`：
   - `request.state.jwt_payload` — 完整的 JWT payload 字典
   - `request.state.user_id` — payload 中的 `sub` 字段（用户标识）
5. 验证失败则返回统一格式的 `401` 响应

**在路由/依赖项中获取当前用户**：

```python
from starlette.requests import Request

@router.get("/profile")
async def get_profile(request: Request):
    user_id = request.state.user_id
    payload = request.state.jwt_payload
    ...
```

也可封装为 FastAPI `Depends`：

```python
from fastapi import Depends, Request
from app.exceptions import AuthException

def get_current_user(request: Request) -> dict:
    """从 request.state 中获取当前登录用户信息（依赖注入）"""
    payload = getattr(request.state, "jwt_payload", None)
    if payload is None:
        raise AuthException(message="请先登录")
    return payload

@router.get("/profile")
async def get_profile(user: dict = Depends(get_current_user)):
    ...
```

**生成 Token 示例**（用于登录接口）：

```python
from datetime import datetime, timedelta, timezone
import jwt
from config.settings import get_settings

def create_access_token(user_id: str) -> str:
    """生成 JWT Access Token"""
    jwt_settings = get_settings().jwt
    expire = datetime.now(timezone.utc) + timedelta(minutes=jwt_settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES)
    payload = {
        "sub": user_id,
        "exp": expire,
        "iat": datetime.now(timezone.utc),
    }
    return jwt.encode(payload, jwt_settings.JWT_SECRET_KEY, algorithm=jwt_settings.JWT_ALGORITHM)
```

---

## 扩展新中间件

参照现有文件结构，新增步骤如下：

1. 在 `app/middlewares/` 下新建 `your_middleware.py`
2. 实现 `register_your_middleware(app: FastAPI) -> None` 函数
3. 在 `app/middlewares/__init__.py` 的 `register_middlewares()` 中按所需层级调用

```python
# __init__.py
def register_middlewares(app: FastAPI) -> None:
    register_jwt_middleware(app)        # 最内层
    register_your_middleware(app)       # 新增中间件（示例位置）
    register_gzip_middleware(app)
    register_cors_middleware(app)       # 最外层
```

