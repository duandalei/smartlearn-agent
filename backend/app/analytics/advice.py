"""今日学习建议模块（P7 analytics，纯规则，无 LLM）。

规则优先级：① overdue（逾期任务）→ ② weakness（薄弱知识点 Top1）
→ ③ streak（连续学习天数 ≥ 7，正向反馈）；命中几条返回几条。
P8 Agent 接管时仅替换本模块实现，接口契约（路径/参数/响应结构）不变。

# 职责分离（spec 已裁定事项 6，2026-10-20）：advice 跳过 trend 风险
# 规则——advice 管「接下来做什么」，风险卡管「发生了什么」；风险预警
# 仅由 trend 接口 risk_alert 与前端独立风险提醒卡呈现，避免同屏出现
# 两遍相同文案。禁止把 trend 风险条加回 advice。
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.analytics.statistics import get_overview
from app.analytics.weakness import get_weakness_top5
from app.schemas.dashboard import AdviceItemOut, AdviceOut

STREAK_ADVICE_MIN_DAYS: int = 7


def generate_advice(db: Session, user_id: int) -> dict:
    """基于规则的今日学习建议（后续由 Agent 接管）。

    Args:
        db: 数据库会话（只读）。
        user_id: 当前用户 id。

    Returns:
        dict: AdviceOut 结构（model_dump）——新用户三条全不命中时
        items=[]；输出仅含语义字段 {type, title, content}，不泄漏
        内部规则编号与阈值。
    """
    items: list[AdviceItemOut] = []
    overview = get_overview(db, user_id)

    overdue_count = overview["overdue_task_count"]
    if overdue_count > 0:
        items.append(
            AdviceItemOut(
                type="overdue",
                title="优先处理逾期任务",
                content=(
                    f"你有 {overdue_count} 个任务已逾期，"
                    f"建议优先完成逾期任务，避免影响整体进度"
                ),
            )
        )

    weakness = get_weakness_top5(db, user_id)
    if weakness["items"]:
        top1 = weakness["items"][0]
        items.append(
            AdviceItemOut(
                type="weakness",
                title="巩固薄弱知识点",
                content=(
                    f"{top1['knowledge_point']} 掌握度 "
                    f"{top1['mastery_score']:g} 分，"
                    f"建议今天安排一次专项复习"
                ),
            )
        )

    streak_days = overview["streak_days"]
    if streak_days >= STREAK_ADVICE_MIN_DAYS:
        items.append(
            AdviceItemOut(
                type="streak",
                title="保持学习节奏",
                content=f"你已连续学习 {streak_days} 天，节奏很稳，继续保持",
            )
        )

    return AdviceOut(items=items).model_dump(mode="json")