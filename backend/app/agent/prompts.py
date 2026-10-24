"""Agent System Prompt 单一事实来源（七段模板 + 档案/概况预取降级）。

本模块是全局**唯一** Prompt 拼接点（spec §5.2.1 规则 8——禁止散落、
禁止前端拼接）。七段模板结构（design 2.4.3-A）：

- ① 身份与风格（静态，恒在）
- ② 日期（三要素之一，动态渲染，恒在——P10 实测：缺日期则模型先调
  两个工具确认上下文，浪费轮次）
- ③ 用户档案（三要素之二，TOOL_MAP 预取；失败整段省略降级）
- ④ 最近学习概况（TOOL_MAP 预取；失败整段省略降级）
- ⑤ 能力边界声明（静态骨架 + 从 TOOLS_SCHEMA 名集合动态生成工具
  清单——P12 追加工具自动跟进；「后续版本」表述是 D2 不编造验收的
  Prompt 侧机制）
- ⑥ 禁止事项（静态，恒在）
- ⑦ 场景引导 + 执行指令（三要素之三，静态，恒在——逐字指令「直接
  调用工具完成任务，不要反问用户确认」）

降级原则（spec §5.2.3）：预取失败（error 信封或异常）仅省略对应段，
**「缺段不缺要素」**——三要素中②⑦恒在；档案从未填写时 P10 工具
返回默认值结构（daily_study_minutes=60）按默认渲染，**不是降级**。

预取方式（裁决 #10/#11）：经 ``TOOL_MAP`` 直调（agent 包内依赖，
不经 LLM 决策、不推 SSE 事件——前端卡片语义 = LLM 决策调用）；
不 import api / services。北京时区常量本地定义，不跨层导入。

回链：design 2.4.3；spec §5.2。
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.agent.registry import TOOLS_SCHEMA, TOOL_MAP

logger = logging.getLogger(__name__)

#: 北京时区（三要素之一「今天的日期」的渲染基准；本地定义不跨层导入）。
TZ_BEIJING = timezone(timedelta(hours=8))

#: 概况预取窗口天数（近 7 天核心数字；与 Dashboard 周口径一致）。
_OVERVIEW_DAYS: int = 7

# ---------------------------------------------------------------------------
# 静态段模板常量（design 2.4.3-A ①⑤⑥⑦ 行内容）
# ---------------------------------------------------------------------------
_IDENTITY_SECTION = (
    "你是彭城智学（SmartLearn）的 AI 学习助手，一位面向高校学生的"
    "智能学习伙伴。回复风格要求：\n"
    "1. 始终使用中文回答；\n"
    "2. 回答分点组织、条理清晰；\n"
    "3. 给出可执行的具体建议，而不是空泛的鼓励。"
)

_BOUNDARY_SECTION_TEMPLATE = (
    "你当前可用的工具清单（共 {count} 个）：\n{tool_list}\n\n"
    "能力边界：学习计划的生成与调整、学习报告生成能力已可用"
    "（generate_learning_plan / adjust_learning_plan / "
    "generate_learning_report，另有 get_learning_plan 查看当前计划）。"
    "计划调整会生成新版本并给出具体理由；生成失败时自动降级为规则"
    "模式，仍返回可用结果。回答中的计划安排与报告数字必须来自工具"
    "返回结果。禁止编造一份并不存在的学习计划或报告。"
)

_FORBIDDEN_SECTION = (
    "禁止事项（必须严格遵守）：\n"
    "1. 不编造数据：回答中的任何学习数字（时长、任务数、分数等）"
    "必须来自工具返回结果，没有数据就明确说明；\n"
    "2. 不做医疗或心理诊断：遇到身心健康问题，建议用户咨询专业机构；\n"
    "3. 不越权：不执行账号操作、不代替用户流转任务状态、"
    "不访问他人数据。"
)

_GUIDE_SECTION = (
    "典型场景的工具路径引导：\n"
    "- 分析学习状态（如「我最近学习怎么样」）：依次调用 "
    "get_learning_statistics、get_tasks、get_knowledge_mastery，"
    "综合三份结果给出含具体数字的分析；\n"
    "- 查询学习明细：get_learning_records（可用 days 收窄范围）；\n"
    "- 添加或修改学习安排：create_task / update_task；\n"
    "- 查看当前计划：get_learning_plan；\n"
    "- 制定下周学习计划：generate_learning_plan；\n"
    "- 调整本周计划（如任务完不成、截止临近）：adjust_learning_plan；\n"
    "- 生成日报/周报/月报：generate_learning_report。\n\n"
    "知识型问题检索作答规则（必须严格遵守）：\n"
    "1. 先检索再回答：知识型问题（知识点、概念、课程资料、笔记/文档"
    "内容）必须先调用 search_knowledge_base 再组织回答，禁止仅凭自身"
    "记忆直接回答知识型问题；\n"
    "2. 知识库仅个人库：检索范围恒为当前用户的个人库，不存在公共库，"
    "不要询问或声称「公共资料」；\n"
    "3. 个人库为空的诚实红线：检索无命中时必须如实说「你的笔记里没有"
    "找到」，随后可给通用解释；不得编造来源或假装检索成功；\n"
    "4. 冲突优先级：检索到的笔记/资料与你的通用知识不一致时，以检索"
    "内容为准并在回答中说明差异，不得用通用知识覆盖或改写笔记事实；\n"
    "5. 两段式回答结构：检索有命中时，先讲「检索到的内容」并以来源"
    "序号 [1][2] 标注，再以「通用知识补充」明确区分自有知识；禁止把"
    "通用知识标注为笔记/资料来源；工具返回后禁止只复述结构化数据，"
    "必须用自然语言组织回答，来源信息由来源卡片承载展示；\n"
    "6. 任务型问题零检索：任务、计划、学习记录、掌握度、报告、目标"
    "管理类问题走对应工具，不得调用 search_knowledge_base；\n"
    "7. 检索为空话术：检索成功但无命中时，明确说明「你的笔记/资料里"
    "没有找到相关记录」，再给通用解释；\n"
    "8. 检索失败话术：工具返回错误时，如实说「暂时无法读取笔记或资料」"
    "，再给通用解释；禁止伪造来源、禁止假装检索成功。\n\n"
    "执行指令：直接调用工具完成任务，不要反问用户确认。"
)

_SUMMARIZE_NOTE = (
    "今天的信息如无特别说明均以工具查询结果为准。"
)

# ---------------------------------------------------------------------------
# 动态段渲染（design 2.4.3-A ②③④）
# ---------------------------------------------------------------------------
def _render_date_section() -> str:
    """渲染日期段（三要素之一，恒在）。

    当天北京日期动态生成（P10 实测：不给日期时模型会先浪费两轮去查
    上下文；不能用 UTC 日期——北京日期与用户认知一致）。
    """
    today = datetime.now(TZ_BEIJING).date().isoformat()
    return f"今天是 {today}（北京时区）。"


def _render_profile_section(profile: dict[str, Any]) -> str:
    """渲染用户档案段（三要素之二）。

    Args:
        profile: get_user_profile 工具返回的档案 dict（含默认值结构
            场景——档案从未填写时 P10 返回默认值，按默认渲染非降级）。
    """
    interests = profile.get("interest_directions") or []
    interests_text = (
        "、".join(str(item) for item in interests) if interests else "暂未填写"
    )
    return (
        "用户档案：\n"
        f"- 姓名：{profile.get('name') or '暂未填写'}\n"
        f"- 学校：{profile.get('school') or '暂未填写'}\n"
        f"- 专业：{profile.get('major') or '暂未填写'}\n"
        f"- 年级：{profile.get('grade') or '暂未填写'}\n"
        f"- 当前目标方向：{profile.get('current_goal_type') or '暂未填写'}\n"
        f"- 兴趣方向：{interests_text}\n"
        f"- 每日可学习时长：{profile.get('daily_study_minutes', 60)} 分钟"
    )


def _render_overview_section(statistics: dict[str, Any]) -> str:
    """渲染最近学习概况段（近 7 天核心数字，overview 层字段）。

    Args:
        statistics: get_learning_statistics 工具返回的统计 dict（取
            第一层全量累计指标中的四个核心数字；trend 层数字量过大
            不进 Prompt——design 2.4.3-A ④）。
    """
    return (
        "用户最近学习概况（全量累计口径）：\n"
        f"- 累计学习时长：{statistics.get('total_minutes', 0)} 分钟\n"
        f"- 任务完成率：{statistics.get('task_completion_rate', 0)}%\n"
        f"- 连续学习天数：{statistics.get('streak_days', 0)} 天\n"
        f"- 逾期任务数：{statistics.get('overdue_task_count', 0)} 个"
    )


def _render_boundary_section() -> str:
    """渲染能力边界段（工具清单从 TOOLS_SCHEMA 名集合动态生成）。"""
    tool_names = [
        str(tool["function"]["name"])
        for tool in TOOLS_SCHEMA
        if "function" in tool and "name" in tool["function"]
    ]
    tool_list = "\n".join(f"- {name}" for name in tool_names)
    return _BOUNDARY_SECTION_TEMPLATE.format(
        count=len(tool_names), tool_list=tool_list
    )


# ---------------------------------------------------------------------------
# 预取与组装（design 2.4.3-B）
# ---------------------------------------------------------------------------
async def _prefetch(
    db: Session, user_id: int, tool_name: str, arguments: dict[str, Any]
) -> dict[str, Any] | None:
    """经 TOOL_MAP 直调预取（裁决 #10/#11：不经 LLM、不推 SSE）。

    Args:
        db: 请求级数据库会话。
        user_id: 当前认证用户 id（服务端注入）。
        tool_name: 工具名（get_user_profile / get_learning_statistics）。
        arguments: 工具参数（概况预取带 days=7）。

    Returns:
        dict[str, Any] | None: 工具返回的业务 dict；error 信封或异常
        时返回 None（调用方整段省略 + warning 日志）。
    """
    try:
        result = await TOOL_MAP[tool_name](db, user_id, arguments)
    except Exception as exc:  # noqa: BLE001 - 预取失败降级不阻塞对话
        logger.warning(
            "System Prompt 预取异常(降级省略该段): user_id=%s tool=%s type=%s",
            user_id,
            tool_name,
            type(exc).__name__,
        )
        return None
    if isinstance(result, dict) and "error" in result:
        logger.warning(
            "System Prompt 预取返回 error 信封(降级省略该段): user_id=%s tool=%s",
            user_id,
            tool_name,
        )
        return None
    if not isinstance(result, dict):
        logger.warning(
            "System Prompt 预取返回非 dict(降级省略该段): user_id=%s tool=%s type=%s",
            user_id,
            tool_name,
            type(result).__name__,
        )
        return None
    return result


async def build_system_prompt(db: Session, user_id: int) -> str:
    """组装 System Prompt（七段模板，单一事实来源入口）。

    预取两次 TOOL_MAP 直调（async await）：get_user_profile 与
    get_learning_statistics(days=7)；任一失败（error 信封或异常）仅
    省略对应段——「缺段不缺要素」，三要素中日期段与执行指令恒在
    （spec 5.2.3 场景 2）。档案从未填写时按 P10 默认值结构渲染
    （非降级，spec 5.2.3 场景 1）。

    Args:
        db: 请求级数据库会话。
        user_id: 当前认证用户 id。

    Returns:
        str: 渲染完成的 System Prompt 文本。
    """
    sections: list[str] = [
        _IDENTITY_SECTION,
        _render_date_section(),
    ]

    profile = await _prefetch(db, user_id, "get_user_profile", {})
    if profile is not None:
        sections.append(_render_profile_section(profile))

    statistics = await _prefetch(
        db, user_id, "get_learning_statistics", {"days": _OVERVIEW_DAYS}
    )
    if statistics is not None:
        sections.append(_render_overview_section(statistics))

    sections.append(_render_boundary_section())
    sections.append(_FORBIDDEN_SECTION)
    sections.append(_GUIDE_SECTION)
    sections.append(_SUMMARIZE_NOTE)

    return "\n\n".join(sections)