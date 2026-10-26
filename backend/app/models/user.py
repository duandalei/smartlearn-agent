"""用户账号与学习档案模型（users / user_profiles）。

账号与档案 1:1 同域，同文件声明；删除用户时档案随之外键级联消失。
"""

from __future__ import annotations

from sqlalchemy import Boolean, CheckConstraint, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin
from app.models.types import JSONListType


class User(TimestampMixin, Base):
    """用户账号（users）。

    Attributes:
        id: 主键，自增。
        username: 登录名，全局唯一。
        email: 邮箱，唯一（可空，SQLite 允许多个 NULL）。
        hashed_password: 非空占位字段（本地单用户不参与登录校验）。
        is_active: 是否启用，禁用后不可登录。
    """

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(
        String(50), unique=True, nullable=False, comment="登录名，全局唯一"
    )
    email: Mapped[str | None] = mapped_column(
        String(120), unique=True, nullable=True, comment="邮箱，唯一"
    )
    hashed_password: Mapped[str] = mapped_column(
        String(255), nullable=False, comment="非空占位字段"
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, nullable=False, comment="是否启用"
    )

    profile: Mapped[UserProfile | None] = relationship(
        back_populates="user",
        uselist=False,
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    goals: Mapped[list["LearningGoal"]] = relationship(  # noqa: F821
        back_populates="user", cascade="all, delete-orphan", passive_deletes=True
    )
    plans: Mapped[list["LearningPlan"]] = relationship(  # noqa: F821
        back_populates="user", cascade="all, delete-orphan", passive_deletes=True
    )
    courses: Mapped[list["Course"]] = relationship(  # noqa: F821
        back_populates="user", cascade="all, delete-orphan", passive_deletes=True
    )
    tasks: Mapped[list["Task"]] = relationship(  # noqa: F821
        back_populates="user", cascade="all, delete-orphan", passive_deletes=True
    )
    records: Mapped[list["LearningRecord"]] = relationship(  # noqa: F821
        back_populates="user", cascade="all, delete-orphan", passive_deletes=True
    )
    mistakes: Mapped[list["Mistake"]] = relationship(  # noqa: F821
        back_populates="user", cascade="all, delete-orphan", passive_deletes=True
    )
    mastery_records: Mapped[list["KnowledgeMastery"]] = relationship(  # noqa: F821
        back_populates="user", cascade="all, delete-orphan", passive_deletes=True
    )
    conversations: Mapped[list["AgentConversation"]] = relationship(  # noqa: F821
        back_populates="user", cascade="all, delete-orphan", passive_deletes=True
    )
    reports: Mapped[list["LearningReport"]] = relationship(  # noqa: F821
        back_populates="user", cascade="all, delete-orphan", passive_deletes=True
    )
    knowledge_items: Mapped[list["KnowledgeItem"]] = relationship(  # noqa: F821
        back_populates="user", cascade="all, delete-orphan", passive_deletes=True
    )


class UserProfile(TimestampMixin, Base):
    """用户学习档案（user_profiles），一人一档。

    Attributes:
        user_id: 外键 users.id，唯一（1:1）。
        name: 姓名。
        school: 学校。
        major: 专业。
        grade: 年级，如「大二」。
        current_goal_type: 当前目标类型（考研/保研/就业/比赛，开放集合）。
        interest_directions: 兴趣方向，JSON 数组字符串（读出为 list[str]）。
        daily_study_minutes: 每日可学习时长（分钟），15–600，默认 60；
            供学习计划生成时估算每日可安排容量。
    """

    __tablename__ = "user_profiles"
    __table_args__ = (
        CheckConstraint(
            "daily_study_minutes BETWEEN 15 AND 600",
            name="ck_user_profiles_daily_study_minutes",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
        comment="外键 users.id，一人一档",
    )
    name: Mapped[str | None] = mapped_column(String(50), nullable=True)
    school: Mapped[str | None] = mapped_column(String(120), nullable=True)
    major: Mapped[str | None] = mapped_column(String(120), nullable=True)
    grade: Mapped[str | None] = mapped_column(String(20), nullable=True)
    current_goal_type: Mapped[str | None] = mapped_column(
        String(30), nullable=True, comment="当前目标：考研/保研/就业/比赛"
    )
    interest_directions: Mapped[list[str]] = mapped_column(
        JSONListType, nullable=True, comment="兴趣方向，JSON 数组"
    )
    daily_study_minutes: Mapped[int] = mapped_column(
        Integer,
        default=60,
        nullable=False,
        comment="每日可学习时长（分钟），范围 15-600，默认 60",
    )

    user: Mapped[User] = relationship(back_populates="profile")