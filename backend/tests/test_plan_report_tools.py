"""计划与报告工具测试（tasks.md 组 9.3：T0–T7）。

覆盖验收：D6（12 工具注册与真实调用）/ D11（双账号隔离与 user_id
注入正确性）。

- T0：注册断言（12 条与契约 §4 逐字一致、参数 schema 扁平）；
- T1–T5：工具直调（``TOOL_MAP[name](db, user_id, arguments)`` 真实
  实现 + mock 规划/总结 LLM）；
- T6：对话集成（P11 SSE 通道 mock ``agent_chat_stream`` 预设
  tool_calls=[generate_learning_plan] → tool_call/tool_result/done）；
- T7：双账号隔离。
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, time as _time, timedelta, timezone
from typing import Any

import pytest

from app.agent.registry import TOOL_MAP, TOOLS_SCHEMA

TZ = timezone(timedelta(hours=8))

_CONTRACT_TOOL_NAMES = [
    "get_user_profile",
    "get_learning_records",
    "get_tasks",
    "get_knowledge_mastery",
    "get_learning_statistics",
    "search_knowledge_base",
    "create_task",
    "update_task",
    "get_learning_plan",
    "generate_learning_plan",
    "adjust_learning_plan",
    "generate_learning_report",
]


def _db():
    from app.db.session import SessionLocal

    return SessionLocal()


def _get_user_id(app_client: Any, user: dict[str, Any]) -> int:
    resp = app_client.get("/api/v1/auth/me", headers=user["headers"])
    return resp.json()["data"]["id"]


def _call_tool(name: str, db: Any, user_id: int, arguments: dict[str, Any]) -> dict[str, Any]:
    """直调工具（真实实现，(db, user_id, arguments) 契约）。"""
    return asyncio.run(TOOL_MAP[name](db, user_id, arguments))


def _install_dead_plan_llm(monkeypatch: pytest.MonkeyPatch) -> None:
    """规划 LLM 不可用（降级 rules——工具行为的确定性路径）。"""
    from app.core.response import BizException

    async def dead(_messages: list[dict[str, Any]]) -> str:
        raise BizException(3000, "AI 服务不可用", 502)

    monkeypatch.setattr("app.services.plan.llm.chat", dead)


def _install_dead_report_llm(monkeypatch: pytest.MonkeyPatch) -> None:
    """总结 LLM 不可用（降级 template）。"""
    from app.core.response import BizException

    async def dead(_messages: list[dict[str, Any]]) -> str:
        raise BizException(3000, "AI 服务不可用", 502)

    monkeypatch.setattr("app.services.report.llm.chat", dead)


# ---------------------------------------------------------------------------
# T0：注册断言（D6 核心）
# ---------------------------------------------------------------------------


def test_t0_registry_twelve_tools() -> None:
    """T0：TOOLS_SCHEMA 恰 12 条且与契约 §4 清单逐字一致；不设 get_plan_diff。"""
    names = [spec["function"]["name"] for spec in TOOLS_SCHEMA]
    assert names == _CONTRACT_TOOL_NAMES
    assert len(TOOL_MAP) == 12
    assert set(TOOL_MAP) == set(_CONTRACT_TOOL_NAMES)
    assert "get_plan_diff" not in TOOL_MAP  # diff 由 adjust 返回值携带

    # 4 个新工具参数 schema 扁平（无 $defs/$ref/anyOf——_build_parameters_schema 契约）
    for spec in TOOLS_SCHEMA:
        if spec["function"]["name"] in (
            "get_learning_plan",
            "generate_learning_plan",
            "adjust_learning_plan",
            "generate_learning_report",
        ):
            params_json = json.dumps(spec["function"]["parameters"])
            assert "$defs" not in params_json and "$ref" not in params_json
            assert "anyOf" not in params_json


# ---------------------------------------------------------------------------
# T1–T4：逐工具场景
# ---------------------------------------------------------------------------


def test_t1_get_learning_plan_with_and_without(
    app_client: Any, user_a: dict[str, Any]
) -> None:
    """T1：无计划返回说明性 dict（非 error 信封）；有计划返回 {plan, items}。"""
    uid = _get_user_id(app_client, user_a)
    with _db() as db:
        result = _call_tool("get_learning_plan", db, uid, {})
    assert result == {"plan": None, "message": "当前没有进行中的学习计划"}
    assert "error" not in result  # 无计划是正常状态不是失败

    # 造一个当前周计划后返回结构
    from app.models.enums import PlanItemStatus, PlanSource, PlanStatus, Priority
    from app.models.plan import LearningPlan, LearningPlanItem

    today = datetime.now(TZ).date()
    monday = today - timedelta(days=today.weekday())
    with _db() as db:
        plan = LearningPlan(
            user_id=uid, goal_id=None, title="本周计划", version=1,
            status=PlanStatus.ACTIVE, source=PlanSource.AGENT,
            start_date=monday, end_date=monday + timedelta(days=6),
        )
        db.add(plan)
        db.flush()
        db.add(
            LearningPlanItem(
                plan_id=plan.id, plan_date=monday, start_time=_time(19, 0),
                end_time=_time(20, 0), topic="晚自习", task_id=None,
                estimated_minutes=60, priority=Priority.MEDIUM,
                status=PlanItemStatus.PLANNED,
            )
        )
        db.commit()
    with _db() as db:
        result2 = _call_tool("get_learning_plan", db, uid, {})
    assert result2["plan"]["id"] == plan.id
    assert len(result2["items"]) == 1
    assert result2["items"][0]["topic"] == "晚自习"


def test_t2_generate_learning_plan_tool(
    app_client: Any, user_a: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    """T2：工具生成计划返回四键集合（与 HTTP 同一 service 函数）。"""
    _install_dead_plan_llm(monkeypatch)
    uid = _get_user_id(app_client, user_a)
    with _db() as db:
        result = _call_tool("generate_learning_plan", db, uid, {})
    assert set(result.keys()) == {"plan", "items", "unplaced_tasks", "generated_by"}
    assert result["generated_by"] == "rules"
    assert result["items"]


def test_t3_adjust_learning_plan_tool(
    app_client: Any, user_a: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    """T3：缺省当前 active；无 active 返回 error 信封。"""
    _install_dead_plan_llm(monkeypatch)
    uid = _get_user_id(app_client, user_a)
    with _db() as db:
        result = _call_tool("adjust_learning_plan", db, uid, {})
    assert result == {"error": "当前没有进行中的学习计划"}

    # 造一个「未完成 + 截止临近」的当前周计划 → 工具缺省定位并调整
    from app.models.enums import PlanItemStatus, PlanSource, PlanStatus, Priority
    from app.models.plan import LearningPlan, LearningPlanItem
    from app.models.task import Task
    from app.models.enums import TaskSource, TaskStatus

    today = datetime.now(TZ).date()
    monday = today - timedelta(days=today.weekday())
    with _db() as db:
        plan = LearningPlan(
            user_id=uid, goal_id=None, title="本周计划", version=1,
            status=PlanStatus.ACTIVE, source=PlanSource.AGENT,
            start_date=monday, end_date=monday + timedelta(days=6),
        )
        db.add(plan)
        db.flush()
        task = Task(
            user_id=uid, title="临期专项", priority="high",
            deadline=datetime.now(TZ) + timedelta(hours=20),
            status=TaskStatus.TODO, source=TaskSource.MANUAL,
        )
        db.add(task)
        db.flush()
        db.add(
            LearningPlanItem(
                plan_id=plan.id, plan_date=monday, start_time=_time(19, 0),
                end_time=_time(20, 0), topic="临期专项", task_id=task.id,
                estimated_minutes=60, priority=Priority.HIGH,
                status=PlanItemStatus.PLANNED,
            )
        )
        db.commit()
    with _db() as db:
        result2 = _call_tool("adjust_learning_plan", db, uid, {})
    assert result2["adjusted"] is True
    assert result2["adjust_reason"]
    assert set(result2.keys()) == {"plan", "adjust_reason", "diff", "adjusted"}


def test_t4_generate_learning_report_tool(
    app_client: Any, user_a: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    """T4：缺省 weekly 返回报告对象（周期取最近完整周期）。"""
    _install_dead_report_llm(monkeypatch)
    uid = _get_user_id(app_client, user_a)
    with _db() as db:
        result = _call_tool("generate_learning_report", db, uid, {})
    assert result["report_type"] == "weekly"
    assert result["content"]["generated_by"] == "template"
    assert result["summary"]

    with _db() as db:
        result2 = _call_tool("generate_learning_report", db, uid, {"report_type": "daily"})
    assert result2["report_type"] == "daily"


# ---------------------------------------------------------------------------
# T5：非法参数（中文信封 + 注入拒绝）
# ---------------------------------------------------------------------------


def test_t5_invalid_params(app_client: Any, user_a: dict[str, Any]) -> None:
    """T5：adjust 传 plan_id=0 → 中文信封；传 user_id → 注入特例拒绝。"""
    uid = _get_user_id(app_client, user_a)
    with _db() as db:
        result = _call_tool("adjust_learning_plan", db, uid, {"plan_id": 0})
    assert "error" in result and "plan_id" in result["error"]

    with _db() as db:
        result2 = _call_tool("generate_learning_plan", db, uid, {"user_id": 1})
    assert "error" in result2
    assert "user_id" in result2["error"] or "不允许" in result2["error"]


# ---------------------------------------------------------------------------
# T6：对话集成（P11 SSE 通道）
# ---------------------------------------------------------------------------


def _tc(call_id: str, name: str, args: dict[str, Any]) -> dict[str, Any]:
    """构造 OpenAI 形态 tool_call。"""
    return {
        "id": call_id,
        "type": "function",
        "function": {"name": name, "arguments": json.dumps(args)},
    }


def _round(tool_calls: list[dict[str, Any]], finish: str = "tool_calls") -> dict[str, Any]:
    return {"tool_calls": tool_calls, "finish_reason": finish}


def _install_script_llm(
    monkeypatch: pytest.MonkeyPatch, script: list[list[dict[str, Any]]]
) -> None:
    """注入脚本假 LLM 流（P11 惯例——core.py 经 llm.agent_chat_stream）。"""

    async def fake(
        messages: list[dict[str, Any]],
        tools: Any = None,
        max_tokens: int = 2048,
    ) -> Any:
        for part in script.pop(0):
            yield part

    monkeypatch.setattr("app.services.llm.agent_chat_stream", fake)


def _parse_sse(text: str) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for block in text.split("\n\n"):
        block = block.strip()
        if not block:
            continue
        assert block.startswith("data: "), f"非法 SSE 块: {block[:80]}"
        events.append(json.loads(block[len("data: "):]))
    return events


def test_t6_agent_chat_calls_generate_learning_plan(
    app_client: Any, user_a: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    """T6/D6：SSE 对话真实调用 generate_learning_plan → tool_call/tool_result/done。

    大结果（7 天条目）触发 P11 既有截断：truncated=true 且 summary ≤ 500；
    tool 消息落库 content 为完整 JSON（P11 完整回灌机制）。
    """
    _install_dead_plan_llm(monkeypatch)  # 工具内规划 LLM 降级（确定性）
    script = [
        [_round([_tc("call_p12", "generate_learning_plan", {})])],  # 第 1 轮：调工具
        [{"content": "已为你生成下周学习计划。"}, _round([], "stop")],  # 第 2 轮：总结
    ]
    _install_script_llm(monkeypatch, script)

    resp = app_client.post(
        "/api/v1/agent/chat", json={"message": "帮我制定下周学习计划"},
        headers=user_a["headers"],
    )
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/event-stream")
    events = _parse_sse(resp.text)
    types = [e["type"] for e in events]

    assert "thinking" in types
    tool_call_events = [e for e in events if e["type"] == "tool_call"]
    assert len(tool_call_events) == 1
    assert tool_call_events[0]["data"]["name"] == "generate_learning_plan"

    tool_result_events = [e for e in events if e["type"] == "tool_result"]
    assert len(tool_result_events) == 1
    result_data = tool_result_events[0]["data"]
    assert result_data["name"] == "generate_learning_plan"
    # 大结果截断（P11 契约：7 天条目必然触发）
    assert result_data.get("truncated") is True
    assert len(result_data.get("summary", "")) <= 500
    delta_text = "".join(e["data"] for e in events if e["type"] == "delta")
    assert "已为你生成下周学习计划" in delta_text
    assert types[-1] == "done"

    # tool 消息落库 content 为完整 JSON（回灌协议）
    conversation_id = None
    for e in events:
        if e["type"] == "done" and "conversation_id" in e.get("data", {}):
            conversation_id = e["data"]["conversation_id"]
    assert conversation_id is not None
    resp_msgs = app_client.get(
        f"/api/v1/agent/conversations/{conversation_id}/messages",
        headers=user_a["headers"],
    )
    messages = resp_msgs.json()["data"]
    tool_messages = [m for m in messages if m.get("role") == "tool"]
    assert len(tool_messages) == 1
    payload = json.loads(tool_messages[0]["content"])
    assert "plan" in payload and "generated_by" in payload  # 完整 JSON 非摘要
    assert payload["generated_by"] == "rules"


# ---------------------------------------------------------------------------
# T7：双账号隔离
# ---------------------------------------------------------------------------


def test_t7_account_isolation(
    app_client: Any, user_a: dict[str, Any], user_b: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    """T7：user_a 生成计划后 user_b 经工具与 HTTP 均不可见（user_id 注入正确性）。"""
    _install_dead_plan_llm(monkeypatch)
    uid_a = _get_user_id(app_client, user_a)
    uid_b = _get_user_id(app_client, user_b)

    with _db() as db:
        result_a = _call_tool("generate_learning_plan", db, uid_a, {})
    assert result_a["plan"]["user_id"] == uid_a

    with _db() as db:
        result_b = _call_tool("get_learning_plan", db, uid_b, {})
    assert result_b == {"plan": None, "message": "当前没有进行中的学习计划"}

    resp = app_client.get("/api/v1/plans/current", headers=user_b["headers"])
    assert resp.status_code == 200 and resp.json()["data"] is None

    # user_b 不能 diff user_a 的计划
    plan_a_id = result_a["plan"]["id"]
    resp_diff = app_client.get(
        f"/api/v1/plans/{plan_a_id}/diff", headers=user_b["headers"]
    )
    assert resp_diff.status_code == 404
    assert resp_diff.json()["code"] == 1005

    # user_b 调整 user_a 的计划 → error 信封（BizException 1005 转换）
    with _db() as db:
        result_adj = _call_tool("adjust_learning_plan", db, uid_b, {"plan_id": plan_a_id})
    assert "error" in result_adj