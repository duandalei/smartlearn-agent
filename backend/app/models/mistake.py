"""错题模型（mistakes）。

一题一知识点（``knowledge_point`` 单数）；跨知识点的题应拆成多条
错题记录，不引入多对多关系。MVP 无录入界面，数据由种子提供。
"""

from __future__ import annotations

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, CreatedAtMixin


class Mistake(CreatedAtMixin, Base):
    """错题（mistakes）。

    Attributes:
        id: 主键。
        user_id: 外键 users.id。
        course_id: 外键 courses.id（可空）。
        knowledge_point: 关联知识点（单数）。
        question: 题目内容。
        user_answer: 用户作答。
        correct_answer: 正确答案。
        analysis: 错因分析。
    """

    __tablename__ = "mistakes"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
        comment="外键 users.id",
    )
    course_id: Mapped[int | None] = mapped_column(
        ForeignKey("courses.id", ondelete="SET NULL"),
        index=True,
        nullable=True,
        comment="外键 courses.id",
    )
    knowledge_point: Mapped[str | None] = mapped_column(
        String(200),
        index=True,
        nullable=True,
        comment="关联知识点（单数，一题一知识点）",
    )
    question: Mapped[str] = mapped_column(Text, nullable=False)
    user_answer: Mapped[str | None] = mapped_column(Text, nullable=True)
    correct_answer: Mapped[str | None] = mapped_column(Text, nullable=True)
    analysis: Mapped[str | None] = mapped_column(Text, nullable=True)

    user: Mapped["User"] = relationship(back_populates="mistakes")  # noqa: F821
    course: Mapped["Course | None"] = relationship(  # noqa: F821
        back_populates="mistakes", passive_deletes=True
    )