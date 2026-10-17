"""学习成长报告出参模型（ReportOut）。"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class ReportOut(BaseModel):
    """学习成长报告出参。

    ``content`` 为结构化 JSON（dict）或 None。
    """

    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    report_type: str
    period_start: date
    period_end: date
    summary: str | None
    content: dict[str, Any] | None
    created_at: datetime