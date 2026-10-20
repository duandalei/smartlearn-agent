"""语义检索端点集成测试（tasks.md 5.7）。

覆盖：响应结构（mode/results 与 hit 三字段）/ score 降序与取值
范围 / 参数校验（空查询、超长、top_k 越界 → 422+1001）/ 空库
返回空 results / mode 双取值（offline 真实兜底路径 + online 假
client 按 mode 选库不串库）/ 公共库检索覆盖。
"""

from __future__ import annotations

from typing import Any

import pytest

import app.rag.embedding as embedding_module

from tests.conftest import upload_document

# 公共文档种子标题（data/public_kb 4 篇 stem）。
_PUBLIC_TITLES = {
    "ml_basics",
    "ds_cheatsheet",
    "probability_formulas",
    "linear_algebra_notes",
}


def _search_raw(client: Any, user: dict[str, Any], payload: dict[str, Any]) -> Any:
    """发检索请求返回原始响应。"""
    return client.post(
        "/api/v1/knowledge/search", json=payload, headers=user["headers"]
    )


def _search(client: Any, user: dict[str, Any], query: str, top_k: int = 10) -> dict[str, Any]:
    """发检索请求并断言成功，返回 data。"""
    resp = _search_raw(client, user, {"query": query, "top_k": top_k})
    assert resp.status_code == 200, resp.text
    return resp.json()["data"]


def _install_fake_online(monkeypatch: Any) -> None:
    """装假在线 client：向量按文本首字符确定性映射（同字符同向量）。"""
    class _Item:
        def __init__(self, index: int, vector: list[float]) -> None:
            self.index = index
            self.embedding = vector

    class _Resp:
        def __init__(self, data: list[_Item]) -> None:
            self.data = data

    class _Emb:
        async def create(self, *, model: str, input: list[str]) -> Any:
            return _Resp(
                [
                    _Item(i, [float(ord(text[0] if text else "x")), 1.0])
                    for i, text in enumerate(input)
                ]
            )

    class _Client:
        embeddings = _Emb()

    monkeypatch.setattr(embedding_module, "get_embedding_client", lambda: _Client())


def test_search_response_structure_and_ordering(
    app_client: Any,
    user_a: dict[str, Any],
    public_docs: list[int],
    offline_embedding: None,
) -> None:
    """响应结构：data={mode,results}，hit 恰含三字段，score 降序且 ∈[-1,1]。"""
    upload_document(
        app_client,
        user_a,
        "聚类算法私讲.md",
        ("聚类算法把无标签样本按相似度分组成簇，K均值与层次聚类是代表方法。" * 8).encode("utf-8"),
    )
    data = _search(app_client, user_a, "机器学习与聚类算法", top_k=8)
    assert set(data.keys()) == {"mode", "results"}
    assert data["mode"] == "offline"
    assert 1 <= len(data["results"]) <= 8
    scores = [hit["score"] for hit in data["results"]]
    assert scores == sorted(scores, reverse=True), "必须按 score 降序"
    assert all(-1.0 <= score <= 1.0 for score in scores)
    for hit in data["results"]:
        assert set(hit.keys()) == {"content", "source_title", "score"}
        assert hit["content"]
        assert hit["source_title"]
        assert isinstance(hit["score"], float)


def test_search_param_validation(
    app_client: Any, user_a: dict[str, Any]
) -> None:
    """参数校验：空查询/超长/top_k 越界 → 422 + code=1001；边界值合法。"""
    invalid_payloads = (
        {"query": "", "top_k": 5},
        {"query": "超" * 501, "top_k": 5},
        {"query": "有效查询", "top_k": 0},
        {"query": "有效查询", "top_k": 21},
    )
    for payload in invalid_payloads:
        resp = _search_raw(app_client, user_a, payload)
        assert resp.status_code == 422, payload
        assert resp.json()["code"] == 1001, payload
    for payload in ({"query": "边界", "top_k": 1}, {"query": "边界", "top_k": 20}):
        resp = _search_raw(app_client, user_a, payload)
        assert resp.status_code == 200, payload
    resp = _search_raw(app_client, user_a, {"query": "默认条数"})
    assert resp.status_code == 200


def test_search_empty_library_returns_empty(
    app_client: Any, user_a: dict[str, Any], offline_embedding: None
) -> None:
    """空库：HTTP 200 + results 为空列表（不报错）。"""
    data = _search(app_client, user_a, "任何关键词")
    assert data == {"mode": "offline", "results": []}


def test_search_offline_mode_hits_with_heading(
    app_client: Any,
    user_a: dict[str, Any],
    public_docs: list[int],
    offline_embedding: None,
) -> None:
    """offline 模式：真实兜底路径命中，heading_path 并入 source_title。"""
    data = _search(app_client, user_a, "什么是机器学习", top_k=5)
    assert data["mode"] == "offline"
    assert data["results"], "公共文档必须可检索命中"
    assert any(
        "»" in hit["source_title"] for hit in data["results"]
    ), "带标题路径的命中应以 '»' 连接标题与路径"


def test_search_online_mode_uses_online_collection(
    app_client: Any, user_a: dict[str, Any], monkeypatch: Any
) -> None:
    """online 模式：在线向量写在线库、查在线库（同空间命中）。"""
    _install_fake_online(monkeypatch)
    resp = upload_document(
        app_client,
        user_a,
        "在线模式讲义.md",
        ("深度学习神经网络反向传播算法逐层推导，链式法则贯穿始终。" * 8).encode("utf-8"),
    )
    assert resp.status_code == 200, resp.text
    data = _search(app_client, user_a, "深")
    assert data["mode"] == "online"
    assert data["results"], "在线库应命中本人文档"
    top = data["results"][0]
    assert "在线模式讲义" in top["source_title"]
    assert top["score"] == pytest.approx(1.0, abs=1e-6)


def test_search_online_mode_skips_offline_library(
    app_client: Any,
    user_a: dict[str, Any],
    public_docs: list[int],
    monkeypatch: Any,
) -> None:
    """模式选库不串库：离线库有数据但在线查询只查在线库（空）。"""
    _install_fake_online(monkeypatch)
    data = _search(app_client, user_a, "机器学习")
    assert data["mode"] == "online"
    assert data["results"] == [], "在线查询不得命中离线空间向量"


def test_search_covers_public_library_for_any_user(
    app_client: Any,
    user_a: dict[str, Any],
    user_b: dict[str, Any],
    public_docs: list[int],
    offline_embedding: None,
) -> None:
    """公共库覆盖：任何用户检索公共关键词均命中公共文档来源。"""
    for user in (user_a, user_b):
        data = _search(app_client, user, "机器学习基础概念", top_k=20)
        assert data["results"], f"{user['username']} 应命中公共文档"
        for hit in data["results"]:
            title_root = hit["source_title"].split(" » ")[0]
            assert title_root in _PUBLIC_TITLES, hit["source_title"]

