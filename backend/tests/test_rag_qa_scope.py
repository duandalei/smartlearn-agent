"""scope 三档检索与 D8 兼容回归测试（tasks.md 9.2，design.md 2.7.1-B）。

检索走**真实路径**：本地兜底 embedding 真算 + 真 Chroma 写入
（复用 conftest 的 ``_isolated_runtime`` / ``public_docs`` /
``upload_document``，P8 惯例）。

覆盖：
- 三档归属（personal 仅本人 / public 仅公共 / all 混合 score 降序）；
- 用户隔离（B 空个人库 → personal 档空结果；任意档不含 A 内容）；
- D8 默认兼容（「不传 scope」≡「显式 all」逐字段相等；P7 端点
  响应含既有三字段且语义不变、新增三字段有值）；
- 字段透出（item_id / chunk_index / scope / source_title 拼接口径）。
"""

from __future__ import annotations

import asyncio
from typing import Any

from sqlalchemy import select

from app.models.user import User
from app.services.knowledge import search_knowledge

from tests.conftest import upload_document

# 用户 A 的个人文档内容（上传后真实离线索引）。
_PERSONAL_DOC_NAME = "聚类算法私讲.md"
_PERSONAL_DOC_BODY = (
    "聚类算法把无标签样本按相似度分组成簇，K均值与层次聚类是代表方法，"
    "K均值通过簇中心迭代最小化簇内平方误差。"
)


def _user_id_of(db: Any, username: str) -> int:
    """按用户名查用户 id（服务层直调需要隔离边界参数）。"""
    return int(db.scalar(select(User.id).where(User.username == username)))


def _search_service(
    app_client: Any,  # noqa: ARG001 - 保证应用已初始化（fixture 链）
    username: str,
    query: str,
    scope: str | None = None,
    top_k: int = 10,
) -> dict[str, Any]:
    """服务层直调 search_knowledge（真实检索路径，无 HTTP 层）。"""
    from app.db.session import SessionLocal

    with SessionLocal() as db:
        user_id = _user_id_of(db, username)
        if scope is None:
            result = asyncio.run(search_knowledge(db, user_id, query, top_k))
        else:
            result = asyncio.run(
                search_knowledge(db, user_id, query, top_k, scope)
            )
    return result


# ---------------------------------------------------------------------------
# 三档归属（验收 D5 / spec 5.2.1 规则 1）
# ---------------------------------------------------------------------------
def test_scope_personal_only_own_docs(
    app_client: Any,
    user_a: dict[str, Any],
    public_docs: list[int],
    offline_embedding: None,
) -> None:
    """personal 档：仅命中本人个人库文档（公共文档不出现）。"""
    resp = upload_document(
        app_client,
        user_a,
        _PERSONAL_DOC_NAME,
        (_PERSONAL_DOC_BODY * 8).encode("utf-8"),
    )
    assert resp.status_code == 200, resp.text

    data = _search_service(app_client, user_a["username"], "聚类算法 K均值", "personal")
    assert data["results"], "personal 档必须命中本人文档"
    assert all(hit["scope"] == "personal" for hit in data["results"])
    assert all(
        hit["source_title"].startswith(_PERSONAL_DOC_NAME.removesuffix(".md"))
        for hit in data["results"]
    )
    # 公共文档标题一律不出现。
    assert not any(
        hit["source_title"].startswith(("机器学习基础", "线性代数", "概率论", "数据结构"))
        for hit in data["results"]
    )


def test_scope_public_only_public_docs(
    app_client: Any,
    user_a: dict[str, Any],
    public_docs: list[int],
    offline_embedding: None,
) -> None:
    """public 档：仅命中公共文档（4 篇种子），不含个人内容。"""
    resp = upload_document(
        app_client,
        user_a,
        _PERSONAL_DOC_NAME,
        (_PERSONAL_DOC_BODY * 8).encode("utf-8"),
    )
    assert resp.status_code == 200, resp.text

    data = _search_service(app_client, user_a["username"], "什么是机器学习", "public")
    assert data["results"], "public 档必须命中公共文档"
    assert all(hit["scope"] == "public" for hit in data["results"])
    assert all(
        not hit["source_title"].startswith("聚类算法私讲")
        for hit in data["results"]
    )


def test_scope_all_merges_both_and_sorted(
    app_client: Any,
    user_a: dict[str, Any],
    public_docs: list[int],
    offline_embedding: None,
) -> None:
    """all 档：个人 + 公共混合命中，score 降序统一排序。"""
    resp = upload_document(
        app_client,
        user_a,
        _PERSONAL_DOC_NAME,
        (_PERSONAL_DOC_BODY * 8).encode("utf-8"),
    )
    assert resp.status_code == 200, resp.text

    data = _search_service(app_client, user_a["username"], "什么是机器学习", "all")
    assert data["results"]
    scopes = {hit["scope"] for hit in data["results"]}
    assert scopes == {"personal", "public"}, f"all 档应混合命中: {scopes}"
    scores = [hit["score"] for hit in data["results"]]
    assert scores == sorted(scores, reverse=True), "all 档须按 score 降序"


# ---------------------------------------------------------------------------
# 用户隔离（验收 D4：检索维度）
# ---------------------------------------------------------------------------
def test_scope_isolation_user_b_empty_personal(
    app_client: Any,
    user_a: dict[str, Any],
    user_b: dict[str, Any],
    public_docs: list[int],
    offline_embedding: None,
) -> None:
    """用户 B 空个人库：personal 档空结果；任意档不含 A 的文档。"""
    resp = upload_document(
        app_client,
        user_a,
        _PERSONAL_DOC_NAME,
        (_PERSONAL_DOC_BODY * 8).encode("utf-8"),
    )
    assert resp.status_code == 200, resp.text

    # B 的 personal 档：空库 → 空结果（不报错）。
    data_b = _search_service(app_client, user_b["username"], "聚类算法 K均值", "personal")
    assert data_b == {"mode": data_b["mode"], "results": []}

    # B 的 all / public 档：不含 A 的文档标题与内容。
    for scope in ("all", "public"):
        data = _search_service(
            app_client, user_b["username"], "聚类算法 K均值", scope
        )
        assert all(
            not hit["source_title"].startswith("聚类算法私讲")
            for hit in data["results"]
        ), f"scope={scope} 不得命中用户 A 的文档"
        assert all(
            "K均值" not in hit["content"] or hit["scope"] == "public"
            for hit in data["results"]
        )


# ---------------------------------------------------------------------------
# D8 默认兼容（「不传 scope」≡「显式 all」，逐字段相等）
# ---------------------------------------------------------------------------
def test_scope_default_equals_explicit_all(
    app_client: Any,
    user_a: dict[str, Any],
    public_docs: list[int],
    offline_embedding: None,
) -> None:
    """同一查询下「不传 scope」与「显式 all」返回逐字段相等。"""
    upload_document(
        app_client,
        user_a,
        _PERSONAL_DOC_NAME,
        (_PERSONAL_DOC_BODY * 8).encode("utf-8"),
    )
    implicit = _search_service(app_client, user_a["username"], "什么是机器学习")
    explicit = _search_service(app_client, user_a["username"], "什么是机器学习", "all")
    assert implicit == explicit, "默认（不传 scope）必须与显式 all 逐字段一致"


def test_p7_search_endpoint_contract_unchanged(
    app_client: Any,
    user_a: dict[str, Any],
    public_docs: list[int],
    offline_embedding: None,
) -> None:
    """P7 端点 POST /knowledge/search：既有三字段语义不变 + 新三字段有值。"""
    resp = app_client.post(
        "/api/v1/knowledge/search",
        json={"query": "什么是机器学习", "top_k": 5},
        headers=user_a["headers"],
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["code"] == 0
    data = body["data"]
    assert set(data.keys()) == {"mode", "results"}
    assert data["results"]
    for hit in data["results"]:
        # 既有三字段（不删不改）。
        assert isinstance(hit["content"], str) and hit["content"]
        assert isinstance(hit["source_title"], str) and hit["source_title"]
        assert isinstance(hit["score"], float)
        # 新增三字段（裁决 #3，实际总有值）。
        assert isinstance(hit["item_id"], int) and hit["item_id"] > 0
        assert isinstance(hit["chunk_index"], int) and hit["chunk_index"] >= 0
        assert hit["scope"] in ("personal", "public")


def test_hit_field_shape_and_source_title(
    app_client: Any,
    user_a: dict[str, Any],
    public_docs: list[int],
    offline_embedding: None,
) -> None:
    """字段透出：item_id 正整数 / chunk_index ≥ 0 / scope 合法 /
    source_title 为「标题 » 路径」拼接（验收 D2 数据侧）。"""
    data = _search_service(app_client, user_a["username"], "Transformer 注意力机制", "public")
    assert data["results"]
    for hit in data["results"]:
        assert hit["item_id"] > 0
        assert hit["chunk_index"] >= 0
        assert hit["scope"] in ("personal", "public")
    # 带标题路径的命中以 '»' 连接（P8 口径保持）。
    assert any("»" in hit["source_title"] for hit in data["results"])