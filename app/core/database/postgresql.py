from asyncio import current_task

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_scoped_session,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from app.core.log import log
from config.settings import get_settings

settings = get_settings()


class Base(DeclarativeBase):
    """SQLAlchemy 2.0+ 声明式基类"""

    pass


class AsyncPgSql:
    def __init__(self, host: str, port: int, user: str, password: str, database: str):
        self.__DATABASE_URL = f"postgresql+asyncpg://{user}:{password}@{host}:{port}/{database}"

        self.__engine: AsyncEngine | None = None
        self.AsyncSessionLocal: async_scoped_session[AsyncSession] | None = None
        self.Base = Base

        self.__create_engine()
        self.AsyncSessionLocal = self.__create_session()

    def __create_engine(self) -> None:
        try:
            self.__engine = create_async_engine(
                self.__DATABASE_URL,
                pool_size=5,  # 连接池大小
                max_overflow=10,  # 超过连接池大小外最多创建的连接
                pool_pre_ping=True,  # 在每次从连接池中获取连接时先发送一个简单的查询
                pool_recycle=300,  # 设置连接的最大空闲时间为 300 秒
                pool_timeout=30,  # 设置从连接池获取连接的超时时间为 30 秒
                echo_pool=False,  # 生产环境关闭连接池调试日志
                connect_args={
                    "command_timeout": 60,  # 连接超时时间
                    "timeout": 30,  # 操作超时时间（秒）
                },
            )
        except SQLAlchemyError as e:
            log.error("数据库引擎创建失败！")
            raise e

    def __create_session(self) -> async_scoped_session[AsyncSession]:
        _async_session = async_sessionmaker(
            bind=self.__engine, class_=AsyncSession, expire_on_commit=False, autoflush=True, autocommit=False
        )
        return async_scoped_session(session_factory=_async_session, scopefunc=current_task)

    @staticmethod
    def db_first_connection():
        log.info(
            f"✅ 数据库 连接成功 - "
            f"主机:{settings.cache.REDIS_HOST} | "
            f"端口:{settings.cache.REDIS_PORT} | "
            f"数据库:{settings.cache.REDIS_DB}"
        )

    async def disconnect(self) -> None:
        if self.__engine:
            await self.__engine.dispose()


__all__ = ["AsyncPgSql"]
