"""确定性调整引擎（纯函数 + reason 模板，P12 调整路径核心，design 2.4.2）。

纯确定性铁律（SPEC 规则 5.2.1-8）：不调 LLM、不碰 DB（数据由
services/plan.py 读库后传入）——调整结果完全由输入决定，
LLM 不可用环境下全量可测（D10）。

diff 幂等重算（design 2.4.2-B / D4）：``compute_diff`` 是唯一 diff
计算函数——``apply_adjustment`` 调整随返与 ``GET /plans/{id}/diff``
端点重算共用同一实现，结构一致性是「同函数」的构造性结果。

reason 模板红线（用户指令 ③）：``render_adjust_reason`` 只引用
``ReasonMaterial`` 真实字段（全部来自新旧两版条目计算）——编造
结构性不可能；日期时段由纯函数转换——与库中数据恒一致；分段
拼接依素材有无——无顺延不出现顺延话术；结果恒含具体任务名与
「从 → 到」日期表述（≥20 字符天然满足）。

依赖方向：仅 import ``analytics.scheduler`` 的时段常量与游标辅助
（决策 A12——两引擎共享时段口径单一来源）；零 services / models /
agent 依赖。

回链：design 2.4.2；SPEC 规则 5.2.1；OP1（调整路径同步义务的
数据基础——moved/removed 驱动 scheduled_date 同步）。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from typing import Any

from app.analytics.scheduler import (
    REST_WEEKDAY,
    _day_free_start,
    _day_windows,
    find_free_slot,
)

# ---------------------------------------------------------------------------
# 模块常量（SPEC §4.4-1 锁定，仅测试可 monkeypatch——O8 铁律）
# ---------------------------------------------------------------------------

#: 截止临近阈值（小时，含已逾期——deadline 与 now 差值 ≤ 48h 即命中）。
DEADLINE_URGENT_HOURS: int = 48

#: 近期时长不足比例（近 7 天学习时长 < 容量 × 7 × 0.6 即不足）。
RECENT_MINUTES_RATIO: float = 0.6

#: 近期时长评估窗口（天）。
RECENT_WINDOW_DAYS: int = 7


# ---------------------------------------------------------------------------
# 快照 dataclass（design 2.3.2-B，不进 schemas/）
# ---------------------------------------------------------------------------


@dataclass
class TaskSnapshot:
    """关联任务只读快照（评估依据）。"""

    deadline: datetime | None
    status: str


@dataclass
class ItemSnapshot:
    """旧版条目只读快照（调整输入；亦可由新版条目读出后重算 diff）。"""

    item_id: int | None
    plan_date: date
    start_time: time | None
    end_time: time | None
    topic: str
    task_id: int | None
    estimated_minutes: int | None
    priority: str | None
    status: str


@dataclass
class AdjustContext:
    """调整评估输入快照（全部由 services/plan.py 读库后传入）。"""

    items: list[ItemSnapshot]
    tasks: dict[int, TaskSnapshot]
    recent_minutes: int
    daily_capacity: int
    now: datetime
    week_days: list[date]


@dataclass
class NewItemLayout:
    """调整产出的新版本条目布局（落库素材）。

    Attributes:
        plan_date / start_time / end_time: 新位置（被顺延的牺牲条目
            与移动集条目为新位置；其余原样）。
        topic / task_id / estimated_minutes / priority / status: 承载
            原条目属性（done/skipped 状态保持——裁决 #13）。
        removed: 是否被移出计划（True 时不落新版本条目，任务保留）。
    """

    plan_date: date
    start_time: time | None
    end_time: time | None
    topic: str
    task_id: int | None
    estimated_minutes: int | None
    priority: str | None
    status: str
    removed: bool = False


@dataclass
class ReasonMaterial:
    """adjust_reason 模板变量素材（全部来自新旧两版条目计算）。

    Attributes:
        moved_topics: 被移动条目 topic 列表（模板取首条嵌入）。
        moved_count: 移动集落位数。
        cause_desc: 触发原因中文短语。
        first_from_desc / first_to_desc: 首个移动条目的原/新日期时段中文。
        postponed_count: 被顺延牺牲条目数。
        postponed_day_desc: 首个被顺延条目的原定日中文。
        postponed_to_desc: 首个被顺延条目的新日期中文。
        removed_desc: 被移出条目概括（无则空串）。
    """

    moved_topics: list[str] = field(default_factory=list)
    moved_count: int = 0
    cause_desc: str = ""
    first_from_desc: str = ""
    first_to_desc: str = ""
    postponed_count: int = 0
    postponed_day_desc: str = ""
    postponed_to_desc: str = ""
    removed_desc: str = ""


@dataclass
class AdjustmentResult:
    """调整结果：新条目布局 + diff + 模板素材。"""

    new_items: list[NewItemLayout]
    diff: dict[str, Any]
    reason_material: ReasonMaterial


# ---------------------------------------------------------------------------
# 三条件量化评估（design 2.4.2 公开接口 1）
# ---------------------------------------------------------------------------


def _deadline_urgent(deadline: datetime | None, now: datetime) -> bool:
    """截止临近判定（含已逾期：deadline - now <= 48h，负数同样命中）。"""
    if deadline is None:
        return False
    return (deadline - now) <= timedelta(hours=DEADLINE_URGENT_HOURS)


def _recent_insufficient(recent_minutes: int, daily_capacity: int) -> bool:
    """近期时长不足判定（全局条件——命中则全部未完成条目可移动）。

    注：本条件是**全局阈值**而非逐条目判定（SPEC §4.4-1）；缺省容量
    按每日 60 分钟口径。
    """
    return recent_minutes < daily_capacity * RECENT_WINDOW_DAYS * RECENT_MINUTES_RATIO


def evaluate_move_set(context: AdjustContext) -> list[ItemSnapshot]:
    """三条件量化评估 → 移动集：未完成 ∧ (截止临近 ∨ 时长不足)。

    未完成 = 条目 status 非 done 且（plan_date < 今天 或 关联任务
    status != done）；截止临近 = 关联任务 deadline 距 now ≤ 48h
    （含已逾期）；时长不足 = 近 7 天学习时长 < 容量 × 7 × 0.6
    （全局条件，命中则全部未完成条目可移动）。

    Args:
        context: 调整输入快照。

    Returns:
        list[ItemSnapshot]: 需要移动的条目（保持原 items 顺序）。
    """
    today = context.now.date()
    insufficient = _recent_insufficient(context.recent_minutes, context.daily_capacity)
    move_set: list[ItemSnapshot] = []
    for item in context.items:
        if item.status in ("done", "skipped"):
            continue
        task = context.tasks.get(item.task_id) if item.task_id is not None else None
        unfinished = item.plan_date < today or (
            task is not None and task.status != "done"
        )
        if not unfinished:
            continue
        urgent = _deadline_urgent(task.deadline if task else None, context.now)
        if urgent or insufficient:
            move_set.append(item)
    return move_set


def _cause_desc(context: AdjustContext, move_set: list[ItemSnapshot]) -> str:
    """触发原因中文短语（与 evaluate_move_set 同口径重算）。"""
    has_urgent = any(
        _deadline_urgent(
            context.tasks[item.task_id].deadline
            if item.task_id is not None and item.task_id in context.tasks
            else None,
            context.now,
        )
        for item in move_set
    )
    if has_urgent:
        return "未完成且截止临近"
    if _recent_insufficient(context.recent_minutes, context.daily_capacity):
        return "未完成且近期学习时长不足"
    return "未完成"


# ---------------------------------------------------------------------------
# 纯确定性重排 + diff（design 2.4.2 公开接口 2）
# ---------------------------------------------------------------------------


def _snapshot_key(item: ItemSnapshot) -> tuple[Any, ...]:
    """diff 对齐键：task_id 优先；无任务条目（休息等）按 topic。"""
    if item.task_id is not None:
        return ("t", item.task_id)
    return ("p", item.topic)


def compute_diff(
    old_items: list[ItemSnapshot],
    new_items: list[NewItemLayout],
    movable_task_ids: set[int] | None = None,
) -> dict[str, Any]:
    """两版条目 → 结构化 diff（moved / added / removed）。

    幂等重算唯一实现（D4）：``apply_adjustment`` 调整随返与
    ``GET /plans/{id}/diff`` 端点共用本函数；对齐键 task_id 优先、
    无任务条目按 topic。reason 由「是否属于移动集」推导——端点
    重算时 movable_task_ids 由 evaluate_move_set 以同一 DB 状态
    重算得出，保证逐条一致。

    Args:
        old_items: 旧版（parent）条目快照。
        new_items: 新版条目布局（removed=True 的条目视为缺失）。
        movable_task_ids: 移动集条目的 task_id 集合（区分主动移动
            与牺牲顺延的 reason 文案；None 时全部按主动移动处理）。

    Returns:
        dict[str, Any]: ``{moved: [...], added: [...], removed: [...]}``。
    """
    movable = movable_task_ids if movable_task_ids is not None else set()
    kept_new = [item for item in new_items if not item.removed]
    old_map = {_snapshot_key(item): item for item in old_items}
    new_map: dict[tuple[Any, ...], NewItemLayout] = {}
    for item in kept_new:
        key = ("t", item.task_id) if item.task_id is not None else ("p", item.topic)
        new_map[key] = item

    moved: list[dict[str, Any]] = []
    added: list[dict[str, Any]] = []
    removed: list[dict[str, Any]] = []

    for key, old_item in old_map.items():
        if key not in new_map:
            if old_item.status == "done":
                continue  # done 条目缺失不产生 diff（防御——调整永不移除 done）
            reason = (
                "周期内无可安排的空闲时段，移出计划"
                if (old_item.task_id is not None and old_item.task_id in movable)
                or old_item.task_id is None
                else "容量不足，移出计划"
            )
            removed.append(
                {
                    "topic": old_item.topic,
                    "task_id": old_item.task_id,
                    "from_date": old_item.plan_date.isoformat(),
                    "reason": reason,
                }
            )
            continue
        new_item = new_map[key]
        position_changed = (
            new_item.plan_date != old_item.plan_date
            or new_item.start_time != old_item.start_time
        )
        if position_changed:
            if old_item.task_id is not None and old_item.task_id not in movable:
                reason = "为紧急任务腾出时段顺延"
            else:
                reason = "任务未完成，已调整到空闲时段"
            moved.append(
                {
                    "topic": old_item.topic,
                    "task_id": old_item.task_id,
                    "from_date": old_item.plan_date.isoformat(),
                    "from_time": (
                        old_item.start_time.isoformat()
                        if old_item.start_time is not None
                        else None
                    ),
                    "to_date": new_item.plan_date.isoformat(),
                    "to_time": (
                        new_item.start_time.isoformat()
                        if new_item.start_time is not None
                        else None
                    ),
                    "reason": reason,
                }
            )

    old_keys = set(old_map)
    for key, new_item in new_map.items():
        if key not in old_keys:
            added.append(
                {
                    "topic": new_item.topic,
                    "task_id": new_item.task_id,
                    "plan_date": new_item.plan_date.isoformat(),
                    "start_time": (
                        new_item.start_time.isoformat()
                        if new_item.start_time is not None
                        else None
                    ),
                    "reason": "调整中新增学习安排",
                }
            )

    return {"moved": moved, "added": added, "removed": removed}


def apply_adjustment(
    context: AdjustContext, move_set: list[ItemSnapshot]
) -> AdjustmentResult:
    """移动 / 顺延 / removed 纯确定性重排 + diff 计算（零 LLM）。

    算法五步（design 2.4.2-A）：
    1. 原样迁移：done/skipped 与未进移动集条目锚定不动；
    2. 移动集重排：``plan_date > max(原日期, 今天)`` 的候选日中
       **周末优先**（weekday >= 5 先于工作日），经共享时段游标
       落位（决策 A12）；
    3. 低优先级顺延：目标日容量不足时从该日非 done/skipped 条目按
       low → medium 选牺牲条目（high 不顺延）挪到更晚空闲时段；
    4. removed 兜底：牺牲条目挪无可挪则移出计划；移动集自身
       无法安排同样移出并如实写 reason；
    5. done/skipped 原样保持（裁决 #13 历史事实不可篡改）。

    Args:
        context: 调整输入快照。
        move_set: evaluate_move_set 产出的移动集。

    Returns:
        AdjustmentResult: 新条目布局 + diff + reason 素材。
    """
    today = context.now.date()
    capacity = context.daily_capacity

    move_ids = {id(item) for item in move_set}
    keepers = [item for item in context.items if id(item) not in move_ids]

    occupied: dict[date, list[tuple[time, time]]] = {d: [] for d in context.week_days}
    used: dict[date, int] = {d: 0 for d in context.week_days}
    layouts: dict[int, NewItemLayout] = {}
    for item in keepers:
        layouts[id(item)] = _to_layout(item)
        if item.start_time is not None and item.end_time is not None:
            occupied.setdefault(item.plan_date, []).append(
                (item.start_time, item.end_time)
            )
            used[item.plan_date] = used.get(item.plan_date, 0) + (
                item.estimated_minutes or 0
            )

    postponed: list[tuple[ItemSnapshot, NewItemLayout]] = []
    removed_removed: list[ItemSnapshot] = []

    def _sacrifices_on(day: date) -> list[ItemSnapshot]:
        """该日可牺牲条目（low → medium；high、done/skipped、休息条目不顺延）。"""
        candidates = [
            item
            for item in keepers
            if item.plan_date == day
            and item.task_id is not None
            and item.status not in ("done", "skipped")
            and (item.priority or "medium") in ("low", "medium")
        ]
        return sorted(
            candidates, key=lambda it: 0 if it.priority == "low" else 1
        )

    def _try_free_capacity(day: date, needed: int) -> bool:
        """从 day 的牺牲条目腾出容量：先顺延到更晚，挪不动才移出。"""
        freed = 0
        for sacrifice in _sacrifices_on(day):
            if freed >= needed:
                break
            est = sacrifice.estimated_minutes or 60
            layout = layouts[id(sacrifice)]
            if sacrifice.start_time is not None and sacrifice.end_time is not None:
                occupied[day] = [
                    slot
                    for slot in occupied.get(day, [])
                    if slot != (sacrifice.start_time, sacrifice.end_time)
                ]
                used[day] = max(0, used.get(day, 0) - est)
            slot = find_free_slot(
                context.week_days,
                day + timedelta(days=1),
                occupied,
                used,
                capacity,
                est,
            )
            if slot is not None:
                target_day, target_start = slot
                target_end = _add_minutes(target_start, est)
                layout.plan_date = target_day
                layout.start_time = target_start
                layout.end_time = target_end
                occupied.setdefault(target_day, []).append((target_start, target_end))
                used[target_day] = used.get(target_day, 0) + est
                postponed.append((sacrifice, layout))
            else:
                layout.removed = True
                removed_removed.append(sacrifice)
            freed += est
        return freed >= needed

    placed_moves: list[tuple[ItemSnapshot, NewItemLayout]] = []
    unplaced_moves: list[ItemSnapshot] = []

    for item in move_set:
        est = item.estimated_minutes or 60
        start_from = max(item.plan_date, today)
        candidate_days = sorted(
            (
                day
                for day in context.week_days
                if day > start_from and day.weekday() != REST_WEEKDAY
            ),
            key=lambda day: (0 if day.weekday() >= 5 else 1, day),
        )
        placed = False
        for day in candidate_days:
            start = _day_free_start(
                occupied.get(day, []), est, _day_windows(day)
            )
            if start is None:
                continue
            if used.get(day, 0) + est > capacity and not _try_free_capacity(
                day, est
            ):
                continue
            # 顺延可能已改变该日窗口占用，重查起始时刻
            start = _day_free_start(
                occupied.get(day, []), est, _day_windows(day)
            )
            if start is None:
                continue
            layout = NewItemLayout(
                plan_date=day,
                start_time=start,
                end_time=_add_minutes(start, est),
                topic=item.topic,
                task_id=item.task_id,
                estimated_minutes=est,
                priority=item.priority,
                status=item.status,
            )
            occupied.setdefault(day, []).append((layout.start_time, layout.end_time))
            used[day] = used.get(day, 0) + est
            placed_moves.append((item, layout))
            placed = True
            break
        if not placed:
            unplaced_moves.append(item)

    final_layouts = [layout for layout in layouts.values() if not layout.removed]
    final_layouts.extend(layout for _, layout in placed_moves)
    final_layouts.sort(key=lambda l: (l.plan_date, l.start_time or time(0, 0)))

    movable_task_ids = {
        item.task_id for item in move_set if item.task_id is not None
    }
    diff = compute_diff(context.items, final_layouts, movable_task_ids)

    removed_all = removed_removed + unplaced_moves
    material = _build_reason_material(
        context, move_set, placed_moves, postponed, removed_all
    )
    return AdjustmentResult(
        new_items=final_layouts, diff=diff, reason_material=material
    )


def _to_layout(item: ItemSnapshot) -> NewItemLayout:
    """旧条目快照 → 新布局（原样迁移）。"""
    return NewItemLayout(
        plan_date=item.plan_date,
        start_time=item.start_time,
        end_time=item.end_time,
        topic=item.topic,
        task_id=item.task_id,
        estimated_minutes=item.estimated_minutes,
        priority=item.priority,
        status=item.status,
    )


def _add_minutes(start: time, minutes: int) -> time:
    """时刻 + 分钟数（分钟粒度，供条目 end_time 推导）。"""
    total = start.hour * 60 + start.minute + minutes
    return time(total // 60, total % 60)


def _build_reason_material(
    context: AdjustContext,
    move_set: list[ItemSnapshot],
    placed_moves: list[tuple[ItemSnapshot, NewItemLayout]],
    postponed: list[tuple[ItemSnapshot, NewItemLayout]],
    removed_items: list[ItemSnapshot],
) -> ReasonMaterial:
    """从新旧两版条目计算 reason 模板素材（质量红线：只引用真实字段）。"""
    material = ReasonMaterial()
    material.moved_topics = [item.topic for item, _ in placed_moves]
    material.moved_count = len(placed_moves)
    material.cause_desc = _cause_desc(context, move_set)
    if placed_moves:
        first_old, first_new = placed_moves[0]
        material.first_from_desc = _position_cn(first_old.plan_date, first_old.start_time)
        material.first_to_desc = _position_cn(first_new.plan_date, first_new.start_time)
    material.postponed_count = len(postponed)
    if postponed:
        first_old, first_new = postponed[0]
        material.postponed_day_desc = _weekday_cn(first_old.plan_date)
        material.postponed_to_desc = _weekday_cn(first_new.plan_date)
    if removed_items:
        topics = [item.topic for item in removed_items]
        if len(topics) > 2:
            material.removed_desc = "、".join(topics[:2]) + f" 等 {len(topics)} 个"
        else:
            material.removed_desc = "、".join(topics)
    return material


# ---------------------------------------------------------------------------
# reason 模板渲染（design 2.4.2-C，用户指令 ③——禁止空话模板）
# ---------------------------------------------------------------------------


def _weekday_cn(day: date) -> str:
    """日期 → 「周三（10-28）」中文表述。"""
    names = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
    return f"{names[day.weekday()]}（{day.month:02d}-{day.day:02d}）"


def _slot_cn(value: time | None) -> str:
    """时刻 → 上午 / 下午 / 晚上（None 返回空串——休息条目无时段）。"""
    if value is None:
        return ""
    if value < time(12, 0):
        return "上午"
    if value < time(18, 0):
        return "下午"
    return "晚上"


def _position_cn(day: date, value: time | None) -> str:
    """日期 + 时段 → 「周三（10-28）晚上」中文表述。"""
    return f"{_weekday_cn(day)}{_slot_cn(value)}"


def render_adjust_reason(material: ReasonMaterial) -> str:
    """adjust_reason 模板渲染（含具体时间与任务名，≥20 字符红线）。

    分段拼接（非单一 format）——段 2/2'/3/4 依素材有无拼接：
    无顺延不出现顺延话术；无移出不出现移出话术。三场景锚定样例
    （design 2.4.2-C）：
    1. 单任务移动：检测到你本周的 Transformer 注意力机制学习任务
       未完成且截止临近，已从周三（10-28）晚上调整到周六（10-31）下午。
    2. 多任务移动：检测到你本周有 2 个学习任务未完成且近期学习时长
       不足，已分别调整到后续空闲时段（周三（10-28）晚上 →
       周六（10-31）下午 等 2 处）。
    3. 任务被顺延：…，并顺延了原定周六（10-31）的 2 个低优先级
       任务到周日（11-01）。

    Args:
        material: 模板变量素材（来自新旧两版条目计算）。

    Returns:
        str: 具体中文调整理由（恒含任务名与「从 → 到」日期表述）。
    """
    if material.moved_count <= 1:
        topic = material.moved_topics[0] if material.moved_topics else "学习"
        segment1 = f"检测到你本周的{topic}学习任务{material.cause_desc}，"
        segment2_body = (
            f"已从{material.first_from_desc}调整到{material.first_to_desc}"
        )
    else:
        segment1 = (
            f"检测到你本周有 {material.moved_count} 个学习任务"
            f"{material.cause_desc}，"
        )
        segment2_body = (
            f"已分别调整到后续空闲时段（{material.first_from_desc} → "
            f"{material.first_to_desc} 等 {material.moved_count} 处）"
        )
    has_postponed = material.postponed_count > 0 and material.postponed_to_desc
    segment3 = (
        f"并顺延了原定{material.postponed_day_desc}的"
        f"{material.postponed_count}个低优先级任务到"
        f"{material.postponed_to_desc}"
        if has_postponed
        else ""
    )
    segment4 = (
        f"因本周容量不足，{material.removed_desc}任务已移出计划，"
        f"可在任务页单独安排。"
        if material.removed_desc
        else ""
    )
    parts = [segment1]
    if segment3:
        parts.append(f"{segment2_body}，{segment3}。")
    else:
        parts.append(f"{segment2_body}。")
    if segment4:
        parts.append(segment4)
    return "".join(parts)