"""动态学习计划编排服务（P12：生成 / 调整 / 查询 / diff，design 2.4.3）。

HTTP 端点与 Agent 工具复用同一 service 函数（单一业务事实来源，
SPEC §5.7）：

- ``generate_plan``：输入聚合 → 规划 LLM 三分支（30s 总窗 + 重试 1
  次 + 降级纯规则）→ 确定性排程引擎 → 同事务落库（OP1 双分支 +
  任务唯一性铁律三道保证）；
- ``adjust_plan``：AI 判断「要不要调、调哪些」→ 确定性排程引擎
  落位 → 版本链落库（parent_plan_id 备份链）+ 任务
  scheduled_date 同步；AI 不可用或输出不合法时直接报错，不降级
  为规则调整；
- ``get_current_plan`` / ``get_plan_diff``：查询与幂等 diff 重算
  （与调整随返共用 adjuster.compute_diff 同一函数，D4）。

铁律：计划不可原地修改——每次生成或调整新建 version、旧版置
archived；多周并存（生成不得归档本周未结束 active）。

LLM 调用形态：``from app.services import llm`` 模块属性访问
（``llm.chat``）——mock 注入点 ``app.services.plan.llm.chat``
（P9/P11 同款惯例）。降级记元数据级日志（禁打印 prompt 与响应
正文，SPEC §4.3-4）。

回链：design 2.4.3；SPEC §5.1/§5.2/§5.3；OP1 裁定定稿。
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from datetime import date, datetime, time, timedelta, timezone, tzinfo
from time import monotonic
from typing import Any, Literal, Sequence

from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.analytics.adjuster import (
    AdjustContext,
    AdjustmentResult,
    ItemSnapshot,
    NewItemLayout,
    TaskSnapshot,
    apply_adjustment,
    compute_diff,
    render_adjust_reason,
)
from app.analytics.scheduler import (
    CANDIDATE_MAX_MINUTES,
    CANDIDATE_MIN_MINUTES,
    ScheduleCandidate,
    ScheduleInput,
    ScheduledItem,
    build_rule_candidates,
    build_week_schedule,
    current_week_window,
    next_week_window,
)
from app.core.response import CODE_INTERNAL_ERROR, CODE_LLM_FAILED, BizException
from app.models.enums import GoalStatus, PlanSource, PlanStatus, TaskSource, TaskStatus
from app.models.goal import LearningGoal
from app.models.plan import LearningPlan, LearningPlanItem
from app.models.record import LearningRecord
from app.models.task import Task
from app.schemas.plan import PlanItemOut, PlanOut
from app.services import llm
from app.services.profile import get_profile_by_user_id
from app.services.llm import ChatMessage

logger = logging.getLogger(__name__)

#: 北京时区（「今天 / 本周」判定口径；本地定义对齐 services/task.py 惯例——
#: 无 tzdata 环境回退固定 UTC+8，数学等价）。
try:
    TZ_BEIJING: tzinfo = ZoneInfo("Asia/Shanghai")
except ZoneInfoNotFoundError:  # pragma: no cover —— Windows 无 tzdata 环境
    TZ_BEIJING = timezone(timedelta(hours=8), "+08:00")

#: 规划 LLM 超时（秒）——首调 + 解析失败重试合计 ≤ 30s 总窗（决策 A3/A7，
#: 锁定 HTTP 35s 上限不破；仅测试可 monkeypatch，O8 铁律）。
PLAN_LLM_TIMEOUT_S: float = 30.0

#: 调整 LLM 超时（秒）——单次调用，需小于前端 30s 请求超时，留出
#: 落库与响应时间（仅测试可 monkeypatch，O8 铁律）。
ADJUST_LLM_TIMEOUT_S: float = 25.0

#: 周期天数（一个完整自然周）。
_WEEK_DAYS: int = 7

#: Markdown 代码围栏剥离正则（沿用 goal.py ``_CODE_FENCE_RE`` 惯例）。
_CODE_FENCE_RE = re.compile(r"^```(?:json)?\s*(.*?)\s*```$", re.DOTALL)


# ---------------------------------------------------------------------------
# LLM 输出契约模型（design 2.1.3-A 契约一：结构性无日期/时间字段）
# ---------------------------------------------------------------------------


class _PlanCandidateLLM(BaseModel):
    """LLM 候选条目（严格 schema：extra="forbid" 拒绝任何日期时间字段）。"""

    model_config = ConfigDict(extra="forbid")

    topic: str = Field(min_length=1, max_length=200)
    knowledge_points: list[str] = Field(default_factory=list, max_length=20)
    estimated_minutes: int = Field(ge=CANDIDATE_MIN_MINUTES, le=CANDIDATE_MAX_MINUTES)
    priority: Literal["low", "medium", "high"] = "medium"
    related_task_id: int | None = Field(default=None, ge=1)


class _PlanCandidatesLLM(BaseModel):
    """LLM 候选输出顶层结构（5-14 条）。"""

    model_config = ConfigDict(extra="forbid")

    candidates: list[_PlanCandidateLLM] = Field(min_length=5, max_length=14)


class _AdjustItemLLM(BaseModel):
    """LLM 调整条目（只引用条目 id 与动作，禁止日期时间）。"""

    model_config = ConfigDict(extra="forbid")

    item_id: int = Field(ge=1)
    action: Literal["move", "drop"]


class _AdjustDecisionLLM(BaseModel):
    """LLM 调整决策顶层结构。"""

    model_config = ConfigDict(extra="forbid")

    needs_adjustment: bool
    reason: str = Field(default="", max_length=500)
    items: list[_AdjustItemLLM] = Field(default_factory=list, max_length=50)


class _ParseFailed(Exception):
    """候选解析失败（附原因摘要，供纠错重试提示词使用）。"""


# ---------------------------------------------------------------------------
# 内部辅助（聚合 / 解析 / 渲染）
# ---------------------------------------------------------------------------


def _beijing_now() -> datetime:
    """北京时区当前时刻（aware）。"""
    return datetime.now(TZ_BEIJING)


def _ensure_bj_aware(value: datetime | None) -> datetime | None:
    """归一化 deadline 的 aware 性（SQLite 读写丢 tzinfo 的防御）。

    任务 deadline 由 HTTP/工具层以北京挂钟 aware 值写入，SQLite 读回
    为 naive 北京挂钟——统一 attach TZ_BEIJING 后再与 aware now 比较
    （naive 与 aware 直接比较会抛 TypeError）。
    """
    if value is None or value.tzinfo is not None:
        return value
    return value.replace(tzinfo=TZ_BEIJING)


def _week_days_of(start: date, end: date) -> list[date]:
    """展开周期日期列表（start..end 逐日）。"""
    days: list[date] = []
    cursor = start
    while cursor <= end:
        days.append(cursor)
        cursor += timedelta(days=1)
    return days


def _collect_roadmap_leaves(tree: dict[str, Any]) -> list[str]:
    """DFS 提取知识树叶子（深度序；与 goal.py ``_collect_leaves`` 同构逻辑
    本地实现——其为私有函数不跨模块导入，口径一致性由单测锚定）。"""
    leaves: list[str] = []
    stack: list[dict[str, Any]] = [tree]
    while stack:
        node = stack.pop()
        children = node.get("children") or []
        if not children:
            name = node.get("name")
            if name:
                leaves.append(str(name))
        else:
            stack.extend(reversed(children))
    return leaves


def _strip_code_fence(text: str) -> str:
    """剥离 Markdown 代码围栏（```json ... ```）。"""
    stripped = text.strip()
    fence = _CODE_FENCE_RE.match(stripped)
    return fence.group(1) if fence else stripped


def _parse_candidates(
    text: str, valid_task_ids: set[int], task_deadlines: dict[int, datetime]
) -> list[ScheduleCandidate]:
    """LLM 文本 → 排程候选（三步：剥围栏 → JSON → schema + 语义校验）。

    唯一性第二道保证：同一 ``related_task_id`` 多条候选只保留首条
    （LLM 对同一任务输出多条时丢弃其余；prompt 明示「每个任务最多
    出现一次」）。

    Raises:
        _ParseFailed: 任一步失败（附中文原因摘要）。
    """
    payload = _strip_code_fence(text)
    try:
        data = json.loads(payload)
    except (json.JSONDecodeError, ValueError):
        raise _ParseFailed("无法解析为 JSON") from None
    try:
        parsed = _PlanCandidatesLLM.model_validate(data)
    except ValidationError as exc:
        raise _ParseFailed(f"候选结构不合法：{exc.errors()[:2]}") from None

    candidates: list[ScheduleCandidate] = []
    seen_task_ids: set[int] = set()
    for entry in parsed.candidates:
        if entry.related_task_id is not None:
            if entry.related_task_id not in valid_task_ids:
                raise _ParseFailed(
                    f"related_task_id={entry.related_task_id} 不在候选任务清单内"
                )
            if entry.related_task_id in seen_task_ids:
                continue  # 唯一性第二道保证：同任务只保留首条候选
            seen_task_ids.add(entry.related_task_id)
        candidates.append(
            ScheduleCandidate(
                topic=entry.topic,
                knowledge_points=list(entry.knowledge_points),
                estimated_minutes=entry.estimated_minutes,
                priority=entry.priority,
                related_task_id=entry.related_task_id,
                deadline=task_deadlines.get(entry.related_task_id)
                if entry.related_task_id is not None
                else None,
            )
        )
    if not candidates:
        raise _ParseFailed("候选列表为空")
    return candidates


def _plan_prompt(
    capacity: int,
    roadmap_leaves: list[str],
    weak_points: list[dict[str, Any]],
    task_pool: list[dict[str, Any]],
    interests: list[str],
    period_label: str = "下一周",
) -> list[ChatMessage]:
    """构造规划 LLM 消息（候选来源 JSON + 「禁止输出日期时间」硬指令）。

    Args:
        period_label: 目标周期中文标签（「下一周」/「本周剩余时间」），
            仅影响提示词措辞，不改变输出 JSON 契约。
    """
    pool_desc = [
        {
            "id": task["id"],
            "title": task["title"],
            "priority": task["priority"],
            "deadline": task["deadline"].isoformat(),
        }
        for task in task_pool
    ]
    weak_desc = [
        {"knowledge_point": w["knowledge_point"], "mastery_score": w["mastery_score"]}
        for w in weak_points[:6]
    ]
    user_content = (
        f"请为用户挑选{period_label}的学习候选。\n\n"
        f"### 候选来源（只读参考）\n"
        f"- 每日可学习时长：{capacity} 分钟\n"
        f"- 学习目标知识树叶子：{json.dumps(roadmap_leaves[:12], ensure_ascii=False)}\n"
        f"- 薄弱知识点（掌握度升序）：{json.dumps(weak_desc, ensure_ascii=False)}\n"
        f"- 待处理任务（逾期/临期，按紧急度升序）：{json.dumps(pool_desc, ensure_ascii=False)}\n"
        f"- 兴趣方向：{json.dumps(interests, ensure_ascii=False)}\n\n"
        "### 输出要求\n"
        "输出严格 JSON，形如：\n"
        '{"candidates": [{"topic": "Transformer 注意力机制", '
        '"knowledge_points": ["Transformer", "Attention"], '
        '"estimated_minutes": 45, "priority": "high", "related_task_id": 12}]}\n'
        "规则：\n"
        "1. 输出 5-14 个候选，每个候选专注一个学习主题，topic 为简洁中文；\n"
        "2. estimated_minutes 取 15-240 之间的整数；\n"
        "3. priority 取 low/medium/high，逾期或临期任务对应的候选建议 high；\n"
        "4. related_task_id 只能引用上方任务清单中的 id（新学项省略该字段）；"
        "每个任务最多出现一次；\n"
        "5. 禁止输出任何日期、时间、星期字段——具体排期由系统确定；\n"
        "6. 直接输出 JSON，不要任何解释文字。"
    )
    return [
        ChatMessage(
            role="system",
            content=(
                f"你是学习计划规划助手，职责是挑选{period_label}值得学习的知识点与任务"
                "（学什么、学多久、优先级），不负责具体时间安排。"
            ),
        ),
        ChatMessage(role="user", content=user_content),
    ]


# ---------------------------------------------------------------------------
# 生成路径（design 2.4.3-A/B：聚合 → LLM 三分支 → 引擎 → 事务落库）
# ---------------------------------------------------------------------------


async def generate_plan(
    db: Session,
    user_id: int,
    target: Literal["next_week", "current_week"] = "next_week",
) -> dict[str, Any]:
    """生成学习计划（HTTP ① 与工具 T2 共用入口）。

    混合模式（O4）：规划 LLM 决定「学什么 / 学多久 / 优先级」；
    确定性排程引擎决定「周几几点 / 容量 / 冲突 / 休息日」。LLM
    失败（超时 / 服务失败 / 两次解析失败）自动降级纯规则候选
    （``generated_by="rules"``），不报错、不阻塞。

    ``target`` 语义（缺省 ``next_week``，逐字节保持原行为）：

    - ``next_week``：下一个完整自然周（下周一~下周日），7 天全量排程；
    - ``current_week``：本周兜底（本周一~本周日），只对今天及以后
      的日期排程，过去日期不落任何条目（周五已过则不注入休息条目）。

    Args:
        db: 数据库会话。
        user_id: 当前用户 id（服务端注入）。
        target: 目标周期（``next_week`` / ``current_week``）。

    Returns:
        dict[str, Any]: ``PlanGenerateOut`` 结构——{plan, items,
        unplaced_tasks, generated_by}。

    Raises:
        BizException: 1007（与既有 active 计划部分重叠）/ 5000（兜底）。
    """
    now = _beijing_now()
    today = now.date()
    rest_day: date | None
    if target == "current_week":
        start, end = current_week_window(today)
        schedule_days = [day for day in _week_days_of(start, end) if day >= today]
        rest_day = start + timedelta(days=4)
        if rest_day < today:
            rest_day = None
        period_label = "本周剩余时间"
    else:
        start, end = next_week_window(today)
        schedule_days = _week_days_of(start, end)
        rest_day = start + timedelta(days=4)
        period_label = "下一周"

    # 1. 输入聚合（只读四查询；唯一性第一道保证：任务池按 id 天然去重）
    profile = get_profile_by_user_id(db, user_id)
    capacity = int(profile.get("daily_study_minutes") or 60)
    interests = [str(i) for i in (profile.get("interest_directions") or [])]

    goal = db.execute(
        select(LearningGoal)
        .where(
            LearningGoal.user_id == user_id,
            LearningGoal.status == GoalStatus.ACTIVE,
        )
        .order_by(LearningGoal.id.desc())
        .limit(1)
    ).scalar_one_or_none()
    roadmap_leaves: list[str] = []
    if goal is not None and goal.roadmap:
        roadmap_leaves = _collect_roadmap_leaves(goal.roadmap)

    from app.analytics.weakness import get_mastery_list

    mastery = get_mastery_list(db, user_id)
    weak_points: list[dict[str, Any]] = mastery.get("items", [])[:6]

    urgent_cutoff = now + timedelta(hours=48)
    task_rows = db.execute(
        select(Task)
        .where(
            Task.user_id == user_id,
            Task.status != TaskStatus.DONE,
            Task.deadline.is_not(None),
            Task.deadline <= urgent_cutoff,
        )
        .order_by(Task.deadline.asc())
        .limit(10)
    ).scalars().all()
    task_pool = [
        {
            "id": row.id,
            "title": row.title,
            "estimated_minutes": row.estimated_minutes,
            "priority": (row.priority.value if row.priority else "medium"),
            "knowledge_points": list(row.knowledge_points or []),
            "deadline": _ensure_bj_aware(row.deadline),
        }
        for row in task_rows
    ]
    valid_task_ids = {task["id"] for task in task_pool}
    task_deadlines = {task["id"]: task["deadline"] for task in task_pool}

    # 2. 候选获取三分支（决策 A7：首调 + 解析失败重试共享同一 30s 总窗）
    candidates: list[ScheduleCandidate] | None = None
    generated_by = "rules"
    messages = _plan_prompt(
        capacity, roadmap_leaves, weak_points, task_pool, interests, period_label
    )
    started = monotonic()
    try:
        candidates = await asyncio.wait_for(
            _fetch_candidates_with_retry(messages, valid_task_ids, task_deadlines),
            timeout=PLAN_LLM_TIMEOUT_S,
        )
        generated_by = "llm"
    except (asyncio.TimeoutError, BizException, _ParseFailed, ValueError) as exc:
        elapsed = monotonic() - started
        logger.warning(
            "plan_llm_fallback user_id=%s type=%s elapsed_s=%.2f",
            user_id,
            type(exc).__name__,
            elapsed,
        )
        candidates = None
    if candidates is None:
        overdue = [t for t in task_pool if t["deadline"] <= now]
        due_soon = [t for t in task_pool if t["deadline"] > now]
        candidates = build_rule_candidates(
            overdue, due_soon, roadmap_leaves, weak_points
        )
        generated_by = "rules"

    # 3. 引擎排程（计算无副作用，事务外完成——事务窗口最小化）
    schedule = build_week_schedule(
        ScheduleInput(
            candidates=candidates,
            daily_capacity_minutes=capacity,
            week_days=schedule_days,
            now=now,
        )
    )

    # 4+5. 同周期判定 + 落库事务（单 commit；中途异常由 get_db 回滚）
    return _persist_generated_plan(
        db,
        user_id,
        goal_id=(goal.id if goal is not None else None),
        start=start,
        end=end,
        schedule=schedule,
        rest_day=rest_day,
        generated_by=generated_by,
        capacity=capacity,
    )


async def _fetch_candidates_with_retry(
    messages: Sequence[ChatMessage],
    valid_task_ids: set[int],
    task_deadlines: dict[int, datetime],
) -> list[ScheduleCandidate]:
    """首调 + 解析失败重试 1 次（附纠错提示；服务类失败不重试直接上抛）。"""
    text = await llm.chat(list(messages))
    try:
        return _parse_candidates(text, valid_task_ids, task_deadlines)
    except _ParseFailed as exc:
        retry_messages: list[ChatMessage] = [
            *messages,
            ChatMessage(role="assistant", content=text[:600]),
            ChatMessage(
                role="user",
                content=(
                    f"上一次输出无法使用（原因：{exc}）。请严格按格式重新输出"
                    " JSON：candidates 数组 5-14 条，禁止任何日期时间字段，"
                    "related_task_id 只能引用给定任务 id。"
                ),
            ),
        ]
        retry_text = await llm.chat(retry_messages)
        return _parse_candidates(retry_text, valid_task_ids, task_deadlines)


def _persist_generated_plan(
    db: Session,
    user_id: int,
    goal_id: int | None,
    start: date,
    end: date,
    schedule: Any,
    rest_day: date | None,
    generated_by: str,
    capacity: int,
) -> dict[str, Any]:
    """落库事务：同周期判定 → 归档+幽灵清理 → 任务落库（OP1 双分支）
    → 计划头 → 条目回填（唯一性断言兜底）→ 单 commit。

    Args:
        rest_day: 休息条目的日期；``None`` 表示本周期不注入休息条目
            （本周兜底生成时周五已过）。
    """
    actives = db.execute(
        select(LearningPlan).where(
            LearningPlan.user_id == user_id,
            LearningPlan.status == PlanStatus.ACTIVE,
        )
    ).scalars().all()

    same_period: list[LearningPlan] = []
    for plan in actives:
        if plan.start_date == start and plan.end_date == end:
            same_period.append(plan)
        elif start <= plan.end_date and plan.start_date <= end:
            raise BizException(
                1007, "目标周期与现有生效计划部分重叠，请先处理现有计划", 400
            )
        # 区间不重叠：多周并存，既有 active 原样保留（D7）

    # (1) 归档同周期旧版 + 幽灵任务清理（只删 agent+todo，不动旧版条目行）
    ghost_task_ids: set[int] = set()
    for old_plan in same_period:
        old_plan.status = PlanStatus.ARCHIVED
        for item in old_plan.items:
            if item.task_id is not None:
                ghost_task_ids.add(item.task_id)
    if ghost_task_ids:
        ghosts = db.execute(
            select(Task).where(
                Task.id.in_(ghost_task_ids),
                Task.user_id == user_id,
                Task.source == TaskSource.AGENT,
                Task.status == TaskStatus.TODO,
            )
        ).scalars().all()
        for ghost in ghosts:
            db.delete(ghost)

    # (2)+(3) 候选落任务（OP1 双分支）与 unplaced 候选建任务
    unplaced_payload: list[dict[str, Any]] = []

    def _resolve_task(candidate: Any, plan_date: date | None) -> Task:
        """OP1 双分支：带 related_task_id 复用既有任务（仅同步 scheduled_date）；
        无则新建 source=agent 任务（兼容 ScheduledItem 与 UnplacedTask 形态）。"""
        if candidate.related_task_id is not None:
            task = db.get(Task, candidate.related_task_id)
            if task is not None and task.user_id == user_id:
                task.scheduled_date = plan_date
                return task
        task = Task(
            user_id=user_id,
            goal_id=goal_id,
            title=candidate.topic[:200],
            description=None,
            knowledge_points=list(getattr(candidate, "knowledge_points", None) or []),
            priority=getattr(candidate, "priority", None) or "medium",
            estimated_minutes=getattr(candidate, "estimated_minutes", None),
            deadline=None,
            scheduled_date=plan_date,
            status=TaskStatus.TODO,
            source=TaskSource.AGENT,
        )
        db.add(task)
        db.flush()
        return task

    item_rows: list[tuple[date, time | None, time | None, str, Task | None, int | None, str | None]] = []
    for placed in schedule.placed:
        task = _resolve_task(placed, placed.plan_date)
        item_rows.append(
            (
                placed.plan_date,
                placed.start_time,
                placed.end_time,
                placed.topic[:200],
                task,
                placed.estimated_minutes,
                placed.priority,
            )
        )
    for unplaced in schedule.unplaced:
        task = _resolve_task(unplaced, None)
        unplaced_payload.append(
            {
                "task_id": task.id,
                "title": task.title,
                "reason": unplaced.reason,
            }
        )

    # (4) 计划头（version = 用户 max version + 1，裁决 #4；生成产物 parent=null）
    max_version = db.execute(
        select(LearningPlan.version)
        .where(LearningPlan.user_id == user_id)
        .order_by(LearningPlan.version.desc())
        .limit(1)
    ).scalar()
    plan = LearningPlan(
        user_id=user_id,
        goal_id=goal_id,
        title=f"学习计划（{start.isoformat()} ~ {end.isoformat()}）",
        version=(max_version or 0) + 1,
        status=PlanStatus.ACTIVE,
        parent_plan_id=None,
        source=PlanSource.AGENT,
        adjust_reason=None,
        start_date=start,
        end_date=end,
    )
    db.add(plan)
    db.flush()

    # (5) 建 items：周五注入「休息 / 复习」条目（task_id 全 None——SQLite
    #     唯一索引对 NULL 不判重）；任务唯一性第三道保证：落库前显式断言。
    #     本周兜底生成且周五已过时 rest_day=None，不注入过去日期的休息条目。
    if rest_day is not None:
        item_rows.append((rest_day, None, None, "休息 / 复习", None, None, None))

    task_ids_seen: list[int] = [t.id for (_, _, _, _, t, _, _) in item_rows if t is not None]
    if len(task_ids_seen) != len(set(task_ids_seen)):
        raise BizException(
            CODE_INTERNAL_ERROR, "计划条目任务关联冲突：同一任务出现多次", 500
        )

    for plan_date, start_time, end_time, topic, task, estimated, priority in item_rows:
        db.add(
            LearningPlanItem(
                plan_id=plan.id,
                plan_date=plan_date,
                start_time=start_time,
                end_time=end_time,
                topic=topic,
                task_id=task.id if task is not None else None,
                estimated_minutes=estimated,
                priority=priority,
            )
        )

    db.commit()
    db.refresh(plan)
    items = _ordered_items(plan)
    return {
        "plan": _plan_out(plan),
        "items": _items_out(db, items),
        "unplaced_tasks": unplaced_payload,
        "generated_by": generated_by,
    }


# ---------------------------------------------------------------------------
# 调整路径（AI 决策 + 确定性排程）
# ---------------------------------------------------------------------------


def _load_plan_or_404(db: Session, user_id: int, plan_id: int) -> LearningPlan:
    """定位本人计划（越权与不存在统一 404/1005——「不可见即不存在」）。"""
    plan = db.get(LearningPlan, plan_id)
    if plan is None or plan.user_id != user_id:
        raise BizException(1005, "学习计划不存在", 404)
    return plan


def _build_adjust_context(
    db: Session, user_id: int, plan: LearningPlan
) -> AdjustContext:
    """读调整输入快照（旧版条目 + 任务快照 + 近 7 天时长 + 档案容量）。"""
    now = _beijing_now()
    today = now.date()
    profile = get_profile_by_user_id(db, user_id)
    capacity = int(profile.get("daily_study_minutes") or 60)

    items = _ordered_items(plan)
    task_ids = [item.task_id for item in items if item.task_id is not None]
    tasks: dict[int, TaskSnapshot] = {}
    if task_ids:
        rows = db.execute(select(Task).where(Task.id.in_(task_ids))).scalars().all()
        tasks = {
            row.id: TaskSnapshot(
                deadline=_ensure_bj_aware(row.deadline),
                status=row.status.value if row.status else "todo",
            )
            for row in rows
        }

    recent_start = today - timedelta(days=6)
    recent_minutes = (
        db.execute(
            select(LearningRecord.duration_minutes)
            .where(
                LearningRecord.user_id == user_id,
                LearningRecord.study_date.between(recent_start, today),
            )
        )
        .scalars()
    )
    total_recent = sum(int(m or 0) for m in recent_minutes)

    return AdjustContext(
        items=[
            ItemSnapshot(
                item_id=item.id,
                plan_date=item.plan_date,
                start_time=item.start_time,
                end_time=item.end_time,
                topic=item.topic,
                task_id=item.task_id,
                estimated_minutes=item.estimated_minutes,
                priority=item.priority.value if item.priority else None,
                status=item.status.value if item.status else "planned",
            )
            for item in items
        ],
        tasks=tasks,
        recent_minutes=total_recent,
        daily_capacity=capacity,
        now=now,
        week_days=_week_days_of(plan.start_date, plan.end_date),
    )


def _adjust_prompt(context: AdjustContext) -> list[ChatMessage]:
    """构造调整决策提示词（AI 只输出条目 id 与动作，禁止日期时间）。

    输入包含条目布局、完成状态、关联任务截止时间/状态、每日容量与
    近 7 天学习时长；AI 据此判断是否需要调整以及调整哪些条目。
    """
    rows: list[dict[str, Any]] = []
    for item in context.items:
        task = (
            context.tasks.get(item.task_id)
            if item.task_id is not None
            else None
        )
        # 已完成/跳过条目（含关联任务已完成）不可调整：直接不喂给模型，
        # 避免它据此编造理由或选中无法执行的条目。
        if item.status in ("done", "skipped") or (
            task is not None and task.status == "done"
        ):
            continue
        rows.append(
            {
                "item_id": item.item_id,
                "date": item.plan_date.isoformat(),
                "start": (
                    item.start_time.strftime("%H:%M")
                    if item.start_time is not None
                    else None
                ),
                "end": (
                    item.end_time.strftime("%H:%M")
                    if item.end_time is not None
                    else None
                ),
                "topic": item.topic,
                "task_id": item.task_id,
                "deadline": (
                    task.deadline.isoformat()
                    if task is not None and task.deadline is not None
                    else None
                ),
                "task_status": task.status if task is not None else None,
                "estimated_minutes": item.estimated_minutes,
                "priority": item.priority,
                "status": item.status,
            }
        )
    user_content = (
        "请评估本周学习计划是否需要调整，并给出要调整的条目。\n\n"
        "### 当前情况\n"
        f"- 今天：{context.now.date().isoformat()}\n"
        f"- 每日可学习时长：{context.daily_capacity} 分钟\n"
        f"- 近 7 天累计学习：{context.recent_minutes} 分钟\n"
        f"- 本周可调整条目：{json.dumps(rows, ensure_ascii=False)}\n"
        "（条目状态或关联任务已完成的条目已省略，不可调整；清单为空时必须"
        "返回 needs_adjustment=false）\n\n"
        "### 判断依据\n"
        "1. 任务未完成且截止临近或已逾期；\n"
        "2. 本周剩余时间不足以完成原计划；\n"
        "3. 任务优先级、依赖关系或执行情况发生变化，需要重新安排；\n"
        "4. 没有充分理由时不要调整（needs_adjustment=false）。\n\n"
        "### 输出要求\n"
        "输出严格 JSON，形如：\n"
        '{"needs_adjustment": true, "reason": "临时说明", '
        '"items": [{"item_id": 12, "action": "move"}]}\n'
        "规则：\n"
        "1. item_id 只能引用上方条目清单中的 id；\n"
        "2. action 取 move（由系统排到本周空闲时段）或 drop"
        "（移出本周计划，任务本身保留）；\n"
        "3. status 为 done/skipped 的条目不可调整，它们是历史事实，"
        "也不应作为调整理由；\n"
        "4. 不需要调整时 needs_adjustment=false 且 items 为空数组；\n"
        "5. reason 用中文说明判断依据（不超过 200 字），提到条目时使用 "
        "topic 名称，不要出现 item_id / task_id 等内部编号；\n"
        "6. 禁止输出任何日期、时间、星期字段——具体排期由系统确定；\n"
        "7. 直接输出 JSON，不要任何解释文字。"
    )
    return [
        ChatMessage(
            role="system",
            content=(
                "你是学习计划调整助手，负责判断本周计划是否需要调整、"
                "调整哪些条目以及原因，不负责具体时间安排。"
            ),
        ),
        ChatMessage(role="user", content=user_content),
    ]


def _parse_adjust_decision(
    text: str, context: AdjustContext
) -> _AdjustDecisionLLM:
    """LLM 文本 → 调整决策（剥围栏 → JSON → schema + 条目合法性校验）。

    Raises:
        _ParseFailed: 结构不合法或引用了不可调整的条目。
    """
    payload = _strip_code_fence(text)
    try:
        data = json.loads(payload)
    except (json.JSONDecodeError, ValueError):
        raise _ParseFailed("无法解析为 JSON") from None
    try:
        decision = _AdjustDecisionLLM.model_validate(data)
    except ValidationError as exc:
        raise _ParseFailed(f"调整结构不合法：{exc.errors()[:2]}") from None

    if not decision.needs_adjustment:
        # 与 needs_adjustment=false 矛盾的多余条目直接忽略。
        return decision.model_copy(update={"items": []})

    adjustable = {
        item.item_id
        for item in context.items
        if item.item_id is not None
        and item.status not in ("done", "skipped")
        and not (
            item.task_id is not None
            and item.task_id in context.tasks
            and context.tasks[item.task_id].status == "done"
        )
    }
    seen: set[int] = set()
    kept: list[_AdjustItemLLM] = []
    for entry in decision.items:
        if entry.item_id not in adjustable:
            raise _ParseFailed(f"item_id={entry.item_id} 不在可调整条目内")
        if entry.item_id in seen:
            continue
        seen.add(entry.item_id)
        kept.append(entry)
    if not kept:
        raise _ParseFailed("needs_adjustment=true 但未给出任何调整条目")
    return decision.model_copy(update={"items": kept})


async def _decide_adjustment(context: AdjustContext) -> _AdjustDecisionLLM:
    """调用 LLM 判断是否需要调整及调整条目；失败直接报错（不降级）。"""
    try:
        text = await asyncio.wait_for(
            llm.chat(_adjust_prompt(context)), timeout=ADJUST_LLM_TIMEOUT_S
        )
    except asyncio.TimeoutError:
        logger.warning("plan_adjust_timeout")
        raise BizException(
            CODE_LLM_FAILED, "AI 调整超时，请稍后重试", http_status=502
        ) from None
    try:
        return _parse_adjust_decision(text, context)
    except _ParseFailed as exc:
        logger.warning("plan_adjust_parse_failed reason=%s", exc)
        raise BizException(
            CODE_LLM_FAILED, "AI 返回的调整方案无法解析，请重试", http_status=502
        ) from None


async def adjust_plan(db: Session, user_id: int, plan_id: int | None) -> dict[str, Any]:
    """动态调整学习计划（HTTP ③ 与工具 T3 共用；AI 决策 + 确定性排程）。

    AI 判断「是否需要调整、调整哪些条目、原因是什么」→ 确定性排程
    引擎把移动集排进本周空闲时段、移出集从计划中移除 → 新版本 +
    parent_plan_id 备份链 + adjust_reason + diff 随返；任务被移动 /
    顺延 / 移出时同步 ``task.scheduled_date``（OP1 调整路径同步义务）。

    AI 调用失败、超时或输出不合法时直接抛错，计划保持原样——本路径
    不再回退规则调整。

    Args:
        db: 数据库会话。
        user_id: 当前用户 id。
        plan_id: 目标计划 id（None 时定位当前 active）。

    Returns:
        dict[str, Any]: ``PlanAdjustOut`` 结构——{plan, adjust_reason,
        diff, adjusted}。

    Raises:
        BizException: 1005（不存在/越权）/ 1007（非 active）/
            3000（AI 不可用或输出不合法，HTTP 502）。
    """
    if plan_id is None:
        plan = _current_active_plan(db, user_id)
        if plan is None:
            raise BizException(1007, "当前没有进行中的学习计划", 400)
    else:
        plan = _load_plan_or_404(db, user_id, plan_id)
    if plan.status != PlanStatus.ACTIVE:
        raise BizException(1007, "仅可调整生效中的计划", 400)

    context = _build_adjust_context(db, user_id, plan)
    # 释放读事务：AI 决策最长等 25s，避免期间持有 SQLite 读锁阻塞其它写入。
    db.commit()
    decision = await _decide_adjustment(context)
    if not decision.needs_adjustment:
        return {
            "plan": _plan_out(plan),
            "adjust_reason": decision.reason.strip() or "AI 判断当前计划无需调整",
            "diff": {"base_plan_id": None, "moved": [], "added": [], "removed": []},
            "adjusted": False,
        }

    item_by_id = {item.item_id: item for item in context.items}
    move_set = [
        item_by_id[entry.item_id]
        for entry in decision.items
        if entry.action == "move"
    ]
    drop_set = [
        item_by_id[entry.item_id]
        for entry in decision.items
        if entry.action == "drop"
    ]

    result: AdjustmentResult = apply_adjustment(context, move_set, drop_set)
    reason = decision.reason.strip() or render_adjust_reason(result.reason_material)

    # 单事务版本链落库（周期不变——start/end 与旧版逐字段相等，裁决 #10）
    plan.status = PlanStatus.ARCHIVED
    new_plan = LearningPlan(
        user_id=user_id,
        goal_id=plan.goal_id,
        title=plan.title,
        version=plan.version + 1,
        status=PlanStatus.ACTIVE,
        parent_plan_id=plan.id,
        source=PlanSource.AGENT,
        adjust_reason=reason,
        start_date=plan.start_date,
        end_date=plan.end_date,
    )
    db.add(new_plan)
    db.flush()

    layouts = result.new_items
    new_task_ids = {layout.task_id for layout in layouts if layout.task_id is not None}
    for layout in layouts:
        db.add(
            LearningPlanItem(
                plan_id=new_plan.id,
                plan_date=layout.plan_date,
                start_time=layout.start_time,
                end_time=layout.end_time,
                topic=layout.topic[:200],
                task_id=layout.task_id,
                estimated_minutes=layout.estimated_minutes,
                priority=layout.priority,
                status=layout.status,  # 裁决 #13：done/skipped 状态原样保持
            )
        )

    # 任务同步（OP1）：被移动/顺延任务 scheduled_date = 新 plan_date；
    # removed（不在新版条目中的旧任务）置空
    old_task_ids = {
        item.task_id for item in context.items if item.task_id is not None
    }
    for task_id in old_task_ids:
        task = db.get(Task, task_id)
        if task is None or task.user_id != user_id:
            continue
        if task_id in new_task_ids:
            layout = next(
                l for l in layouts if l.task_id == task_id
            )
            task.scheduled_date = layout.plan_date
        else:
            task.scheduled_date = None

    db.commit()
    db.refresh(new_plan)
    return {
        "plan": _plan_out(new_plan),
        "adjust_reason": reason,
        "diff": {"base_plan_id": plan.id, **result.diff},
        "adjusted": True,
    }


# ---------------------------------------------------------------------------
# 查询路径（design 2.4.3：current 语义 + 幂等 diff 重算）
# ---------------------------------------------------------------------------


def _current_active_plan(db: Session, user_id: int) -> LearningPlan | None:
    """定位当前 active 计划（start_date <= 今天 <= end_date）。"""
    today = _beijing_now().date()
    return db.execute(
        select(LearningPlan)
        .where(
            LearningPlan.user_id == user_id,
            LearningPlan.status == PlanStatus.ACTIVE,
            LearningPlan.start_date <= today,
            LearningPlan.end_date >= today,
        )
        .order_by(LearningPlan.version.desc())
        .limit(1)
    ).scalar_one_or_none()


def _ordered_items(plan: LearningPlan) -> list[LearningPlanItem]:
    """条目排序：plan_date 升序、同日 start_time 升序（None 休息条目最前）。"""
    return sorted(
        plan.items,
        key=lambda item: (
            item.plan_date,
            0 if item.start_time is None else 1,
            item.start_time or time(0, 0),
        ),
    )


def get_current_plan(db: Session, user_id: int) -> dict[str, Any] | None:
    """当前 active 计划及条目（HTTP ② 与工具 T1；空态返回 None 非 404）。"""
    plan = _current_active_plan(db, user_id)
    if plan is None:
        return None
    return {
        "plan": _plan_out(plan),
        "items": _items_out(db, _ordered_items(plan)),
    }


def _upcoming_active_plan(db: Session, user_id: int) -> LearningPlan | None:
    """定位最近一条尚未开始的 active 计划（start_date > 今天）。"""
    today = _beijing_now().date()
    return db.execute(
        select(LearningPlan)
        .where(
            LearningPlan.user_id == user_id,
            LearningPlan.status == PlanStatus.ACTIVE,
            LearningPlan.start_date > today,
        )
        .order_by(LearningPlan.start_date.asc(), LearningPlan.version.desc())
        .limit(1)
    ).scalar_one_or_none()


def get_upcoming_plan(db: Session, user_id: int) -> dict[str, Any] | None:
    """最近一条尚未开始的 active 计划及条目（空态返回 None 非 404）。

    与 :func:`get_current_plan` 的区别是筛选 ``start_date > 今天``，
    用于回读「已生成但还没开始」的下周计划；出参与 current 同构。
    """
    plan = _upcoming_active_plan(db, user_id)
    if plan is None:
        return None
    return {
        "plan": _plan_out(plan),
        "items": _items_out(db, _ordered_items(plan)),
    }


def get_plan_diff(db: Session, user_id: int, plan_id: int) -> dict[str, Any]:
    """版本对比（幂等重算——与调整随返共用 adjuster.compute_diff，D4）。

    ``parent_plan_id=null``（首版）返回空结构（200，裁决 #9）。
    """
    plan = _load_plan_or_404(db, user_id, plan_id)
    if plan.parent_plan_id is None:
        return {"base_plan_id": None, "moved": [], "added": [], "removed": []}
    base = db.get(LearningPlan, plan.parent_plan_id)
    if base is None or base.user_id != user_id:
        return {"base_plan_id": None, "moved": [], "added": [], "removed": []}

    old_items = _ordered_items(base)
    old_snapshots = [
        ItemSnapshot(
            item_id=item.id,
            plan_date=item.plan_date,
            start_time=item.start_time,
            end_time=item.end_time,
            topic=item.topic,
            task_id=item.task_id,
            estimated_minutes=item.estimated_minutes,
            priority=item.priority.value if item.priority else None,
            status=item.status.value if item.status else "planned",
        )
        for item in old_items
    ]
    new_layouts = [
        NewItemLayout(
            plan_date=item.plan_date,
            start_time=item.start_time,
            end_time=item.end_time,
            topic=item.topic,
            task_id=item.task_id,
            estimated_minutes=item.estimated_minutes,
            priority=item.priority.value if item.priority else None,
            status=item.status.value if item.status else "planned",
        )
        for item in _ordered_items(plan)
    ]
    # AI 决策不可重放：统一以旧版全部任务 id 作为 movable 集合，
    # 与 apply_adjustment 调整随返使用同一口径（reason 文案一致）。
    movable_ids = {
        item.task_id for item in old_items if item.task_id is not None
    }
    diff = compute_diff(old_snapshots, new_layouts, movable_ids)
    return {"base_plan_id": base.id, **diff}


# ---------------------------------------------------------------------------
# 出参组装（ORM → dict，字段名与 schemas/plan.py 对齐）
# ---------------------------------------------------------------------------


def _plan_out(plan: LearningPlan) -> dict[str, Any]:
    """计划头 ORM → PlanOut 形态 dict（model_dump mode="json"——HTTP 与
    Agent 工具共用同一 service 出参，date/datetime 统一 ISO 字符串）。"""
    return PlanOut.model_validate(plan).model_dump(mode="json")


def _item_out(item: LearningPlanItem) -> dict[str, Any]:
    """条目 ORM → PlanItemOut 形态 dict（JSON 序列化安全）。"""
    return PlanItemOut.model_validate(item).model_dump(mode="json")


def apply_task_completion(
    db: Session, item_dicts: list[dict[str, Any]]
) -> None:
    """就地合并条目完成态：关联任务 done/review → 条目出参 status=done。

    初版计划条目自身 status 无写入入口（用户勾选交互属后续阶段），
    完成事实只记在关联任务上；这里按当前页条目 id 批量查一次任务
    状态（禁止 N+1），只把 planned 升级为 done——

    - 不降级：条目自身已 done/skipped 的保持原值（历史事实不可篡改）；
    - review 计入完成（与任务完成率口径一致，裁定②）。

    Args:
        db: 数据库会话。
        item_dicts: 已序列化的条目 dict 列表（含 task_id / status），原地修改。
    """
    task_ids = [
        int(d["task_id"])
        for d in item_dicts
        if d.get("task_id") is not None
    ]
    if not task_ids:
        return
    finished = set(
        db.execute(
            select(Task.id).where(
                Task.id.in_(task_ids),
                Task.status.in_([TaskStatus.DONE, TaskStatus.REVIEW]),
            )
        ).scalars()
    )
    if not finished:
        return
    for data in item_dicts:
        if data.get("status") == "planned" and data.get("task_id") in finished:
            data["status"] = "done"


def _items_out(
    db: Session, items: Sequence[LearningPlanItem]
) -> list[dict[str, Any]]:
    """批量组装条目出参（含关联任务完成态合并）。"""
    payload = [_item_out(item) for item in items]
    apply_task_completion(db, payload)
    return payload