"""学习成长报告编排服务（P12：周期推导 + 七要素聚合 + 总结双路径，design 2.4.4）。

报告管道：统计数据（**全部本地 ORM 聚合，零 LLM——SPEC §5.4.1-2
红线：任何数字不得来自模型**）→ LLM 自然语言总结（30s 超时）→
失败降级模板总结（``generated_by="template"``，仍含全部真实数字）
→ 落库 ``learning_reports``（append，O2——旧行永不 UPDATE）。

降级与正常路径同构（用户指令 ②）：两路径产出完全相同的落库结构
与响应结构，差异仅 ``content.generated_by`` 一个标记字段（随报告
持久化，可审计）。LLM 失败不构成业务失败——错误码 3000 不用于
本路径（O1）；**统计本身异常**（ORM 查询抛错）才上抛 500/5000。

复用映射红线（design 1.2.4）：⑤ 薄弱点直接调 ``get_mastery_list``
（零重写排除逻辑）；⑦ 趋势 slope 调 ``get_trend``；advice 三规则
自建（不复用 advice.generate_advice——口径污染，决策 A10）。

回链：design 2.4.4；SPEC §5.4/§5.5；O1/O2 裁定。
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections import Counter
from datetime import date, datetime, timedelta, timezone, tzinfo
from time import monotonic
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.core.response import BizException
from app.models.enums import TaskStatus
from app.models.record import LearningRecord
from app.models.report import LearningReport
from app.models.task import Task
from app.schemas.report import ReportGenerateIn, ReportOut
from app.services import llm
from app.services.llm import ChatMessage

logger = logging.getLogger(__name__)

#: 北京时区（周期自然日口径；本地定义对齐 services/task.py 惯例）。
try:
    TZ_BEIJING: tzinfo = ZoneInfo("Asia/Shanghai")
except ZoneInfoNotFoundError:  # pragma: no cover —— Windows 无 tzdata 环境
    TZ_BEIJING = timezone(timedelta(hours=8), "+08:00")

#: 总结 LLM 超时（秒）——与 PLAN_LLM_TIMEOUT_S 各自独立定义同值
#: （模块独立 monkeypatch 前提，design 2.5.3；仅测试可 monkeypatch）。
REPORT_LLM_TIMEOUT_S: float = 30.0

#: 薄弱点取前 N 条进报告。
_WEAK_POINT_TOP_N: int = 3

#: 报告类型 → 周期中文名（模板文案用）。
_PERIOD_CN: dict[str, str] = {
    "daily": "本日",
    "weekly": "本周",
    "monthly": "本月",
}


def _completed_bj_date(value: datetime) -> date:
    """completed_at（utc_now 生成，SQLite 读回 naive UTC 语义）→ 北京日期。"""
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(TZ_BEIJING).date()


def _deadline_bj_date(value: datetime) -> date:
    """deadline（HTTP/工具层以北京挂钟写入，SQLite 读回 naive 北京语义）→ 北京日期。"""
    if value.tzinfo is None:
        value = value.replace(tzinfo=TZ_BEIJING)
    return value.astimezone(TZ_BEIJING).date()


# ---------------------------------------------------------------------------
# 周期推导（纯函数，design 2.4.4-A）
# ---------------------------------------------------------------------------


def resolve_period(
    report_type: str, period_end: date | None, today: date
) -> tuple[date, date]:
    """推导报告统计区间（start, end）。

    - daily：end 缺省昨天，start = end；
    - weekly：end 缺省上周日，start = end 所在周周一；
    - monthly：end 缺省上月末日，start = end 所在月首日。

    Args:
        report_type: daily / weekly / monthly。
        period_end: 指定区间末日（None 取缺省；晚于今天已被 schema 拒绝）。
        today: 基准日期（北京今天）。

    Returns:
        tuple[date, date]: (period_start, period_end)。
    """
    if report_type == "daily":
        end = period_end or (today - timedelta(days=1))
        return end, end
    if report_type == "weekly":
        end = period_end or (today - timedelta(days=today.weekday() + 1))
        return end - timedelta(days=end.weekday()), end
    if report_type == "monthly":
        if period_end is not None:
            return period_end.replace(day=1), period_end
        first_of_this_month = today.replace(day=1)
        end = first_of_this_month - timedelta(days=1)
        return end.replace(day=1), end
    raise BizException(1001, f"不支持的报告类型：{report_type}", 422)


# ---------------------------------------------------------------------------
# 七要素聚合（全部本地 ORM，零 LLM——SPEC §5.4.1-2 红线）
# ---------------------------------------------------------------------------


def collect_statistics(
    db: Session, user_id: int, start: date, end: date
) -> dict[str, Any]:
    """聚合报告七要素（design 2.4.4-B）。

    ① total_minutes ② task_completed ③ completion_rate ④ top_direction
    ⑤ weak_points（复用 get_mastery_list 前 3）⑥ progress（上一等长
    周期三差值）⑦ advice（三规则自建）。零数据容错：全 0/null/[]。

    Args:
        db: 数据库会话（只读）。
        user_id: 当前用户 id。
        start / end: 统计区间（北京自然日口径）。

    Returns:
        dict[str, Any]: 七要素 dict（JSON 序列化安全值）。
    """
    days = (end - start).days + 1

    # ① 周期内学习时长合计
    total_minutes = int(
        db.execute(
            select(func.coalesce(func.sum(LearningRecord.duration_minutes), 0)).where(
                LearningRecord.user_id == user_id,
                LearningRecord.study_date.between(start, end),
            )
        ).scalar()
        or 0
    )

    # ② 周期内完成任务数（completed_at 转北京日期落窗口）
    completed_rows = db.execute(
        select(Task.completed_at).where(
            Task.user_id == user_id,
            Task.completed_at.is_not(None),
        )
    ).scalars()
    task_completed = sum(
        1
        for completed_at in completed_rows
        if completed_at is not None
        and start <= _completed_bj_date(completed_at) <= end
    )

    # ③ 完成率：周期内截止任务中 done（含 review）占比
    deadline_rows = db.execute(
        select(Task.status, Task.deadline).where(
            Task.user_id == user_id,
            Task.deadline.is_not(None),
        )
    ).all()
    in_window = [
        status
        for status, deadline in deadline_rows
        if deadline is not None and start <= _deadline_bj_date(deadline) <= end
    ]
    finished = sum(
        1 for status in in_window if status in (TaskStatus.DONE, TaskStatus.REVIEW)
    )
    completion_rate = round(finished / len(in_window) * 100, 1) if in_window else 0.0

    # ④ 学习最多方向：周期内记录的知识点 JSON 摊平 Counter 取最大
    kp_rows = db.execute(
        select(LearningRecord.knowledge_points).where(
            LearningRecord.user_id == user_id,
            LearningRecord.study_date.between(start, end),
        )
    ).scalars()
    counter: Counter[str] = Counter()
    for points in kp_rows:
        for point in points or []:
            counter[str(point)] += 1
    top_direction = counter.most_common(1)[0][0] if counter else None

    # ⑤ 薄弱知识点（复用 get_mastery_list——排除逻辑零重写）
    from app.analytics.weakness import get_mastery_list

    mastery = get_mastery_list(db, user_id)
    weak_points = [
        {"knowledge_point": item["knowledge_point"], "mastery_score": item["mastery_score"]}
        for item in (mastery.get("items") or [])[:_WEAK_POINT_TOP_N]
    ]

    # ⑥ 阶段进步：上一等长周期三差值（分钟 / 完成率 / 平均自评掌握度）
    prev_end = start - timedelta(days=1)
    prev_start = prev_end - timedelta(days=days - 1)
    prev_minutes = int(
        db.execute(
            select(func.coalesce(func.sum(LearningRecord.duration_minutes), 0)).where(
                LearningRecord.user_id == user_id,
                LearningRecord.study_date.between(prev_start, prev_end),
            )
        ).scalar()
        or 0
    )
    prev_completed = sum(
        1
        for completed_at in db.execute(
            select(Task.completed_at).where(
                Task.user_id == user_id,
                Task.completed_at.is_not(None),
            )
        ).scalars()
        if completed_at is not None
        and prev_start <= _completed_bj_date(completed_at) <= prev_end
    )
    avg_mastery = _avg_mastery(db, user_id, start, end)
    prev_avg_mastery = _avg_mastery(db, user_id, prev_start, prev_end)
    progress = {
        "minutes_diff": total_minutes - prev_minutes,
        "task_completed_diff": task_completed - prev_completed,
        "avg_mastery_diff": (
            round(avg_mastery - prev_avg_mastery, 1)
            if avg_mastery is not None and prev_avg_mastery is not None
            else None
        ),
    }

    # ⑦ 建议（三规则自建：周期内逾期 + 薄弱点 + 趋势 slope；决策 A10）
    overdue_count = sum(
        1
        for status, deadline in deadline_rows
        if deadline is not None
        and _deadline_bj_date(deadline) < start
        and status not in (TaskStatus.DONE, TaskStatus.REVIEW)
    )
    advice: list[str] = []
    if overdue_count > 0:
        advice.append(f"有 {overdue_count} 个任务已逾期，建议优先安排补上")
    if weak_points:
        advice.append(
            f"{weak_points[0]['knowledge_point']}掌握度较低"
            f"（{weak_points[0]['mastery_score']:.0f} 分），建议安排专项复习"
        )
    slope = _trend_slope(db, user_id, days)
    if slope is not None and slope < 0:
        advice.append("近期学习时长呈下降趋势，建议保持稳定的每日学习节奏")
    if not advice:
        advice.append("暂无明显风险，建议按当前学习计划继续推进")

    return {
        "total_minutes": total_minutes,
        "task_completed": task_completed,
        "completion_rate": completion_rate,
        "top_direction": top_direction,
        "weak_points": weak_points,
        "progress": progress,
        "advice": advice,
    }


def _avg_mastery(db: Session, user_id: int, start: date, end: date) -> float | None:
    """周期内学习记录自评掌握度均值（decision A11 口径）。"""
    value = db.execute(
        select(func.avg(LearningRecord.mastery_level)).where(
            LearningRecord.user_id == user_id,
            LearningRecord.study_date.between(start, end),
            LearningRecord.mastery_level.is_not(None),
        )
    ).scalar()
    return round(float(value), 1) if value is not None else None


def _trend_slope(db: Session, user_id: int, days: int) -> float | None:
    """趋势斜率（复用 get_trend——⑦ 复用映射；窗口=周期天数，下限 7）。"""
    from app.analytics.trend import get_trend

    trend = get_trend(db, user_id, max(days, 7))
    slope = trend.get("slope")
    return float(slope) if slope is not None else None


# ---------------------------------------------------------------------------
# 总结双路径（design 2.4.4-C：LLM / 模板降级——同构输出）
# ---------------------------------------------------------------------------


def _period_phrase(
    report_type: str, period_start: date | None, period_end: date | None
) -> str:
    """周期措辞短语（与 LLM Prompt 同一措辞规则，用户 2026-10-24 裁定）。

    缺省统计区间是过去周期（昨天 / 上周 / 上月）——措辞用「昨日 /
    上周 / 上月」或日期范围，不得用「今天 / 本周 / 本月」指代过去
    区间；仅当区间确为当前自然周期时才用「今天 / 本周 / 本月」。

    Args:
        report_type: daily / weekly / monthly。
        period_start / period_end: 统计区间（None 时回退静态短语）。

    Returns:
        str: 周期措辞短语（如「上周」「2026-10-12 至 2026-10-18」）。
    """
    if period_start is None or period_end is None:
        return _PERIOD_CN.get(report_type, "本周期")
    today = datetime.now(TZ_BEIJING).date()
    this_monday = today - timedelta(days=today.weekday())
    if report_type == "daily":
        if period_start == today and period_end == today:
            return "今天"
        if period_start == today - timedelta(days=1):
            return "昨日"
        return f"{period_start.isoformat()} 至 {period_end.isoformat()}"
    if report_type == "weekly":
        if period_start == this_monday:
            return "本周"
        if period_start == this_monday - timedelta(days=7):
            return "上周"
        return f"{period_start.isoformat()} 至 {period_end.isoformat()}"
    if period_start == today.replace(day=1):
        return "本月"
    if period_end == today.replace(day=1) - timedelta(days=1):
        return "上月"
    return f"{period_start.isoformat()} 至 {period_end.isoformat()}"


def render_template_summary(
    stats: dict[str, Any],
    report_type: str,
    period_start: date | None = None,
    period_end: date | None = None,
) -> str:
    """模板总结（降级路径）——含全部真实数字（O1：非空泛鼓励话）。

    Args:
        stats: ``collect_statistics`` 七要素 dict。
        report_type: daily / weekly / monthly。
        period_start / period_end: 统计区间（措辞判定；None 时回退
            静态短语「本日/本周/本月」，向后兼容直调）。

    Returns:
        str: 中文总结文本（空数据走引导分支）。
    """
    period_cn = _period_phrase(report_type, period_start, period_end)
    total_minutes = int(stats.get("total_minutes") or 0)
    if total_minutes <= 0 and not stats.get("task_completed"):
        weak = stats.get("weak_points") or []
        lead = (
            f"{weak[0]['knowledge_point']}"
            if weak
            else "当前学习目标的第一个知识点"
        )
        return f"{period_cn}暂无学习记录，建议从 {lead} 开始，先建立每日学习的节奏。"
    hours = round(total_minutes / 60, 1)
    completed = int(stats.get("task_completed") or 0)
    rate = stats.get("completion_rate") or 0.0
    direction = stats.get("top_direction")
    weak = stats.get("weak_points") or []
    advice_list = stats.get("advice") or []
    parts = [
        f"{period_cn}学习 {hours} 小时（{total_minutes} 分钟），"
        f"完成任务 {completed} 个，完成率 {rate}%。"
    ]
    if direction:
        parts.append(f"学习最多的方向是{direction}；")
    if weak:
        parts.append(
            f"最需要加强的知识点是{weak[0]['knowledge_point']}"
            f"（掌握度 {weak[0]['mastery_score']:.0f} 分）；"
        )
    if advice_list:
        parts.append(f"建议：{advice_list[0]}。")
    return "".join(parts)


def _summary_messages(
    stats: dict[str, Any],
    report_type: str,
    period_start: date,
    period_end: date,
) -> list[ChatMessage]:
    """构造总结 LLM 消息（统计 JSON + 区间措辞指令，用户 2026-10-24 裁定）。

    缺省统计区间都不是「当前」周期（daily=昨天 / weekly=上周 /
    monthly=上月）——Prompt 必须写明具体区间并约束措辞，否则 LLM
    会把过去的统计写成「本周学习 X 分钟」，用户会误以为是当前周。
    """
    return [
        ChatMessage(
            role="system",
            content="你是学习成长报告撰写助手，为学生写简短、具体、可执行的总结。",
        ),
        ChatMessage(
            role="user",
            content=(
                f"报告统计区间为 {period_start.isoformat()} 至 "
                f"{period_end.isoformat()}，请根据以下统计数据写一份该区间的"
                "学习总结（120 字以内，中文）：\n"
                f"{json.dumps(stats, ensure_ascii=False, default=str)}\n"
                "措辞要求：如该区间不是当前自然周/自然日/自然月，请用「上周」"
                "「昨天」「上月」或直接写日期范围指代，不要用「本周」「今天」"
                "「本月」指代过去的统计区间。\n"
                "内容要求：1. 必须引用其中的真实数字（时长、任务数、完成率等），"
                "不得编造数据；2. 指出薄弱知识点与阶段进步；3. 给出 1-2 条"
                "可执行建议；4. 直接输出总结正文，不要任何前缀或解释。"
            ),
        ),
    ]


async def generate_report(
    db: Session, user_id: int, data: ReportGenerateIn
) -> dict[str, Any]:
    """生成学习成长报告（HTTP ⑦ 与工具 T4 共用）。

    Args:
        db: 数据库会话。
        user_id: 当前用户 id。
        data: 入参（report_type 必填；period_end 可选，晚于今天已被
            schema validator 拒绝）。

    Returns:
        dict[str, Any]: 报告对象（ReportOut 同构 + content.generated_by）。

    Raises:
        BizException: 5000（统计查询本身异常——不落半截报告）。
    """
    today = datetime.now(TZ_BEIJING).date()
    start, end = resolve_period(data.report_type, data.period_end, today)
    try:
        stats = collect_statistics(db, user_id, start, end)
    except BizException:
        raise
    except Exception as exc:  # noqa: BLE001 - 统计异常整体上抛（SPEC 5.4.3-2）
        logger.error(
            "report_stats_failed user_id=%s type=%s err=%s",
            user_id,
            data.report_type,
            f"{type(exc).__name__}: {exc}",
            exc_info=True,
        )
        raise BizException(5000, "报告统计生成失败，请稍后重试", 500) from None

    summary: str | None = None
    generated_by = "template"
    started = monotonic()
    try:
        text = await asyncio.wait_for(
            llm.chat(_summary_messages(stats, data.report_type, start, end)),
            timeout=REPORT_LLM_TIMEOUT_S,
        )
        if text and text.strip():
            summary = text.strip()
            generated_by = "llm"
    except (asyncio.TimeoutError, BizException, ValueError) as exc:
        elapsed = monotonic() - started
        logger.warning(
            "report_llm_fallback user_id=%s type=%s err_type=%s elapsed_s=%.2f",
            user_id,
            data.report_type,
            type(exc).__name__,
            elapsed,
        )
    if summary is None:
        summary = render_template_summary(stats, data.report_type, start, end)
        generated_by = "template"

    content = {**stats, "generated_by": generated_by}
    report = LearningReport(
        user_id=user_id,
        report_type=data.report_type,
        period_start=start,
        period_end=end,
        summary=summary,
        content=content,
    )
    db.add(report)
    db.commit()
    db.refresh(report)
    return _report_out(report)


def _report_out(report: LearningReport) -> dict[str, Any]:
    """报告 ORM → ReportOut 同构 dict（model_dump mode="json"——HTTP 与
    Agent 工具共用，date/datetime 统一 ISO 字符串）。"""
    return ReportOut.model_validate(report).model_dump(mode="json")