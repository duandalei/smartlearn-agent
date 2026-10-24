"""SSE 问答契约 e2e（tasks.md 9.3，design.md 2.7.1-C）。

ASGI TestClient 直调 + **唯一外部 LLM 调用点 mock**（注入假流，
chat_stream 走 services 层注入形态）；检索走真实路径（本地兜底
embedding 真算 + 真 Chroma）。真实流式节奏归用户本机清单（10.5）。

覆盖：事件序列（有据/无据/chat 三路径 + done 四字段）/ 受理错误走
统一响应体 / 流内异常 → error 事件（LLM 创建失败、流中断、检索
失败）/ 落库时机与裁定③失败处理 / 历史隔离与分页 / 真实流式
结构性证明（D1 沙箱内结构等价部分）。
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

import pytest

from app.core.config import settings
from app.core.response import BizException

# 无据固定句式（模板二，答辩必测锚点）。
_UNGROUNDED_SENTENCE = "你的知识库中没有找到相关内容，以下为基于通用知识的回答"


# ---------------------------------------------------------------------------
# 测试辅助
# ---------------------------------------------------------------------------
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


def _ask(
    client: Any,
    user: dict[str, Any],
    question: str,
) -> Any:
    """发起一次 SSE 问答，返回原始响应（TestClient 消费完整流）。"""
    return client.post(
        "/api/v1/chat/qa",
        json={"question": question},
        headers=user["headers"],
    )


def _install_fake_llm(
    monkeypatch: pytest.MonkeyPatch,
    pieces: list[str],
) -> dict[str, Any]:
    """注入假 LLM 流（模块属性形态），并捕获收到的 messages。

    chat_stream 是 qa_stream 的唯一 LLM 调用点（经
    ``llm.chat_stream(...)`` 属性访问），patch
    ``app.services.llm.chat_stream`` 即可注入。
    """
    captured: dict[str, Any] = {}

    async def fake_stream(messages: list[dict[str, str]]) -> Any:
        captured["messages"] = messages
        for piece in pieces:
            yield piece

    monkeypatch.setattr("app.services.llm.chat_stream", fake_stream)
    return captured


def _history(
    client: Any, user: dict[str, Any], page: int = 1, page_size: int = 10
) -> dict[str, Any]:
    """查询历史问答并断言成功，返回 data。"""
    resp = client.get(
        f"/api/v1/chat/history?page={page}&page_size={page_size}",
        headers=user["headers"],
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["data"]


# ---------------------------------------------------------------------------
# 事件序列：有据路径（spec 5.1.1 规则 2/8；裁决 #8；裁定①）
# ---------------------------------------------------------------------------
def test_stream_grounded_event_sequence(
    app_client: Any,
    user_a: dict[str, Any],
    demo_docs: list[int],
    offline_embedding: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """有据：sources(恰1) → delta(3片,顺序一致) → done(四字段,有据)。"""
    # 本地兜底哈希向量分数分布与在线 bge-m3 不同，测试用低阈值
    # 保证「有检索命中 → 有据」路径稳定（阈值行为本身在 9.1 单测锁定）。
    monkeypatch.setattr(settings, "RAG_MIN_SCORE", 0.0)
    captured = _install_fake_llm(monkeypatch, ["Transformer 是", "一种基于", "自注意力的架构"])

    resp = _ask(app_client, user_a, "什么是 Transformer")
    assert resp.status_code == 200, resp.text
    assert resp.headers["content-type"].startswith("text/event-stream")
    assert resp.headers["cache-control"] == "no-cache"

    events = _parse_sse(resp.text)
    types = [e["type"] for e in events]
    assert types[0] == "sources"
    assert types[1:-1] == ["delta", "delta", "delta"]
    assert types[-1] == "done"
    assert types.count("sources") == 1
    assert types.count("done") == 1

    sources_event = events[0]
    assert sources_event["data"], "演示文档必须检索命中"
    for hit in sources_event["data"]:
        assert hit["item_id"] > 0
        assert hit["chunk_index"] >= 0
        assert hit["scope"] == "personal"

    deltas = [e["data"] for e in events[1:-1]]
    assert deltas == ["Transformer 是", "一种基于", "自注意力的架构"]

    done = events[-1]["data"]
    assert set(done.keys()) == {"is_grounded", "mode", "intent", "history_id"}
    assert done["is_grounded"] is True
    assert done["mode"] == "offline"  # offline_embedding 下走本地兜底
    assert done["intent"] == "knowledge"
    assert isinstance(done["history_id"], int)

    # 有据路径：系统提示为模板一（含第二道防线指令与 [1] 来源块）。
    system = captured["messages"][0]["content"]
    assert "如果检索片段与问题无关，直接说明知识库中没有相关内容，不要强行拼接" in system
    assert "[1]（来源：" in system


def test_stream_ungrounded_empty_library(
    app_client: Any,
    user_a: dict[str, Any],
    offline_embedding: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """knowledge 无据（空库）：sources=[] + done 无据四要素 + 模板二句式。"""
    captured = _install_fake_llm(monkeypatch, ["你的知识库中没有找到相关内容，", "以下为基于通用知识的回答。"])

    resp = _ask(app_client, user_a, "法国大革命的历史背景")
    assert resp.status_code == 200, resp.text
    events = _parse_sse(resp.text)
    types = [e["type"] for e in events]
    assert types == ["sources", "delta", "delta", "done"]

    assert events[0]["data"] == []
    done = events[-1]["data"]
    assert done["is_grounded"] is False
    assert done["intent"] == "knowledge"
    assert done["history_id"] is not None

    # 模板二真的被使用：系统提示含固定句式逐字文本（答辩必测锚点）。
    system = captured["messages"][0]["content"]
    assert _UNGROUNDED_SENTENCE in system

    # 落库记录：sources=[] / intent=knowledge / is_grounded=false。
    data = _history(app_client, user_a)
    assert data["total"] == 1
    record = data["items"][0]
    assert record["question"] == "法国大革命的历史背景"
    assert record["sources"] == []
    assert record["is_grounded"] is False
    assert record["intent"] == "knowledge"
    assert record["mode"] == "offline"


def test_stream_knowledge_below_threshold(
    app_client: Any,
    user_a: dict[str, Any],
    demo_docs: list[int],
    offline_embedding: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """knowledge 且检索结果全部低于阈值：有召回但无据（验收场景核心）。

    先以服务层原始口径确认该查询有召回（results 非空），再抬阈值
    至 1.1（cosine score 恒 ≤ 1.0）验证「检索了但没找到」路径。
    """
    import app.services.chat as chat_module

    raw_calls: dict[str, Any] = {}

    async def spy_search(db: Any, user_id: int, query: str, top_k: int) -> dict[str, Any]:
        result = await _real_search(db, user_id, query, top_k)
        raw_calls["result"] = result
        return result

    _real_search = chat_module.search_knowledge
    monkeypatch.setattr("app.services.chat.search_knowledge", spy_search)
    monkeypatch.setattr(settings, "RAG_MIN_SCORE", 1.1)
    _install_fake_llm(monkeypatch, ["通用回答。"])

    resp = _ask(app_client, user_a, "什么是机器学习")
    assert resp.status_code == 200, resp.text
    events = _parse_sse(resp.text)
    assert [e["type"] for e in events] == ["sources", "delta", "done"]

    # 确认底层确实召回了片段（非空库空结果）——被阈值全部挡下。
    assert raw_calls["result"]["results"], "前置：该查询应有召回"
    assert events[0]["data"] == [], "低于阈值的命中不得外透"
    done = events[-1]["data"]
    assert done["is_grounded"] is False
    assert done["intent"] == "knowledge"


# ---------------------------------------------------------------------------
# 事件序列：chat 路径（R3 裁定① / 决策 D9）
# ---------------------------------------------------------------------------
def test_stream_chat_intent_skips_retrieval(
    app_client: Any,
    user_a: dict[str, Any],
    demo_docs: list[int],
    offline_embedding: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """问候类：跳过检索（search_knowledge 计数 0）+ intent=chat + 模板三。"""
    calls = {"count": 0}

    async def counting_search(
        db: Any, user_id: int, query: str, top_k: int
    ) -> dict[str, Any]:
        calls["count"] += 1
        return {"mode": "online", "results": []}

    monkeypatch.setattr("app.services.chat.search_knowledge", counting_search)
    captured = _install_fake_llm(monkeypatch, ["你好！我是彭城智学的 AI 学习助手。"])

    resp = _ask(app_client, user_a, "你好")
    assert resp.status_code == 200, resp.text
    events = _parse_sse(resp.text)
    types = [e["type"] for e in events]
    assert types == ["sources", "delta", "done"]

    # 未发起无意义检索（intent=chat 跳检）。
    assert calls["count"] == 0
    assert events[0]["data"] == []
    done = events[-1]["data"]
    assert done["is_grounded"] is False  # 没检索 → 无据
    assert done["intent"] == "chat"  # 但不是「检索无果」——由 intent 区分
    assert done["mode"] == "online"  # 约定值（决策 D3）
    assert done["history_id"] is not None

    # 模板三：不含无据固定句式（chat 类禁用）。
    system = captured["messages"][0]["content"]
    assert _UNGROUNDED_SENTENCE not in system
    assert "闲聊" in system

    # 落库 intent=chat（历史回放区分两种 false 的前置，D9）。
    data = _history(app_client, user_a)
    assert data["total"] == 1
    assert data["items"][0]["intent"] == "chat"
    assert data["items"][0]["is_grounded"] is False


# ---------------------------------------------------------------------------
# 受理错误走统一响应体（裁决 #10；spec 5.1.1 规则 1/6）
# ---------------------------------------------------------------------------
def test_qa_requires_auth(app_client: Any) -> None:
    """无 token：HTTP 401 + code=1003 JSON（非 SSE）。"""
    resp = app_client.post("/api/v1/chat/qa", json={"question": "什么是 Transformer"})
    assert resp.status_code == 401
    body = resp.json()
    assert body["code"] == 1003
    assert "text/event-stream" not in resp.headers.get("content-type", "")


@pytest.mark.parametrize(
    "payload",
    [
        {"question": "   "},  # 去空白后为空
        {"question": "超" * 501},  # 超长
        {"question": "有效问题", "scope": "personal"},  # 已移除的 scope 字段
        {"question": "有效问题", "extra": 1},  # 多余字段
    ],
)
def test_qa_validation_errors(
    app_client: Any, user_a: dict[str, Any], payload: dict[str, Any]
) -> None:
    """入参越界：HTTP 422 + code=1001。"""
    resp = app_client.post(
        "/api/v1/chat/qa", json=payload, headers=user_a["headers"]
    )
    assert resp.status_code == 422, payload
    assert resp.json()["code"] == 1001


def test_history_requires_auth(app_client: Any) -> None:
    """历史端点无 token：401 + 1003。"""
    resp = app_client.get("/api/v1/chat/history")
    assert resp.status_code == 401
    assert resp.json()["code"] == 1003


# ---------------------------------------------------------------------------
# 流内异常 → error 事件（spec 5.1.3 场景 1/2/3；裁决 #4）
# ---------------------------------------------------------------------------
def test_stream_llm_create_failure_yields_error(
    app_client: Any,
    user_a: dict[str, Any],
    demo_docs: list[int],
    offline_embedding: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """LLM 创建阶段失败（BizException 3000）：sources 后恰一条 error，无 done。"""
    monkeypatch.setattr(settings, "RAG_MIN_SCORE", 0.0)

    async def failing_stream(messages: list[dict[str, str]]) -> Any:
        raise BizException(3000, "AI 服务暂时不可用，请稍后重试", http_status=502)
        yield ""  # pragma: no cover - 使其成为异步生成器

    monkeypatch.setattr("app.services.llm.chat_stream", failing_stream)

    resp = _ask(app_client, user_a, "什么是 Transformer")
    assert resp.status_code == 200, resp.text
    events = _parse_sse(resp.text)
    types = [e["type"] for e in events]
    assert types == ["sources", "error"]
    assert events[0]["data"]  # sources 已推（检索成功）
    error = events[-1]["data"]
    assert error == {"code": 3000, "message": "AI 服务暂时不可用，请稍后重试"}

    # error 流不落库（裁决 #7）。
    assert _history(app_client, user_a)["total"] == 0


def test_stream_llm_midway_break_yields_error(
    app_client: Any,
    user_a: dict[str, Any],
    offline_embedding: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """LLM 流中途断开（首片后原始异常）：error 3000「回答生成中断，请重试」。"""
    monkeypatch.setattr(settings, "RAG_MIN_SCORE", 0.0)

    async def breaking_stream(messages: list[dict[str, str]]) -> Any:
        yield "回答开头"
        raise RuntimeError("connection reset")

    monkeypatch.setattr("app.services.llm.chat_stream", breaking_stream)

    resp = _ask(app_client, user_a, "什么是机器学习")
    assert resp.status_code == 200, resp.text
    events = _parse_sse(resp.text)
    types = [e["type"] for e in events]
    assert types == ["sources", "delta", "error"]
    assert events[1]["data"] == "回答开头"
    error = events[-1]["data"]
    assert error == {"code": 3000, "message": "回答生成中断，请重试"}
    assert _history(app_client, user_a)["total"] == 0


def test_stream_search_failure_yields_error(
    app_client: Any,
    user_a: dict[str, Any],
    offline_embedding: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """检索失败（3001）：恰一条 error 收尾，不伪装为无据降级。"""

    async def failing_search(
        db: Any, user_id: int, query: str, top_k: int
    ) -> dict[str, Any]:
        raise BizException(3001, "检索失败请稍后重试", http_status=500)

    monkeypatch.setattr("app.services.chat.search_knowledge", failing_search)
    _install_fake_llm(monkeypatch, ["不应被调用"])

    resp = _ask(app_client, user_a, "什么是机器学习")
    assert resp.status_code == 200, resp.text
    events = _parse_sse(resp.text)
    # 检索失败发生在 sources 之前：流内仅有 error（无 sources 空数组、
    # 无无据句式路径——不伪装为无据降级，spec 5.3.1 规则 6）。
    assert [e["type"] for e in events] == ["error"]
    assert events[0]["data"] == {"code": 3001, "message": "检索失败请稍后重试"}
    assert _history(app_client, user_a)["total"] == 0


# ---------------------------------------------------------------------------
# 落库时机与裁定③失败处理（裁决 #7；裁定③核心）
# ---------------------------------------------------------------------------
def test_stream_persists_after_done(
    app_client: Any,
    user_a: dict[str, Any],
    demo_docs: list[int],
    offline_embedding: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """成功流后：历史新增 1 条且 answer = delta 拼接、sources 与事件一致。"""
    monkeypatch.setattr(settings, "RAG_MIN_SCORE", 0.0)
    _install_fake_llm(monkeypatch, ["片段一", "片段二", "片段三"])

    resp = _ask(app_client, user_a, "什么是 Transformer")
    events = _parse_sse(resp.text)
    done = events[-1]["data"]
    history_id = done["history_id"]
    assert isinstance(history_id, int)

    data = _history(app_client, user_a)
    assert data["total"] == 1
    record = data["items"][0]
    assert record["id"] == history_id
    assert record["answer"] == "片段一片段二片段三"
    assert record["sources"] == events[0]["data"]
    assert record["is_grounded"] is True
    assert record["intent"] == "knowledge"


def test_stream_save_failure_still_done(
    app_client: Any,
    user_a: dict[str, Any],
    offline_embedding: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """落库失败（裁定③）：事件流仍 done 收尾且 history_id=null、无 error。"""

    def boom_save(*args: Any, **kwargs: Any) -> int:
        raise RuntimeError("db write failed")

    monkeypatch.setattr("app.services.chat.save_qa_history", boom_save)
    _install_fake_llm(monkeypatch, ["完整回答"])

    resp = _ask(app_client, user_a, "什么是机器学习")
    assert resp.status_code == 200, resp.text
    events = _parse_sse(resp.text)
    types = [e["type"] for e in events]
    # 主链路（回答）成功不被辅链路（历史保存）失败拖垮。
    assert types == ["sources", "delta", "done"]
    done = events[-1]["data"]
    assert done["history_id"] is None
    assert _history(app_client, user_a)["total"] == 0


# ---------------------------------------------------------------------------
# 历史隔离与分页（验收 D4 历史维度 / D6）
# ---------------------------------------------------------------------------
def test_history_isolation_and_pagination(
    app_client: Any,
    user_a: dict[str, Any],
    user_b: dict[str, Any],
    offline_embedding: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """双账号隔离互查不含对方记录；page_size=2 翻页正确、total 正确。"""
    _install_fake_llm(monkeypatch, ["回答"])

    questions_a = ["你好", "谢谢", "什么是机器学习"]
    for q in questions_a:
        resp = _ask(app_client, user_a, q)
        assert resp.status_code == 200, resp.text
    resp = _ask(app_client, user_b, "你是谁")
    assert resp.status_code == 200, resp.text

    # 隔离：A 查 3 条、B 查 1 条，互不包含对方记录。
    data_a = _history(app_client, user_a)
    data_b = _history(app_client, user_b)
    assert data_a["total"] == 3
    assert data_b["total"] == 1
    assert {i["question"] for i in data_a["items"]} == set(questions_a)
    assert data_b["items"][0]["question"] == "你是谁"

    # 分页：page_size=2 → 第 1 页 2 条、第 2 页 1 条。
    page1 = _history(app_client, user_a, page=1, page_size=2)
    page2 = _history(app_client, user_a, page=2, page_size=2)
    assert page1["total"] == 3 and page1["page"] == 1 and page1["page_size"] == 2
    assert len(page1["items"]) == 2
    assert len(page2["items"]) == 1
    ids = [i["id"] for i in page1["items"]] + [i["id"] for i in page2["items"]]
    assert len(set(ids)) == 3

    # 倒序：第 1 页首条 = 最近一次问答。
    assert page1["items"][0]["question"] == questions_a[-1]


def test_history_empty_returns_empty(
    app_client: Any, user_a: dict[str, Any]
) -> None:
    """无历史：{items: [], total: 0} 不报错（spec 5.5.3 场景 1）。"""
    data = _history(app_client, user_a)
    assert data == {"items": [], "total": 0, "page": 1, "page_size": 10}


# ---------------------------------------------------------------------------
# 真实流式结构性证明（验收 D1 沙箱内结构等价部分）
# ---------------------------------------------------------------------------
def test_streaming_is_incremental_not_batched(
    app_client: Any,
    user_a: dict[str, Any],
    offline_embedding: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """mock 为「yield → sleep → yield」异步生成器：TestClient 收到
    完整流且事件顺序即产出顺序（StreamingResponse 逐段拉取语义，
    先算完再一次性返回无法通过此结构）。"""
    produced_order: list[str] = []

    async def slow_stream(messages: list[dict[str, str]]) -> Any:
        for piece in ("第一片", "第二片", "第三片"):
            await asyncio.sleep(0.05)
            produced_order.append(piece)
            yield piece

    monkeypatch.setattr("app.services.llm.chat_stream", slow_stream)

    resp = _ask(app_client, user_a, "什么是机器学习")
    assert resp.status_code == 200, resp.text
    events = _parse_sse(resp.text)
    deltas = [e["data"] for e in events if e["type"] == "delta"]
    assert deltas == produced_order == ["第一片", "第二片", "第三片"]
    assert events[-1]["type"] == "done"