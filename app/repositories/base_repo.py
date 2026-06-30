from typing import ClassVar, Self, cast

from sqlalchemy.orm import Query
from sqlalchemy.sql import Delete, Insert, Select, Update
from sqlalchemy.sql.compiler import SQLCompiler

SQL = Select | Update | Insert | Delete


class BaseRepository:
    _instances: ClassVar[dict[type["BaseRepository"], "BaseRepository"]] = {}

    def __new__(cls, *args: object, **kwargs: object) -> Self:
        if cls not in cls._instances:
            instance = super().__new__(cls)
            cls._instances[cls] = instance
        return cast(Self, cls._instances[cls])

    @staticmethod
    def sql_compile[QueryT](sql: Query[QueryT] | SQL) -> SQLCompiler:
        if isinstance(sql, Query):
            statement = sql.statement
        elif isinstance(sql, SQL):
            statement = sql
        else:
            raise TypeError("sql must be Query or SQL")

        return statement.compile(compile_kwargs={"literal_binds": True})
