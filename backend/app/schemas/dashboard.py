"""Dashboard 出参模型（P7，纯出参，无入参）。"""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel


class OverviewOut(BaseModel):
    total_minutes: int
    task_completion_rate: float
    avg_mastery: float
    streak_days: int
    total_record_count: int
    avg_session_minutes: float
    overdue_task_count: int


class TrendItemOut(BaseModel):
    date: date
    minutes: int


class RiskAlertOut(BaseModel):
    level: str
    title: str
    message: str
    suggestion: str


class TrendOut(BaseModel):
    days: int
    start_date: date
    end_date: date
    items: list[TrendItemOut]
    slope: float
    risk_alert: RiskAlertOut | None = None


class MasteryItemOut(BaseModel):
    knowledge_point: str
    mastery_score: float


class MasteryOut(BaseModel):
    items: list[MasteryItemOut]


class WeaknessItemOut(BaseModel):
    knowledge_point: str
    mastery_score: float
    recent_count: int
    advice: str


class WeaknessOut(BaseModel):
    items: list[WeaknessItemOut]


class AdviceItemOut(BaseModel):
    type: str
    title: str
    content: str


class AdviceOut(BaseModel):
    items: list[AdviceItemOut]