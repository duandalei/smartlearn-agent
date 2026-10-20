"""学习统计模块（P7 analytics，纯只读）。

overview 七指标：累计学习时长、任务完成率、平均掌握度、连续学习
天数、记录条数、平均单次时长、逾期任务数。完成率口径与 P5
``weekly_completion_rate`` 一致（分子 = done + review，review 为
「已完成、正在复盘」）；streak 与 P6 ``get_stats`` 同口径独立实现
（不 import services——分层铁律）。
"""

from __future__ import annotations

from datetime import date, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.base import utc_now
from app.models.enums import MasterySource, TaskStatus
from app.models.mastery import KnowledgeMastery
from app.models.record import LearningRecord
from app.models.task import Task
from app.schemas.dashboard import OverviewOut

try:
    TZ_BEIJING: timezone = ZoneInfo("Asia/Shanghai")
except ZoneInfoNotFoundError:  # pragma: no cover —— Windows 无 tzdata 环境
    TZ_BEIJING = timezone(timedelta(hours=8), "+08:00")


def get_overview(db: Session, user_id: int) -> dict:
    """Dashboard 四指标卡 + 三副文案的七指标汇总。

    Args:
        db: 数据库会话（只读）。
        user_id: 当前用户 id。

    Returns:
        dict: OverviewOut 结构（model_dump）——空用户七字段全 0
        不报错；avg_mastery 排除零分待学点（source='goal_breakdown'
        且 mastery_score=0，PROJECT_CONTEXT §6.12）。
    """
    total_minutes, total_count = db.execute(
        select(
            func.sum(LearningRecord.duration_minutes),
            func.count(),
        ).where(LearningRecord.user_id == user_id)
    ).one()
    total_minutes = int(total_minutes or 0)
    total_count = int(total_count or 0)
    avg_session_minutes = (
        round(total_minutes / total_count, 1) if total_count else 0.0
    )

    status_rows = db.execute(
        select(Task.status, func.count())
        .where(Task.user_id == user_id)
        .group_by(Task.status)
    ).all()
    status_counts = {status: int(count or 0) for status, count in status_rows}
    task_total = sum(status_counts.values())
    done_review = (
        status_counts.get(TaskStatus.DONE, 0)
        + status_counts.get(TaskStatus.REVIEW, 0)
    )
    task_completion_rate = (
        round(done_review / task_total * 100, 1) if task_total else 0.0
    )

    now = utc_now()
    overdue_task_count = int(
        db.scalar(
            select(func.count())
            .select_from(Task)
            .where(
                Task.user_id == user_id,
                Task.deadline.is_not(None),
                Task.deadline < now,
                Task.status != TaskStatus.DONE,
            )
        )
        or 0
    )

    avg_mastery = db.scalar(
        select(func.avg(KnowledgeMastery.mastery_score)).where(
            KnowledgeMastery.user_id == user_id,
            ~(
                (KnowledgeMastery.source == MasterySource.GOAL_BREAKDOWN)
                & (KnowledgeMastery.mastery_score == 0)
            ),
        )
    )
    avg_mastery = (
        round(float(avg_mastery), 1) if avg_mastery is not None else 0.0
    )

    return OverviewOut(
        total_minutes=total_minutes,
        task_completion_rate=task_completion_rate,
        avg_mastery=avg_mastery,
        streak_days=_calc_streak_days(db, user_id),
        total_record_count=total_count,
        avg_session_minutes=avg_session_minutes,
        overdue_task_count=overdue_task_count,
    ).model_dump(mode="json")


def _calc_streak_days(db: Session, user_id: int) -> int:
    """连续学习天数（与 P6 ``get_stats`` 同口径独立实现）。

    DISTINCT study_date 集合上，anchor 取北京今天（今天无记录则取
    昨天，不清零——学生早上打开页面不会看到连续天数被抹），向前
    逐日连续计数，无记录为 0。
    """
    today_bj = utc_now().astimezone(TZ_BEIJING).date()
    study_dates: set[date] = set(
        db.scalars(
            select(LearningRecord.study_date)
            .where(LearningRecord.user_id == user_id)
            .distinct()
        )
    )
    anchor = (
        today_bj
        if today_bj in study_dates
        else today_bj - timedelta(days=1)
    )
    streak_days = 0
    while anchor in study_dates:
        streak_days += 1
        anchor -= timedelta(days=1)
    return streak_days