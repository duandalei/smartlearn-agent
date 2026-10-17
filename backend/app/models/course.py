"""课程模型（courses）。"""

from __future__ import annotations

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, CreatedAtMixin


class Course(CreatedAtMixin, Base):
    """课程（courses）。

    Attributes:
        id: 主键。
        user_id: 外键 users.id。
        name: 课程名称，如「机器学习」。
        description: 课程描述。
        teacher: 授课教师。
        semester: 学期，如「2025-2026-1」。
    """

    __tablename__ = "courses"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
        comment="外键 users.id",
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    teacher: Mapped[str | None] = mapped_column(String(50), nullable=True)
    semester: Mapped[str | None] = mapped_column(String(30), nullable=True)

    user: Mapped["User"] = relationship(back_populates="courses")  # noqa: F821
    tasks: Mapped[list["Task"]] = relationship(  # noqa: F821
        back_populates="course", passive_deletes=True
    )
    records: Mapped[list["LearningRecord"]] = relationship(  # noqa: F821
        back_populates="course", passive_deletes=True
    )
    mistakes: Mapped[list["Mistake"]] = relationship(  # noqa: F821
        back_populates="course", passive_deletes=True
    )