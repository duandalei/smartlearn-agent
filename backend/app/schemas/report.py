"""学习成长报告出参模型（ReportOut）+ P12 ReportGenerateIn 追加区。"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Any, Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, model_validator

#: 北京时区（period_end ≤ 今天校验的口径时区；本地定义不跨层导入，
#: 对齐 services/task.py 惯例——无 tzdata 环境回退固定 UTC+8，数学等价）。
try:
    _TZ_BEIJING = ZoneInfo("Asia/Shanghai")
except ZoneInfoNotFoundError:  # pragma: no cover —— Windows 无 tzdata 环境
    _TZ_BEIJING = timezone(timedelta(hours=8), "+08:00")


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

# ---------------------------------------------------------------------------
# P12 追加区：报告生成入参（design 2.3.2-A / SPEC §6.3）
# ---------------------------------------------------------------------------


class ReportGenerateIn(BaseModel):
    """POST /reports/generate 请求体。

    Attributes:
        report_type: 报告类型（daily / weekly / monthly）。
        period_end: 统计区间末日（可选，不得晚于北京时区今天）；
            period_start 不接受传入——由类型与 period_end 推导
            （防首尾矛盾，SPEC §6.3）。
    """

    model_config = ConfigDict(extra="forbid")

    report_type: Literal["daily", "weekly", "monthly"]
    period_end: date | None = None

    @model_validator(mode="after")
    def _period_end_not_future(self) -> "ReportGenerateIn":
        """校验 period_end 不得晚于今天（北京时区自然日口径）。"""
        if self.period_end is not None:
            today = datetime.now(_TZ_BEIJING).date()
            if self.period_end > today:
                raise ValueError(
                    f"period_end 不得晚于今天（{today.isoformat()}，格式 YYYY-MM-DD）"
                )
        return self