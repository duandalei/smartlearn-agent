"""Agent SSE 契约 e2e（tasks.md 组 8，design 2.5.2-C + D13 观测组）。

ASGI TestClient 直调 + **唯一外部 LLM 调用点 mock**（脚本假流注入
``app.services.llm.agent_chat_stream``——core.py 模块属性访问形态）；
工具层走真实实现（临时 SQLite 真实读写）。覆盖：多工具事件序列 /
落库链 / 上下文回灌 / max_tokens / 6 轮上限 / O5 三分支 / 60s 总预算
（O8 monkeypatch 运行时证明）/ 非法工具名 / 错误信封 / 摘要截断 /
LLM 失败双场景 / 落库失败不拖垮 / 受理错误三态 / 慢工具日志 /
D13 上下文体积观测四断言。

P10 测试坑规避：不使用 ``from datetime import time``（防覆盖 stdlib
time）；慢日志断言用自装 logging.Handler 捕获（P10 惯例）。
"""

from __future__ import annotations

import asyncio
import json
import logging
import time as _time
from typing import Any

import pytest

from app.agent.registry import TOOLS_SCHEMA


# ---------------------------------------------------------------------------
# 测试辅助（假流工厂 / SSE 解析 / 断言原语）
# ---------------------------------------------------------------------------
def _tc(call_id: str, name: str, args: dict[str, Any]) -> dict[str, Any]:
    """构造 OpenAI 形态 tool_call。"""
    return {
        "id": call_id,
        "type": "function",
        "function": {"name": name, "arguments": json.dumps(args)},
    }


def _round(
    tool_calls: list[dict[str, Any]], finish: str = "tool_calls"
) -> dict[str, Any]:
    """构造轮终聚合块。"""
    return {"tool_calls": tool_calls, "finish_reason": finish}


def _install_fake_llm(
    monkeypatch: pytest.MonkeyPatch,
    script: list[list[dict[str, Any]]],
    piece_delay_s: float = 0.0,
) -> list[dict[str, Any]]:
    """注入脚本假 LLM 流并捕获每次调用 (messages, tools, max_tokens)。

    脚本项按调用次序消费；**耗尽即 AssertionError**（O5 保护条件测试
    依赖此行为证明「无第 7 次调用」）。
    """
    captured: list[dict[str, Any]] = []
    state = {"n": 0}

    async def fake(
        messages: list[dict[str, Any]],
        tools: Any = None,
        max_tokens: int = 2048,
    ) -> Any:
        captured.append(
            {
                "messages": [dict(m) for m in messages],
                "tools": tools,
                "max_tokens": max_tokens,
            }
        )
        idx = state["n"]
        state["n"] += 1
        assert idx < len(script), f"脚本耗尽：第 {idx + 1} 次意外 LLM 调用"
        for part in script[idx]:
            if piece_delay_s > 0:
                await asyncio.sleep(piece_delay_s)
            yield part

    monkeypatch.setattr("app.services.llm.agent_chat_stream", fake)
    return captured


def _parse_sse(text: str) -> list[dict[str, Any]]:
    """解析 SSE 响应文本为事件 dict 列表（data: {JSON} 块）。"""
    events: list[dict[str, Any]] = []
    for block in text.split("\n\n"):
        block = block.strip()
        if not block:
            continue
        assert block.startswith("data: "), f"非法 SSE 块: {block[:80]}"
        events.append(json.loads(block[len("data: "):]))
    return events


def _chat(
    client: Any,
    user: dict[str, Any],
    message: str,
    conversation_id: int | None = None,
) -> Any:
    """发起一次 Agent chat，返回原始响应。"""
    body: dict[str, Any] = {"message": message}
    if conversation_id is not None:
        body["conversation_id"] = conversation_id
    return client.post(
        "/api/v1/agent/chat", json=body, headers=user["headers"]
    )


def _events_of(
    client: Any,
    user: dict[str, Any],
    message: str,
    conversation_id: int | None = None,
) -> list[dict[str, Any]]:
    """发起 chat 并返回解析后的事件列表。"""
    resp = _chat(client, user, message, conversation_id=conversation_id)
    assert resp.status_code == 200, resp.text
    assert resp.headers["content-type"].startswith("text/event-stream")
    assert resp.headers["cache-control"] == "no-cache"
    return _parse_sse(resp.text)


def _types(events: list[dict[str, Any]]) -> list[str]:
    return [e["type"] for e in events]


def _thinking_rounds(events: list[dict[str, Any]]) -> list[int]:
    """带 round 的 thinking 轮次信号（决策 A6 两形态之轮次形态）。"""
    return [
        e["data"]["round"] for e in events if e["type"] == "thinking" and "round" in e["data"]
    ]


def _done_of(events: list[dict[str, Any]]) -> dict[str, Any]:
    done = [e for e in events if e["type"] == "done"]
    assert len(done) == 1, f"done 事件数异常: {len(done)}"
    return done[0]["data"]


def _messages_of(
    client: Any, user: dict[str, Any], conversation_id: int
) -> list[dict[str, Any]]:
    resp = client.get(
        f"/api/v1/agent/conversations/{conversation_id}/messages",
        headers=user["headers"],
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["data"]


class _LogCapture(logging.Handler):
    """自装日志捕获（P10 惯例，避免 caplog 传播差异）。"""

    def __init__(self, logger_name: str, level: int) -> None:
        super().__init__(level=level)
        self.lines: list[str] = []
        self._logger = logging.getLogger(logger_name)
        self._logger.addHandler(self)

    def close(self) -> None:
        self._logger.removeHandler(self)
        super().close()

    def emit(self, record: logging.LogRecord) -> None:
        self.lines.append(record.getMessage())


# ---------------------------------------------------------------------------
# 8.2 多工具事件序列 + 落库链 + 上下文回灌 + max_tokens（D1/D3/D4）
# ---------------------------------------------------------------------------
def test_multi_tool_event_sequence(
    app_client: Any,
    user_a: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """轮 1 三 tool_calls → 轮 2 文本：SSE 序列与偏序契约（D1/D3）。"""
    script = [
        [
            _round(
                [
                    _tc("call_1", "get_learning_statistics", {"days": 7}),
                    _tc("call_2", "get_tasks", {}),
                    _tc("call_3", "get_knowledge_mastery", {}),
                ]
            )
        ],
        [
            {"content": "近 7 天你共学习 0 分钟，暂无任务与知识点记录。"},
            _round([], "stop"),
        ],
    ]
    captured = _install_fake_llm(monkeypatch, script)
    events = _events_of(app_client, user_a, "我最近学习怎么样")

    assert _types(events) == [
        "thinking",
        "tool_call",
        "tool_call",
        "tool_call",
        "tool_result",
        "tool_result",
        "tool_result",
        "thinking",
        "delta",
        "done",
    ]
    assert _thinking_rounds(events) == [1, 2]
    # tool_call 载荷：解析后参数对象 + call_id 配对（R2 补充约束 2）。
    tool_calls = [e["data"] for e in events if e["type"] == "tool_call"]
    assert tool_calls[0]["arguments"] == {"days": 7}
    assert tool_calls[0]["name"] == "get_learning_statistics"
    results = [e["data"] for e in events if e["type"] == "tool_result"]
    assert {r["call_id"] for r in results} == {t["call_id"] for t in tool_calls}
    for r in results:
        assert set(r.keys()) == {
            "call_id",
            "name",
            "ok",
            "elapsed_ms",
            "summary",
            "truncated",
        }
        assert r["ok"] is True
        if r["truncated"]:
            # 大结果（statistics 含 trend 七日序列）截断是 D3 预期。
            assert len(r["summary"]) <= 500
    # done 五字段与统计一致。
    done = _done_of(events)
    assert done["rounds"] == 2
    assert done["tool_call_count"] == 3
    assert done["finish_reason"] == "normal"
    assert done["conversation_id"] > 0
    assert done["message_id"] is not None
    # captured messages：回灌序列 system + user + assistant(tc×3) + tool×3。
    assert captured[0]["tools"] == TOOLS_SCHEMA
    assert captured[0]["max_tokens"] == 2048
    first = captured[0]["messages"]
    assert first[0]["role"] == "system"
    assert first[-1]["role"] == "user"
    second = captured[1]["messages"]
    assert second[-4]["role"] == "assistant"
    assert len(second[-4]["tool_calls"]) == 3
    assert [m["role"] for m in second[-3:]] == ["tool", "tool", "tool"]


def test_persist_chain_and_context_reload(
    app_client: Any,
    user_a: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """落库链成对有序；第二次请求历史成对回灌（D4 / 规则 5）。"""
    script = [
        [_round([_tc("call_1", "get_knowledge_mastery", {})])],
        [{"content": "还没有学习记录。"}, _round([], "stop")],
    ]
    captured = _install_fake_llm(monkeypatch, script)
    events = _events_of(app_client, user_a, "我的掌握度怎么样")
    cid = _done_of(events)["conversation_id"]

    messages = _messages_of(app_client, user_a, cid)
    assert [m["role"] for m in messages] == [
        "user",
        "assistant",
        "tool",
        "assistant",
    ]
    assert messages[1]["tool_calls"][0]["id"] == "call_1"
    assert messages[2]["tool_call_id"] == "call_1"
    assert messages[2]["tool_name"] == "get_knowledge_mastery"

    # 第二次请求（带 conversation_id）：重装假流（脚本状态重置），
    # captured_b 首条（system 后）非孤立 tool、历史成对出现。
    captured_b = _install_fake_llm(monkeypatch, script)
    events2 = _events_of(app_client, user_a, "再看看呢", conversation_id=cid)
    assert _done_of(events2)["conversation_id"] == cid
    history = captured_b[0]["messages"]
    assert history[0]["role"] == "system"
    assert history[1]["role"] != "tool"
    roles = [m["role"] for m in history]
    assert "assistant" in roles and "tool" in roles
    tool_idx = roles.index("tool")
    assert roles[tool_idx - 1] == "assistant"


def test_resume_conversation_promotes_in_list(
    app_client: Any,
    user_a: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """续聊会话在倒序列表升至首位（spec 5.4.1 规则 4 行为级验证）。"""
    _install_fake_llm(
        monkeypatch, [[{"content": "好。"}, _round([], "stop")]]
    )
    events = _events_of(app_client, user_a, "第一通")
    cid = _done_of(events)["conversation_id"]
    _install_fake_llm(
        monkeypatch, [[{"content": "好。"}, _round([], "stop")]]
    )
    _events_of(app_client, user_a, "另一通")
    _install_fake_llm(
        monkeypatch, [[{"content": "续聊。"}, _round([], "stop")]]
    )
    _events_of(app_client, user_a, "继续", conversation_id=cid)
    resp = app_client.get(
        "/api/v1/agent/conversations?page=1&page_size=10",
        headers=user_a["headers"],
    )
    assert resp.status_code == 200
    assert resp.json()["data"]["items"][0]["id"] == cid


# ---------------------------------------------------------------------------
# 8.3 6 轮上限 + O5 三分支 + 60s 总预算（D6/D7）
# ---------------------------------------------------------------------------
def test_rounds_limit_with_summary_call(
    app_client: Any,
    user_a: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """6 轮上限 + O5 分支①：第 7 次总结调用（tools 不传、无 thinking）。"""
    script = [
        [_round([_tc(f"call_{i}", "get_knowledge_mastery", {})])]
        for i in range(1, 7)
    ] + [
        [{"content": "总结：你还没有学习记录。"}, _round([], "stop")],
    ]
    captured = _install_fake_llm(monkeypatch, script)
    events = _events_of(app_client, user_a, "查一下")

    assert len(captured) == 7
    assert captured[6]["tools"] is None  # 总结调用禁工具（决策 A7）
    assert _thinking_rounds(events) == [1, 2, 3, 4, 5, 6]  # 无第 7 条
    done = _done_of(events)
    assert done["finish_reason"] == "max_rounds"
    assert done["rounds"] == 6
    assert done["tool_call_count"] == 6
    assert "error" not in _types(events)
    # 总结产出以 delta 推送。
    deltas = [e["data"] for e in events if e["type"] == "delta"]
    assert any("总结" in d for d in deltas)
    # 落库 6 轮链完整。
    messages = _messages_of(app_client, user_a, done["conversation_id"])
    tool_rounds = [m for m in messages if m["role"] == "assistant" and m["tool_calls"]]
    assert len(tool_rounds) == 6


def test_rounds_limit_o5_protect_template(
    app_client: Any,
    user_a: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """O5 分支③（保护条件）：剩余 < 15s → 无总结调用、模板拼接。"""
    monkeypatch.setattr("app.agent.core.GRACEFUL_MIN_BUDGET_S", 61.0)
    script = [
        [_round([_tc(f"call_{i}", "get_knowledge_mastery", {})])]
        for i in range(1, 7)
    ]
    captured = _install_fake_llm(monkeypatch, script)
    events = _events_of(app_client, user_a, "查一下")

    assert len(captured) == 6  # 无第 7 次总结调用
    done = _done_of(events)
    assert done["finish_reason"] == "max_rounds"
    deltas = [e["data"] for e in events if e["type"] == "delta"]
    assert any("已为你查询到以下信息" in d for d in deltas)


def test_timeout_budget_template(
    app_client: Any,
    user_a: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """60s 总预算（O8 monkeypatch）：timeout 收尾、模板拼接、无总结。"""
    monkeypatch.setattr("app.agent.core.TOTAL_BUDGET_S", 1.0)
    slow_script = [
        [{"content": "片"} for _ in range(40)]
        + [_round([_tc("call_slow", "get_knowledge_mastery", {})])]
    ]
    captured = _install_fake_llm(monkeypatch, slow_script, piece_delay_s=0.05)
    started = _time.monotonic()
    events = _events_of(app_client, user_a, "慢速查询")
    elapsed = _time.monotonic() - started

    done = _done_of(events)
    assert done["finish_reason"] == "timeout"
    assert "error" not in _types(events)
    assert len(captured) == 1  # 无总结调用（剩余必 < 15s 保护线）
    deltas = [e["data"] for e in events if e["type"] == "delta"]
    assert any("已为你查询到以下信息" in d or "处理时间较长" in d for d in deltas)
    # 总耗时 ≤ 预算 + 单步容忍（软预算：在途轮不硬中断）。
    assert elapsed <= 1.0 + 8.0


def test_o5_summary_degrade_to_template(
    app_client: Any,
    user_a: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """O5 分支②：总结调用抛 BizException → 降级模板拼接。"""
    from app.core.response import BizException

    script = [
        [_round([_tc(f"call_{i}", "get_knowledge_mastery", {})])]
        for i in range(1, 7)
    ]
    captured = _install_fake_llm(monkeypatch, script)

    async def failing_summary(
        messages: list[dict[str, Any]], tools: Any = None, max_tokens: int = 2048
    ) -> Any:
        if captured and len(captured) >= 6:
            raise BizException(3000, "AI 服务暂时不可用，请稍后重试")
        idx = len(captured) - 1
        for part in script[idx]:
            yield part

    # 重新安装：第 7 次调用（idx 6 越界 → 抛 BizException）。
    state = {"n": 0}

    async def fake(
        messages: list[dict[str, Any]], tools: Any = None, max_tokens: int = 2048
    ) -> Any:
        idx = state["n"]
        state["n"] += 1
        if idx >= 6:
            raise BizException(3000, "AI 服务暂时不可用，请稍后重试")
        for part in script[idx]:
            yield part

    monkeypatch.setattr("app.services.llm.agent_chat_stream", fake)
    events = _events_of(app_client, user_a, "查一下")
    done = _done_of(events)
    assert done["finish_reason"] == "max_rounds"
    deltas = [e["data"] for e in events if e["type"] == "delta"]
    assert any("已为你查询到以下信息" in d for d in deltas)
    assert "error" not in _types(events)


# ---------------------------------------------------------------------------
# 8.4 异常与边界全家桶（D5/D8/D9/D11 + 截断 + 受理错误）
# ---------------------------------------------------------------------------
def test_illegal_tool_name_continues(
    app_client: Any,
    user_a: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """非法工具名：ok=false「该工具不可用」、对话继续（D5）。"""
    script = [
        [
            _round(
                [
                    _tc("call_bad", "foo_bar", {}),
                    _tc("call_ok", "get_knowledge_mastery", {}),
                ]
            )
        ],
        [{"content": "查询完成。"}, _round([], "stop")],
    ]
    captured = _install_fake_llm(monkeypatch, script)
    events = _events_of(app_client, user_a, "帮我查")

    results = [e["data"] for e in events if e["type"] == "tool_result"]
    assert len(results) == 2
    bad = next(r for r in results if r["call_id"] == "call_bad")
    assert bad["ok"] is False
    assert "该工具不可用" in bad["summary"]
    assert bad["elapsed_ms"] == 0
    assert _done_of(events)["finish_reason"] == "normal"
    # 落库 tool_name 照存（截断 50 内无需截断）。
    messages = _messages_of(
        app_client, user_a, _done_of(events)["conversation_id"]
    )
    tool_rows = [m for m in messages if m["role"] == "tool"]
    assert any(m["tool_name"] == "foo_bar" for m in tool_rows)
    # 回灌 content 为同款信封 JSON（LLM 自纠通道统一）。
    tool_msg = json.loads(
        next(m["content"] for m in tool_rows if m["tool_name"] == "foo_bar")
    )
    assert tool_msg["error"] == "该工具不可用"


def test_error_envelope_self_correction(
    app_client: Any,
    user_a: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """错误信封回灌：days=999 → ok=false、LLM 收到错误文案（规则 9）。"""
    script = [
        [
            _round(
                [_tc("call_env", "get_learning_records", {"days": 999})]
            )
        ],
        [{"content": "参数超范围了。"}, _round([], "stop")],
    ]
    captured = _install_fake_llm(monkeypatch, script)
    events = _events_of(app_client, user_a, "查近 999 天记录")

    results = [e["data"] for e in events if e["type"] == "tool_result"]
    assert results[0]["ok"] is False
    assert results[0]["truncated"] is False
    assert _done_of(events)["finish_reason"] == "normal"
    # 回灌 content 为信封 JSON（LLM 收到错误文案——P10 自纠机制被消费）。
    second = captured[1]["messages"]
    tool_contents = [m["content"] for m in second if m["role"] == "tool"]
    assert tool_contents
    envelope = json.loads(tool_contents[-1])
    assert "error" in envelope


def test_summary_truncation(
    app_client: Any,
    user_a: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """大结果摘要截断：≤500 且 truncated=true；小结果原样（D3）。"""
    # 直插 100 条学习记录（近 7 天）驱动真实工具大结果。
    from datetime import date, timedelta

    from app.db.session import SessionLocal
    from app.models.record import LearningRecord

    resp = app_client.get("/api/v1/auth/me", headers=user_a["headers"])
    uid = resp.json()["data"]["id"]
    today = date.today()
    with SessionLocal() as db:
        for i in range(100):
            db.add(
                LearningRecord(
                    user_id=uid,
                    content=f"学习记录 {i}：内容详情较长一些用于撑大结果体积 abcdefghijklmnop",
                    duration_minutes=30,
                    knowledge_points=json.dumps(["机器学习"]),
                    study_date=today - timedelta(days=i % 7),
                )
            )
        db.commit()

    script = [
        [
            _round(
                [
                    _tc("call_big", "get_learning_records", {"days": 7}),
                    _tc("call_small", "get_knowledge_mastery", {}),
                ]
            )
        ],
        [{"content": "查完了。"}, _round([], "stop")],
    ]
    _install_fake_llm(monkeypatch, script)
    events = _events_of(app_client, user_a, "查全部")

    results = {e["data"]["call_id"]: e["data"] for e in events if e["type"] == "tool_result"}
    big = results["call_big"]
    small = results["call_small"]
    assert big["truncated"] is True
    assert len(big["summary"]) <= 500
    assert small["truncated"] is False
    assert json.loads(small["summary"])["total"] == 0


def test_llm_fail_bizexception(
    app_client: Any,
    user_a: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """LLM 创建即抛 BizException → error 事件；user 消息已落库（D11/裁决 #12）。"""
    from app.core.response import BizException

    async def fake(
        messages: list[dict[str, Any]], tools: Any = None, max_tokens: int = 2048
    ) -> Any:
        raise BizException(3000, "AI 服务暂时不可用，请稍后重试")
        yield  # pragma: no cover - 使其为异步生成器

    monkeypatch.setattr("app.services.llm.agent_chat_stream", fake)
    resp = _chat(app_client, user_a, "你好")
    assert resp.status_code == 200
    events = _parse_sse(resp.text)
    assert _types(events) == ["thinking", "error"]
    assert events[-1]["data"]["code"] == 3000
    assert events[-1]["data"]["message"] == "AI 服务暂时不可用，请稍后重试"
    # user 消息保留（裁决 #12 验收）。
    body = json.loads(
        [b for b in resp.text.split("\n\n") if "error" in b][0][len("data: "):]
    )
    # conversation_id 不在 error data 中——从会话列表反查。
    resp = app_client.get(
        "/api/v1/agent/conversations?page=1&page_size=10", headers=user_a["headers"]
    )
    items = resp.json()["data"]["items"]
    assert items
    messages = _messages_of(app_client, user_a, items[0]["id"])
    assert [m["role"] for m in messages] == ["user"]


def test_llm_fail_midstream(
    app_client: Any,
    user_a: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """流中途异常（首 delta 后）→ error「回答生成中断，请重试」（D11）。"""
    script: list[list[dict[str, Any]]] = [[]]
    state = {"n": 0}

    async def fake(
        messages: list[dict[str, Any]], tools: Any = None, max_tokens: int = 2048
    ) -> Any:
        idx = state["n"]
        state["n"] += 1
        yield {"content": "部分回答"}
        raise RuntimeError("流中断模拟")

    monkeypatch.setattr("app.services.llm.agent_chat_stream", fake)
    events = _events_of(app_client, user_a, "你好")
    assert _types(events) == ["thinking", "delta", "error"]
    assert events[-1]["data"]["code"] == 3000
    assert events[-1]["data"]["message"] == "回答生成中断，请重试"


def test_save_final_failure_not_fatal(
    app_client: Any,
    user_a: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """save_final_message 抛异常 → done(message_id=null)、无 error（规则 4.2-6）。"""
    import app.agent.memory as memory_module

    _install_fake_llm(
        monkeypatch, [[{"content": "正常回答。"}, _round([], "stop")]]
    )

    def raising_save(db: Any, conversation: Any, content: str) -> int | None:
        raise RuntimeError("落库炸了（模拟）")

    monkeypatch.setattr(memory_module, "save_final_message", raising_save)
    events = _events_of(app_client, user_a, "你好")
    done = _done_of(events)
    assert done["message_id"] is None
    assert done["finish_reason"] == "normal"
    assert "error" not in _types(events)


def test_auth_and_acceptance_errors(app_client: Any, user_a: dict[str, Any]) -> None:
    """受理错误三态：401/1003、422/1001、404/1005（D9，统一 JSON 非 SSE）。"""
    resp = app_client.post(
        "/api/v1/agent/chat", json={"message": "未登录提问"}
    )
    assert resp.status_code == 401
    assert resp.json()["code"] == 1003
    assert "text/event-stream" not in resp.headers.get("content-type", "")

    headers = user_a["headers"]
    resp = app_client.post(
        "/api/v1/agent/chat", json={"message": "   "}, headers=headers
    )
    assert resp.status_code == 422
    assert resp.json()["code"] == 1001
    resp = app_client.post(
        "/api/v1/agent/chat", json={"message": "x" * 2001}, headers=headers
    )
    assert resp.status_code == 422
    resp = app_client.post(
        "/api/v1/agent/chat",
        json={"message": "hi", "conversation_id": "abc"},
        headers=headers,
    )
    assert resp.status_code == 422
    resp = app_client.post(
        "/api/v1/agent/chat",
        json={"message": "hi", "conversation_id": 99999},
        headers=headers,
    )
    assert resp.status_code == 404
    assert resp.json()["code"] == 1005


def test_slow_tool_log(
    app_client: Any,
    user_a: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """慢工具（>300ms）→ agent_tool_slow 三字段 warning（D8，P10 Handler 惯例）。"""
    import app.agent.tools as tools_module

    original = tools_module.get_board

    def slow_get_board(db: Any, user_id: int) -> dict[str, Any]:
        _time.sleep(0.4)
        return original(db, user_id)

    monkeypatch.setattr(tools_module, "get_board", slow_get_board)
    script = [
        [_round([_tc("call_slow", "get_tasks", {})])],
        [{"content": "查询完成。"}, _round([], "stop")],
    ]
    _install_fake_llm(monkeypatch, script)

    capture = _LogCapture("app.agent.tools", logging.WARNING)
    try:
        events = _events_of(app_client, user_a, "我的任务")
    finally:
        capture.close()
    slow_lines = [line for line in capture.lines if "agent_tool_slow" in line]
    assert slow_lines, f"未捕获慢日志: {capture.lines[:3]}"
    line = slow_lines[0]
    assert "tool_name=get_tasks" in line
    assert "user_id=" in line
    assert "elapsed_ms=" in line
    assert _done_of(events)["finish_reason"] == "normal"


# ---------------------------------------------------------------------------
# 8.5 上下文体积观测（D13——R3 补充约束 3）
# ---------------------------------------------------------------------------
def test_context_size_debug_each_round(
    app_client: Any,
    user_a: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """每轮 LLM 调用前 debug 级 agent_context_size 三字段（D13）。"""
    script = [
        [_round([_tc("call_1", "get_knowledge_mastery", {})])],
        [{"content": "查完了。"}, _round([], "stop")],
    ]
    _install_fake_llm(monkeypatch, script)
    with caplog.at_level(logging.DEBUG, logger="app.agent.core"):
        events = _events_of(app_client, user_a, "查一下")
    lines = [r for r in caplog.records if "agent_context_size" in r.message]
    assert len(lines) == 2
    assert all(r.levelno == logging.DEBUG for r in lines)
    rounds = []
    for record in lines:
        assert "conversation_id=" in record.message
        assert "chars=" in record.message
        rounds.append(int(record.message.split("round=")[1].split()[0]))
    assert rounds == [1, 2]


def test_context_size_warning_threshold(
    app_client: Any,
    user_a: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """chars > 30000 的轮次升 warning 同三字段（阈值边界）。"""
    from app.db.session import SessionLocal
    from app.models.agent import AgentConversation

    resp = app_client.get("/api/v1/auth/me", headers=user_a["headers"])
    uid = resp.json()["data"]["id"]
    with SessionLocal() as db:
        convo = AgentConversation(user_id=uid, title=None)
        db.add(convo)
        db.commit()
        cid = convo.id
    from app.models.agent import AgentMessage
    from app.models.enums import MessageRole

    big_content = "长" * 32000
    with SessionLocal() as db:
        db.add(
            AgentMessage(
                conversation_id=cid,
                role=MessageRole.USER,
                content=big_content,
            )
        )
        db.commit()

    _install_fake_llm(
        monkeypatch, [[{"content": "收到。"}, _round([], "stop")]]
    )
    with caplog.at_level(logging.DEBUG, logger="app.agent.core"):
        events = _events_of(app_client, user_a, "继续", conversation_id=cid)
    warnings = [
        r
        for r in caplog.records
        if "agent_context_size" in r.message and r.levelno == logging.WARNING
    ]
    assert warnings, "大上下文未升 warning"
    chars = int(warnings[0].message.split("chars=")[1].split()[0])
    assert chars > 30000
    assert _done_of(events)["finish_reason"] == "normal"


def test_context_size_observation_no_truncation(
    app_client: Any,
    user_a: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """观测不改内容：两个独立会话同脚本 → captured messages 逐字节一致。"""
    script = [
        [_round([_tc("call_1", "get_knowledge_mastery", {})])],
        [{"content": "查完了。"}, _round([], "stop")],
    ]
    captured_a = _install_fake_llm(monkeypatch, script)
    _events_of(app_client, user_a, "查一下")
    captured_b = _install_fake_llm(monkeypatch, script)
    _events_of(app_client, user_a, "查一下")

    dump_a = json.dumps(captured_a[0]["messages"], sort_keys=True)
    dump_b = json.dumps(captured_b[0]["messages"], sort_keys=True)
    assert dump_a == dump_b  # 逐字节一致（不截断的直接验证）
    assert '"role": "system"' in dump_a


def test_context_size_not_in_sse(
    app_client: Any,
    user_a: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """观测不进 SSE：全部事件不含 agent_context_size / chars 字段。"""
    script = [
        [_round([_tc("call_1", "get_knowledge_mastery", {})])],
        [{"content": "查完了。"}, _round([], "stop")],
    ]
    _install_fake_llm(monkeypatch, script)
    events = _events_of(app_client, user_a, "查一下")
    payload = json.dumps(events, ensure_ascii=False)
    assert "agent_context_size" not in payload
    assert "chars" not in payload

# ---------------------------------------------------------------------------
# 8.x tool_result sources 扩展（L2 agent_absorb_ask，design 2.1.3-B）
# monkeypatch 口径（tasks 2.3 修订）：patch app.agent.tools 模块全局
# search_knowledge（TOOL_MAP 在 registry，tools.py 内不存在 TOOL_MAP）——
# 真实 search_knowledge_base 包装函数（tool_endpoint 参数校验链路保留）
# 经模块全局 search_knowledge 返回假数据。
# ---------------------------------------------------------------------------
def _search_hit(idx: int, content_len: int = 30) -> dict[str, Any]:
    """构造一条合法六字段检索命中（content 长度由 content_len 控制）。"""
    return {
        "content": f"第{idx}条命中片段" + "文" * content_len,
        "source_title": f"线性代数要点笔记 » 第{idx}章",
        "score": round(0.9 - idx * 0.01, 4),
        "item_id": idx + 1,
        "chunk_index": idx,
        "scope": "personal" if idx % 2 else "public",
    }


def _install_fake_search(monkeypatch: pytest.MonkeyPatch, payload: Any) -> None:
    """patch app.agent.tools.search_knowledge 模块全局返回假检索结果。

    payload 为 Exception 实例时抛出（走 tool_endpoint → error 信封真实
    链路）；否则原样返回（如 {mode, results}）。
    """

    async def fake_search(*args: Any, **kwargs: Any) -> Any:
        if isinstance(payload, Exception):
            raise payload
        return payload

    monkeypatch.setattr("app.agent.tools.search_knowledge", fake_search)


def _search_script(
    args: dict[str, Any] | None = None,
) -> list[list[dict[str, Any]]]:
    """轮 1 单次 search_knowledge_base 调用 → 轮 2 文本收尾。"""
    return [
        [
            _round(
                [
                    _tc(
                        "call_1",
                        "search_knowledge_base",
                        args or {"query": "特征值分解"},
                    )
                ]
            )
        ],
        [{"content": "根据检索到的内容作答。"}, _round([], "stop")],
    ]


def _sole_tool_result(events: list[dict[str, Any]]) -> dict[str, Any]:
    results = [e["data"] for e in events if e["type"] == "tool_result"]
    assert len(results) == 1, f"tool_result 数异常: {len(results)}"
    return results[0]


_SOURCE_KEYS = {"source_title", "content", "score", "item_id", "chunk_index", "scope"}
_LEGACY_KEYS = {"call_id", "name", "ok", "elapsed_ms", "summary", "truncated"}


def test_search_sources_hit(
    app_client: Any,
    user_a: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """命中：tool_result 含 sources 键、2 条六字段齐、content ≤240、六旧字段仍在。"""
    _install_fake_llm(monkeypatch, _search_script())
    _install_fake_search(
        monkeypatch,
        {"mode": "online", "results": [_search_hit(1), _search_hit(2)]},
    )
    events = _events_of(app_client, user_a, "我的笔记里特征值分解在 PCA 里起什么作用？")
    r = _sole_tool_result(events)
    assert r["ok"] is True
    assert r["name"] == "search_knowledge_base"
    assert _LEGACY_KEYS <= set(r.keys())
    sources = r["sources"]
    assert len(sources) == 2
    for s in sources:
        assert set(s.keys()) == _SOURCE_KEYS
        assert len(s["content"]) <= 240
        assert s["scope"] in ("personal", "public")
        assert isinstance(s["score"], float)


def test_search_sources_empty_hit(
    app_client: Any,
    user_a: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """空命中：results=[] → sources 键存在且 == []、ok True（查过没查到）。"""
    _install_fake_llm(monkeypatch, _search_script())
    _install_fake_search(monkeypatch, {"mode": "online", "results": []})
    events = _events_of(app_client, user_a, "什么是量子纠缠")
    r = _sole_tool_result(events)
    assert r["ok"] is True
    assert "sources" in r
    assert r["sources"] == []


def test_search_sources_failure(
    app_client: Any,
    user_a: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """检索失败：error 信封 → tool_result 无 sources 键、ok False（禁伪造）。"""
    from app.core.response import CODE_VECTOR_FAILED, BizException

    _install_fake_llm(monkeypatch, _search_script())
    _install_fake_search(
        monkeypatch, BizException(CODE_VECTOR_FAILED, "知识库检索暂不可用")
    )
    events = _events_of(app_client, user_a, "我的笔记里特征值分解怎么写的？")
    r = _sole_tool_result(events)
    assert r["ok"] is False
    assert "sources" not in r
    assert set(r.keys()) == _LEGACY_KEYS


def test_search_sources_truncation_and_limit(
    app_client: Any,
    user_a: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """截断限量：25 条 × 300+ 字 → sources 恰 20 条、每条 content ≤240。"""
    _install_fake_llm(monkeypatch, _search_script())
    payload = {
        "mode": "online",
        "results": [_search_hit(i, content_len=300) for i in range(25)],
    }
    _install_fake_search(monkeypatch, payload)
    events = _events_of(app_client, user_a, "Transformer 的注意力机制是什么？")
    r = _sole_tool_result(events)
    assert r["ok"] is True
    sources = r["sources"]
    assert len(sources) == 20
    for s in sources:
        assert len(s["content"]) <= 240
        assert set(s.keys()) == _SOURCE_KEYS
        assert s["scope"] in ("personal", "public")