"""错题出参模型（MistakeOut）。"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class MistakeOut(BaseModel):
    """错题出参。"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    course_id: int | None
    knowledge_point: str | None
    question: str
    user_answer: str | None
    correct_answer: str | None
    analysis: str | None
    created_at: datetime