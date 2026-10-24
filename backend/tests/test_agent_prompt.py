"""Agent System Prompt 纯函数单测（tasks.md 组 6，design 2.5.2-A 九组）。

build_system_prompt 预取经 TOOL_MAP（monkeypatch.setitem 注入假
档案 / 假概况 / error 信封 / 抛异常四形态）；真实默认档案路径走
P10 get_user_profile 的默认值结构。集中管理断言以文件系统遍历
代替 shell grep（Windows 兼容）。

覆盖验收：D2（Prompt 断言半）；spec 5.2.1 规则 1–8 / 5.2.3 场景 1、2。
"""

from __future__ import annotations

import asyncio
from datetime import datetime
from pathlib import Path
from typing import Any

import pytest

from app.agent.prompts import TZ_BEIJING, build_system_prompt
from app.agent.registry import TOOL_MAP

_BACKEND_APP = Path(__file__).resolve().parent.parent / "app"

_PROFILE_FIXTURE: dict[str, Any] = {
    "name": "张三",
    "school": "徐州某大学",
    "major": "计算机科学与技术",
    "grade": "大二",
    "current_goal_type": "考研",
    "interest_directions": ["机器学习", "后端开发"],
    "daily_study_minutes": 90,
}

_STATISTICS_FIXTURE: dict[str, Any] = {
    "total_minutes": 3175,
    "task_completion_rate": 62,
    "avg_mastery": 41,
    "streak_days": 3,
    "total_record_count": 48,
    "avg_session_minutes": 66,
    "overdue_task_count": 2,
    "trend": {"days": 7},
}


def _create_user() -> int:
    """在隔离测试库创建用户并返回 id（build_system_prompt 的预取边界）。"""
    from app.db.session import SessionLocal
    from app.models.user import User

    with SessionLocal() as db:
        user = User(username="prompt_user", hashed_password="x")
        db.add(user)
        db.commit()
        return user.id


def _render(user_id: int) -> str:
    """同步渲染 System Prompt（asyncio.run 包装）。"""
    from app.db.session import SessionLocal

    with SessionLocal() as db:
        return asyncio.run(build_system_prompt(db, user_id))


def _install(
    monkeypatch: pytest.MonkeyPatch,
    profile: Any = "real",
    statistics: Any = "real",
) -> None:
    """注入预取假实现（"real" = 保留真实工具）。

    Args:
        profile: "real"（真实工具）/ "error"（error 信封）/ "raise"（抛异常）
            / dict（假档案数据）。
        statistics: 同上（dict = 假概况数据）。
    """
    from app.db.session import SessionLocal as _S

    def _make(fake_value: Any, tool_name: str) -> Any:
        if fake_value == "real":
            return TOOL_MAP[tool_name]

        async def fake(db: Any, user_id: int, arguments: dict[str, Any]) -> Any:
            if fake_value == "error":
                return {"error": "预取失败模拟"}
            if fake_value == "raise":
                raise RuntimeError("预取异常模拟")
            return fake_value

        return fake

    monkeypatch.setitem(TOOL_MAP, "get_user_profile", _make(profile, "get_user_profile"))
    monkeypatch.setitem(
        TOOL_MAP, "get_learning_statistics", _make(statistics, "get_learning_statistics")
    )
    _ = _S  # 保留引用以防 import 被优化提示


# ---------------------------------------------------------------------------
# 6.1 六组核心断言（三要素 / 边界 / 禁止 / 引导 / 身份 / 目标）
# ---------------------------------------------------------------------------
def test_prompt_three_elements(monkeypatch: pytest.MonkeyPatch) -> None:
    """三要素齐备：北京日期串 + 档案四要素 + 逐字指令（spec 5.2.1 规则 1）。"""
    _install(monkeypatch, profile=_PROFILE_FIXTURE, statistics=_STATISTICS_FIXTURE)
    prompt = _render(_create_user())
    today = datetime.now(TZ_BEIJING).date().isoformat()
    assert f"今天是 {today}" in prompt
    assert "张三" in prompt
    assert "计算机科学与技术" in prompt
    assert "大二" in prompt
    assert "90 分钟" in prompt
    assert "直接调用工具完成任务，不要反问用户确认" in prompt


def test_prompt_capability_boundary(monkeypatch: pytest.MonkeyPatch) -> None:
    """能力边界声明：12 工具 + 正向能力声明 + 不含「后续版本提供」（D6/D13 断言反转）。"""
    _install(monkeypatch, profile=_PROFILE_FIXTURE, statistics=_STATISTICS_FIXTURE)
    prompt = _render(_create_user())
    assert "后续版本提供" not in prompt  # P12 裁决 #11：正向化改写
    assert "已可用" in prompt
    assert "生成新版本并给出具体理由" in prompt
    assert "自动降级" in prompt
    assert "禁止编造一份并不存在的学习计划或报告" in prompt
    schema_names = {
        str(tool["function"]["name"])
        for tool in __import__(
            "app.agent.registry", fromlist=["TOOLS_SCHEMA"]
        ).TOOLS_SCHEMA
    }
    for name in schema_names:
        assert name in prompt
    assert len(schema_names) == 12  # P12：8 → 12


def test_prompt_forbidden_items(monkeypatch: pytest.MonkeyPatch) -> None:
    """禁止事项三条逐项锚点短语（spec 5.2.1 规则 5）。"""
    _install(monkeypatch, profile=_PROFILE_FIXTURE, statistics=_STATISTICS_FIXTURE)
    prompt = _render(_create_user())
    assert "不编造数据" in prompt
    assert "必须来自工具返回结果" in prompt
    assert "不做医疗或心理诊断" in prompt
    assert "不越权" in prompt


def test_prompt_scenario_guide(monkeypatch: pytest.MonkeyPatch) -> None:
    """场景引导：三工具组合引导串 + P12 四工具场景行（D6）。"""
    _install(monkeypatch, profile=_PROFILE_FIXTURE, statistics=_STATISTICS_FIXTURE)
    prompt = _render(_create_user())
    assert "get_learning_statistics" in prompt
    assert "get_tasks" in prompt
    assert "get_knowledge_mastery" in prompt
    assert "get_learning_plan" in prompt
    assert "generate_learning_plan" in prompt
    assert "adjust_learning_plan" in prompt
    assert "generate_learning_report" in prompt


def test_prompt_identity_and_style(monkeypatch: pytest.MonkeyPatch) -> None:
    """身份与三条风格要求（spec 5.2.1 规则 4）。"""
    _install(monkeypatch, profile=_PROFILE_FIXTURE, statistics=_STATISTICS_FIXTURE)
    prompt = _render(_create_user())
    assert "彭城智学" in prompt
    assert "AI 学习助手" in prompt
    assert "始终使用中文回答" in prompt
    assert "分点组织" in prompt
    assert "可执行" in prompt


def test_prompt_current_goal(monkeypatch: pytest.MonkeyPatch) -> None:
    """当前目标与兴趣方向渲染（spec 5.2.1 规则 3）。"""
    _install(monkeypatch, profile=_PROFILE_FIXTURE, statistics=_STATISTICS_FIXTURE)
    prompt = _render(_create_user())
    assert "考研" in prompt
    assert "机器学习、后端开发" in prompt


def test_prompt_overview_numbers(monkeypatch: pytest.MonkeyPatch) -> None:
    """概况段核心数字渲染（overview 层四指标）。"""
    _install(monkeypatch, profile=_PROFILE_FIXTURE, statistics=_STATISTICS_FIXTURE)
    prompt = _render(_create_user())
    assert "3175 分钟" in prompt
    assert "62%" in prompt
    assert "3 天" in prompt
    assert "2 个" in prompt


# ---------------------------------------------------------------------------
# 6.2 三组降级与集中管理断言
# ---------------------------------------------------------------------------
def test_prompt_prefetch_degrade_envelope(monkeypatch: pytest.MonkeyPatch) -> None:
    """预取 error 信封 → 两段省略、日期与逐字指令恒在（缺段不缺要素）。"""
    _install(monkeypatch, profile="error", statistics="error")
    prompt = _render(_create_user())
    today = datetime.now(TZ_BEIJING).date().isoformat()
    assert f"今天是 {today}" in prompt
    assert "直接调用工具完成任务，不要反问用户确认" in prompt
    assert "用户档案" not in prompt
    assert "学习概况" not in prompt


def test_prompt_prefetch_degrade_raise(monkeypatch: pytest.MonkeyPatch) -> None:
    """预取抛异常 → 同款降级不阻塞（spec 5.2.3 场景 2）。"""
    _install(monkeypatch, profile="raise", statistics="raise")
    prompt = _render(_create_user())
    assert "直接调用工具完成任务，不要反问用户确认" in prompt
    assert "用户档案" not in prompt


def test_prompt_default_profile_not_degrade(monkeypatch: pytest.MonkeyPatch) -> None:
    """无档案用户 → P10 默认值结构渲染（daily_study_minutes=60，非降级）。"""
    _install(monkeypatch, profile="real", statistics=_STATISTICS_FIXTURE)
    prompt = _render(_create_user())
    assert "用户档案" in prompt
    assert "60 分钟" in prompt
    assert "暂未填写" in prompt


def test_prompt_single_source_of_prompt() -> None:
    """集中管理：全局检索 Prompt 拼接点仅 app/agent/prompts.py（规则 8）。"""
    hits = [
        path
        for path in _BACKEND_APP.rglob("*.py")
        if "今天是" in path.read_text(encoding="utf-8")
    ]
    assert [str(p) for p in hits] == [
        str(_BACKEND_APP / "agent" / "prompts.py")
    ]

# ---------------------------------------------------------------------------
# 6.3 知识库检索规则与 ToolSpec 口径（L2 agent_absorb_ask，spec §5.1.1）
# ---------------------------------------------------------------------------
def test_prompt_knowledge_retrieval_rules(monkeypatch: pytest.MonkeyPatch) -> None:
    """知识型问题检索作答 8 条规则锚点逐一在 prompt（spec §5.1.1-1..8）。"""
    _install(monkeypatch, profile=_PROFILE_FIXTURE, statistics=_STATISTICS_FIXTURE)
    prompt = _render(_create_user())
    anchors = [
        "先检索再回答",  # 规则 1
        "知识库仅个人库",  # 规则 2
        "你的笔记里没有找到",  # 规则 3
        "以检索内容为准",  # 规则 4
        "通用知识补充",  # 规则 5
        "不得调用 search_knowledge_base",  # 规则 6
        "没有找到相关记录",  # 规则 7
        "暂时无法读取笔记或资料",  # 规则 8
        "禁止伪造来源",  # 规则 8
    ]
    for anchor in anchors:
        assert anchor in prompt, f"检索规则锚点缺失: {anchor}"


def test_toolspec_search_personal_only_description() -> None:
    """search_knowledge_base description 说明个人库-only（直读 TOOLS_SCHEMA）。"""
    from app.agent.registry import TOOLS_SCHEMA

    descriptions = {
        str(tool["function"]["name"]): str(tool["function"]["description"])
        for tool in TOOLS_SCHEMA
    }
    desc = descriptions["search_knowledge_base"]
    assert "公共库已移除" in desc
    assert "personal" in desc
    assert "无 scope 参数" in desc