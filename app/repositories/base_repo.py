from typing import ClassVar, Self, cast

from sqlalchemy.engine import Compiled, Dialect
from sqlalchemy.sql import Executable
from sqlalchemy.sql.elements import ClauseElement

SQL = ClauseElement


class BaseRepository:
    """无状态 Repository 的共享实例基类。"""

    _instances: ClassVar[dict[type["BaseRepository"], "BaseRepository"]] = {}

    def __new__(cls, *args: object, **kwargs: object) -> Self:
        if cls not in cls._instances:
            instance = super().__new__(cls)
            cls._instances[cls] = instance
        return cast(Self, cls._instances[cls])

    @staticmethod
    def sql_compile(
        sql: SQL,
        *,
        dialect: Dialect | None = None,
        unsafe_literal_binds: bool = False,
    ) -> Compiled:
        """编译异步 SQLAlchemy 语句，默认保留参数占位符以避免泄露敏感值。

        调试时可通过返回对象的 ``params`` 属性单独检查绑定参数。只有在确认
        参数不含敏感信息时，才应显式启用 ``unsafe_literal_binds``。
        """
        if not isinstance(sql, ClauseElement) or not isinstance(sql, Executable):
            raise TypeError("sql 必须是 SQLAlchemy 2.x 可执行语句")

        if unsafe_literal_binds:
            return sql.compile(dialect=dialect, compile_kwargs={"literal_binds": True})
        return sql.compile(dialect=dialect)
