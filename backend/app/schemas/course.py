"""课程出参模型（CourseOut）。"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class CourseOut(BaseModel):
    """课程出参。"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    name: str
    description: str | None
    teacher: str | None
    semester: str | None
    created_at: datetime