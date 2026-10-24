"""AI Agent 工具注册表（P10 + P12）：TOOLS_SCHEMA 与 TOOL_MAP 的单一事实来源。

P12 交付后注册 12 个工具（名称与 PROJECT_CONTEXT §4 工具清单逐字一致）：
    get_user_profile / get_learning_records / get_tasks /
    get_knowledge_mastery / get_learning_statistics /
    search_knowledge_base / create_task / update_task /
    get_learning_plan / generate_learning_plan /
    adjust_learning_plan / generate_learning_report

计划与报告四工具（P12 接入，2026-10-23 交付）：get_learning_plan
读取当前生效计划；generate_learning_plan 生成下一完整自然周
（失败自动降级规则模式）；adjust_learning_plan 动态调整并给出
具体理由（零 LLM 纯确定性）；generate_learning_report 生成
日报/周报/月报（失败自动降级模板总结）。不设 get_plan_diff
独立工具——diff 由 adjust_learning_plan 返回值携带（工具数量
越少模型选择越准）。

一致性结构保证：TOOLS_SCHEMA 与 TOOL_MAP 均由 ``_TOOL_SPECS``
列表推导——工具名集合相等是构造性事实而非纪律约定；P12 扩展
仅在列表追加 ToolSpec 条目，天然不破坏既有 8 条契约。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel

from app.agent.tools import (
    AdjustLearningPlanParams,
    CreateTaskParams,
    GenerateLearningPlanParams,
    GenerateLearningReportParams,
    GetKnowledgeMasteryParams,
    GetLearningPlanParams,
    GetLearningRecordsParams,
    GetLearningStatisticsParams,
    GetTasksParams,
    GetUserProfileParams,
    SearchKnowledgeBaseParams,
    UpdateTaskParams,
    ToolFunc,
    adjust_learning_plan,
    create_task,
    generate_learning_plan,
    generate_learning_report,
    get_knowledge_mastery,
    get_learning_plan,
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
            "在学习知识库中语义检索学习资料片段（仅当前用户的个人库）。"
            "当用户问知识型问题（如概念解释、公式、算法原理）且需要引用"
            "学习资料回答时调用。参数：query（必填字符串，1–500 字符，用"
            "自然语言描述要查的内容）；top_k（可选整数，1–20，默认 5，"
            "期望返回条数）。返回 {mode, results}：mode 为 online"
            "（正常向量检索）或 offline（向量化服务降级后的检索，结果置信度"
            "较低）；results 按相似度降序、最多 top_k 条，每条含 content"
            "（片段正文）、source_title（来源标题»章节路径）、score（相似度"
            "分数）、item_id（来源文档 id）、chunk_index（分块序号）、scope"
            "（当前恒为 personal）。无命中返回空 results，不是错误。"
            "公共库已移除，无 scope 参数；用户说「我的笔记/我上传的/资料里」"
            "就是检索个人库；无命中时直接据实回答，不得编造来源。"
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
    ToolSpec(
        name="get_learning_plan",
        func=get_learning_plan,
        params_model=GetLearningPlanParams,
        description=(
            "获取当前用户生效中的学习计划及全部条目（周视图课表）。当用户问"
            "『我现在的计划是什么 / 这周怎么安排的 / 今天该学什么』时调用。"
            "本工具不需要任何参数。返回 {plan, items}：plan 为计划版本对象"
            "（含 id、version、start_date、end_date、status、adjust_reason"
            "（若被 AI 调整过则含具体理由）等）；items 按日期与时间升序排列，"
            "每条含 plan_date（安排日期）、start_time / end_time（时段，休息"
            "条目为 null）、topic（本次学什么）、task_id（关联任务）、"
            "estimated_minutes（预计时长分钟）、priority（优先级）；周五为"
            "「休息 / 复习」条目。当前没有进行中的学习计划时返回 "
            "{plan: null, message: \"当前没有进行中的学习计划\"}——这是正常"
            "状态不是错误。"
        ),
    ),
    ToolSpec(
        name="generate_learning_plan",
        func=generate_learning_plan,
        params_model=GenerateLearningPlanParams,
        description=(
            "为当前用户生成下一个完整自然周的学习计划（写操作，7 天结构化"
            "课表）。当用户说『帮我制定下周学习计划 / 安排下周学习』时调用。"
            "本工具不需要任何参数，恒生成下一个完整自然周（下周一到下周日）。"
            "返回 {plan, items, unplaced_tasks, generated_by}：items 为 7 天"
            "条目（每日总时长不超过档案设定的每日可学习时长、周五固定休息、"
            "逾期与临期任务优先安排）；unplaced_tasks 为容量不足未排入的候选"
            "（对应任务已创建，可在任务页单独安排）；generated_by 为 llm"
            "（AI 规划内容）或 rules（降级规则模式）——生成失败时自动降级为"
            "规则模式，仍会返回可用结果，不会报错。"
        ),
    ),
    ToolSpec(
        name="adjust_learning_plan",
        func=adjust_learning_plan,
        params_model=AdjustLearningPlanParams,
        description=(
            "动态调整当前用户的学习计划（写操作，核心能力）。当用户说『帮我"
            "调整一下这周的计划 / 计划跟不上了 / 任务完不成』，或检测到任务"
            "未完成且截止临近、近期学习时长不足时调用。参数：plan_id（可选"
            "正整数，目标计划 id，缺省调整当前生效计划）。计划调整会生成新"
            "版本并给出具体理由（含调整到哪天、顺延了什么），原版本保留为"
            "历史快照可随时对比。返回 {plan, adjust_reason, diff, adjusted}："
            "adjust_reason 为具体中文理由（含任务名与从哪天调整到哪天）；"
            "diff 为结构化改动清单（moved / added / removed，每条含主题、"
            "原位置、新位置与原因）；无可调整项时 adjusted=false 且不新建"
            "版本。当前没有进行中的学习计划时返回 {\"error\": \"当前没有"
            "进行中的学习计划\"}。"
        ),
    ),
    ToolSpec(
        name="generate_learning_report",
        func=generate_learning_report,
        params_model=GenerateLearningReportParams,
        description=(
            "为当前用户生成学习成长报告（写操作）。当用户说『给我生成一份"
            "周报 / 学习总结 / 月报 / 日报』时调用。参数：report_type（可选："
            "daily 日报 / weekly 周报 / monthly 月报，缺省 weekly；周期取最近"
            "完整周期）。返回报告对象：summary 为自然语言总结（中文、引用"
            "真实数字——学习时长、完成任务数、完成率、学习最多的方向、薄弱"
            "知识点、阶段进步与建议）；content 为结构化统计（total_minutes、"
            "task_completed、completion_rate、top_direction、weak_points、"
            "progress、advice 数组）。报告数字全部来自数据库统计，不是估算；"
            "AI 总结失败时自动降级模板模式（仍含全部真实数字），仍会返回"
            "可用结果。"
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