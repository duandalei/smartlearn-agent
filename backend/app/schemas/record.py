"""学习记录出入参模型。

读侧 ``RecordOut``（P2 既有，保持不动）``knowledge_points`` 永为字符串数组
（JSONListType 读出语义，不会出现 null）；写侧 ``RecordCreate / RecordUpdate``
不接收 ``user_id`` 系统维护字段（携带即 1001/422，中文提示，spec 5.1.1）。

部分更新语义（spec 5.5.1 规则 1/6 定稿，与 TaskUpdate 的「传 null 不清空」
不同）：``RecordUpdate`` 采用 ``model_dump(exclude_unset=True)`` —— 提交即
生效（**含显式 null**），未提交保持原值；``mastery_level`` 置 null 表达
「该记录退出掌握度聚合」、``task_id`` 置 null 表达「解除任务关联」。
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

# ---------------------------------------------------------------------------
# 系统维护字段拒绝（创建与编辑共用）
# ---------------------------------------------------------------------------
_FORBIDDEN_FIELDS: tuple[str, ...] = ("user_id",)

_FORBIDDEN_MSG: dict[str, str] = {
    "user_id": "记录归属由系统维护，不可手动传入",
}


def _reject_forbidden(data: Any) -> Any:
    """携带系统维护字段时抛中文 ValueError。

    作为 ``model_validator(mode="before")`` 挂载：命中禁止字段抛出的
    ValueError 经全局处理器转 1001/422 且 message 原样透出；
    ``extra="forbid"`` 的默认英文提示仅做兜底。

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
    1~100），返回值即唯一落库来源。原实现在此用 ``len(item.strip())``
    校验却返回原值数组、按原值判重，导致 ``" Transformer"`` 与
    ``"Transformer"`` 分裂为两个掌握度行（P6 交付后缺陷，本修复收敛
    到公共模块单点实现）。

    Args:
        v: 知识点数组（None 表示未提交，原样放行交由部分更新语义
            处理；空数组 ``[]`` 合法，表达「本次学习不挂知识点」）。

    Returns:
        list[str] | None: 清洗去重后的数组。

    Raises:
        ValueError: 元素为纯空白 / 超长时抛出。
    """
    return normalize_knowledge_points(v)


class RecordOut(BaseModel):
    """学习记录出参。

    ``mastery_level`` 为学生自评（聚合输入），与
    ``knowledge_mastery.mastery_score``（聚合输出）语义不同。
    """

    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    task_id: int | None
    course_id: int | None
    content: str
    duration_minutes: int
    achievement: str | None
    problems: str | None
    knowledge_points: list[str]
    mastery_level: int | None
    study_date: date
    created_at: datetime


class RecordCreate(BaseModel):
    """新建学习记录入参。

    ``study_date`` 允许补记历史日期，但不得晚于北京时间「今天」
    （service 层校验，spec 5.1.1 规则 3）；``mastery_level`` 可空，
    为空表示本次不参与掌握度自评聚合。
    """

    model_config = ConfigDict(extra="forbid")
    _forbid: Any = model_validator(mode="before")(_reject_forbidden)

    content: str = Field(min_length=1, max_length=500, description="学习内容")
    duration_minutes: int = Field(
        ge=1, le=1440, description="学习时长（分钟），1~1440"
    )
    study_date: date = Field(description="学习日期（可补记，不得晚于今天）")
    mastery_level: int | None = Field(
        default=None, ge=0, le=100, description="自评掌握程度 0-100（可空）"
    )
    knowledge_points: list[str] = Field(
        default=[], max_length=20, description="知识点标签（最多 20 个）"
    )
    task_id: int | None = Field(
        default=None, ge=1, description="关联学习任务（须属本人）"
    )
    course_id: int | None = Field(
        default=None, ge=1, description="关联课程（须属本人）"
    )
    achievement: str | None = Field(
        default=None, max_length=2000, description="学习成果"
    )
    problems: str | None = Field(
        default=None, max_length=2000, description="遇到的问题"
    )

    _kps = field_validator("knowledge_points")(_normalize_knowledge_points)


class RecordUpdate(BaseModel):
    """编辑学习记录入参（字段级部分更新，提交即生效含显式 null）。

    仅提交要修改的字段：未提交保持原值；显式提交 null 按字段语义
    处理——``mastery_level`` / ``task_id`` / ``course_id`` /
    ``achievement`` / ``problems`` / ``knowledge_points`` 可清空，
    ``content`` / ``duration_minutes`` / ``study_date`` 为必填字段
    （已提交且为 null 时 service 层 422 拒绝）。
    """

    model_config = ConfigDict(extra="forbid")
    _forbid: Any = model_validator(mode="before")(_reject_forbidden)

    content: str | None = Field(default=None, min_length=1, max_length=500)
    duration_minutes: int | None = Field(default=None, ge=1, le=1440)
    study_date: date | None = None
    mastery_level: int | None = Field(default=None, ge=0, le=100)
    knowledge_points: list[str] | None = Field(default=None, max_length=20)
    task_id: int | None = Field(default=None, ge=1)
    course_id: int | None = Field(default=None, ge=1)
    achievement: str | None = Field(default=None, max_length=2000)
    problems: str | None = Field(default=None, max_length=2000)

    _kps = field_validator("knowledge_points")(_normalize_knowledge_points)


class TimelineItemOut(BaseModel):
    """时间线单日出参（无记录的天补 0，验收③）。"""

    date: date
    minutes: int


class TimelineOut(BaseModel):
    """学习时间线出参（恰 ``days`` 条、date 升序）。"""

    days: int
    start_date: date
    end_date: date
    items: list[TimelineItemOut]


class RecordStatsOut(BaseModel):
    """学习统计出参（三值全部后端计算，前端零本地计算）。"""

    weekly_minutes: int
    streak_days: int
    total_count: int