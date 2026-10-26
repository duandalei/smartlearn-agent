"""薄弱知识点分析模块（P7 analytics，纯只读）。

掌握度列表与薄弱点 Top5 共用唯一排除条件：NOT (source='goal_breakdown'
AND mastery_score=0)——目标拆解产出的零分待学点是「已规划、尚未学习」
的正常产物，不排除会占满 Top5（PROJECT_CONTEXT §6.12）；goal_breakdown
但分数非 0 的知识点正常参与排序。
"""

from __future__ import annotations

from collections import Counter
from datetime import date, timedelta, timezone, tzinfo
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.base import utc_now
from app.models.enums import MasterySource
from app.models.mastery import KnowledgeMastery
from app.models.record import LearningRecord
from app.schemas.dashboard import (
    MasteryItemOut,
    MasteryOut,
    WeaknessItemOut,
    WeaknessOut,
)

try:
    TZ_BEIJING: tzinfo = ZoneInfo("Asia/Shanghai")
except ZoneInfoNotFoundError:  # pragma: no cover —— Windows 无 tzdata 环境
    TZ_BEIJING = timezone(timedelta(hours=8), "+08:00")

WEAKNESS_TOP_N: int = 5
RECENT_WINDOW_DAYS: int = 30


def get_mastery_list(db: Session, user_id: int) -> dict:
    """掌握度升序列表（排除零分待学点），供横向柱状图直接消费。

    Args:
        db: 数据库会话（只读）。
        user_id: 当前用户 id。

    Returns:
        dict: MasteryOut 结构（model_dump）。
    """
    rows = db.execute(
        select(KnowledgeMastery.knowledge_point, KnowledgeMastery.mastery_score)
        .where(KnowledgeMastery.user_id == user_id, _excluded_filter())
        .order_by(KnowledgeMastery.mastery_score.asc())
    ).all()
    return MasteryOut(
        items=[
            MasteryItemOut(knowledge_point=kp, mastery_score=float(score))
            for kp, score in rows
        ]
    ).model_dump(mode="json")


def get_weakness_top5(db: Session, user_id: int) -> dict:
    """薄弱知识点 Top5（掌握度升序为主序，同分按近 30 天出现频次降序）。

    Args:
        db: 数据库会话（只读）。
        user_id: 当前用户 id。

    Returns:
        dict: WeaknessOut 结构（model_dump）——不足 5 条返回实际数量，
        不填充占位；每条 advice 文案含知识点名 + 分数 + 频次，中性
        措辞、无诊断性表述。
    """
    rows = db.execute(
        select(KnowledgeMastery.knowledge_point, KnowledgeMastery.mastery_score)
        .where(KnowledgeMastery.user_id == user_id, _excluded_filter())
        .order_by(KnowledgeMastery.mastery_score.asc())
    ).all()
    today = utc_now().astimezone(TZ_BEIJING).date()
    start = today - timedelta(days=RECENT_WINDOW_DAYS - 1)
    recent_rows = db.scalars(
        select(LearningRecord.knowledge_points).where(
            LearningRecord.user_id == user_id,
            LearningRecord.study_date.between(start, today),
        )
    )
    recent: Counter[str] = Counter(
        kp for kps in recent_rows for kp in (kps or [])
    )
    ordered = sorted(rows, key=lambda r: (r[1], -recent[r[0]]))
    items: list[WeaknessItemOut] = []
    for kp, score in ordered[:WEAKNESS_TOP_N]:
        count = recent[kp]
        items.append(
            WeaknessItemOut(
                knowledge_point=kp,
                mastery_score=float(score),
                recent_count=count,
                advice=(
                    f"{kp} 掌握度 {score:g} 分，近 30 天学习了 {count} 次，"
                    f"建议结合错题集中复习、安排专项巩固"
                ),
            )
        )
    return WeaknessOut(items=items).model_dump(mode="json")


def _excluded_filter():
    """零分待学点排除条件（mastery 列表与薄弱点共用的唯一判定点）。"""
    return ~(
        (KnowledgeMastery.source == MasterySource.GOAL_BREAKDOWN)
        & (KnowledgeMastery.mastery_score == 0)
    )