# Redis 缓存

`app/core/cache/` 提供异步 Redis 连接管理、项目级键前缀、严格 JSON 序列化、常用数据结构操作和
异步函数缓存装饰器。

Redis 是当前模板的启动强依赖：应用启动时必须连接成功并通过 `PING`，否则服务不会进入就绪状态。
连接、命令和写入序列化错误默认会记录并向外传播，不会自动静默降级；读取到损坏的版本化 JSON
载荷时是例外，模块会记录警告并返回原始字符串。

## 文件职责

```text
app/core/cache/
├── __init__.py       # init_cache / close_cache 与公共导出
├── redis.py          # RedisManager、连接池和数据操作
├── decorators.py     # @cache 异步函数缓存
├── prefixes.py       # 业务键前缀常量
└── README.md
```

配置位于 [`config/cache_config.py`](../../../config/cache_config.py)，依赖由 `pyproject.toml` 和
`uv.lock` 管理，无需单独执行 `pip install redis`。

## 生命周期

应用生命周期已经完成集成：

```text
启动：PostgreSQL 检查 -> Redis connect + PING -> 启动 30 秒心跳
关闭：PostgreSQL -> Redis -> Loguru 队列
```

连接行为：

- 并发 `connect()` 通过锁串行化，只初始化一个客户端。
- 客户端仅在 `PING` 成功后才对外发布。
- 心跳每 30 秒执行一次。
- 心跳失败后每次等待 5 秒重连，最多尝试 5 次。
- 持续失败达到上限后停止当前心跳任务，不会无限重试。
- `disconnect()` 会先取消并等待心跳结束，再关闭客户端和连接池。
- 启动中途失败仍会进入统一资源清理流程。

正常通过 `main:app` 启动时不需要手工调用 `init_cache()` 或 `close_cache()`。

## 配置

配置类读取进程环境变量，不会自行加载根目录 `.env`。本地可使用
`uv run --env-file .env.local ...`，Docker 由 Compose 注入。

| 变量 | 类型 | 默认值 | 约束与用途 |
| --- | --- | --- | --- |
| `REDIS_HOST` | `str` | `localhost` | 不得为空白 |
| `REDIS_PORT` | `int` | `6379` | `1..65535` |
| `REDIS_DB` | `int` | `0` | 必须大于等于 0 |
| `REDIS_PASSWORD` | `str \| None` | `None` | 可选认证密码 |
| `REDIS_MAX_CONNECTIONS` | `int` | `10` | 单进程连接池上限，至少 1 |
| `REDIS_TIMEOUT` | `float` | `5` | 建立连接超时，必须大于 0 |
| `REDIS_COMMAND_TIMEOUT` | `float` | `5` | 命令读写超时，必须大于 0 |
| `REDIS_PREFIX` | `str` | `template` | 项目键命名空间，不得为空白 |

连接池上限按应用进程计算；多进程部署时需要乘以进程数并结合 Redis 连接上限评估。

## 快速使用

```python
from app.core.cache import RedisPrefixes, get_redis_manager


async def save_user_profile(
    user_id: int,
    profile: dict[str, str | int],
) -> None:
    """写入用户资料缓存。"""
    redis_manager = get_redis_manager()
    cache_key = f"{RedisPrefixes.USER_PROFILE}:{user_id}"
    await redis_manager.hset(cache_key, profile, ex=300)
```

所有公开操作都是异步方法，必须使用 `await`。

## 键前缀

`RedisManager` 自动把 `REDIS_PREFIX` 加到每个业务键前：

```python
await redis_manager.set("user:1", {"id": 1}, ex=300)
```

当 `REDIS_PREFIX=template` 时，实际键为：

```text
template:user:1
```

建议使用 `{domain}:{resource}:{id}` 这样的稳定结构。模板当前提供以下业务前缀常量：

| 常量 | 值 |
| --- | --- |
| `USER_PROFILE` | `user:profile` |
| `USER_SETTINGS` | `user:settings` |
| `USER_PERMISSIONS` | `user:permissions` |
| `USER_SESSIONS` | `user:sessions` |
| `INVENTORY_STOCK` | `inventory:stock` |
| `INVENTORY_RESERVED` | `inventory:reserved` |
| `REPORT_DAILY` | `report:daily` |
| `REPORT_MONTHLY` | `report:monthly` |
| `REPORT_SUMMARY` | `report:summary` |
| `CONFIG_APP` | `config:app` |
| `CONFIG_PRODUCTS` | `config:products` |
| `CACHE_TRENDING` | `cache:trending` |

新增真实业务后再扩展 [`prefixes.py`](prefixes.py)，不要在文档或调用方引用不存在的常量。

`REDIS_PREFIX` 只是命名隔离，不是安全边界。共享 Redis 时仍需配置认证、网络策略和独立权限。

## 序列化协议

写入值使用带版本标记的 JSON 协议。支持的精确类型为：

- `str`
- `bool`
- `int`
- 有限 `float`
- `None`
- `list`，元素递归遵循同一规则
- 字符串键 `dict`，值递归遵循同一规则

不支持直接写入：

- `tuple`
- Pydantic 模型
- ORM 对象
- `datetime`、`UUID`、`Enum`
- 自定义类或基础类型子类
- 非字符串键字典
- `NaN`、`Infinity`

不支持的值会抛出 `TypeError` 或 JSON 数值校验错误，不会隐式调用 `str()`。业务对象应先通过明确的
响应 Schema 筛选字段，再使用 `model_dump(mode="json")` 转为 JSON-safe 数据：

```python
cache_value = user_response.model_dump(mode="json")
await redis_manager.set("user:1", cache_value, ex=300)
```

不要缓存密码哈希、Token、密钥或未稳定加载关系的完整 ORM 对象。

### 旧值兼容

没有当前版本标记的旧缓存值会按原始字符串返回，不再猜测 `"123"`、`"true"` 或 JSON 外观字符串
的类型。升级序列化协议时：

- 有 TTL 的旧键可以等待自然过期。
- 无 TTL 的旧键应按项目 `REDIS_PREFIX` 定向清理。
- 损坏的版本化载荷会记录不包含原始值的警告，并按原始字符串返回。
- Redis Set 中的新旧编码可能形成逻辑重复，新版 `srem()` 只会移除新版编码成员。
- 不要对共享数据库执行 `FLUSHDB`。

## API 速查

### 连接与通用键操作

| 方法 | 返回值 | 说明 |
| --- | --- | --- |
| `connect()` | `None` | 创建连接池、验证 PING 并启动心跳 |
| `disconnect()` | `None` | 停止心跳并关闭连接 |
| `ping()` | `bool` | 检查当前客户端连接 |
| `set(key, value, ex=None)` | `bool` | 写入 JSON 值，可设置 TTL |
| `get(key, default=None)` | `Any` | 获取并反序列化；未命中返回 `default` |
| `delete(*keys)` | `int` | 返回删除键数量 |
| `exists(*keys)` | `int` | 返回存在的键数量，不是布尔值 |
| `expire(key, ex)` | `bool` | 为已有键设置 TTL |
| `ttl(key)` | `int` | 剩余秒数；`-1` 无过期，`-2` 不存在 |
| `clear()` | `None` | 分批清理当前项目前缀下的键 |

### 批量、Hash、List 与 Set

| 方法 | 返回值 | 说明 |
| --- | --- | --- |
| `mset(data, ex=None)` | `bool` | 批量写入，可统一设置 TTL |
| `mget(*keys)` | `list[Any]` | 严格按传入键顺序返回 |
| `hset(name, mapping, ex=None)` | `int` | 返回新增字段数量 |
| `hget(name, key)` | `Any` | 获取单个 Hash 字段 |
| `hgetall(name)` | `dict[str, Any]` | 获取全部 Hash 字段 |
| `hdel(name, *keys)` | `int` | 返回删除字段数量 |
| `lpush(name, *values, ex=None)` | `int` | 左侧推入，返回列表长度 |
| `rpush(name, *values, ex=None)` | `int` | 右侧推入，返回列表长度 |
| `lpop(name)` / `rpop(name)` | `Any` | 弹出元素；空列表返回 `None` |
| `lrange(name, start=0, end=-1)` | `list[Any]` | 获取闭区间范围 |
| `sadd(name, *members, ex=None)` | `int` | 返回新增成员数量 |
| `smembers(name)` | `list[Any]` | 返回无序列表 |
| `srem(name, *members)` | `int` | 返回移除成员数量 |

批量获取示例：

```python
await redis_manager.mset(
    {
        "key1": "value1",
        "key2": {"nested": "data"},
        "key3": [1, 2, 3],
    },
    ex=300,
)

values = await redis_manager.mget("key1", "key2", "key3")
# ["value1", {"nested": "data"}, [1, 2, 3]]
```

传入空键或空成员时，批量删除、存在检查和集合/列表写入会返回 0；空 `mset` 返回 `True`。

## TTL 原子性

以下带 `ex` 的复合写操作会在 Redis 事务 pipeline 中同时执行写入和 `EXPIRE`：

- `mset`
- `hset`
- `lpush`
- `rpush`
- `sadd`

这样可以避免写入成功但进程在设置 TTL 前中断，留下意外的永久键。普通 `set(..., ex=...)` 由 Redis
单条命令原子完成。

设置 TTL 时仍需根据一致性和容量选择合理时长；`ex=None` 表示不自动过期，应谨慎使用。

## 按项目前缀清理

```python
await redis_manager.clear()
```

`clear()`：

- 使用 `SCAN` 分批查找当前 `REDIS_PREFIX` 下的键。
- `SCAN` 使用 `COUNT 500` 作为扫描提示，实际每批返回数量由 Redis 决定。
- 优先使用 `UNLINK` 异步释放。
- Redis 不支持 `UNLINK` 时回退到当前批次的 `DELETE`。
- 不影响其他项目前缀，不调用 `FLUSHDB`。

清理仍是高影响操作，应只在缓存协议升级、测试隔离或明确的运维流程中执行。

## 函数缓存装饰器

`@cache` 只支持异步函数：

```python
from app.core.cache import cache


@cache(key_prefix="item:category-options", ttl=3600)
async def get_item_category_options() -> list[dict[str, int | str]]:
    """读取稳定且可 JSON 序列化的商品分类选项。"""
    return [{"label": "默认分类", "value": 1}]
```

### 键生成规则

装饰器按以下内容生成 SHA-256 键：

- 函数 `module + qualname`
- 绑定后的全部参数
- 补齐后的默认参数
- 可选 `key_prefix`

因此：

- 位置参数与等价关键字参数命中同一键。
- 显式传入默认值与省略默认值命中同一键。
- 不同模块或不同限定名称的同名函数不会冲突。
- `None` 可以被正确缓存，不会与“未命中”混淆。

缓存键参数支持 `str / bool / int / finite float / None / list / tuple / 字符串键 dict`。
`Request`、`AsyncSession`、ORM 对象和其他运行时对象会被拒绝。

实例方法与类方法会按接收者类型生成键，不读取对象状态。因此装饰器只适合不依赖实例可变状态的
无状态 Service；影响结果的稳定状态必须显式作为函数参数。

### 限制

- 返回值必须符合前述 Redis 序列化协议；键参数支持 `tuple`，返回值不支持 `tuple`。
- 装饰器不提供 singleflight、分布式锁或缓存击穿保护。
- Redis 读写错误默认向外传播。
- `ttl=None` 会产生无过期键。
- 装饰器没有自动失效业务关联键的能力。

高并发热点、条件 TTL、跨多个键失效或写后一致性场景应使用 Service 层手动缓存策略。

## 缓存一致性与降级

推荐的写操作顺序：

1. 在 Service 中开启数据库事务。
2. 完成数据库写入并成功退出事务。
3. 删除或更新相关缓存键。
4. 明确缓存失效失败时是让请求失败、记录待补偿任务，还是允许短暂不一致。

不要在 Repository 中操作缓存或提交事务，Router 也不应直接编排“查缓存 → 查数据库 → 回填”。

对于明确允许降级的只读缓存，Service 可以只捕获预期的 Redis 连接类异常、记录安全上下文并回源
数据库。不要把“缓存失败永远放行”作为全局规则，也不要捕获所有 `Exception` 后静默忽略，
否则序列化错误和业务缺陷会被隐藏。

## 故障排查

### Redis 客户端未初始化

```text
Redis 客户端未初始化，请先调用 connect() 建立连接
```

通过 `main:app` 启动时由 lifespan 自动连接。单独调用 Service 或脚本时，需要显式管理
`init_cache()` / `close_cache()`，并保证日志已初始化。

### 连接失败

检查：

- Redis 服务是否运行且能从当前进程或容器访问。
- `REDIS_HOST / REDIS_PORT / REDIS_DB / REDIS_PASSWORD` 是否正确。
- 容器内是否误用了 `localhost`。
- 防火墙、网络策略和 Redis ACL 是否允许连接。
- 连接池是否耗尽，超时是否符合当前网络环境。

### 序列化失败

把 Pydantic / ORM 对象显式转换为 JSON-safe 的基础类型。不要通过 `str(obj)` 绕过类型检查，
否则会破坏读取后的类型契约。

### 心跳重连耗尽

持续故障最多重试 5 次。恢复 Redis 后需要由运维重启应用或由上层恢复机制重新建立连接；不要假设
已经退出的心跳任务会无限自行恢复。

## 相关测试

```bash
uv run pytest tests/test_cache_decorator.py tests/test_redis_atomic_expiry.py tests/test_redis_data_safety.py tests/test_redis_reconnect.py
```

这些测试覆盖键稳定性、`None` 缓存、严格序列化、TTL 原子性、前缀清理、并发连接和有限重连。

[返回项目 README](../../../README.md)
