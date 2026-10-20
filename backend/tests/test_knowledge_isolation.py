"""多用户隔离与写操作防护集成测试（tasks.md 5.6）。

覆盖：列表隔离 / 详情与分块「不可见即不存在」1005 / 检索隔离 /
公共库删除保护 1004 / 公共文档重索引允许（spec 5.4.1 规则 3 裁决）/
pending、parsing 状态重索引防护 1007 / 删除级联（列表、详情、
分块、检索、SQLite chunk 行全维度收敛）。
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select

from app.db.session import SessionLocal
from app.models.enums import KnowledgeItemStatus, KnowledgeScope, KnowledgeSourceType
from app.models.knowledge import KnowledgeChunk, KnowledgeItem
from app.models.user import User
from tests.conftest import upload_document


def _search(client: Any, user: dict[str, Any], query: str) -> dict[str, Any]:
    """发起语义检索并返回 data。"""
    resp = client.post(
        "/api/v1/knowledge/search",
        json={"query": query, "top_k": 10},
        headers=user["headers"],
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["data"]


def _upload_indexed(client: Any, user: dict[str, Any], filename: str, content: bytes) -> int:
    """上传并等待流水线完成（TestClient 同步执行后台任务），返回 item_id。"""
    resp = upload_document(client, user, filename, content)
    assert resp.status_code == 200, resp.text
    item_id = resp.json()["data"]["item_id"]
    detail = client.get(
        f"/api/v1/knowledge/items/{item_id}", headers=user["headers"]
    )
    assert detail.json()["data"]["status"] == "indexed", detail.text
    return item_id


def test_list_isolation_between_users(
    app_client: Any,
    user_a: dict[str, Any],
    user_b: dict[str, Any],
    offline_embedding: None,
) -> None:
    """列表隔离：各自仅见本人个人库文档，互不可见。"""
    id_a = _upload_indexed(
        app_client, user_a, "用户A私有笔记.md", ("独占内容甲" * 60).encode("utf-8")
    )
    id_b = _upload_indexed(
        app_client, user_b, "用户B私有笔记.md", ("独占内容乙" * 60).encode("utf-8")
    )
    for user, own_id, other_id in (
        (user_a, id_a, id_b),
        (user_b, id_b, id_a),
    ):
        resp = app_client.get(
            "/api/v1/knowledge/items?page=1&page_size=50", headers=user["headers"]
        )
        ids = [item["id"] for item in resp.json()["data"]["items"]]
        assert own_id in ids
        assert other_id not in ids, "他人个人库文档不得出现在列表中"


def test_invisible_item_is_404_for_all_endpoints(
    app_client: Any,
    user_a: dict[str, Any],
    user_b: dict[str, Any],
    offline_embedding: None,
) -> None:
    """「不可见即不存在」：他人个人库文档在详情/分块/重索引/删除统一 1005。"""
    item_id = _upload_indexed(
        app_client, user_a, "隐私文档.md", ("机密内容不可外泄" * 60).encode("utf-8")
    )
    endpoints = (
        ("get", f"/api/v1/knowledge/items/{item_id}"),
        ("get", f"/api/v1/knowledge/items/{item_id}/chunks"),
        ("post", f"/api/v1/knowledge/items/{item_id}/reindex"),
        ("delete", f"/api/v1/knowledge/items/{item_id}"),
    )
    for method, url in endpoints:
        resp = getattr(app_client, method)(url, headers=user_b["headers"])
        assert resp.status_code == 404, (method, url, resp.text)
        assert resp.json()["code"] == 1005, (method, url)


def test_search_isolation_between_users(
    app_client: Any,
    user_a: dict[str, Any],
    user_b: dict[str, Any],
    offline_embedding: None,
) -> None:
    """检索隔离：A 的私有内容不出现在 B 的检索结果，反之亦然。"""
    _upload_indexed(
        app_client,
        user_a,
        "量子纠缠讲义.md",
        ("量子纠缠态叠加坍缩测量问题详解与贝尔不等式推导" * 20).encode("utf-8"),
    )
    _upload_indexed(
        app_client,
        user_b,
        "宏观经济学讲义.md",
        ("通货膨胀菲利普斯曲线货币政策财政政策 IS-LM 模型分析" * 20).encode("utf-8"),
    )
    results_a = _search(app_client, user_a, "量子纠缠态叠加")["results"]
    assert results_a, "本人私有文档必须可检索命中"
    assert all("量子纠缠" in hit["source_title"] for hit in results_a)

    results_b = _search(app_client, user_b, "量子纠缠态叠加")["results"]
    assert all(
        "量子纠缠" not in hit["source_title"] for hit in results_b
    ), "他人私有文档不得被检索命中"

    results_b_self = _search(app_client, user_b, "通货膨胀菲利普斯曲线")["results"]
    assert results_b_self, "B 本人文档可检索命中"


def test_public_delete_forbidden(
    app_client: Any,
    user_a: dict[str, Any],
    public_docs: list[int],
) -> None:
    """公共库删除保护：任何用户删除公共文档 → 403 + code=1004。"""
    public_id = public_docs[0]
    resp = app_client.delete(
        f"/api/v1/knowledge/items/{public_id}", headers=user_a["headers"]
    )
    assert resp.status_code == 403
    assert resp.json()["code"] == 1004
    detail = app_client.get(
        f"/api/v1/knowledge/items/{public_id}", headers=user_a["headers"]
    )
    assert detail.status_code == 200, "公共文档删除被拒后仍可见"


def test_public_reindex_allowed(
    app_client: Any,
    user_b: dict[str, Any],
    public_docs: list[int],
) -> None:
    """公共文档允许重索引（spec 5.4.1 规则 3 裁决）：受理 parsing → 幂等重跑 indexed。"""
    public_id = public_docs[0]
    resp = app_client.post(
        f"/api/v1/knowledge/items/{public_id}/reindex", headers=user_b["headers"]
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["data"] == {"item_id": public_id, "status": "parsing"}
    detail = app_client.get(
        f"/api/v1/knowledge/items/{public_id}", headers=user_b["headers"]
    )
    data = detail.json()["data"]
    assert data["status"] == "indexed"
    assert data["chunk_count"] > 0
    assert data["error_msg"] is None


def test_reindex_rejected_while_pending_or_parsing(
    app_client: Any, user_a: dict[str, Any]
) -> None:
    """处理中防护：pending / parsing 状态触发重索引 → 400 + code=1007。"""
    with SessionLocal() as db:
        owner = db.scalar(select(User).where(User.username == user_a["username"]))
        assert owner is not None
        for status in (KnowledgeItemStatus.PENDING, KnowledgeItemStatus.PARSING):
            db.add(
                KnowledgeItem(
                    user_id=owner.id,
                    title=f"状态测试_{status.value}",
                    source_type=KnowledgeSourceType.MD,
                    file_path=None,
                    scope=KnowledgeScope.PERSONAL,
                    status=status,
                    chunk_count=0,
                )
            )
        db.commit()
        ids = [
            row[0]
            for row in db.execute(
                select(KnowledgeItem.id).where(
                    KnowledgeItem.user_id == owner.id,
                    KnowledgeItem.status.in_(
                        [KnowledgeItemStatus.PENDING, KnowledgeItemStatus.PARSING]
                    ),
                )
            ).all()
        ]
    assert len(ids) == 2
    for item_id in ids:
        resp = app_client.post(
            f"/api/v1/knowledge/items/{item_id}/reindex", headers=user_a["headers"]
        )
        assert resp.status_code == 400, resp.text
        assert resp.json()["code"] == 1007


def test_delete_cascades_everywhere(
    app_client: Any,
    user_a: dict[str, Any],
    user_b: dict[str, Any],
    offline_embedding: None,
) -> None:
    """删除级联：列表消失 / 详情 404 / 分块 404 / SQLite chunk 行清空 / 检索不再命中。"""
    keyword = "超导量子干涉器件专属笔记"
    item_id = _upload_indexed(
        app_client, user_a, "超导器件笔记.md", (keyword * 40).encode("utf-8")
    )
    assert _search(app_client, user_a, "超导量子干涉器件")["results"], "删除前必须可命中"

    resp = app_client.delete(
        f"/api/v1/knowledge/items/{item_id}", headers=user_a["headers"]
    )
    assert resp.status_code == 200

    list_ids = [
        item["id"]
        for item in app_client.get(
            "/api/v1/knowledge/items?page=1&page_size=50", headers=user_a["headers"]
        ).json()["data"]["items"]
    ]
    assert item_id not in list_ids
    assert (
        app_client.get(
            f"/api/v1/knowledge/items/{item_id}", headers=user_a["headers"]
        ).status_code
        == 404
    )
    assert (
        app_client.get(
            f"/api/v1/knowledge/items/{item_id}/chunks", headers=user_a["headers"]
        ).status_code
        == 404
    )
    with SessionLocal() as db:
        rows = db.scalars(
            select(KnowledgeChunk).where(KnowledgeChunk.item_id == item_id)
        ).all()
        assert rows == [], "SQLite 分块行必须级联删除"
    results = _search(app_client, user_a, "超导量子干涉器件")["results"]
    assert all(
        "超导器件笔记" not in hit["source_title"] for hit in results
    ), "删除后向量清理生效，检索不得再命中"
    _ = user_b  # user_b 仅用于保证双用户环境与真实隔离基线