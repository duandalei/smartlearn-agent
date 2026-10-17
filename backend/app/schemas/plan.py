"""学习计划出参模型（PlanOut / PlanItemOut）。"""

from __future__ import annotations

from datetime import date, datetime, time

from pydantic import BaseModel, ConfigDict


class PlanOut(BaseModel):
    """学习计划版本出参。"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    goal_id: int | None
    title: str
    version: int
    status: str
    parent_plan_id: int | None
    source: str
    adjust_reason: str | None
    start_date: date
    end_date: date
    created_at: datetime


class PlanItemOut(BaseModel):
    """学习计划条目出参。"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    plan_id: int
    plan_date: date
    start_time: time | None
    end_time: time | None
    topic: str
    task_id: int | None
    estimated_minutes: int | None
    priority: str | None
    status: str
    created_at: datetime