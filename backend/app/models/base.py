"""ORM 模型统一基类与时间戳混入。

提供：
1. ``Base``：全部 15 个模型的唯一声明式基类（同一 ``Base.metadata``，
   ``create_all`` 一次建齐全部表）。
2. ``utc_now()``：全项目唯一时间源（UTC aware），所有时间字段的
   ``default`` / ``onupdate`` 与种子时间戳必须经由此函数，
   禁止裸 ``datetime.now()``。
3. ``CreatedAtMixin``：仅 ``created_at``（供 8 张单时间戳表）。
4. ``TimestampMixin``：``created_at`` + ``updated_at``
   （供 6 张双时间戳表）。
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import DateTime
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def utc_now() -> datetime:
    """返回当前 UTC 时间（aware）。

    全项目统一时间源：所有时间字段默认值与种子数据一律调用本函数，
    保证时间字段统一按 UTC 存储（PROJECT_CONTEXT 第 6 章通用约定）。

    Returns:
        datetime: 携带 UTC 时区信息的当前时间。
    """
    return datetime.now(timezone.utc)


def sa_enum(enum_cls: type, length: int = 20) -> SAEnum:
    """构造统一落库策略的枚举列类型。

    SQLite 无原生 ENUM：``native_enum=False`` 生成 VARCHAR，
    ``create_constraint=True`` 附加 CHECK 约束（DB 层拒绝超界值），
    ``values_callable`` 保证落库的是枚举 value（如 ``todo``）而非
    枚举 name（如 ``TODO``）。

    Args:
        enum_cls: 枚举类（定义于 app.models.enums）。
        length: VARCHAR 长度，默认 20。

    Returns:
        SAEnum: 枚举列类型实例（每次调用新建，可安全用于多个列）。
    """
    return SAEnum(
        enum_cls,
        native_enum=False,
        create_constraint=True,
        length=length,
        values_callable=lambda e: [m.value for m in e],
    )


class Base(DeclarativeBase):
    """全部 ORM 模型的统一声明式基类。"""
    pass


class CreatedAtMixin:
    """创建时间混入：仅含 ``created_at`` 的表使用。"""

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        nullable=False,
        comment="创建时间（UTC）",
    )


class TimestampMixin(CreatedAtMixin):
    """双时间戳混入：含 ``created_at`` 与 ``updated_at`` 的表使用。"""

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        onupdate=utc_now,
        nullable=False,
        comment="更新时间（UTC）",
    )