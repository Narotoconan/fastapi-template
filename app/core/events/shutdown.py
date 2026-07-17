from collections.abc import Awaitable, Callable

from app.core.cache import close_cache
from app.core.database import db_disconnect
from app.core.log import complete_log, log


async def _run_cleanup(resource_name: str, cleanup: Callable[[], Awaitable[None]]) -> None:
    """执行单项资源清理并记录失败，避免阻断后续资源释放。"""
    try:
        await cleanup()
    except Exception as exc:
        log.error(f"❌ 应用关闭时清理 {resource_name} 失败: error_type={type(exc).__name__}")


async def shutdown() -> None:
    """依次释放应用资源，单项失败不阻断其余清理流程。"""
    await _run_cleanup("数据库", db_disconnect)
    await _run_cleanup("Redis", close_cache)
    await _run_cleanup("日志队列", complete_log)


__all__ = ["shutdown"]
