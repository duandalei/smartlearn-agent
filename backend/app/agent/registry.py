"""AI Agent 工具注册表（P10）：TOOLS_SCHEMA 与 TOOL_MAP 的单一事实来源。

本阶段注册 8 个工具（名称与 PROJECT_CONTEXT §4 工具清单逐字一致）：
    get_user_profile / get_learning_records / get_tasks /
    get_knowledge_mastery / get_learning_statistics /
    search_knowledge_base / create_task / update_task

「P12 接入」标注：get_learning_plan / generate_learning_plan /
adjust_learning_plan / generate_learning_report 4 个工具依赖 P12
规划与报告服务，留待 P12 注册——本阶段不造桩、不注册进
TOOLS_SCHEMA / TOOL_MAP（禁止占位桩函数：LLM 会调用一个不存在
的真实实现）。

一致性结构保证：TOOLS_SCHEMA 与 TOOL_MAP 均由 ``_TOOL_SPECS``
列表推导——工具名集合相等是构造性事实而非纪律约定；P12 扩展
仅在列表追加 ToolSpec 条目，天然不破坏既有 8 条契约。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel

from app.agent.tools import (
    CreateTaskParams,
    GetKnowledgeMasteryParams,
    GetLearningRecordsParams,
    GetLearningStatisticsParams,
    GetTasksParams,
    GetUserProfileParams,
    SearchKnowledgeBaseParams,
    UpdateTaskParams,
    ToolFunc,
    create_task,
    get_knowledge_mastery,
    get_learning_records,
    get_learning_statistics,
    get_tasks,
    get_user_profile,
    search_knowledge_base,
    update_task,
)

__all__ = ["TOOLS_SCHEMA", "TOOL_MAP"]


@dataclass(frozen=True)
class ToolSpec:
    """工具注册条目（不可变值对象，模块加载期构建、进程内常驻）。

    Attributes:
        name: 工具名（LLM tool_call 的 function.name）。
        func: tools.py 的装饰后实现（ToolFunc 签名）。
        params_model: 参数模型（schema 生成 + 白名单同源）。
        description: 三要素长文案（何时调用 / 参数填法 / 返回结构）。
    """

    name: str
    func: ToolFunc
    params_model: type[BaseModel]
    description: str


def _build_parameters_schema(params_model: type[BaseModel]) -> dict[str, Any]:
    """把 Pydantic 参数模型转为扁平 OpenAI function calling parameters。

    流水线（design.md 2.1.3-B）：``model_json_schema()`` → ``$defs``
    内联展开（``anyOf[$ref, null]`` 拆掉 null 包装、enum 直接平铺）→
    移除 ``$defs`` 键 → 输出 ``{type, properties, required,
    additionalProperties: false}`` 的扁平 object schema——规避
    OpenAI 兼容端对 $refs 的兼容不确定性；可选性仅由 required
    缺失表达。

    Args:
        params_model: 工具参数模型。

    Returns:
        dict[str, Any]: 无 ``$defs`` / ``$ref`` / ``anyOf`` 的扁平
            JSON Schema。
    """

    def _resolve(branch: dict[str, Any]) -> dict[str, Any]:
        if "$ref" in branch:
            ref_name = branch["$ref"].split("/")[-1]
            resolved = dict(defs.get(ref_name, {}))
            resolved.pop("title", None)
            return resolved
        return {k: v for k, v in branch.items() if k != "title"}

    raw = params_model.model_json_schema()
    defs: dict[str, Any] = raw.pop("$defs", {})
    flat_properties: dict[str, Any] = {}
    for name, prop in raw.get("properties", {}).items():
        prop = dict(prop)
        prop.pop("title", None)
        if "anyOf" in prop:
            any_of = prop.pop("anyOf")
            non_null = [_resolve(b) for b in any_of if b.get("type") != "null"]
            merged: dict[str, Any] = {}
            for branch in non_null:
                merged.update(branch)
            flat_properties[name] = {**prop, **merged}
        elif "$ref" in prop:
            flat_properties[name] = {**prop, **_resolve(prop)}
        else:
            flat_properties[name] = prop
    schema: dict[str, Any] = {"type": "object", "properties": flat_properties}
    required = raw.get("required", [])
    if required:
        schema["required"] = required
    schema["additionalProperties"] = False
    return schema


_TOOL_SPECS: list[ToolSpec] = [
    ToolSpec(
        name="get_user_profile",
        func=get_user_profile,
        params_model=GetUserProfileParams,
        description=(
            "获取当前用户的学习画像基础信息（学校、专业、年级、目标方向、"
            "兴趣方向、每日可学习时长）。当需要提供个性化建议、评估学习容量"
            "或制定学习安排时调用。本工具不需要任何参数。返回档案对象："
            "name（姓名）、school（学校）、major（专业）、grade（年级）、"
            "current_goal_type（目标方向，如考研/就业）、interest_directions"
            "（兴趣方向数组）、daily_study_minutes（每日可学习时长，分钟）；"
            "从未填写档案时返回默认值结构（daily_study_minutes=60），不是错误。"
        ),
    ),
    ToolSpec(
        name="get_learning_records",
        func=get_learning_records,
        params_model=GetLearningRecordsParams,
        description=(
            "查询当前用户的学习记录明细（学过什么、学了多久、自评掌握度、"
            "遇到的问题），用于分析学习行为与学习进度。参数：days（可选整数，"
            "1–365，默认 7，查询最近 N 天，按自然日计算、包含今天）；"
            "course_id（可选正整数，只看某门课程的记录，传非本人课程 id 时"
            "返回空列表）。返回 {days, start_date, end_date, records, total}："
            "records 按学习日期降序排列，每条含 content（学习内容）、"
            "duration_minutes（学习时长分钟）、achievement（成果）、problems"
            "（问题）、knowledge_points（涉及知识点）、mastery_level（自评"
            "掌握度 0-100）、study_date（学习日期）；total 为窗口内满足条件"
            "的记录总数。结果最多返回 100 条，记录很多时可缩小 days 收窄范围。"
        ),
    ),
    ToolSpec(
        name="get_tasks",
        func=get_tasks,
        params_model=GetTasksParams,
        description=(
            "查询当前用户的学习任务列表。当用户问『我还有哪些任务没做完 / "
            "待办 / 逾期』时调用本工具；未完成 = status 为 todo 或 "
            "in_progress；判断逾期可传 due_before=当前时间。参数：status"
            "（可选，todo 待办 / in_progress 进行中 / done 已完成 / review "
            "待复盘，不传=全部状态）；due_before（可选，ISO 8601 日期或日期"
            "时间，只返回截止时间早于该时刻的任务，如 \"2026-10-21\" 或 "
            "\"2026-10-21T23:59:59\"；指定后没有截止时间的任务不会返回）。"
            "返回 {tasks, total}：tasks 按截止时间升序（最紧急在前，无截止"
            "时间的排在最后），每条含 id、title、description、status、"
            "priority、deadline、scheduled_date、estimated_minutes、"
            "actual_minutes、knowledge_points、goal_id、course_id、source"
            "（manual/agent）、created_at 等字段；total 为满足条件的任务"
            "总数。结果最多 100 条。"
        ),
    ),
    ToolSpec(
        name="get_knowledge_mastery",
        func=get_knowledge_mastery,
        params_model=GetKnowledgeMasteryParams,
        description=(
            "查询当前用户各知识点的掌握度分数（0–100 分，分数越低越薄弱）。"
            "当需要分析薄弱知识点、评估某知识点的掌握情况时调用。参数："
            "topic（可选字符串，知识点名称，精确匹配；省略则返回全部知识点）。"
            "返回 {items, total}：items 每条为 {knowledge_point, "
            "mastery_score}，全量查询时按分数升序排列（最薄弱的在前）。"
            "注意：结果不含尚未开始学习的知识点（已排除零分待学点，非数据"
            "缺失）；查某个 topic 无结果时表示该知识点尚未学习或不存在，"
            "返回空列表而非错误。"
        ),
    ),
    ToolSpec(
        name="get_learning_statistics",
        func=get_learning_statistics,
        params_model=GetLearningStatisticsParams,
        description=(
            "获取当前用户的学习统计总览与近期趋势。当需要分析学习状态、"
            "汇报学习进展、评估学习效果时调用。参数：days（可选整数，1–365，"
            "默认 7，趋势窗口天数）。返回两层信息：第一层为全量累计统计七指标"
            "（注意是全部历史累计、不是近 N 天）：total_minutes（累计学习"
            "分钟数）、task_completion_rate（任务完成率%）、avg_mastery（平均"
            "掌握度，排除未开始学习的知识点）、streak_days（连续学习天数）、"
            "total_record_count（学习记录总条数）、avg_session_minutes（平均"
            "单次学习时长分钟）、overdue_task_count（逾期任务数）；第二层为 "
            "trend 近 N 天窗口趋势：{days, start_date, end_date, items（每日 "
            "{date, minutes} 序列，无记录的天为 0，共 N 条）, slope（时长趋势"
            "斜率，负值表示在下降）, risk_alert（连续 5 天时长递减的预警对象"
            "或 null）}。"
        ),
    ),
    ToolSpec(
        name="search_knowledge_base",
        func=search_knowledge_base,
        params_model=SearchKnowledgeBaseParams,
        description=(
            "在学习知识库中语义检索学习资料片段。当用户问知识型问题（如概念"
            "解释、公式、算法原理）且需要引用学习资料回答时调用。参数：query"
            "（必填字符串，1–500 字符，用自然语言描述要查的内容）；top_k"
            "（可选整数，1–20，默认 5，期望返回条数）；scope（可选，"
            "personal=仅当前用户上传的个人库 / public=系统预置公共库 / "
            "all=两者合并，默认 all）。返回 {mode, results}：mode 为 online"
            "（正常向量检索）或 offline（向量化服务降级后的检索，结果置信度"
            "较低）；results 按相似度降序、最多 top_k 条，每条含 content"
            "（片段正文）、source_title（来源标题»章节路径）、score（相似度"
            "分数）、item_id（来源文档 id）、chunk_index（分块序号）、scope"
            "（该条归属 personal/public）。无命中返回空 results，不是错误。"
        ),
    ),
    ToolSpec(
        name="create_task",
        func=create_task,
        params_model=CreateTaskParams,
        description=(
            "为当前用户创建一条新的学习任务（写操作）。当用户表达『帮我加个"
            "任务 / 安排一个学习事项 / 提醒我学 XX』时调用。参数：title"
            "（必填字符串，1–200 字符，任务名称）；description（可选，任务"
            "描述）；goal_id（可选正整数，关联学习目标，必须属于本人）；"
            "course_id（可选正整数，关联课程，必须属于本人）；knowledge_points"
            "（可选字符串数组，最多 20 个知识点标签）；priority（可选，"
            "low/medium/high，默认 medium）；estimated_minutes（可选整数 ≥1，"
            "预计耗时分钟）；deadline（可选，ISO 8601 截止时间，如 "
            "\"2026-10-21T23:59:59\"）。创建成功返回新任务的完整快照（含 id、"
            "status=\"todo\" 待办、创建时间）；任务来源由系统标记为 agent。"
            "不能传入 status（状态由用户在任务页操作）、user_id 等字段。"
        ),
    ),
    ToolSpec(
        name="update_task",
        func=update_task,
        params_model=UpdateTaskParams,
        description=(
            "修改当前用户的已有学习任务（写操作），可改标题、描述、截止时间、"
            "优先级、知识点、预计耗时、实际耗时、计划执行日期、关联目标/课程。"
            "当用户说『把这个任务改到周X / 延后截止时间 / 提高优先级』时调用；"
            "需要先知道 task_id，可用 get_tasks 查询。参数：task_id（必填正"
            "整数，目标任务 id）；其余字段全部可选、至少提供一个待修改字段："
            "title（1–200 字符）、description、goal_id / course_id（须属本人）、"
            "knowledge_points（≤20 个）、priority（low/medium/high）、"
            "estimated_minutes（≥1）、actual_minutes（≥0 实际耗时）、deadline"
            "（ISO 8601）、scheduled_date（ISO 日期，计划执行日期）。字段传 "
            "null 等同于不修改（无法通过本工具清空字段值）。不支持修改 "
            "status——任务状态流转请由用户在任务页操作，本工具不支持修改 "
            "status。更新成功返回更新后的完整任务快照。"
        ),
    ),
]

#: OpenAI function calling 工具描述（``tools=`` 直传；P11 执行器消费）。
TOOLS_SCHEMA: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": spec.name,
            "description": spec.description,
            "parameters": _build_parameters_schema(spec.params_model),
        },
    }
    for spec in _TOOL_SPECS
]

#: 工具名 → 实现函数映射（执行器派发入口；与 TOOLS_SCHEMA 同源推导）。
TOOL_MAP: dict[str, ToolFunc] = {spec.name: spec.func for spec in _TOOL_SPECS}