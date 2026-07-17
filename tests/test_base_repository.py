from typing import cast

import pytest
from sqlalchemy import bindparam, column, delete, insert, select, table, text, union_all, update
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Query

from app.repositories.base_repo import SQL, BaseRepository


class UserRepository(BaseRepository):
    """验证无状态仓储共享实例行为。"""


class AuditRepository(BaseRepository):
    """验证不同仓储类型不会共享同一个实例。"""


users = table(
    "users",
    column("id"),
    column("email"),
)


def test_repository_reuses_instance_only_within_same_subclass() -> None:
    """同一无状态仓储类型复用实例，不同仓储类型彼此隔离。"""
    assert UserRepository() is UserRepository()
    assert UserRepository() is not AuditRepository()


@pytest.mark.parametrize(
    "statement",
    [
        select(users).where(users.c.id == 1),
        update(users).where(users.c.id == 1).values(email="updated@example.com"),
        insert(users).values(id=1, email="created@example.com"),
        delete(users).where(users.c.id == 1),
        union_all(select(users.c.id), select(users.c.id)),
        text("SELECT :value").bindparams(value=1),
    ],
)
def test_sql_compile_accepts_async_repository_statement_types(statement: SQL) -> None:
    """调试工具支持异步仓储常用的 SQLAlchemy 2.x 语句。"""
    compiled = BaseRepository.sql_compile(statement)

    assert str(compiled)


def test_sql_compile_keeps_sensitive_values_out_of_default_sql_text() -> None:
    """默认 SQL 文本保留占位符，参数值只能从 params 显式读取。"""
    sensitive_email = "private@example.com"
    statement = select(users).where(users.c.email == bindparam("email", sensitive_email))

    compiled = BaseRepository.sql_compile(statement, dialect=postgresql.dialect())

    assert sensitive_email not in str(compiled)
    assert compiled.params == {"email": sensitive_email}
    assert "%(email)s" in str(compiled)


def test_sql_compile_does_not_render_literal_execute_values_by_default() -> None:
    """安全默认分支也不得展开 SQLAlchemy 的后编译字面量参数。"""
    sensitive_token = "private-token"
    statement = select(bindparam("token", sensitive_token, literal_execute=True))

    compiled = BaseRepository.sql_compile(statement, dialect=postgresql.dialect())

    assert sensitive_token not in str(compiled)
    assert "__[POSTCOMPILE_token]" in str(compiled)
    assert compiled.params == {"token": sensitive_token}


def test_sql_compile_can_explicitly_render_trusted_literal_values() -> None:
    """仅显式开启不安全选项时才把可信参数展开到 SQL 文本。"""
    trusted_email = "debug@example.com"
    statement = select(users).where(users.c.email == bindparam("email", trusted_email))

    compiled = BaseRepository.sql_compile(
        statement,
        dialect=postgresql.dialect(),
        unsafe_literal_binds=True,
    )

    assert trusted_email in str(compiled)
    assert compiled.params == {}


def test_sql_compile_rejects_legacy_sync_query_objects() -> None:
    """仓储仅接受 SQLAlchemy 2.x 语句，不再兼容同步 Query 接口。"""
    legacy_query = Query([column("legacy_id")])

    with pytest.raises(TypeError, match=r"SQLAlchemy 2\.x 可执行语句"):
        BaseRepository.sql_compile(cast(SQL, legacy_query))
