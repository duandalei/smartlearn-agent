"""学习时间趋势分析（P7 analytics，纯只读）。

按北京自然日聚合补零序列（与 P6 ``get_timeline`` 同口径的独立实现，
不 import services——分层铁律 ``api → services → analytics``），输出
可直接喂给 ECharts 的 ``{date, minutes}`` 序列、最小二乘斜率与
「连续 5 天下降」风险预警对象。
"""

from __future__ import annotations

from datetime import date, timedelta, timezone, tzinfo
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.base import utc_now
from app.models.record import LearningRecord
from app.schemas.dashboard import RiskAlertOut, TrendItemOut, TrendOut

try:
    TZ_BEIJING: tzinfo = ZoneInfo("Asia/Shanghai")
except ZoneInfoNotFoundError:  # pragma: no cover —— Windows 无 tzdata 环境
    TZ_BEIJING = timezone(timedelta(hours=8), "+08:00")

RISK_WINDOW_DAYS: int = 5


def get_trend(db: Session, user_id: int, days: int) -> dict:
    """近 N 天按北京自然日聚合补零的学习时长序列 + 斜率 + 风险预警。

    Args:
        db: 数据库会话（只读）。
        user_id: 当前用户 id。
        days: 统计天数（1~365，路由层 Query 校验）。

    Returns:
        dict: TrendOut 结构（model_dump）——恰 ``days`` 条、date 升序、
        末条为北京今天；slope 为最小二乘斜率（days=1 时 0.0）；
        risk_alert 为 RiskAlertOut 或 None。
    """
    today = utc_now().astimezone(TZ_BEIJING).date()
    start_date = today - timedelta(days=days - 1)
    rows = db.execute(
        select(
            LearningRecord.study_date,
            func.sum(LearningRecord.duration_minutes),
        )
        .where(
            LearningRecord.user_id == user_id,
            LearningRecord.study_date.between(start_date, today),
        )
        .group_by(LearningRecord.study_date)
    ).all()
    found: dict[date, int] = {d: int(m or 0) for d, m in rows}
    items: list[TrendItemOut] = []
    current = start_date
    while current <= today:
        items.append(TrendItemOut(date=current, minutes=found.get(current, 0)))
        current += timedelta(days=1)

    if days <= 1:
        slope = 0.0
    else:
        minutes = [item.minutes for item in items]
        x_mean = (days - 1) / 2
        y_mean = sum(minutes) / days
        numerator = sum(
            (i - x_mean) * (y - y_mean) for i, y in enumerate(minutes)
        )
        denominator = sum((i - x_mean) ** 2 for i in range(days))
        slope = round(numerator / denominator, 1)

    return TrendOut(
        days=days,
        start_date=start_date,
        end_date=today,
        items=items,
        slope=slope,
        risk_alert=evaluate_risk_alert(db, user_id),
    ).model_dump(mode="json")


def evaluate_risk_alert(db: Session, user_id: int) -> dict | None:
    """「最近 5 个自然日学习时长严格递减」风险预警判定。

    数据源独立于 ``days`` 参数：恒取最近 5 个自然日（含今天）的
    每日时长总和，无记录按 0 计；触发条件为严格递减
    ``d1 > d2 > d3 > d4 > d5`` 且 ``d1 > 0``。「完全停学」（连续
    全 0）因 d1=0 不触发，属 MVP 取舍，不硬塞进本条规则。

    Args:
        db: 数据库会话（只读）。
        user_id: 当前用户 id。

    Returns:
        dict | None: RiskAlertOut 结构（model_dump）或 None；文案仅做
        学习行为分析，不含任何医疗或心理诊断表述。
    """
    today = utc_now().astimezone(TZ_BEIJING).date()
    start = today - timedelta(days=RISK_WINDOW_DAYS - 1)
    rows = db.execute(
        select(
            LearningRecord.study_date,
            func.sum(LearningRecord.duration_minutes),
        )
        .where(
            LearningRecord.user_id == user_id,
            LearningRecord.study_date.between(start, today),
        )
        .group_by(LearningRecord.study_date)
    ).all()
    found: dict[date, int] = {d: int(m or 0) for d, m in rows}
    durations = [
        found.get(start + timedelta(days=i), 0)
        for i in range(RISK_WINDOW_DAYS)
    ]
    if durations[0] > 0 and all(
        durations[i] > durations[i + 1] for i in range(RISK_WINDOW_DAYS - 1)
    ):
        return RiskAlertOut(
            level="warning",
            title="学习时长持续下降",
            message=(
                f"最近 5 天你的学习时长从 {durations[0]} 分钟持续下降到 "
                f"{durations[-1]} 分钟"
            ),
            suggestion="建议适当降低每日任务量，先恢复稳定的学习节奏",
        ).model_dump(mode="json")
    return None