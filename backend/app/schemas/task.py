"""学习任务出入参模型。

读侧 ``TaskOut``（P2 既有，保持不动）``knowledge_points`` 永为字符串数组
（JSONListType 读出语义，不会出现 null）；写侧 ``TaskCreate / TaskUpdate``
不接收 status / completed_at / source / user_id 四个系统维护字段
（携带即 1001/422，中文提示，spec 5.1.1 规则 1e/2b）。
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

from app.core.normalize import normalize_knowledge_points
from app.models.enums import Priority, TaskStatus

# ---------------------------------------------------------------------------
# 系统维护字段拒绝（创建与编辑共用，spec 裁定⑥⑦）
# ---------------------------------------------------------------------------
_FORBIDDEN_FIELDS: tuple[str, ...] = ("status", "completed_at", "source", "user_id")

_FORBIDDEN_MSG: dict[str, str] = {
    "status": "任务状态请通过状态流转接口修改",
    "completed_at": "完成时间由系统维护，不可手动传入",
    "source": "任务来源由系统维护，不可手动传入",
    "user_id": "任务归属由系统维护，不可手动传入",
}


def _reject_forbidden(data: Any) -> Any:
    """携带系统维护字段时抛中文 ValueError。

    作为 ``model_validator(mode="before")`` 挂载：命中禁止字段抛出的
    ValueError 经全局处理器转 1001/422 且 message 原样透出（spec
    5.1.1 规则 1e/2b）；``extra="forbid"`` 的默认英文提示仅做兜底。

    Args:
        data: 入参原始 dict。

    Returns:
        Any: 原样返回入参。
    """
    if isinstance(data, dict):
        for field in _FORBIDDEN_FIELDS:
            if field in data:
                raise ValueError(_FORBIDDEN_MSG[field])
    return data


def _normalize_knowledge_points(v: list[str] | None) -> list[str] | None:
    """知识点标签规范化（委托 ``app.core.normalize`` 数组管线）。

    strip → 空白判错 → 按 strip 后值去重保序 → 长度校验（strip 后
    1~100），返回值即唯一落库来源。原实现与 record.py 为复制粘贴的
    同构缺陷（校验 strip 值却返回原值数组），本修复收敛到公共模块
    单点实现。

    Args:
        v: 知识点数组（None 表示未提交，原样放行交由部分更新语义处理）。

    Returns:
        list[str] | None: 清洗去重后的数组。

    Raises:
        ValueError: 元素为纯空白 / 超长时抛出。
    """
    return normalize_knowledge_points(v)


class TaskOut(BaseModel):
    """学习任务出参。

    ``knowledge_points`` 永为字符串数组（JSONListType 读出语义，
    不会出现 null）。
    """

    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    goal_id: int | None
    course_id: int | None
    title: str
    description: str | None
    knowledge_points: list[str]
    priority: str
    estimated_minutes: int | None
    actual_minutes: int | None
    deadline: datetime | None
    scheduled_date: date | None
    status: str
    source: str
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None


class TaskCreate(BaseModel):
    """新建任务入参（status 固定 todo、source 固定 manual，均不接收）。

    不含 scheduled_date——该字段仅编辑可维护（Agent 生成计划时写入，
    spec 裁定⑲）；deadline 允许早于当前时间（补录场景，不拦截，裁定⑳）。
    """

    model_config = ConfigDict(extra="forbid")
    _forbid: Any = model_validator(mode="before")(_reject_forbidden)

    title: str = Field(min_length=1, max_length=200, description="任务名称")
    description: str | None = Field(default=None, description="任务描述")
    goal_id: int | None = Field(
        default=None, ge=1, description="关联学习目标（须属本人）"
    )
    course_id: int | None = Field(
        default=None, ge=1, description="关联课程（须属本人）"
    )
    knowledge_points: list[str] = Field(
        default=[], max_length=20, description="知识点标签（最多 20 个）"
    )
    priority: Priority = Field(default=Priority.MEDIUM, description="优先级")
    estimated_minutes: int | None = Field(
        default=None, ge=1, description="预计耗时（分钟）"
    )
    deadline: datetime | None = Field(default=None, description="截止时间")

    _kps = field_validator("knowledge_points")(_normalize_knowledge_points)


class TaskUpdate(BaseModel):
    """编辑任务入参（字段级部分更新，status 等四禁止字段不可触碰）。

    在 TaskCreate 可编辑字段之上额外含 actual_minutes（本阶段手动维护，
    裁定⑰）与 scheduled_date（Agent 预留，裁定⑲）。
    """

    model_config = ConfigDict(extra="forbid")
    _forbid: Any = model_validator(mode="before")(_reject_forbidden)

    title: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = None
    goal_id: int | None = Field(default=None, ge=1)
    course_id: int | None = Field(default=None, ge=1)
    knowledge_points: list[str] | None = Field(default=None, max_length=20)
    priority: Priority | None = None
    estimated_minutes: int | None = Field(default=None, ge=1)
    actual_minutes: int | None = Field(
        default=None, ge=0, description="实际耗时（分钟）"
    )
    deadline: datetime | None = None
    scheduled_date: date | None = Field(
        default=None, description="计划执行日期"
    )

    _kps = field_validator("knowledge_points")(_normalize_knowledge_points)


class TaskStatusUpdate(BaseModel):
    """状态流转入参（PATCH /tasks/{id}/status，唯一合法的状态修改通道）。

    非法枚举值由 TaskStatus 枚举自动 422/1001（spec 5.3.1 规则 2f）；
    合法性校验（状态机判定）在 service 层单点完成。
    """

    model_config = ConfigDict(extra="forbid")

    status: TaskStatus


class TaskStatsOut(BaseModel):
    """统计出参（一次请求返回全部口径，spec 5.5.1 规则 1）。"""

    total: int
    status_counts: dict[str, int]
    overdue_count: int
    weekly_completion_rate: float
    today_todo_count: int


class TaskBoardOut(BaseModel):
    """看板出参（固定四键，列序 = 状态机流转序，裁定⑫）。"""

    todo: list[TaskOut]
    in_progress: list[TaskOut]
    done: list[TaskOut]
    review: list[TaskOut]