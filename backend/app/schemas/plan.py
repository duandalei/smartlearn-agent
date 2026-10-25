"""学习计划出参模型（PlanOut / PlanItemOut）+ P12 动态计划出入参追加区。

追加区模型（design 2.3.2-A）：``PlanGenerateIn`` / ``PlanAdjustIn`` /
``UnplacedTaskOut`` / ``PlanGenerateOut`` / ``DiffEntryMoved`` /
``DiffEntryAdded`` / ``DiffEntryRemoved`` / ``PlanDiffOut`` /
``PlanAdjustOut``。

单一输出 schema 红线（design 2.3.1-1）：``generated_by="llm"`` 与
``"rules"`` 两条生成路径共用 ``PlanGenerateOut``——降级路径与正常
路径产出完全同构的结构，差异仅 ``generated_by`` 一个标记字段
（结构性保证，非纪律约定）。
"""

from __future__ import annotations

from datetime import date, datetime, time
from typing import Literal

from pydantic import BaseModel, ConfigDict


class PlanOut(BaseModel):
    """学习计划版本出参。"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    goal_id: int | None
    title: str
    version: int
    status: str
    parent_plan_id: int | None
    source: str
    adjust_reason: str | None
    start_date: date
    end_date: date
    created_at: datetime


class PlanItemOut(BaseModel):
    """学习计划条目出参。"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    plan_id: int
    plan_date: date
    start_time: time | None
    end_time: time | None
    topic: str
    task_id: int | None
    estimated_minutes: int | None
    priority: str | None
    status: str
    created_at: datetime

# ---------------------------------------------------------------------------
# P12 追加区：动态学习计划出入参（design 2.3.2-A）
# ---------------------------------------------------------------------------


class PlanGenerateIn(BaseModel):
    """POST /plans/generate 请求体。

    ``target`` 缺省为 ``next_week``（保持原「生成下一个完整自然周」语义）；
    ``current_week`` 生成本周剩余时间（周期仍为本周一~本周日，只排今天
    及以后）。``user_id`` 仍不可注入。
    """

    model_config = ConfigDict(extra="forbid")

    target: Literal["next_week", "current_week"] = "next_week"


class PlanAdjustIn(BaseModel):
    """POST /plans/{id}/adjust 请求体（零字段，防 user_id 注入）。"""

    model_config = ConfigDict(extra="forbid")


class UnplacedTaskOut(BaseModel):
    """容量不足未排入计划的候选任务（任务仍落 tasks 表可见）。"""

    task_id: int | None
    title: str
    reason: str


class PlanGenerateOut(BaseModel):
    """计划生成统一出参（LLM 路径与纯规则降级路径共用，单一输出 schema）。

    Attributes:
        plan: 新建的计划版本对象。
        items: 计划条目（含周五休息条目）。
        unplaced_tasks: 容量不足未排入的候选（任务已建、scheduled_date=null）。
        generated_by: 候选来源标记——llm（规划 LLM）或 rules（降级纯规则）。
    """

    plan: PlanOut
    items: list[PlanItemOut]
    unplaced_tasks: list[UnplacedTaskOut]
    generated_by: Literal["llm", "rules"]


class DiffEntryMoved(BaseModel):
    """diff 被移动条目（from → to 五要素）。"""

    topic: str
    task_id: int | None
    from_date: date
    from_time: time | None
    to_date: date
    to_time: time | None
    reason: str


class DiffEntryAdded(BaseModel):
    """diff 新增条目（调整路径通常为空）。"""

    topic: str
    task_id: int | None
    plan_date: date
    start_time: time | None
    reason: str


class DiffEntryRemoved(BaseModel):
    """diff 被移出条目（任务保留在 tasks 表）。"""

    topic: str
    task_id: int | None
    from_date: date
    reason: str


class PlanDiffOut(BaseModel):
    """版本对比结构化改动清单（moved / added / removed）。"""

    base_plan_id: int | None
    moved: list[DiffEntryMoved]
    added: list[DiffEntryAdded]
    removed: list[DiffEntryRemoved]


class PlanAdjustOut(BaseModel):
    """计划调整统一出参。

    Attributes:
        plan: 新版本计划对象（无可调整项时为调整目标原计划）。
        adjust_reason: 具体中文调整理由（adjusted=false 时为提示文案）。
        diff: 结构化改动清单（adjusted=false 时为空结构）。
        adjusted: 是否实际生成了新版本。
    """

    plan: PlanOut
    adjust_reason: str | None
    diff: PlanDiffOut
    adjusted: bool