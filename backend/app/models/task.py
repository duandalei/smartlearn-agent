"""学习任务模型（tasks）。

状态枚举锁定 PROJECT_CONTEXT 裁决：``todo / in_progress / done / review``；
知识点字段为复数 ``knowledge_points``（JSON 数组，一任务挂多个知识点）。
"""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, sa_enum
from app.models.enums import Priority, TaskSource, TaskStatus
from app.models.types import JSONListType


class Task(TimestampMixin, Base):
    """学习任务（tasks）。

    Attributes:
        id: 主键。
        user_id: 外键 users.id。
        goal_id: 外键 learning_goals.id（可空）。
        course_id: 外键 courses.id（可空）。
        title: 任务名称。
        description: 任务描述。
        knowledge_points: 所属知识点（JSON 数组字符串，读出 list[str]）。
        priority: low / medium / high，默认 medium。
        estimated_minutes: 预计耗时（分钟）。
        actual_minutes: 实际花费分钟数（由学习记录回填）。
        deadline: 截止时间（UTC）。
        scheduled_date: 计划执行日期（Agent 生成计划时写入）。
        status: todo / in_progress / done / review，默认 todo。
        source: manual / agent。
        completed_at: 完成时间，状态置 done 时写入。
    """

    __tablename__ = "tasks"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
        comment="外键 users.id",
    )
    goal_id: Mapped[int | None] = mapped_column(
        ForeignKey("learning_goals.id", ondelete="SET NULL"),
        index=True,
        nullable=True,
        comment="外键 learning_goals.id",
    )
    course_id: Mapped[int | None] = mapped_column(
        ForeignKey("courses.id", ondelete="SET NULL"),
        index=True,
        nullable=True,
        comment="外键 courses.id",
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    knowledge_points: Mapped[list[str]] = mapped_column(
        JSONListType, nullable=True, comment="知识点 JSON 数组"
    )
    priority: Mapped[Priority] = mapped_column(
        sa_enum(Priority),
        default=Priority.MEDIUM,
        nullable=False,
        comment="low/medium/high",
    )
    estimated_minutes: Mapped[int | None] = mapped_column(
        Integer, nullable=True, comment="预计耗时（分钟）"
    )
    actual_minutes: Mapped[int | None] = mapped_column(
        Integer, nullable=True, comment="实际花费分钟数"
    )
    deadline: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        index=True,
        nullable=True,
        comment="截止时间（UTC）",
    )
    scheduled_date: Mapped[date | None] = mapped_column(
        Date, nullable=True, comment="计划执行日期"
    )
    status: Mapped[TaskStatus] = mapped_column(
        sa_enum(TaskStatus),
        default=TaskStatus.TODO,
        index=True,
        nullable=False,
        comment="todo/in_progress/done/review",
    )
    source: Mapped[TaskSource] = mapped_column(
        sa_enum(TaskSource),
        default=TaskSource.MANUAL,
        nullable=False,
        comment="manual/agent",
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, comment="完成时间（UTC）"
    )

    user: Mapped["User"] = relationship(back_populates="tasks")  # noqa: F821
    goal: Mapped["LearningGoal | None"] = relationship(  # noqa: F821
        back_populates="tasks", passive_deletes=True
    )
    course: Mapped["Course | None"] = relationship(  # noqa: F821
        back_populates="tasks", passive_deletes=True
    )
    records: Mapped[list["LearningRecord"]] = relationship(  # noqa: F821
        back_populates="task", passive_deletes=True
    )
    plan_items: Mapped[list["LearningPlanItem"]] = relationship(  # noqa: F821
        back_populates="task", passive_deletes=True
    )