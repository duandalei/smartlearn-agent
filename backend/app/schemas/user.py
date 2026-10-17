"""用户与档案出参模型（UserOut / UserProfileOut）。

安全红线：``UserOut`` 不含 ``hashed_password``，任何出参不得暴露哈希。
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict


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
    created_at: datetime
    updated_at: datetime