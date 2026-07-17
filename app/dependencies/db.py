from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import AsyncSessionLocal, close_db_session
from app.core.log import log


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """为每个请求创建独立会话，并在异常或取消时安全回滚。"""
    session = AsyncSessionLocal()
    try:
        yield session
    except BaseException as request_error:
        try:
            await session.rollback()
        except BaseException as rollback_error:
            log.error(
                "数据库会话回滚失败"
                f" | request_error_type={type(request_error).__name__}"
                f" | rollback_error_type={type(rollback_error).__name__}"
            )

        try:
            await close_db_session(session)
        except BaseException as close_error:
            log.error(
                "数据库会话关闭失败"
                f" | request_error_type={type(request_error).__name__}"
                f" | close_error_type={type(close_error).__name__}"
            )
        raise
    else:
        await close_db_session(session)
