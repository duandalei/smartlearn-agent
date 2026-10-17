"""学习记录出参模型（RecordOut）。"""

from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict


class RecordOut(BaseModel):
    """学习记录出参。

    ``mastery_level`` 为学生自评（聚合输入），与
    ``knowledge_mastery.mastery_score``（聚合输出）语义不同。
    """

    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    task_id: int | None
    course_id: int | None
    content: str
    duration_minutes: int
    achievement: str | None
    problems: str | None
    knowledge_points: list[str]
    mastery_level: int | None
    study_date: date
    created_at: datetime