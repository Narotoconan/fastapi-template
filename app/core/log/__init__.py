from __future__ import annotations

from typing import Any

import loguru

from .log_loguru import register


class _LazyLogger:
    """延迟初始化的日志代理。

    在 register_log() 调用之前持有空引用；调用后将所有日志方法转发给真实的
    logger 实例。外部代码始终通过模块级 `log` 变量使用，无需感知内部状态。
    """

    def __init__(self) -> None:
        self._logger: loguru.Logger | None = None

    def _get(self) -> loguru.Logger:
        """获取真实 logger，未初始化时抛出 RuntimeError。"""
        if self._logger is None:
            raise RuntimeError("日志未初始化，请先在应用启动时调用 register_log()")
        return self._logger

    def initialize(self) -> None:
        """初始化真实 logger 实例，由 register_log() 在应用启动时调用。"""
        self._logger = register()

    def info(self, msg: str, *args: Any, **kwargs: Any) -> None:
        self._get().info(msg, *args, **kwargs)

    def error(self, msg: str, *args: Any, **kwargs: Any) -> None:
        self._get().error(msg, *args, **kwargs)

    def warning(self, msg: str, *args: Any, **kwargs: Any) -> None:
        self._get().warning(msg, *args, **kwargs)

    def debug(self, msg: str, *args: Any, **kwargs: Any) -> None:
        self._get().debug(msg, *args, **kwargs)

    async def complete(self) -> None:
        """等待 Loguru 队列及异步 sink 完成，未初始化时安全返回。"""
        logger = self._logger
        if logger is not None:
            await logger.complete()


log = _LazyLogger()


def register_log() -> None:
    """初始化全局日志实例，应在应用启动阶段调用一次。"""
    log.initialize()


async def complete_log() -> None:
    """排空全局日志队列，应在其他应用资源清理完成后调用。"""
    await log.complete()


__all__ = ["complete_log", "log", "register_log"]
