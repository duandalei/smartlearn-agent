"""学习目标出入参模型。

读侧 ``GoalOut.goal_type`` 保持宽松 ``str | None``（兼容种子数据中的
历史类型值）；写侧 ``GoalCreate / GoalUpdate`` 用 5 枚举 Literal 严格
收口（非法值 422 / 1001，spec 6.1 规则 2）。
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import GoalStatus

# 目标类型 5 枚举（spec 裁定⑤：可空，但填写时必属枚举）。
GoalTypeStr = Literal["考研", "保研", "就业", "比赛", "技能提升"]


class GoalCreate(BaseModel):
    """新建目标入参。

    创建即 ``active``、``roadmap=None``（从未拆解），故不含 status /
    roadmap 字段；``extra="forbid"`` 拒绝多余字段（含 roadmap 篡改）。
    """

    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1, max_length=200, description="目标名称")
    goal_type: GoalTypeStr | None = Field(default=None, description="目标类型")
    description: str | None = Field(default=None, description="目标描述")
    start_date: date | None = Field(default=None, description="开始日期")
    end_date: date | None = Field(default=None, description="截止日期")


class GoalUpdate(BaseModel):
    """编辑目标入参（字段级部分更新）。

    仅提交要修改的字段；``extra="forbid"`` 拒绝 roadmap /
    roadmap_updated_at / user_id 等未声明字段。
    """

    model_config = ConfigDict(extra="forbid")

    title: str | None = Field(
        default=None, min_length=1, max_length=200, description="目标名称"
    )
    goal_type: GoalTypeStr | None = Field(default=None, description="目标类型")
    description: str | None = Field(default=None, description="目标描述")
    start_date: date | None = Field(default=None, description="开始日期")
    end_date: date | None = Field(default=None, description="截止日期")
    status: GoalStatus | None = Field(default=None, description="目标状态")


class RoadmapNode(BaseModel):
    """知识树节点（递归结构，用于 LLM 输出校验与出参序列化）。

    仅认可 name / children 两个字段，LLM 夹带的多余字段（如
    description / level）一律忽略（spec 6.2 规则 4）。``children``
    为空数组的节点即叶子节点——叶子将在拆解落库时写入
    ``knowledge_mastery``（初始 0 分、source=goal_breakdown）。
    ``name`` 上限 200 与 ``knowledge_mastery.knowledge_point`` 的
    VARCHAR(200) 对齐。
    """

    model_config = ConfigDict(extra="ignore")

    name: str = Field(min_length=1, max_length=200, description="节点名称")
    children: list[RoadmapNode] = Field(default=[], description="子节点列表")


class RoadmapOut(BaseModel):
    """知识树出参（breakdown 与 GET /roadmap 共用）。

    ``roadmap`` 为 ``None`` 表示「从未拆解」（JSONType None 语义，
    禁止被替换成 ``{}``，spec 6.1 规则 7）。
    """

    model_config = ConfigDict(from_attributes=True)

    goal_id: int
    roadmap: RoadmapNode | None = None
    roadmap_updated_at: datetime | None = None


class GoalOut(BaseModel):
    """学习目标出参。

    ``roadmap`` 为 ``dict | None``：None 表示「从未拆解」（JSONType
    的 None 语义，禁止被替换成 ``{}``）。
    """

    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    title: str
    goal_type: str | None
    description: str | None
    start_date: date | None
    end_date: date | None
    status: str
    roadmap: dict[str, Any] | None
    roadmap_updated_at: datetime | None
    created_at: datetime
    updated_at: datetime