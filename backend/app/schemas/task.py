"""学习任务出参模型（TaskOut）。"""

from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict


class TaskOut(BaseModel):
    """学习任务出参。

    ``knowledge_points`` 永为字符串数组（JSONListType 读出语义，
    不会出现 null）。
    """

    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    goal_id: int | None
    course_id: int | None
    title: str
    description: str | None
    knowledge_points: list[str]
    priority: str
    estimated_minutes: int | None
    actual_minutes: int | None
    deadline: datetime | None
    scheduled_date: date | None
    status: str
    source: str
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None