from datetime import datetime

from sqlalchemy import DateTime, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class BaseModel(Base):
    __abstract__ = True
    # Mapped[datetime] — 这是一个 Python 类型注解，告诉类型检查器（mypy、Pyright）和 IDE："这个字段在 Python 侧是 datetime 类型"。这样你在代码里访问 obj.created_at 时，IDE 会知道它是 datetime，能正确补全 .year、.strftime() 等方法。
    # mapped_column(...) — 这是 数据库侧的列配置，替代旧的 Column()，功能完全相同，但能与 Mapped 类型注解协同工作。
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=func.now(), comment="创建时间")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=func.now(), onupdate=func.now(), comment="更新时间"
    )
