"""确定性排程引擎（纯函数，P12 生成路径核心，design 2.4.1）。

职责边界（design 2.1.3-A，答辩口径「LLM 决定学什么，引擎决定何时学」）：
- 规划 LLM 负责：选哪些知识点学、每个学多久、优先级；
- 本引擎负责：排在周几几点、每日不超 ``daily_study_minutes``、
  时段不冲突、周五休息——四条硬约束的**构造性保证**（游标单调
  前进 ⇒ 无冲突；逐日容量计数 ⇒ 不超限），不是「校验后修复」
  而是「结构上不可能违反」。

零依赖铁律（分层契约 §4）：纯函数模块，不 import services /
models / agent（对齐 analytics/statistics.py 先例）——可直接
构造 dataclass 单测，不依赖 LLM 与 DB。

LLM 候选与纯规则候选同构（design 决策 A8）：两条生成路径产出
同型 ``ScheduleCandidate`` 列表、共用同一引擎——降级路径是
「换候选源」不是「换管线」，差异仅 ``generated_by`` 标记字段。

常量全部仅测试可 monkeypatch（O8 铁律：函数体内以模块常量名
直接引用，禁默认参数捕获）。

回链：design 2.4.1；SPEC 规则 5.1.1-6；OP2（三窗口锚点定稿）。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from typing import Any

# ---------------------------------------------------------------------------
# 模块常量（值与依据注释必写，仅测试可 monkeypatch——design 2.4.1 常量表）
# ---------------------------------------------------------------------------

#: 休息日固定周五（ISO weekday=4；SPEC O3 裁定：固定周五休息、无特例）。
REST_WEEKDAY: int = 4

#: 时段锚点（OP2 用户裁定定稿 2026-10-23）：上午 / 下午 / 晚上三窗口。
#: 支撑「周六下午」等真实时段语义（需求文档第 13 章示例
#: 「周六 14:00 - 17:00 机器学习项目」——固定晚间单窗口表达不了「下午」）。
DAY_SLOT_ANCHORS: list[time] = [time(9, 0), time(14, 0), time(19, 0)]

#: 各窗口上界（每窗 300 分钟，合计 840 ≥ 档案上限 600——任何合法容量有解）。
DAY_SLOT_LIMITS: list[time] = [time(14, 0), time(19, 0), time(23, 0)]

#: 单条目时长上限（单窗口可容纳上限；超出者直接进 unplaced）。
CANDIDATE_MAX_MINUTES: int = 240

#: 单条目时长下限（低于 15 分钟的学习块无意义）。
CANDIDATE_MIN_MINUTES: int = 15

#: 优先级排序权重（high=0 < medium=1 < low=2；字典序陷阱规避——
#: priority 为 VARCHAR，字典序 high < low < medium 是错序，必须经权重映射）。
_PRIORITY_WEIGHT: dict[str, int] = {"high": 0, "medium": 1, "low": 2}


# ---------------------------------------------------------------------------
# 引擎数据契约对象（design 2.3.2-B，不进 schemas/）
# ---------------------------------------------------------------------------


@dataclass
class ScheduleCandidate:
    """排程候选条目（引擎输入；LLM 候选与纯规则候选同构，决策 A8）。

    Attributes:
        topic: 本次学什么（1-200 字符）。
        knowledge_points: 涉及知识点。
        estimated_minutes: 预计时长（分钟）。
        priority: low / medium / high。
        related_task_id: 关联既有任务 id（None 表示新学项，落库时新建任务）。
        deadline: 关联任务截止时间（逾期/临期排序依据；None 无截止）。
    """

    topic: str
    knowledge_points: list[str] = field(default_factory=list)
    estimated_minutes: int = 45
    priority: str = "medium"
    related_task_id: int | None = None
    deadline: datetime | None = None


@dataclass
class ScheduleInput:
    """排程引擎输入（design 2.1.3-A 契约二）。

    Attributes:
        candidates: 候选列表（LLM 候选或纯规则候选，同构）。
        daily_capacity_minutes: 每日可学习容量（档案值，缺省 60）。
        week_days: 目标周 7 天日期（服务端推导，LLM 无参与）。
        rest_weekday: 休息日 ISO weekday（默认周五）。
        now: 当前时刻（deadline 距今计算用；仅透传给排序口径）。
    """

    candidates: list[ScheduleCandidate]
    daily_capacity_minutes: int = 60
    week_days: list[date] = field(default_factory=list)
    rest_weekday: int = REST_WEEKDAY
    now: datetime | None = None


@dataclass
class ScheduledItem:
    """已排条目（design 2.1.3-A 契约三：日期时间 100% 引擎推导）。

    Attributes:
        plan_date: 安排日期。
        start_time / end_time: 起止时刻（end = start + estimated，恒等）。
        topic: 学习主题。
        knowledge_points: 涉及知识点。
        estimated_minutes: 预计时长。
        priority: 优先级。
        related_task_id: 关联任务 id（引擎透传；落库阶段决定复用或新建）。
    """

    plan_date: date
    start_time: time
    end_time: time
    topic: str
    knowledge_points: list[str] = field(default_factory=list)
    estimated_minutes: int = 45
    priority: str = "medium"
    related_task_id: int | None = None


@dataclass
class UnplacedTask:
    """容量不足未排入计划的候选（任务仍建、任务页可见）。"""

    topic: str
    related_task_id: int | None
    reason: str
    estimated_minutes: int | None = None
    priority: str | None = None


@dataclass
class ScheduleOutput:
    """引擎输出：已排条目 + 未排候选清单。"""

    placed: list[ScheduledItem] = field(default_factory=list)
    unplaced: list[UnplacedTask] = field(default_factory=list)


# ---------------------------------------------------------------------------
# 时间辅助（纯函数，三窗口游标逻辑单一来源——决策 A12）
# ---------------------------------------------------------------------------


def _to_minutes(value: time) -> int:
    """时刻转当日分钟数。"""
    return value.hour * 60 + value.minute


def _from_minutes(minutes: int) -> time:
    """当日分钟数转时刻（分钟粒度）。"""
    return time(minutes // 60, minutes % 60)


def _day_windows(day: date) -> list[tuple[time, time]]:
    """按星期返回当日窗口遍历顺序（首选锚点裁定，用户 2026-10-24）。

    需求文档第 13 章作息语义：工作日晚上学、周末下午学。原实现
    三窗口固定 09:00 → 14:00 → 19:00 顺序，容量 ≤ 300 分钟时永远
    用不到后两窗口（七天全 09:00，周视图一片早九点，三窗口形同
    虚设）。裁定：

    - 周六 → 首选下午 14:00，次选上午 09:00，最后晚上 19:00；
    - 周一~周四与周日 → 首选晚上 19:00，次选下午 14:00，最后上午
      09:00；
    - 周五休息（调用方跳过，不入此处）。

    窗口边界（anchor, limit）不变；仅遍历顺序按星期区分，窗口内
    连续排布、放不下移下一锚点的推进逻辑不变。

    Args:
        day: 目标日期。

    Returns:
        list[tuple[time, time]]: 当日 (anchor, limit) 窗口遍历顺序。
    """
    pairs = list(zip(DAY_SLOT_ANCHORS, DAY_SLOT_LIMITS))
    if day.weekday() == 5:  # 周六：下午优先
        order = [1, 0, 2]
    else:  # 周一~周四与周日：晚上优先
        order = [2, 1, 0]
    return [pairs[i] for i in order]


def _day_free_start(
    occupied: list[tuple[time, time]],
    estimated_minutes: int,
    windows: list[tuple[time, time]] | None = None,
) -> time | None:
    """在当日三窗口内找可容纳 ``estimated_minutes`` 的最早起始时刻。

    空洞扫描（对生成连排与调整重排均正确）：对每个窗口
    ``[anchor, limit]``，游标从锚点起推进——游标与下一占用区间
    之间的空隙足够则用之，否则游标推进到该占用结束；窗口尾部
    空隙足够同样可用。结构性保证：起始时刻与已占区间不重叠。

    Args:
        occupied: 该日已占区间列表（start, end）。
        estimated_minutes: 需要容纳的分钟数。
        windows: 当日窗口遍历顺序（``_day_windows(day)`` 产物，
            首选锚点按星期区分）；None 时回退固定锚点序。

    Returns:
        time | None: 最早可用起始时刻；三窗口全满返回 None。
    """
    if windows is None:
        windows = list(zip(DAY_SLOT_ANCHORS, DAY_SLOT_LIMITS))
    intervals = sorted(
        (_to_minutes(start), _to_minutes(end)) for start, end in occupied
    )
    for anchor, limit in windows:
        anchor_m = _to_minutes(anchor)
        limit_m = _to_minutes(limit)
        cursor = anchor_m
        for seg_start, seg_end in intervals:
            if seg_end <= cursor:
                continue
            if seg_start >= limit_m:
                break
            if seg_start - cursor >= estimated_minutes:
                return _from_minutes(cursor)
            cursor = max(cursor, seg_end)
        if limit_m - cursor >= estimated_minutes:
            return _from_minutes(cursor)
    return None


def find_free_slot(
    week_days: list[date],
    start_from: date,
    occupied: dict[date, list[tuple[time, time]]],
    used_minutes: dict[date, int],
    daily_capacity: int,
    estimated_minutes: int,
) -> tuple[date, time] | None:
    """跨日递进查找最早可用 (日期, 起始时刻)（决策 A12 公开辅助）。

    供调整引擎（adjuster）重排复用——两引擎共享同一时段常量与
    游标逻辑，防 ``DAY_SLOT_ANCHORS`` 口径漂移。

    Args:
        week_days: 周期日期列表（升序）。
        start_from: 查找起始日（含当日）。
        occupied: 各日已占区间映射。
        used_minutes: 各日已用容量映射。
        daily_capacity: 每日容量上限。
        estimated_minutes: 需要容纳的分钟数。

    Returns:
        tuple[date, time] | None: 最早可用 (日期, 起始时刻)；
        全周期无可容位置返回 None。
    """
    for day in week_days:
        if day < start_from:
            continue
        if day.weekday() == REST_WEEKDAY:
            continue
        if used_minutes.get(day, 0) + estimated_minutes > daily_capacity:
            continue
        start = _day_free_start(
            occupied.get(day, []), estimated_minutes, _day_windows(day)
        )
        if start is not None:
            return day, start
    return None


# ---------------------------------------------------------------------------
# 公开接口（design 2.4.1）
# ---------------------------------------------------------------------------


def next_week_window(today: date) -> tuple[date, date]:
    """北京今天 → (下一个完整自然周的周一, 周日)。

    ``days_ahead = 7 - today.weekday()``（周一=0）；当日为周一
    时则恰 +7（「下一个完整自然周」固定语义，SPEC 领域术语）。

    Args:
        today: 基准日期。

    Returns:
        tuple[date, date]: (下周一, 下周日)。
    """
    days_ahead = 7 - today.weekday()
    start = today + timedelta(days=days_ahead)
    return start, start + timedelta(days=6)


def current_week_window(today: date) -> tuple[date, date]:
    """北京今天 → (本周一, 本周日)。

    与 :func:`next_week_window` 的区别：本函数返回**包含今天**的自然周，
    周一当天返回当天而不是 +7；用于「本周剩余计划」兜底生成。

    Args:
        today: 基准日期。

    Returns:
        tuple[date, date]: (本周一, 本周日)。
    """
    start = today - timedelta(days=today.weekday())
    return start, start + timedelta(days=6)


def build_rule_candidates(
    overdue_tasks: list[dict[str, Any]],
    due_soon_tasks: list[dict[str, Any]],
    roadmap_leaves: list[str],
    weak_points: list[dict[str, Any]],
) -> list[ScheduleCandidate]:
    """降级路径的纯规则候选构造（顺序铁律：逾期 → 临期 → roadmap/薄弱点）。

    与 LLM 候选同构（决策 A8「降级是换候选源」）：产出同型
    ``ScheduleCandidate`` 列表，共用同一引擎与同一出参结构。

    Args:
        overdue_tasks: 逾期任务（deadline 升序；每条含 id / title /
            estimated_minutes / priority / knowledge_points / deadline）。
        due_soon_tasks: 临期任务（deadline 升序，同上结构）。
        roadmap_leaves: 目标 roadmap 叶子知识点（深度序）。
        weak_points: 薄弱知识点（掌握度升序，含 knowledge_point）。

    Returns:
        list[ScheduleCandidate]: 纯规则候选（最多 14 条，对齐 LLM
        候选数量契约上限）。
    """
    candidates: list[ScheduleCandidate] = []

    for task in overdue_tasks:
        candidates.append(_task_to_candidate(task))
    for task in due_soon_tasks:
        candidates.append(_task_to_candidate(task))

    seen_topics: set[str] = set()
    for leaf in roadmap_leaves:
        if leaf in seen_topics:
            continue
        seen_topics.add(leaf)
        candidates.append(
            ScheduleCandidate(
                topic=f"{leaf} 专项学习",
                knowledge_points=[leaf],
                estimated_minutes=45,
                priority="medium",
            )
        )
    for point in weak_points:
        name = str(point.get("knowledge_point") or "").strip()
        if not name or name in seen_topics:
            continue
        seen_topics.add(name)
        candidates.append(
            ScheduleCandidate(
                topic=f"{name} 薄弱专项",
                knowledge_points=[name],
                estimated_minutes=45,
                priority="medium",
            )
        )
    return candidates[:14]


def _task_to_candidate(task: dict[str, Any]) -> ScheduleCandidate:
    """任务 dict → 排程候选（携带 related_task_id 与 deadline）。"""
    estimated = task.get("estimated_minutes")
    return ScheduleCandidate(
        topic=str(task.get("title") or "学习任务"),
        knowledge_points=list(task.get("knowledge_points") or []),
        estimated_minutes=int(estimated) if estimated else 60,
        priority=str(task.get("priority") or "medium"),
        related_task_id=task.get("id"),
        deadline=task.get("deadline"),
    )


def build_week_schedule(schedule_input: ScheduleInput) -> ScheduleOutput:
    """候选 → 7 天条目布局 + unplaced（核心纯函数）。

    布局算法（design 2.4.1 六步）：
    1. 候选排序：deadline 非空升序在前（逾期/临期排周期前段）→
       优先级权重（high=0 < medium=1 < low=2）→ 输入顺序稳定；
    2. 逐日贪心装入：日期游标从周一顺序前进，跳过休息日；
    3. 三窗口锚点分配：当前窗口内从游标处连续排布，放不下移下一
       锚点（09:00 → 14:00 → 19:00），三窗口全满该日结束；
    4. 约束构造性：装入前查 ``estimated <= remaining``；游标单调
       前进 ⇒ (plan_date, start_time) 结构性无重复；end = start +
       estimated 恒等；
    5. unplaced 截断：装不下的候选进 unplaced（中文原因），不因
       容量不足失败；
    6. 休息条目不在引擎内生成（plan_svc 在引擎输出后注入周五
       「休息 / 复习」条目）。

    Args:
        schedule_input: 排程输入（候选 + 容量 + 周期 + 休息日）。

    Returns:
        ScheduleOutput: 已排条目与未排候选。
    """
    ordered = _order_candidates(schedule_input.candidates)
    week_days = [d for d in schedule_input.week_days]
    occupied: dict[date, list[tuple[time, time]]] = {d: [] for d in week_days}
    used: dict[date, int] = {d: 0 for d in week_days}

    placed: list[ScheduledItem] = []
    unplaced: list[UnplacedTask] = []

    for candidate in ordered:
        minutes = candidate.estimated_minutes
        if minutes > CANDIDATE_MAX_MINUTES:
            unplaced.append(
                UnplacedTask(
                    topic=candidate.topic,
                    related_task_id=candidate.related_task_id,
                    reason="单条目时长超出可排时段窗口",
                    estimated_minutes=minutes,
                    priority=candidate.priority,
                )
            )
            continue
        if minutes < CANDIDATE_MIN_MINUTES:
            unplaced.append(
                UnplacedTask(
                    topic=candidate.topic,
                    related_task_id=candidate.related_task_id,
                    reason="单条目时长低于最小学习块（15 分钟）",
                    estimated_minutes=minutes,
                    priority=candidate.priority,
                )
            )
            continue

        slot: tuple[date, time] | None = None
        for day in week_days:
            if day.weekday() == schedule_input.rest_weekday:
                continue
            if used[day] + minutes > schedule_input.daily_capacity_minutes:
                continue
            start = _day_free_start(occupied[day], minutes, _day_windows(day))
            if start is not None:
                slot = (day, start)
                break
        if slot is None:
            unplaced.append(
                UnplacedTask(
                    topic=candidate.topic,
                    related_task_id=candidate.related_task_id,
                    reason="本周学习容量不足，按优先级截断",
                    estimated_minutes=minutes,
                    priority=candidate.priority,
                )
            )
            continue

        day, start = slot
        end = _from_minutes(_to_minutes(start) + minutes)
        occupied[day].append((start, end))
        used[day] += minutes
        placed.append(
            ScheduledItem(
                plan_date=day,
                start_time=start,
                end_time=end,
                topic=candidate.topic,
                knowledge_points=list(candidate.knowledge_points),
                estimated_minutes=minutes,
                priority=candidate.priority,
                related_task_id=candidate.related_task_id,
            )
        )

    return ScheduleOutput(placed=placed, unplaced=unplaced)


def _order_candidates(
    candidates: list[ScheduleCandidate],
) -> list[ScheduleCandidate]:
    """候选排序：deadline 升序在前 → 优先级权重 → 输入顺序稳定。

    deadline 非空者在前（逾期/临期优先排在周期前段，SPEC 规则
    5.1.1-6 ③）；同组按 priority 权重；同级按输入顺序（稳定排序，
    enumerate 序号 tie-break）。
    """

    def sort_key(pair: tuple[int, ScheduleCandidate]) -> tuple[Any, ...]:
        index, candidate = pair
        if candidate.deadline is not None:
            deadline_key: tuple[Any, ...] = (0, candidate.deadline)
        else:
            deadline_key = (1, None)
        return (
            deadline_key,
            _PRIORITY_WEIGHT.get(candidate.priority, 1),
            index,
        )

    return [
        candidate
        for _, candidate in sorted(
            enumerate(candidates), key=sort_key
        )
    ]