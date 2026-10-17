"""学习目标出参模型（GoalOut）。"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class GoalOut(BaseModel):
    """学习目标出参。

    ``roadmap`` 为 ``dict | None``：None 表示「从未拆解」（JSONType
    的 None 语义，禁止被替换成 ``{}``）。
    """

    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    title: str
    goal_type: str | None
    description: str | None
    start_date: date | None
    end_date: date | None
    status: str
    roadmap: dict[str, Any] | None
    roadmap_updated_at: datetime | None
    created_at: datetime
    updated_at: datetime