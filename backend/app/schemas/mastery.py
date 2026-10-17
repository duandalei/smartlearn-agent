"""知识掌握度出参模型（MasteryOut）。"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class MasteryOut(BaseModel):
    """知识掌握度出参。"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    knowledge_point: str
    mastery_score: float
    source: str
    updated_at: datetime