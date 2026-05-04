# Redis Cache Module 📦

轻量级异步 Redis 缓存模块，为中小型项目设计，提供开箱即用的缓存解决方案。

## 核心特性 ✨

- ✅ **异步连接管理** - 完全异步 I/O，零阻塞
- ✅ **自动连接池** - 内置连接池管理，自动复用
- ✅ **连接保活** - 自动心跳检查，30 秒间隔，连接故障自动重连
- ✅ **JSON 序列化** - 自动支持复杂数据结构序列化
- ✅ **灵活配置** - 环境变量配置，开箱即用
- ✅ **单例模式** - 全局唯一管理器实例
- ✅ **丰富 API** - 支持 String、Hash、List、Set 等数据结构
- ✅ **函数缓存** - 装饰器简化函数结果缓存

## 快速开始 🚀

### 1. 环境配置

在 `.env` 文件中配置 Redis 连接参数（可选，已有默认值）：

```env
REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_DB=0
REDIS_PASSWORD=  # 如果需要认证
REDIS_MAX_CONNECTIONS=10
REDIS_TIMEOUT=5
```

### 2. 自动初始化

模块已集成到应用生命周期中，启动时自动连接，关闭时自动断开：

```python
# app/core/events/startup.py - 应用启动时
from app.core.cache import init_cache


async def startup():
    await init_cache()  # 自动初始化 Redis 连接


# app/core/events/shutdown.py - 应用关闭时
from app.core.cache import close_cache


async def shutdown():
    await close_cache()  # 自动关闭 Redis 连接
```

**无需手动操作，应用启动时自动初始化 Redis 连接！**

### 2. 连接保活机制

模块内置自动心跳检查（完全自动，无需配置）：

- 🫀 **心跳间隔** - 每 30 秒检查一次连接
- 🔄 **自动重连** - 连接失败时 5 秒后自动重连
- 📊 **日志记录** - 所有状态通过 loguru 以中文日志记录
- ✅ **故障恢复** - 异常情况下自动恢复连接

**心跳检查日志：**
```
正常运行:    [DEBUG] ❤️ Redis 心跳检查: 正常
启动时:      [INFO]  ❤️ Redis 心跳检查已启动 (检查间隔: 30 秒)
连接失败:    [WARNING] ⚠️ Redis 心跳检查失败: {error}
开始重连:    [INFO]  🔄 开始重连 Redis...
重连成功:    [INFO]  ✅ Redis 重连成功
关闭时:      [DEBUG] ❤️ Redis 心跳检查已停止
```

### 3. 基本使用

#### 自动项目前缀

所有的键都会自动添加项目前缀（`REDIS_PREFIX`），用于区分多个项目在同一 Redis 实例中的数据。

```python
# REDIS_PREFIX 配置: anda_erp
# 输入的键
await redis.set('user:1', {'id': 1, 'name': 'Alice'})

# Redis 中实际存储的键
# anda_erp:user:1
```

**前缀规则：**
- 基于 `REDIS_PREFIX` 配置项（可手动修改）
- 默认值：`anda_erp`
- 自动与键名用 `:` 拼接

**配置示例：**
```env
# .env 或环境变量
REDIS_PREFIX=anda_erp          # 生产环境
# 或改为
REDIS_PREFIX=shop_system       # 其他项目
```

#### 字符串操作

```python
from app.core.cache import get_redis_manager

redis_manager = get_redis_manager()

# 设置缓存（支持 TTL，自动添加项目前缀）
await redis_manager.set('user:1', {'id': 1, 'name': 'Alice'}, ex=3600)
# 实际键名: anda_erp:user:1

# 获取缓存（自动反序列化）
user = await redis_manager.get('user:1')
print(user)  # {'id': 1, 'name': 'Alice'}

# 删除缓存
await redis_manager.delete('user:1')

# 检查是否存在
exists = await redis_manager.exists('user:1')
```

#### 批量操作

```python
# 批量设置
await redis_manager.mset({
    'key1': 'value1',
    'key2': {'nested': 'data'},
    'key3': [1, 2, 3]
})

# 批量获取
values = await redis_manager.mget('key1', 'key2', 'key3')
# [{'nested': 'data'}, [1, 2, 3], 'value1']
```

#### 哈希操作

```python
# 设置哈希字段
await redis_manager.hset('user:profile', {
    'name': 'Alice',
    'age': 30,
    'tags': ['admin', 'user']
})

# 获取单个字段
name = await redis_manager.hget('user:profile', 'name')

# 获取所有字段
profile = await redis_manager.hgetall('user:profile')

# 删除字段
await redis_manager.hdel('user:profile', 'age')
```

#### 列表操作

```python
# 从左端推入
await redis_manager.lpush('tasks', 'task1', 'task2')

# 从右端推入
await redis_manager.rpush('tasks', 'task3')

# 获取列表范围
tasks = await redis_manager.lrange('tasks', 0, -1)

# 弹出元素
task = await redis_manager.lpop('tasks')
```

#### 集合操作

```python
# 添加成员
await redis_manager.sadd('tags', 'python', 'fastapi', 'redis')

# 获取所有成员
tags = await redis_manager.smembers('tags')

# 移除成员
await redis_manager.srem('tags', 'redis')
```

## 装饰器缓存 🎯

用装饰器简化函数结果缓存，支持异步函数：

```python
from app.core.cache import cache


@cache(key_prefix="user", ttl=3600)
async def get_user(user_id: int):
    """获取用户信息，结果缓存 1 小时"""
    # 模拟数据库查询
    return await db.users.get(user_id)


# 第一次调用：执行函数并缓存结果
user = await get_user(1)

# 第二次调用：直接从缓存返回
user = await get_user(1)  # 从缓存读取
```

**参数说明：**
- `key_prefix` - 缓存键前缀（可选，用于区分不同的缓存空间）
- `ttl` - 过期时间，单位秒（可选，不指定则永不过期）

### 装饰器 vs 手动缓存

**使用装饰器 ✅（推荐）**
```python
@cache(key_prefix="user", ttl=3600)
async def get_user(user_id: int):
    return await db.users.get(user_id)
```

**手动管理 🎯（复杂场景）**
```python
async def get_user(user_id: int):
    redis = get_redis_manager()
    
    cached = await redis.get(f'user:{user_id}')
    if cached:
        return cached
    
    user = await db.users.get(user_id)
    await redis.set(f'user:{user_id}', user, ex=3600)
    return user
```

**何时使用装饰器：**
- 简单的只读查询函数
- 多个类似的缓存查询
- 想要代码简洁

**何时手动管理：**
- 需要复杂的缓存逻辑
- 数据修改操作（需要清除缓存）
- 条件性 TTL 设置

## 在 API 中的使用 📡

```python
from fastapi import APIRouter, Depends
from app.core.cache import get_redis_manager

router = APIRouter()


@router.get('/users/{user_id}')
async def get_user_info(user_id: int):
    redis_manager = get_redis_manager()

    # 尝试从缓存获取
    cached = await redis_manager.get(f'user:{user_id}')
    if cached:
        return cached

    # 缓存未命中，从数据库获取
    user = await db.get_user(user_id)

    # 存入缓存（TTL 1 小时）
    await redis_manager.set(f'user:{user_id}', user, ex=3600)

    return user
```

## API 参考 📚

### 字符串操作

| 方法 | 说明 | 示例 |
|------|------|------|
| `set(key, value, ex)` | 设置值 | `await redis.set('key', 'value', ex=3600)` |
| `get(key, default)` | 获取值 | `await redis.get('key')` |
| `delete(*keys)` | 删除键 | `await redis.delete('key1', 'key2')` |
| `exists(*keys)` | 检查存在性 | `await redis.exists('key')` |
| `expire(key, ex)` | 为已存在的键设置过期时间 | `await redis.expire('key', 3600)` |
| `ttl(key)` | 获取键的剩余生存时间 | `await redis.ttl('key')` |
| `clear()` | 清空数据库 | `await redis.clear()` |

### 批量操作

| 方法 | 说明 |
|------|------|
| `mset(data, ex)` | 批量设置（支持过期时间） |
| `mget(*keys)` | 批量获取 |

### 哈希操作

| 方法 | 说明 |
|------|------|
| `hset(name, mapping, ex)` | 设置哈希字段（支持过期时间） |
| `hget(name, key)` | 获取单个字段 |
| `hgetall(name)` | 获取所有字段 |
| `hdel(name, *keys)` | 删除字段 |

### 列表操作

| 方法 | 说明 |
|------|------|
| `lpush(name, *values, ex)` | 左端推入（支持过期时间） |
| `rpush(name, *values, ex)` | 右端推入（支持过期时间） |
| `lpop(name)` | 左端弹出 |
| `rpop(name)` | 右端弹出 |
| `lrange(name, start, end)` | 获取范围 |

### 集合操作

| 方法 | 说明 |
|------|------|
| `sadd(name, *members, ex)` | 添加成员（支持过期时间） |
| `smembers(name)` | 获取所有成员 |
| `srem(name, *members)` | 移除成员 |

## 序列化说明 🔄

模块自动处理 Python 对象和 Redis 字符串的转换：

```python
# 支持的类型自动序列化
data = {
    'string': 'hello',
    'number': 42,
    'float': 3.14,
    'boolean': True,
    'null': None,
    'list': [1, 2, 3],
    'dict': {'nested': 'value'},
    'custom': datetime.now()  # 通过 default=str 转换
}

await redis_manager.set('data', data)
result = await redis_manager.get('data')
# 完全相同的数据结构
```

## 最佳实践 💡

### 1. 缓存键设计

所有键都会自动添加项目前缀，确保多个项目共享 Redis 实例时不会冲突。

#### 第一层：项目级前缀（自动）

```python
# REDIS_PREFIX = 'anda_erp'（来自配置）
await redis.set('user:1', user_data)
# 实际键: anda_erp:user:1
```

#### 第二层：业务模块前缀（可选，推荐）

对于 ERP 这样的大型系统，建议在键名中包含**业务模块名**，形成两层前缀结构：

```python
# 推荐：在键名中包含模块名
await redis.set('user:profile:1', user_data)           # 用户模块
# 实际键: anda_erp:user:profile:1

await redis.set('order:pending:O001', order_data)      # 订单模块
# 实际键: anda_erp:order:pending:O001

await redis.set('payment:invoice:INV001', invoice)     # 支付模块
# 实际键: anda_erp:payment:invoice:INV001

await redis.set('inventory:stock:SKU001', stock)       # 库存模块
# 实际键: anda_erp:inventory:stock:SKU001
```

**使用常量类管理模块前缀（推荐）：**

```python
# app/cache/prefixes.py
class RedisPrefixes:
    """业务模块前缀常量"""
    USER_PROFILE = "user:profile"
    USER_SETTINGS = "user:settings"
    ORDER_PENDING = "order:pending"
    ORDER_COMPLETED = "order:completed"
    PAYMENT_INVOICE = "payment:invoice"
    INVENTORY_STOCK = "inventory:stock"


# 使用
from app.core.cache.prefixes import RedisPrefixes

await redis.set(f'{RedisPrefixes.USER_PROFILE}:1', user_data)
await redis.set(f'{RedisPrefixes.ORDER_PENDING}:O001', order_data)
```

**两层前缀的优势：**
- ✅ 键名结构清晰，易于理解
- ✅ 可按模块查询和管理缓存
- ✅ 便于不同团队维护各自模块
- ✅ 支持模块级的性能监控

**键名设计建议：**

```python
# ✅ 推荐 - 使用模块前缀
anda_erp:user:profile:1
anda_erp:user:settings:1
anda_erp:order:pending:O001
anda_erp:post:article:100
anda_erp:session:token:abc123

# ❌ 避免 - 键名设计不清晰
anda_erp:user1profile
anda_erp:userdata
anda_erp:order1pending
```

### 2. TTL 设置

所有主要数据操作函数都支持过期时间（TTL）设置，只需传递 `ex` 参数：

```python
# 字符串 - 设置过期时间
await redis_manager.set('user:1', user_data, ex=3600)

# 哈希 - 设置过期时间
await redis_manager.hset('user:profile', {'name': 'Alice', 'age': 30}, ex=3600)

# 列表 - 设置过期时间
await redis_manager.lpush('tasks', 'task1', 'task2', ex=300)

# 集合 - 设置过期时间
await redis_manager.sadd('tags', 'python', 'fastapi', ex=600)

# 批量设置 - 设置过期时间
await redis_manager.mset({
    'key1': 'value1',
    'key2': 'value2'
}, ex=3600)
```

**为已存在的键设置过期时间：**

```python
# 为已存在的键设置过期时间
await redis_manager.expire('user:1', 3600)

# 获取键的剩余生存时间
remaining = await redis_manager.ttl('user:1')
# 返回剩余秒数
# -1 表示键存在但没有过期时间
# -2 表示键不存在
```

**根据数据特性设置合理的过期时间：**

```python
# 用户信息：1 小时
await redis_manager.set('user:1', user, ex=3600)

# 验证码：5 分钟
await redis_manager.set('code:verify:user1', code, ex=300)

# 热门数据：30 秒
await redis_manager.set('trending:posts', posts, ex=30)

# 永不过期（谨慎使用）
await redis_manager.set('config:app', config)
```

### 3. 缓存预热

在应用启动时预加载关键数据：

```python
# 在 startup 事件中
async def warm_cache():
    redis_manager = get_redis_manager()
    
    # 预加载常用配置
    config = await db.get_config()
    await redis_manager.set('app:config', config)
    
    # 预加载热门数据
    trending = await db.get_trending_posts(limit=20)
    await redis_manager.set('trending:posts', trending, ex=3600)
```

### 4. 缓存失效策略

```python
# 更新数据时主动清除缓存
async def update_user(user_id: int, data: dict):
    redis_manager = get_redis_manager()
    
    # 更新数据库
    updated = await db.users.update(user_id, data)
    
    # 清除相关缓存
    await redis_manager.delete(
        f'user:{user_id}',
        f'user:{user_id}:profile',
        'users:list'  # 列表缓存也需要清除
    )
    
    return updated
```

### 5. 错误处理

```python
from redis.exceptions import RedisError

async def safe_cache_get(key: str, default=None):
    try:
        redis_manager = get_redis_manager()
        return await redis_manager.get(key, default)
    except RedisError as e:
        # 缓存异常不应影响主业务流程
        print(f"Cache error: {e}")
        return default
```

## 性能提示 ⚡

1. **批量操作优先** - 使用 `mset/mget` 而不是循环调用 `set/get`
2. **管道操作** - 对于大量操作，考虑使用 Redis 管道
3. **异步 I/O** - 始终使用 `await` 充分利用异步优势
4. **合理 TTL** - 避免过长的 TTL 导致内存占用
5. **监控内存** - 定期检查 Redis 内存使用情况

## 故障排查 🔧

### 配置错误提示

模块会在连接前检查所有配置，配置错误时会立即提示：

```
❌ Redis 连接失败: Redis 主机地址或端口配置错误
❌ Redis 连接失败: Redis 连接池大小必须大于 0，当前值: 0
❌ Redis 连接失败: Redis 连接超时时间必须大于 0，当前值: 0
```

**前置配置检查项：**
- ✓ 主机地址是否为空
- ✓ 端口号是否大于 0
- ✓ 连接池大小是否大于 0
- ✓ 连接超时是否大于 0

### 连接问题

```
日志: Redis client not connected. Call connect() first.
原因: 未调用 init_cache() 初始化
解决: 确保应用生命周期正确调用 init_cache()
```

### 连接拒绝

```
日志: ❌ Redis 连接失败: Connection refused
检查:
1. Redis 服务是否启动: redis-cli ping
2. REDIS_HOST/REDIS_PORT 配置是否正确
3. 防火墙是否开放 Redis 端口
```

### 序列化错误

```
日志: JSON serialization failed
原因: 自定义对象无法序列化
解决: 在对象中定义 __str__ 方法或使用 default=str
```

### 心跳检查失败（自动恢复）

```
日志: ⚠️ Redis 心跳检查失败: {error}
原因: 连接中断或 Redis 服务故障
处理: 模块自动重连，无需手动干预
    - 首次失败：记录 WARNING
    - 断开连接：wait 5 秒
    - 开始重连：记录 INFO 日志
    - 重连成功：✅ Redis 重连成功
    - 重连失败：❌ Redis 重连失败
```

### 查看日志示例

**连接成功时：**
```
[DEBUG] [Redis] 连接前配置检查 - 主机:localhost, 端口:6379
[DEBUG] [Redis] 创建连接池 - 最大连接数:10
[INFO]  ✅ Redis 连接成功 - 主机:localhost | 端口:6379 | 数据库:0
[INFO]  ❤️ Redis 心跳检查已启动 (检查间隔: 30 秒)
```

**运行正常时（每 30 秒）：**
```
[DEBUG] ❤️ Redis 心跳检查: 正常
```

**连接故障时：**
```
[WARNING] ⚠️ Redis 心跳检查失败: Connection lost
[INFO]  🔄 开始重连 Redis...
[INFO]  🔄 尝试重新连接 Redis...
[INFO]  ✅ Redis 重连成功
```

## 文件结构 📂

```
app/cache/
├── __init__.py          # 模块入口
├── redis.py             # 核心 Redis 管理器
├── decorators.py        # 缓存装饰器
└── README.md            # 文档（本文件）

config/
└── cache_config.py      # Redis 配置
```

## 配置详解 ⚙️

### CacheSettings

位置：`config/cache_config.py`

| 参数 | 类型 | 默认值 | 说明 | 验证 |
|------|------|--------|------|------|
| `REDIS_HOST` | str | localhost | Redis 服务器地址 | 不能为空 ✓ |
| `REDIS_PORT` | int | 6379 | Redis 端口 | 必须 > 0 ✓ |
| `REDIS_DB` | int | 0 | 数据库编号 | 直接使用 |
| `REDIS_PASSWORD` | str \| None | None | 认证密码 | 可选 |
| `REDIS_MAX_CONNECTIONS` | int | 10 | 连接池最大连接数 | 必须 > 0 ✓ |
| `REDIS_TIMEOUT` | int | 5 | 连接超时时间（秒） | 必须 > 0 ✓ |
| `REDIS_PREFIX` | str | anda_erp | **项目级键前缀**（手动配置）| 用于区分多项目 |

**REDIS_PREFIX 说明：**

```python
# 用途：在多项目共享 Redis 实例时，区分不同项目的数据
# 示例：
# "anda_erp"      # anda-erp 项目
# "shop_system"   # 电商系统
# "blog_platform" # 博客平台
```

**键名中的前缀使用方式：**

```python
# 代码
await redis.set('user:1', data)

# Redis 中实际存储（自动添加前缀）
anda_erp:user:1
```

**业务模块前缀（可选）：**

在键名中包含业务模块名，实现两层前缀结构：

```python
# 项目前缀  + 模块名  + 业务键
#   ↓         ↓        ↓
anda_erp  :  user     :  profile:1
anda_erp  :  order    :  pending:123
anda_erp  :  payment  :  invoice:456

# 在代码中
await redis.set('user:profile:1', data)
# Redis 中: anda_erp:user:profile:1
```

### 环境变量配置示例

```bash
# Linux/macOS
export REDIS_HOST=redis.example.com
export REDIS_PORT=6379
export REDIS_DB=0
export REDIS_MAX_CONNECTIONS=20
export REDIS_PREFIX=anda_erp

# Windows PowerShell
$env:REDIS_HOST = "redis.example.com"
$env:REDIS_PORT = 6379
$env:REDIS_DB = 0
$env:REDIS_MAX_CONNECTIONS = 20
$env:REDIS_PREFIX = "anda_erp"
```

### 多项目场景示例

假设有 3 个项目共享同一个 Redis 实例：

```python
# 项目 1: anda-erp
REDIS_PREFIX = 'anda_erp'
# Redis 键: anda_erp:user:1, anda_erp:order:123

# 项目 2: shop-system
REDIS_PREFIX = 'shop_system'
# Redis 键: shop_system:user:1, shop_system:order:123

# 项目 3: blog-platform  
REDIS_PREFIX = 'blog_platform'
# Redis 键: blog_platform:user:1, blog_platform:post:100
```

**关键点：** 每个项目配置不同的 `REDIS_PREFIX`，数据完全隔离 ✅

## 依赖 📦

```
redis>=5.0.0
```

自动通过 `pip install redis` 或项目依赖安装。

## License

MIT

