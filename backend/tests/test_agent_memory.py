"""Agent memory 单测 + 会话管理端点行为（tasks.md 组 7，design 2.5.2-B 八组）。

覆盖：会话 CRUD / 标题截断 O4 / 列表倒序 O2（含同秒 id tie-break）/
空会话 / 双账号隔离 D9 / 窗口成对截断 O7 / updated_at 触碰行为级
验证 / 消息全量还原链 D4。LLM 以脚本假流注入（模块属性形态），
工具层走真实实现。

覆盖验收：D4 / D9 / D10；O2 / O3 / O4 / O7。
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

import pytest

from app.agent.memory import load_context_window


# ---------------------------------------------------------------------------
# 测试辅助（脚本假流 / 消息直插 / chat 发起）
# ---------------------------------------------------------------------------
def _tc(call_id: str, name: str, args: dict[str, Any]) -> dict[str, Any]:
    """构造 OpenAI 形态 tool_call。"""
    return {
        "id": call_id,
        "type": "function",
        "function": {"name": name, "arguments": json.dumps(args)},
    }


def _round(tool_calls: list[dict[str, Any]], finish: str = "tool_calls") -> dict[str, Any]:
    """构造轮终聚合块。"""
    return {"tool_calls": tool_calls, "finish_reason": finish}


def _install_script_llm(
    monkeypatch: pytest.MonkeyPatch, script: list[list[dict[str, Any]]]
) -> list[dict[str, Any]]:
    """注入脚本假 LLM 流并捕获每次调用入参（脚本耗尽时重复末项）。"""
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
        idx = min(state["n"], len(script) - 1)
        state["n"] += 1
        for part in script[idx]:
            yield part

    monkeypatch.setattr("app.services.llm.agent_chat_stream", fake)
    return captured


def _simple_script(text: str = "好的。") -> list[list[dict[str, Any]]]:
    """单轮文本脚本。"""
    return [[{"content": text}, _round([], "stop")]]


def _chat(
    client: Any,
    user: dict[str, Any],
    message: str,
    conversation_id: int | None = None,
    monkeypatch: pytest.MonkeyPatch | None = None,
    script: list[list[dict[str, Any]]] | None = None,
) -> Any:
    """发起一次 Agent chat（先安装假流再 POST，返回原始响应）。"""
    if monkeypatch is not None:
        _install_script_llm(
            monkeypatch, script if script is not None else _simple_script()
        )
    body: dict[str, Any] = {"message": message}
    if conversation_id is not None:
        body["conversation_id"] = conversation_id
    return client.post(
        "/api/v1/agent/chat", json=body, headers=user["headers"]
    )


def _add_message(
    conversation_id: int,
    role: str,
    content: str,
    tool_name: str | None = None,
    tool_calls: list[dict[str, Any]] | None = None,
    tool_call_id: str | None = None,
) -> None:
    """ORM 直插一条 Agent 消息（窗口截断测试的数据构造）。"""
    from app.db.session import SessionLocal
    from app.models.agent import AgentMessage
    from app.models.enums import MessageRole

    with SessionLocal() as db:
        db.add(
            AgentMessage(
                conversation_id=conversation_id,
                role=MessageRole(role),
                content=content,
                tool_name=tool_name,
                tool_calls=tool_calls,
                tool_call_id=tool_call_id,
            )
        )
        db.commit()


def _user_id(client: Any, user: dict[str, Any]) -> int:
    """经 /auth/me 获取当前用户 id（fixture 不直接携带）。"""
    resp = client.get("/api/v1/auth/me", headers=user["headers"])
    assert resp.status_code == 200, resp.text
    return resp.json()["data"]["id"]


def _make_conversation(user_id: int, title: str | None) -> int:
    """直插会话并返回 id。"""
    from app.db.session import SessionLocal
    from app.models.agent import AgentConversation

    with SessionLocal() as db:
        convo = AgentConversation(user_id=user_id, title=title)
        db.add(convo)
        db.commit()
        return convo.id


def _get_conversation(db_obj: Any, conversation_id: int) -> Any:
    """取会话 ORM 对象（load_context_window 入参）。"""
    from app.models.agent import AgentConversation

    return db_obj.get(AgentConversation, conversation_id)


# ---------------------------------------------------------------------------
# 7.1 会话 CRUD / 标题截断 / 列表倒序 / 空会话（D10）
# ---------------------------------------------------------------------------
def test_conversation_crud(app_client: Any, user_a: dict[str, Any]) -> None:
    """新建（显式/空 title）→ 重命名（边界 422）→ 删除后 404。"""
    headers = user_a["headers"]

    resp = app_client.post(
        "/api/v1/agent/conversations", json={"title": None}, headers=headers
    )
    assert resp.status_code == 200, resp.text
    created = resp.json()["data"]
    assert created["title"] is None
    cid = created["id"]

    resp = app_client.post(
        "/api/v1/agent/conversations", json={"title": "我的会话"}, headers=headers
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["data"]["title"] == "我的会话"

    resp = app_client.patch(
        f"/api/v1/agent/conversations/{cid}",
        json={"title": "新名字"},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["data"]["title"] == "新名字"

    for bad in ("", "x" * 201):
        resp = app_client.patch(
            f"/api/v1/agent/conversations/{cid}",
            json={"title": bad},
            headers=headers,
        )
        assert resp.status_code == 422, resp.text
        assert resp.json()["code"] == 1001

    resp = app_client.delete(
        f"/api/v1/agent/conversations/{cid}", headers=headers
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["data"] is None

    resp = app_client.get(
        f"/api/v1/agent/conversations/{cid}/messages", headers=headers
    )
    assert resp.status_code == 404
    assert resp.json()["code"] == 1005


def test_title_truncate_o4(
    app_client: Any, user_a: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    """首条 30 字符 user 消息 → title 为前 20 字符（O4 裁定）。"""
    message = "一二三四五六七八九十" * 3
    assert len(message) == 30
    resp = _chat(app_client, user_a, message, monkeypatch=monkeypatch)
    assert resp.status_code == 200, resp.text

    resp = app_client.get(
        "/api/v1/agent/conversations?page=1&page_size=10", headers=user_a["headers"]
    )
    assert resp.status_code == 200, resp.text
    items = resp.json()["data"]["items"]
    assert items, "会话列表为空"
    assert items[0]["title"] == message[:20]


def test_list_order_desc_and_tiebreak(
    app_client: Any, user_a: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    """多会话按最近活跃倒序（O2）；同秒并列 id 倒序 tie-break。"""
    cids: list[int] = []
    for _ in range(3):
        resp = _chat(app_client, user_a, "你好", monkeypatch=monkeypatch)
        assert resp.status_code == 200, resp.text
        body = json.loads(
            [b for b in resp.text.split("\n\n") if "done" in b][0][len("data: "):]
        )
        cids.append(body["data"]["conversation_id"])

    resp = app_client.get(
        "/api/v1/agent/conversations?page=1&page_size=10", headers=user_a["headers"]
    )
    assert resp.status_code == 200, resp.text
    items = resp.json()["data"]["items"]
    assert [item["id"] for item in items[:3]] == list(reversed(cids))

    # tie-break：直插两条相同 updated_at 的会话 → id 大的在前。
    from app.db.session import SessionLocal
    from app.models.agent import AgentConversation

    uid = _user_id(app_client, user_a)
    fixed_time = datetime(2026, 1, 1, tzinfo=timezone.utc)
    with SessionLocal() as db:
        for _ in range(2):
            convo = AgentConversation(user_id=uid, title=None)
            db.add(convo)
            db.flush()
            convo.updated_at = fixed_time
        db.commit()
    resp = app_client.get(
        "/api/v1/agent/conversations?page=1&page_size=10", headers=user_a["headers"]
    )
    items = resp.json()["data"]["items"]
    assert len(items) >= 5
    # 末两位为固定时间会话（早于今日活跃），id 倒序。
    assert items[-1]["id"] < items[-2]["id"]


def test_empty_conversation_messages(
    app_client: Any, user_a: dict[str, Any]
) -> None:
    """显式新建后消息端点返回 [] 不报错（spec 5.4.3 场景 3）。"""
    resp = app_client.post(
        "/api/v1/agent/conversations", json={"title": "空"}, headers=user_a["headers"]
    )
    cid = resp.json()["data"]["id"]
    resp = app_client.get(
        f"/api/v1/agent/conversations/{cid}/messages", headers=user_a["headers"]
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["data"] == []


# ---------------------------------------------------------------------------
# 7.2 隔离 / 窗口成对截断 / updated_at 触碰 / 消息全量（D9/D4/O7）
# ---------------------------------------------------------------------------
def test_isolation_two_users(
    app_client: Any, user_a: dict[str, Any], user_b: dict[str, Any]
) -> None:
    """双账号互查会话/消息/重命名/删除 → 404/1005（D9）。"""
    resp = app_client.post(
        "/api/v1/agent/conversations", json={"title": None}, headers=user_a["headers"]
    )
    cid = resp.json()["data"]["id"]

    for method, path in [
        ("GET", f"/api/v1/agent/conversations/{cid}"),
        ("GET", f"/api/v1/agent/conversations/{cid}/messages"),
        ("PATCH", f"/api/v1/agent/conversations/{cid}"),
        ("DELETE", f"/api/v1/agent/conversations/{cid}"),
    ]:
        kwargs: dict[str, Any] = {"headers": user_b["headers"]}
        if method == "PATCH":
            kwargs["json"] = {"title": "越权重命名"}
        resp = getattr(app_client, method.lower())(path, **kwargs)
        assert resp.status_code == 404, (method, resp.text)
        assert resp.json()["code"] == 1005

    resp = app_client.post(
        "/api/v1/agent/chat",
        json={"message": "hi", "conversation_id": cid},
        headers=user_b["headers"],
    )
    assert resp.status_code == 404
    assert resp.json()["code"] == 1005


def test_context_window_pair_truncation(app_client: Any, user_a: dict[str, Any]) -> None:
    """25 条历史（含 tool 链）→ ≤20 条且首条非孤立 tool（O7，决策 A9）。"""
    cid = _make_conversation(_user_id(app_client, user_a), None)
    # 6 轮 × [user, assistant(tc), tool, tool] + 尾部 1 user = 25 条。
    for i in range(6):
        _add_message(cid, "user", f"问题 {i}")
        _add_message(
            cid,
            "assistant",
            "",
            tool_calls=[_tc(f"call_{i}_a", "get_tasks", {})],
        )
        _add_message(
            cid, "tool", json.dumps({"total": 1}), tool_name="get_tasks", tool_call_id=f"call_{i}_a"
        )
        _add_message(
            cid,
            "tool",
            json.dumps({"total": 2}),
            tool_name="get_knowledge_mastery",
            tool_call_id=f"call_{i}_b",
        )
    _add_message(cid, "user", "最新问题")

    from app.db.session import SessionLocal

    with SessionLocal() as db:
        convo = _get_conversation(db, cid)
        window = load_context_window(db, convo)
    assert len(window) <= 20
    assert window[0]["role"] != "tool"
    # 历史轮 assistant(tool_calls) 与 tool 成对出现（协议合法）。
    roles = [m["role"] for m in window]
    for idx, role in enumerate(roles):
        if role == "tool":
            assert roles[idx - 1] in ("assistant", "tool")
    assert roles[-1] == "user"
    # 尾部对齐：最后一条是最新 user 消息。
    assert window[-1]["content"] == "最新问题"


def test_updated_at_touch_promotes_conversation(
    app_client: Any, user_a: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    """续聊会话在倒序列表升至首位（spec 5.4.1 规则 4 验收原句）。"""
    resp = _chat(app_client, user_a, "第一通", monkeypatch=monkeypatch)
    done = json.loads(
        [b for b in resp.text.split("\n\n") if '"done"' in b][0][len("data: "):]
    )
    first_id = done["data"]["conversation_id"]
    resp = _chat(app_client, user_a, "第二通", monkeypatch=monkeypatch)
    second_id = json.loads(
        [b for b in resp.text.split("\n\n") if '"done"' in b][0][len("data: "):]
    )["data"]["conversation_id"]
    assert first_id != second_id

    # 续聊第一通 → 其 updated_at 最新 → 升至首位。
    _chat(
        app_client,
        user_a,
        "续聊旧会话",
        conversation_id=first_id,
        monkeypatch=monkeypatch,
    )
    resp = app_client.get(
        "/api/v1/agent/conversations?page=1&page_size=10", headers=user_a["headers"]
    )
    items = resp.json()["data"]["items"]
    assert items[0]["id"] == first_id
    assert second_id in {item["id"] for item in items}


def test_messages_full_chain(
    app_client: Any, user_a: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    """多轮对话后消息端点全量返回成对链（D4 / spec 5.4.1 规则 6）。"""
    script = [
        [_round([_tc("call_1", "get_knowledge_mastery", {})])],
        [{"content": "你还没有学过任何知识点。"}, _round([], "stop")],
    ]
    resp = _chat(
        app_client, user_a, "我的掌握度如何", monkeypatch=monkeypatch, script=script
    )
    assert resp.status_code == 200, resp.text
    done = json.loads(
        [b for b in resp.text.split("\n\n") if '"done"' in b][0][len("data: "):]
    )
    cid = done["data"]["conversation_id"]

    resp = app_client.get(
        f"/api/v1/agent/conversations/{cid}/messages", headers=user_a["headers"]
    )
    assert resp.status_code == 200, resp.text
    messages = resp.json()["data"]
    roles = [m["role"] for m in messages]
    assert roles == ["user", "assistant", "tool", "assistant"]
    # assistant 工具轮含完整 tool_calls（arguments + id）。
    tool_round = messages[1]
    assert tool_round["tool_calls"][0]["function"]["name"] == "get_knowledge_mastery"
    assert tool_round["tool_calls"][0]["id"] == "call_1"
    # tool 消息关联字段齐备（前端卡片还原）。
    tool_msg = messages[2]
    assert tool_msg["tool_name"] == "get_knowledge_mastery"
    assert tool_msg["tool_call_id"] == "call_1"
    assert json.loads(tool_msg["content"])
    # 最终回答落库。
    assert messages[3]["content"] == "你还没有学过任何知识点。"