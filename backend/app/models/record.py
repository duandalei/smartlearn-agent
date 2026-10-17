"""学习记录模型（learning_records）。

``mastery_level`` 是学生本次学习后的自评（掌握度聚合的**输入**，
0-100 整数），与 ``knowledge_mastery.mastery_score``（系统聚合的
**输出**）不是同一个东西，禁止混用。
"""

from __future__ import annotations

from datetime import date

from sqlalchemy import Date, ForeignKey, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, CreatedAtMixin
from app.models.types import JSONListType


class LearningRecord(CreatedAtMixin, Base):
    """学习记录（learning_records）。

    Attributes:
        id: 主键。
        user_id: 外键 users.id。
        task_id: 外键 tasks.id（可空）。
        course_id: 外键 courses.id（可空）。
        content: 学习内容。
        duration_minutes: 学习时长（分钟）。
        achievement: 学习成果。
        problems: 遇到的问题。
        knowledge_points: 本次涉及的知识点（JSON 数组字符串）。
        mastery_level: 用户自评掌握程度 0-100。
        study_date: 学习日期（按天统计依据，UTC 日期）。
    """

    __tablename__ = "learning_records"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
        comment="外键 users.id",
    )
    task_id: Mapped[int | None] = mapped_column(
        ForeignKey("tasks.id", ondelete="SET NULL"),
        index=True,
        nullable=True,
        comment="外键 tasks.id",
    )
    course_id: Mapped[int | None] = mapped_column(
        ForeignKey("courses.id", ondelete="SET NULL"),
        index=True,
        nullable=True,
        comment="外键 courses.id",
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)
    duration_minutes: Mapped[int] = mapped_column(
        Integer, nullable=False, comment="学习时长（分钟）"
    )
    achievement: Mapped[str | None] = mapped_column(Text, nullable=True)
    problems: Mapped[str | None] = mapped_column(Text, nullable=True)
    knowledge_points: Mapped[list[str]] = mapped_column(
        JSONListType, nullable=True, comment="涉及知识点 JSON 数组"
    )
    mastery_level: Mapped[int | None] = mapped_column(
        Integer, nullable=True, comment="自评掌握程度 0-100"
    )
    study_date: Mapped[date] = mapped_column(
        Date, index=True, nullable=False, comment="学习日期（按天统计）"
    )

    user: Mapped["User"] = relationship(back_populates="records")  # noqa: F821
    task: Mapped["Task | None"] = relationship(  # noqa: F821
        back_populates="records", passive_deletes=True
    )
    course: Mapped["Course | None"] = relationship(  # noqa: F821
        back_populates="records", passive_deletes=True
    )