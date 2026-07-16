import asyncio
from contextlib import asynccontextmanager
from typing import override

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker

import app.core.database as database_module
import app.dependencies.db as db_dependency_module


class FakeResult:
    """提供健康检查所需的最小查询结果接口。"""

    def __init__(self, scalar_value: int) -> None:
        self.scalar_value = scalar_value

    def scalar_one(self) -> int:
        """返回模拟的单个标量值。"""
        return self.scalar_value


class FakeSession:
    """记录请求会话的进入、回滚、查询和关闭行为。"""

    def __init__(
        self,
        *,
        rollback_error: BaseException | None = None,
        close_error: BaseException | None = None,
        execute_error: BaseException | None = None,
        scalar_value: int = 1,
    ) -> None:
        self.rollback_error = rollback_error
        self.close_error = close_error
        self.execute_error = execute_error
        self.scalar_value = scalar_value
        self.rollback_calls = 0
        self.close_calls = 0
        self.execute_calls = 0

    async def rollback(self) -> None:
        """记录回滚调用，并按需模拟回滚失败。"""
        self.rollback_calls += 1
        if self.rollback_error is not None:
            raise self.rollback_error

    async def close(self) -> None:
        """记录关闭调用，并按需模拟关闭失败。"""
        self.close_calls += 1
        if self.close_error is not None:
            raise self.close_error

    async def execute(self, _statement: object) -> FakeResult:
        """返回健康检查使用的模拟查询结果。"""
        self.execute_calls += 1
        if self.execute_error is not None:
            raise self.execute_error
        return FakeResult(self.scalar_value)


class BlockingCloseSession(FakeSession):
    """模拟可在关闭阶段精确触发任务取消的会话。"""

    def __init__(self) -> None:
        super().__init__()
        self.close_started = asyncio.Event()
        self.close_allowed = asyncio.Event()
        self.close_finished = asyncio.Event()

    @override
    async def close(self) -> None:
        self.close_calls += 1
        self.close_started.set()
        await self.close_allowed.wait()
        self.close_finished.set()


class FakeSessionFactory:
    """每次调用返回指定的模拟请求会话。"""

    def __init__(self, session: FakeSession) -> None:
        self.session = session
        self.calls = 0

    def __call__(self) -> FakeSession:
        self.calls += 1
        return self.session


def test_database_uses_plain_async_sessionmaker() -> None:
    """数据库入口应暴露普通会话工厂，不再保留任务级 scoped registry。"""
    assert isinstance(database_module.AsyncSessionLocal, async_sessionmaker)
    assert not hasattr(database_module.AsyncSessionLocal, "remove")


def test_get_db_closes_successful_request_session(monkeypatch: pytest.MonkeyPatch) -> None:
    """请求正常结束时应由异步上下文管理器关闭独立会话。"""
    session = FakeSession()
    session_factory = FakeSessionFactory(session)
    monkeypatch.setattr(db_dependency_module, "AsyncSessionLocal", session_factory)

    async def run_case() -> None:
        dependency_context = asynccontextmanager(db_dependency_module.get_db)
        async with dependency_context() as yielded_session:
            assert yielded_session is session

    asyncio.run(run_case())

    assert session_factory.calls == 1
    assert session.close_calls == 1
    assert session.rollback_calls == 0


def test_get_db_preserves_request_error_when_rollback_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    """回滚自身失败时仍应向上游重新抛出原始请求异常。"""
    request_error = RuntimeError("原始请求异常")
    session = FakeSession(rollback_error=OSError("模拟回滚失败"))
    session_factory = FakeSessionFactory(session)
    error_logs: list[str] = []
    monkeypatch.setattr(db_dependency_module, "AsyncSessionLocal", session_factory)
    monkeypatch.setattr(db_dependency_module.log, "error", error_logs.append)

    async def run_case() -> None:
        dependency_context = asynccontextmanager(db_dependency_module.get_db)
        async with dependency_context():
            raise request_error

    with pytest.raises(RuntimeError) as exc_info:
        asyncio.run(run_case())

    assert exc_info.value is request_error
    assert session.rollback_calls == 1
    assert session.close_calls == 1
    assert error_logs == ["数据库会话回滚失败 | request_error_type=RuntimeError | rollback_error_type=OSError"]


def test_get_db_preserves_request_error_when_close_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    """关闭会话失败时不得覆盖原始请求异常。"""
    request_error = RuntimeError("原始请求异常")
    session = FakeSession(close_error=OSError("模拟关闭失败"))
    session_factory = FakeSessionFactory(session)
    error_logs: list[str] = []
    monkeypatch.setattr(db_dependency_module, "AsyncSessionLocal", session_factory)
    monkeypatch.setattr(db_dependency_module.log, "error", error_logs.append)

    async def run_case() -> None:
        dependency_context = asynccontextmanager(db_dependency_module.get_db)
        async with dependency_context():
            raise request_error

    with pytest.raises(RuntimeError) as exc_info:
        asyncio.run(run_case())

    assert exc_info.value is request_error
    assert session.rollback_calls == 1
    assert session.close_calls == 1
    assert error_logs == ["数据库会话关闭失败 | request_error_type=RuntimeError | close_error_type=OSError"]


def test_get_db_rolls_back_cancelled_request(monkeypatch: pytest.MonkeyPatch) -> None:
    """请求任务被取消时也应回滚并关闭数据库会话。"""
    session = FakeSession()
    session_factory = FakeSessionFactory(session)
    monkeypatch.setattr(db_dependency_module, "AsyncSessionLocal", session_factory)

    async def run_case() -> None:
        request_started = asyncio.Event()
        never_complete = asyncio.Event()
        dependency_context = asynccontextmanager(db_dependency_module.get_db)

        async def simulated_request() -> None:
            async with dependency_context():
                request_started.set()
                await never_complete.wait()

        request_task = asyncio.create_task(simulated_request())
        await request_started.wait()
        request_task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await request_task

    asyncio.run(run_case())

    assert session.rollback_calls == 1
    assert session.close_calls == 1


def test_get_db_preserves_cancellation_when_close_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    """取消请求的关闭失败也不能替换 CancelledError。"""
    session = FakeSession(close_error=OSError("模拟关闭失败"))
    session_factory = FakeSessionFactory(session)
    error_logs: list[str] = []
    monkeypatch.setattr(db_dependency_module, "AsyncSessionLocal", session_factory)
    monkeypatch.setattr(db_dependency_module.log, "error", error_logs.append)

    async def run_case() -> None:
        dependency_context = asynccontextmanager(db_dependency_module.get_db)
        async with dependency_context():
            raise asyncio.CancelledError

    with pytest.raises(asyncio.CancelledError):
        asyncio.run(run_case())

    assert session.rollback_calls == 1
    assert session.close_calls == 1
    assert error_logs == ["数据库会话关闭失败 | request_error_type=CancelledError | close_error_type=OSError"]


def test_get_db_propagates_close_error_after_success(monkeypatch: pytest.MonkeyPatch) -> None:
    """没有原始请求异常时，会话关闭失败应正常暴露。"""
    close_error = OSError("模拟关闭失败")
    session = FakeSession(close_error=close_error)
    session_factory = FakeSessionFactory(session)
    monkeypatch.setattr(db_dependency_module, "AsyncSessionLocal", session_factory)

    async def run_case() -> None:
        dependency_context = asynccontextmanager(db_dependency_module.get_db)
        async with dependency_context():
            pass

    with pytest.raises(OSError) as exc_info:
        asyncio.run(run_case())

    assert exc_info.value is close_error
    assert session.close_calls == 1


def test_get_db_shields_session_close_from_request_cancellation(monkeypatch: pytest.MonkeyPatch) -> None:
    """取消恰好发生在关闭阶段时，底层关闭任务仍必须继续完成。"""
    session = BlockingCloseSession()
    session_factory = FakeSessionFactory(session)
    monkeypatch.setattr(db_dependency_module, "AsyncSessionLocal", session_factory)

    async def run_case() -> None:
        dependency_context = asynccontextmanager(db_dependency_module.get_db)

        async def simulated_request() -> None:
            async with dependency_context():
                pass

        request_task = asyncio.create_task(simulated_request())
        await session.close_started.wait()
        request_task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await request_task

        assert session.close_finished.is_set() is False
        session.close_allowed.set()
        await asyncio.wait_for(session.close_finished.wait(), timeout=1)

    asyncio.run(run_case())

    assert session.close_calls == 1
    assert session.close_finished.is_set() is True


def test_database_health_check_uses_session_context(monkeypatch: pytest.MonkeyPatch) -> None:
    """数据库健康检查应使用同一个普通会话工厂并可靠关闭会话。"""
    session = FakeSession(scalar_value=1)
    session_factory = FakeSessionFactory(session)
    monkeypatch.setattr(database_module, "AsyncSessionLocal", session_factory)

    is_healthy = asyncio.run(database_module.db_health_check())

    assert is_healthy is True
    assert session_factory.calls == 1
    assert session.execute_calls == 1
    assert session.close_calls == 1


def test_database_health_check_closes_session_after_query_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """健康检查查询失败时也应退出会话上下文，避免连接滞留。"""
    query_error = RuntimeError("模拟健康检查失败")
    session = FakeSession(execute_error=query_error)
    session_factory = FakeSessionFactory(session)
    monkeypatch.setattr(database_module, "AsyncSessionLocal", session_factory)

    with pytest.raises(RuntimeError) as exc_info:
        asyncio.run(database_module.db_health_check())

    assert exc_info.value is query_error
    assert session.execute_calls == 1
    assert session.close_calls == 1


def test_database_health_check_preserves_query_error_when_close_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """健康检查关闭失败不得覆盖原始查询异常。"""
    query_error = RuntimeError("模拟健康检查失败")
    session = FakeSession(
        execute_error=query_error,
        close_error=OSError("模拟关闭失败"),
    )
    session_factory = FakeSessionFactory(session)
    error_logs: list[str] = []
    monkeypatch.setattr(database_module, "AsyncSessionLocal", session_factory)
    monkeypatch.setattr(database_module.log, "error", error_logs.append)

    with pytest.raises(RuntimeError) as exc_info:
        asyncio.run(database_module.db_health_check())

    assert exc_info.value is query_error
    assert session.execute_calls == 1
    assert session.close_calls == 1
    assert error_logs == ["数据库健康检查会话关闭失败 | query_error_type=RuntimeError | close_error_type=OSError"]
