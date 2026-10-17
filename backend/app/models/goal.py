"""学习目标模型（learning_goals）。

目标可先建后补时间（start_date / end_date 保持可空，与
learning_plans 的非空约定区分）；``roadmap`` 为 AI 拆解出的知识树
（JSON），``None`` 表示「从未拆解」。
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from sqlalchemy import Date, DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, sa_enum
from app.models.enums import GoalStatus
from app.models.types import JSONType


class LearningGoal(TimestampMixin, Base):
    """学习目标（learning_goals）。

    Attributes:
        id: 主键。
        user_id: 外键 users.id。
        title: 目标名称，如「6个月掌握机器学习」。
        goal_type: 目标类型（开放集合，如 期末备考/刷题训练/考试/竞赛）。
        description: 目标描述。
        start_date / end_date: 起止日期（可空：支持先建目标后补时间）。
        status: active / completed / archived。
        roadmap: AI 拆解出的知识树 JSON；``None`` 表示从未拆解。
        roadmap_updated_at: 最近一次拆解时间。
    """

    __tablename__ = "learning_goals"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
        comment="外键 users.id",
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    goal_type: Mapped[str | None] = mapped_column(
        String(50), nullable=True, comment="目标类型（开放集合）"
    )
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    start_date: Mapped[date | None] = mapped_column(
        Date, nullable=True, comment="开始时间（可空）"
    )
    end_date: Mapped[date | None] = mapped_column(
        Date, nullable=True, comment="截止时间（可空）"
    )
    status: Mapped[GoalStatus] = mapped_column(
        sa_enum(GoalStatus),
        default=GoalStatus.ACTIVE,
        nullable=False,
        index=True,
        comment="active/completed/archived",
    )
    roadmap: Mapped[dict[str, Any] | None] = mapped_column(
        JSONType, nullable=True, comment="AI 拆解知识树 JSON；None=从未拆解"
    )
    roadmap_updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, comment="最近一次拆解时间（UTC）"
    )

    user: Mapped["User"] = relationship(back_populates="goals")  # noqa: F821
    tasks: Mapped[list["Task"]] = relationship(  # noqa: F821
        back_populates="goal", passive_deletes=True
    )
    plans: Mapped[list["LearningPlan"]] = relationship(  # noqa: F821
        back_populates="goal", passive_deletes=True
    )