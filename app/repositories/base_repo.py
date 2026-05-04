from typing import ClassVar, Union

from sqlalchemy.orm import Query
from sqlalchemy.sql import Delete, Insert, Select, Update
from sqlalchemy.sql.compiler import SQLCompiler

SQL = Union[Select, Update, Insert, Delete]


class BaseRepository:
    _instances: ClassVar[dict] = {}

    def __new__(cls, *args, **kwargs):
        if cls not in cls._instances:
            instance = super().__new__(cls)
            cls._instances[cls] = instance
        return cls._instances[cls]

    @staticmethod
    def sql_compile(sql: Union[Query, SQL]) -> SQLCompiler:
        _ = None

        if isinstance(sql, Query):
            _ = sql.statement
        elif isinstance(sql, SQL):
            _ = sql
        else:
            raise TypeError("sql must be Query or SQL")

        return _.compile(compile_kwargs={"literal_binds": True})
