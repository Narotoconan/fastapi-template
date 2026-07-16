from sqlalchemy.engine import URL
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from app.core.log import log

DATABASE_TIMEZONE = "Asia/Shanghai"


class Base(DeclarativeBase):
    """SQLAlchemy 2.0+ 声明式基类"""

    pass


def build_database_url(host: str, port: int, user: str, password: str, database: str) -> URL:
    """构造结构化数据库 URL，确保特殊字符密码不会破坏连接信息。"""
    return URL.create(
        drivername="postgresql+asyncpg",
        username=user,
        password=password,
        host=host,
        port=port,
        database=database,
    )


class AsyncPgSql:
    def __init__(
        self,
        host: str,
        port: int,
        user: str,
        password: str,
        database: str,
        pool_size: int,
        max_overflow: int,
        pool_recycle: int,
        pool_timeout: float,
        command_timeout: float,
        connect_timeout: float,
    ) -> None:
        self.__DATABASE_URL = build_database_url(host, port, user, password, database)
        self.__POOL_SIZE = pool_size
        self.__MAX_OVERFLOW = max_overflow
        self.__POOL_RECYCLE = pool_recycle
        self.__POOL_TIMEOUT = pool_timeout
        self.__COMMAND_TIMEOUT = command_timeout
        self.__CONNECT_TIMEOUT = connect_timeout

        self.__engine: AsyncEngine = self.__create_engine()
        self.AsyncSessionLocal: async_sessionmaker[AsyncSession] = self.__create_session()
        self.Base = Base

    def __create_engine(self) -> AsyncEngine:
        try:
            return create_async_engine(
                self.__DATABASE_URL,
                pool_size=self.__POOL_SIZE,
                max_overflow=self.__MAX_OVERFLOW,
                pool_pre_ping=True,  # 在每次从连接池中获取连接时先发送一个简单的查询
                pool_recycle=self.__POOL_RECYCLE,
                pool_timeout=self.__POOL_TIMEOUT,
                echo_pool=False,  # 生产环境关闭连接池调试日志
                connect_args={
                    "command_timeout": self.__COMMAND_TIMEOUT,
                    "timeout": self.__CONNECT_TIMEOUT,
                    "server_settings": {"timezone": DATABASE_TIMEZONE},
                },
            )
        except SQLAlchemyError as e:
            log.error("数据库引擎创建失败！")
            raise e

    def __create_session(self) -> async_sessionmaker[AsyncSession]:
        return async_sessionmaker(
            bind=self.__engine, class_=AsyncSession, expire_on_commit=False, autoflush=True, autocommit=False
        )

    async def disconnect(self) -> None:
        await self.__engine.dispose()


__all__ = ["DATABASE_TIMEZONE", "AsyncPgSql", "Base", "build_database_url"]
