import asyncio
from typing import Any

from loguru import logger

import app.core.log as log_module
import app.core.log.log_loguru as loguru_module


class FakeLogger:
    """记录日志 sink 配置，避免测试创建真实文件或后台队列。"""

    def __init__(self) -> None:
        self.add_calls: list[dict[str, Any]] = []

    def remove(self) -> None:
        """模拟移除默认 handler。"""

    def add(self, _sink: object = None, **kwargs: Any) -> int:
        """记录 sink 参数。"""
        self.add_calls.append(kwargs)
        return len(self.add_calls)


def test_log_sinks_disable_variable_diagnostics(monkeypatch: Any) -> None:
    """所有日志输出均应关闭可能泄漏局部变量的诊断信息。"""
    fake_logger = FakeLogger()
    monkeypatch.setattr(loguru_module, "logger", fake_logger)

    registered_logger = loguru_module.register()

    assert registered_logger is fake_logger
    assert len(fake_logger.add_calls) == 2
    assert all(call["diagnose"] is False for call in fake_logger.add_calls)
    assert all(call["backtrace"] is False for call in fake_logger.add_calls)


def _emit_stdlib_log(handler: Any) -> None:
    """从业务调用点发出一条标准库日志，用于验证来源透传。"""
    stdlib_logger = loguru_module.logging.getLogger("tests.intercept-caller")
    original_handlers = stdlib_logger.handlers.copy()
    original_propagate = stdlib_logger.propagate
    try:
        stdlib_logger.handlers = [handler]
        stdlib_logger.propagate = False
        stdlib_logger.warning("intercept caller test")
    finally:
        stdlib_logger.handlers = original_handlers
        stdlib_logger.propagate = original_propagate


def test_intercept_handler_preserves_actual_caller() -> None:
    """标准库日志转发后应定位到真实调用函数，而不是 logging.callHandlers。"""
    captured_functions: list[str] = []
    sink_id = logger.add(
        lambda message: captured_functions.append(message.record["function"]),
        filter=lambda record: record["message"] == "intercept caller test",
    )
    try:
        _emit_stdlib_log(loguru_module.InterceptHandler())
    finally:
        logger.remove(sink_id)

    assert captured_functions == ["_emit_stdlib_log"]


def test_complete_log_waits_for_lazy_logger_queue(monkeypatch: Any) -> None:
    """应用关闭时应等待已初始化 logger 的 complete 完成。"""
    complete_calls: list[str] = []

    class FakeCompletableLogger:
        async def complete(self) -> None:
            await asyncio.sleep(0)
            complete_calls.append("complete")

    monkeypatch.setattr(log_module.log, "_logger", FakeCompletableLogger())

    asyncio.run(log_module.complete_log())

    assert complete_calls == ["complete"]
