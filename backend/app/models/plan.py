"""学习计划模型（learning_plans / learning_plan_items）。

计划版本与条目强从属（CASCADE），同文件声明以规避跨文件前向引用。
``learning_plans.start_date / end_date`` 非空且强制
``end_date >= start_date``（DB 层 CHECK + 应用层双重校验的 DB 半边），
与 ``learning_goals`` 的可空约定严格区分。
"""

from __future__ import annotations

from datetime import date, time

from sqlalchemy import (
    CheckConstraint,
    Date,
    ForeignKey,
    Integer,
    String,
    Text,
    Time,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, CreatedAtMixin, sa_enum
from app.models.enums import PlanItemStatus, PlanSource, PlanStatus, Priority


class LearningPlan(CreatedAtMixin, Base):
    """学习计划版本（learning_plans）。

    每次生成 / 调整计划都新建 version，旧版本置 archived，禁止原地
    修改；``parent_plan_id`` 指向被调整的上一版，用于 diff 与回滚。

    Attributes:
        id: 主键。
        user_id: 外键 users.id。
        goal_id: 外键 learning_goals.id（可空）。
        title: 计划标题。
        version: 版本号，每次重新规划自增。
        status: active / archived。
        parent_plan_id: 自引用外键，指向被调整的上一版计划。
        source: agent / manual。
        adjust_reason: Agent 调整计划时写给用户的理由。
        start_date / end_date: 计划起止日期（非空，end >= start）。
    """

    __tablename__ = "learning_plans"
    __table_args__ = (
        CheckConstraint("end_date >= start_date", name="ck_plan_date_range"),
    )

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
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    version: Mapped[int] = mapped_column(
        Integer, default=1, nullable=False, comment="版本号"
    )
    status: Mapped[PlanStatus] = mapped_column(
        sa_enum(PlanStatus),
        default=PlanStatus.ACTIVE,
        nullable=False,
        comment="active/archived",
    )
    parent_plan_id: Mapped[int | None] = mapped_column(
        ForeignKey("learning_plans.id", ondelete="SET NULL"),
        nullable=True,
        comment="指向被调整的上一版计划",
    )
    source: Mapped[PlanSource] = mapped_column(
        sa_enum(PlanSource),
        default=PlanSource.AGENT,
        nullable=False,
        comment="agent/manual",
    )
    adjust_reason: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="Agent 调整计划的原因说明"
    )
    start_date: Mapped[date] = mapped_column(
        Date, nullable=False, comment="计划起始日期（非空）"
    )
    end_date: Mapped[date] = mapped_column(
        Date, nullable=False, comment="计划结束日期（非空，>= start_date）"
    )

    user: Mapped["User"] = relationship(back_populates="plans")  # noqa: F821
    goal: Mapped["LearningGoal | None"] = relationship(  # noqa: F821
        back_populates="plans", passive_deletes=True
    )
    parent_plan: Mapped["LearningPlan | None"] = relationship(
        remote_side=[id],
        back_populates="child_plans",
        passive_deletes=True,
    )
    child_plans: Mapped[list[LearningPlan]] = relationship(
        back_populates="parent_plan", passive_deletes=True
    )
    items: Mapped[list[LearningPlanItem]] = relationship(
        back_populates="plan", cascade="all, delete-orphan", passive_deletes=True
    )


class LearningPlanItem(CreatedAtMixin, Base):
    """学习计划条目（learning_plan_items）。

    周视图课表 = 查 active 计划的 items 按 ``plan_date × 时间段``
    排网格；调整 diff = 对比 parent_plan_id 与当前计划的 items。

    Attributes:
        id: 主键。
        plan_id: 外键 learning_plans.id（CASCADE）。
        plan_date: 安排在周几。
        start_time / end_time: 起止时间（如 19:00 / 20:30）。
        topic: 本次学什么。
        task_id: 外键 tasks.id（休息/复习类条目可空）。
        estimated_minutes: 预计时长。
        priority: low / medium / high。
        status: planned / done / skipped。
    """

    __tablename__ = "learning_plan_items"
    __table_args__ = (
        UniqueConstraint(
            "plan_id", "plan_date", "start_time", name="uq_plan_item_slot"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    plan_id: Mapped[int] = mapped_column(
        ForeignKey("learning_plans.id", ondelete="CASCADE"),
        nullable=False,
        comment="外键 learning_plans.id",
    )
    plan_date: Mapped[date] = mapped_column(
        Date, nullable=False, comment="安排日期"
    )
    start_time: Mapped[time | None] = mapped_column(
        Time, nullable=True, comment="开始时间，如 19:00"
    )
    end_time: Mapped[time | None] = mapped_column(
        Time, nullable=True, comment="结束时间，如 20:30"
    )
    topic: Mapped[str] = mapped_column(String(200), nullable=False)
    task_id: Mapped[int | None] = mapped_column(
        ForeignKey("tasks.id", ondelete="SET NULL"),
        nullable=True,
        comment="关联任务 id；休息/复习类条目可空",
    )
    estimated_minutes: Mapped[int | None] = mapped_column(
        Integer, nullable=True, comment="预计时长（分钟）"
    )
    priority: Mapped[Priority | None] = mapped_column(
        sa_enum(Priority), nullable=True, comment="low/medium/high"
    )
    status: Mapped[PlanItemStatus] = mapped_column(
        sa_enum(PlanItemStatus),
        default=PlanItemStatus.PLANNED,
        nullable=False,
        comment="planned/done/skipped",
    )

    plan: Mapped[LearningPlan] = relationship(back_populates="items")
    task: Mapped["Task | None"] = relationship(  # noqa: F821
        back_populates="plan_items", passive_deletes=True
    )