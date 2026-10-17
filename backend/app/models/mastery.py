"""知识掌握度模型（knowledge_mastery）。

命名锁定（PROJECT_CONTEXT 第 7 行裁决）：
- 字段为 ``mastery_score``（不用 ``mastery``）；
- 知识点为单数 ``knowledge_point``（与 tasks / learning_records 的
  复数 ``knowledge_points`` JSON 数组严格区分）；
- ``source`` 为英文枚举 self_report / record / quiz / goal_breakdown /
  agent（quiz 为 V2 接入，P2 不写入）。

``mastery_score`` 是系统聚合的**输出**；聚合公式
``clamp(旧分 × 0.7 + 本次自评 × 0.3, 0, 100)`` 属 P7 analytics，
模型层不实现。
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, sa_enum, utc_now
from app.models.enums import MasterySource


class KnowledgeMastery(Base):
    """知识掌握度（knowledge_mastery），(user_id, knowledge_point) 唯一。

    Attributes:
        id: 主键。
        user_id: 外键 users.id。
        knowledge_point: 知识点名称（单数）。
        mastery_score: 掌握度 0-100。
        source: self_report / record / quiz / goal_breakdown / agent。
        updated_at: 最近更新时间（本表无 created_at）。
    """

    __tablename__ = "knowledge_mastery"
    __table_args__ = (
        UniqueConstraint("user_id", "knowledge_point", name="uq_mastery_user_point"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        comment="外键 users.id",
    )
    knowledge_point: Mapped[str] = mapped_column(
        String(200), nullable=False, comment="知识点名称（单数）"
    )
    mastery_score: Mapped[float] = mapped_column(
        Float, nullable=False, comment="掌握度 0-100"
    )
    source: Mapped[MasterySource] = mapped_column(
        sa_enum(MasterySource),
        nullable=False,
        comment="self_report/record/quiz/goal_breakdown/agent",
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        onupdate=utc_now,
        nullable=False,
        comment="最近更新时间（UTC）",
    )

    user: Mapped["User"] = relationship(  # noqa: F821
        back_populates="mastery_records"
    )