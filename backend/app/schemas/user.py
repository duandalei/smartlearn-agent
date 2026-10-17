"""用户与档案出入参模型（UserOut / UserProfileOut / UserProfileUpdate）。

安全红线：``UserOut`` 不含 ``hashed_password``，任何出参不得暴露哈希；
``UserProfileUpdate`` 为字段级部分更新入参（未提交字段保持原值，
不接受通过 null 清空字段）。
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class UserOut(BaseModel):
    """用户账号出参（排除 hashed_password）。"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    email: str | None
    is_active: bool
    created_at: datetime
    updated_at: datetime


class UserProfileOut(BaseModel):
    """用户学习档案出参。"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    name: str | None
    school: str | None
    major: str | None
    grade: str | None
    current_goal_type: str | None
    interest_directions: list[str]
    daily_study_minutes: int = Field(ge=15, le=600)
    created_at: datetime
    updated_at: datetime


class UserProfileUpdate(BaseModel):
    """用户学习档案更新入参（PUT /api/v1/profile，字段级部分更新）。

    语义：仅更新「已提交且非 null」的字段，未提交字段保持原值；
    null 视同未提交，不支持通过 null 清空字段（PROJECT_CONTEXT 7.2
    锁定 PUT 路径，语义为部分更新，不提供 PATCH）。
    """

    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, max_length=50)
    school: str | None = Field(default=None, max_length=120)
    major: str | None = Field(default=None, max_length=120)
    grade: str | None = Field(default=None, max_length=20)
    current_goal_type: str | None = Field(default=None, max_length=30)
    interest_directions: list[str] | None = None
    daily_study_minutes: int | None = Field(default=None, ge=15, le=600)