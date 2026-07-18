# 异步数据访问工作流

在修改 SQLAlchemy 模型、Repository、数据库查询、事务、关系加载或并发数据库任务时读取本文件。

下列代码使用虚构的 `Item` 业务对象演示稳定结构。复制前应替换业务命名，并核对当前模型、Schema、Repository 与会话配置。

## 目录

- [先检查当前实现](#先检查当前实现)
- [Session 与事务](#session-与事务)
- [查询与返回值](#查询与返回值)
- [约束与迁移](#约束与迁移)
- [Repository 边界](#repository-边界)

## 先检查当前实现

读取当前数据库引擎与会话工厂、请求级数据库依赖、`BaseRepository`、相关模型和测试。不要在 skill 中假设会话参数、时间语义、迁移工具或 Repository 实例策略始终不变。

## Session 与事务

- 将 `AsyncSession` 视为请求或任务级资源，通过参数显式传递。
- 不要在并发任务之间共享同一个 `AsyncSession`；确需并发数据库任务时，为每个任务建立并可靠关闭独立会话。
- 让 Service 或任务编排层拥有写事务，Repository 不提交或回滚调用方事务。
- 准备写入时，在第一次属于该写流程的数据库访问前进入事务，避免 SQLAlchemy autobegin 与显式 `begin()` 冲突。
- 按需使用 `flush()` 获取数据库生成值或尽早暴露约束错误；仅在确有需要时 `refresh()`。
- 读流程通常不需要为了形式统一而额外包裹显式写事务。

### 写事务示例

写事务通常由 Service 或任务编排层声明。需要从 ORM 对象构造响应时，可在事务退出前完成字段读取，避免依赖未知的提交后过期策略：

```python
from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.item_repo import ItemRepository
from app.schemas.item_schema import ItemCreate, ItemResponse


async def create_item(
    session: AsyncSession,
    payload: ItemCreate,
    repository: ItemRepository,
) -> ItemResponse:
    """在 Service 层完成一个原子写流程。"""
    async with session.begin():
        item = await repository.create(session, name=payload.name)
        response = ItemResponse.model_validate(item)

    return response
```

Repository 在这个流程中可以 `add()`、`flush()` 或按需 `refresh()`，但不应自行 `commit()` 或 `rollback()`。

## 查询与返回值

- 使用异步 SQLAlchemy 2.x statement API，并正确等待执行结果。
- 根据查询基数选择 `scalar_one_or_none()`、`scalar_one()` 或 `scalars().all()`，不要用错误的结果读取方式掩盖重复数据。
- 对列表和总数分别建立正确查询；当前页为空不代表总数为零。
- 在 Repository 中明确关系加载策略，响应转换前加载所需关系，避免 N+1、隐式 I/O 或异步懒加载错误。
- 原生 SQL 仅在确有必要时使用参数绑定，不拼接用户输入。

### 查询示例

单条查询和分页查询应显式表达基数；数据查询与总数查询要应用同一组过滤条件：

```python
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.item import Item


async def get_by_id(
    session: AsyncSession,
    item_id: int,
) -> Item | None:
    """按主键查询单个业务对象。"""
    statement = select(Item).where(Item.id == item_id)
    result = await session.execute(statement)
    return result.scalar_one_or_none()


async def list_page(
    session: AsyncSession,
    *,
    offset: int,
    limit: int,
) -> tuple[list[Item], int]:
    """分页查询业务对象并返回独立统计结果。"""
    data_statement = select(Item).order_by(Item.id).offset(offset).limit(limit)
    count_statement = select(func.count(Item.id))

    item_result = await session.scalars(data_statement)
    total = await session.scalar(count_statement)
    return list(item_result.all()), total or 0
```

如果响应需要关系字段，在当前模型确认关系名后，先从 `sqlalchemy.orm` 导入 `selectinload`，再显式加载，例如 `select(Item).options(selectinload(Item.tags))`；不要把示例中的关系名当成项目现状。

## 约束与迁移

- 用数据库约束保证并发下的唯一性和完整性；“先查再写”只能改善提示，不能替代约束。
- 只转换能够可靠识别的预期数据库异常，不向客户端或日志暴露敏感数据库细节。
- 修改表、列、索引、外键或持久化枚举前，确认当前项目的迁移机制和交付范围。
- 如果任务不包含迁移执行，在交付中明确尚未应用的数据库变化及风险。

## Repository 边界

- 保持 Repository 无状态，不保存请求、当前用户或会话等调用级状态。
- 让 Repository 返回 ORM 对象、标量、集合或明确的数据结构，由 Service 解释业务含义。
- 调试 SQL 时优先复用项目现有的安全编译或日志方式；不要把绑定参数和凭证渲染进日志。

为查询语义、事务、约束冲突和会话生命周期补充对应测试。
