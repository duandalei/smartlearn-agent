"""学习成长报告模型（learning_reports）。"""

from __future__ import annotations

from datetime import date
from typing import Any

from sqlalchemy import Date, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, CreatedAtMixin, sa_enum
from app.models.enums import ReportType
from app.models.types import JSONType


class LearningReport(CreatedAtMixin, Base):
    """学习成长报告（learning_reports）。

    Attributes:
        id: 主键。
        user_id: 外键 users.id。
        report_type: daily / weekly / monthly。
        period_start / period_end: 统计区间。
        summary: 报告摘要（面向用户的结论）。
        content: 结构化报告内容（JSON 字符串）。
    """

    __tablename__ = "learning_reports"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
        comment="外键 users.id",
    )
    report_type: Mapped[ReportType] = mapped_column(
        sa_enum(ReportType, length=10),
        nullable=False,
        comment="daily/weekly/monthly",
    )
    period_start: Mapped[date] = mapped_column(Date, nullable=False)
    period_end: Mapped[date] = mapped_column(Date, nullable=False)
    summary: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="报告摘要"
    )
    content: Mapped[dict[str, Any] | None] = mapped_column(
        JSONType, nullable=True, comment="结构化报告内容 JSON"
    )

    user: Mapped["User"] = relationship(back_populates="reports")  # noqa: F821