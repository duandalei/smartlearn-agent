"""上传受理与异步流水线集成测试（tasks.md 5.5）。

覆盖：未登录 401 / 扩展名白名单（.exe → 2000）/ 大小超限（30MB →
1001）/ 标题规则（stem、空 stem 兜底、路径穿越清洗）/ 合法 .md
全链路（受理 pending → 后台流水线 indexed → 分块可查）/ 扫描件
failed 固定文案。TestClient 在响应返回后同步执行 BackgroundTasks，
故请求返回即可断言终态。在线向量化一律 mock 不可用（本地兜底
真实执行）。
"""

from __future__ import annotations

from typing import Any

from app.rag.loader import SCAN_FILE_ERROR_MSG

_MD_CONTENT = (
    "# 线性代数基础\n\n"
    "向量空间是线性代数的核心研究对象，基与维数刻画了空间的结构的复杂度。\n\n"
    "## 矩阵分解\n\n"
    "特征值分解适用于方阵，奇异值分解则推广到任意矩阵，广泛用于降维与压缩。\n\n"
    "## 数值稳定性\n\n"
    "条件数衡量矩阵接近奇异的程度，直接决定线性方程组求解的误差放大倍数。\n"
).encode("utf-8")


def _get_item(client: Any, user: dict[str, Any], item_id: int) -> dict[str, Any]:
    """取文档详情 dict。"""
    resp = client.get(
        f"/api/v1/knowledge/items/{item_id}", headers=user["headers"]
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["data"]


def test_upload_requires_login(app_client: Any) -> None:
    """未登录上传 → HTTP 401 + code=1003。"""
    resp = app_client.post(
        "/api/v1/knowledge/upload",
        files={"file": ("a.md", _MD_CONTENT)},
    )
    assert resp.status_code == 401
    assert resp.json()["code"] == 1003


def test_upload_type_unsupported_exe(
    app_client: Any, user_a: dict[str, Any]
) -> None:
    """扩展名白名单外（.exe）→ HTTP 400 + code=2000。"""
    resp = app_client.post(
        "/api/v1/knowledge/upload",
        files={"file": ("malware.exe", b"MZ" + b"\x00" * 64)},
        headers=user_a["headers"],
    )
    assert resp.status_code == 400
    body = resp.json()
    assert body["code"] == 2000
    assert "不支持的文件类型" in body["message"]


def test_upload_exceeds_size_limit(
    app_client: Any, user_a: dict[str, Any]
) -> None:
    """大小超限（30MB > 20MB 上限）→ HTTP 422 + code=1001。"""
    resp = app_client.post(
        "/api/v1/knowledge/upload",
        files={"file": ("big.md", b"0" * (30 * 1024 * 1024))},
        headers=user_a["headers"],
    )
    assert resp.status_code == 422
    body = resp.json()
    assert body["code"] == 1001
    assert "20MB" in body["message"]


def test_upload_title_rules(
    app_client: Any, user_a: dict[str, Any], offline_embedding: None
) -> None:
    """标题规则：stem 作标题；空 stem 兜底「未命名文档」。"""
    resp = app_client.post(
        "/api/v1/knowledge/upload",
        files={"file": ("线性回归笔记.MD", _MD_CONTENT)},
        headers=user_a["headers"],
    )
    assert resp.status_code == 200, resp.text
    item_id = resp.json()["data"]["item_id"]
    item = _get_item(app_client, user_a, item_id)
    assert item["title"] == "线性回归笔记"
    assert item["source_type"] == "md"

    resp2 = app_client.post(
        "/api/v1/knowledge/upload",
        files={"file": (" .md", _MD_CONTENT)},
        headers=user_a["headers"],
    )
    assert resp2.status_code == 200, resp2.text
    item2 = _get_item(app_client, user_a, resp2.json()["data"]["item_id"])
    assert item2["title"] == "未命名文档"


def test_upload_path_traversal_sanitized(
    app_client: Any, user_a: dict[str, Any], offline_embedding: None
) -> None:
    """路径穿越文件名清洗：只保留 basename，正常建档索引。"""
    resp = app_client.post(
        "/api/v1/knowledge/upload",
        files={"file": ("../../evil.md", _MD_CONTENT)},
        headers=user_a["headers"],
    )
    assert resp.status_code == 200, resp.text
    item_id = resp.json()["data"]["item_id"]
    item = _get_item(app_client, user_a, item_id)
    assert item["title"] == "evil"
    assert ".." not in (item["file_path"] or "")


def test_upload_md_full_pipeline_indexed(
    app_client: Any, user_a: dict[str, Any], offline_embedding: None
) -> None:
    """合法 .md 全链路：受理返回 pending → 流水线 indexed → 分块可查。"""
    resp = app_client.post(
        "/api/v1/knowledge/upload",
        files={"file": ("线性代数笔记.md", _MD_CONTENT)},
        headers=user_a["headers"],
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data == {"item_id": data["item_id"], "status": "pending"}

    item = _get_item(app_client, user_a, data["item_id"])
    assert item["status"] == "indexed"
    assert item["error_msg"] is None
    assert item["chunk_count"] >= 2
    assert item["file_size"] == len(_MD_CONTENT)
    assert item["scope"] == "personal"
    assert item["user_id"] is not None

    chunks_resp = app_client.get(
        f"/api/v1/knowledge/items/{data['item_id']}/chunks",
        headers=user_a["headers"],
    )
    assert chunks_resp.status_code == 200, chunks_resp.text
    chunks = chunks_resp.json()["data"]
    assert len(chunks) == item["chunk_count"]
    assert [c["chunk_index"] for c in chunks] == list(range(len(chunks)))
    assert all(c["content"] for c in chunks)
    assert any(c["heading_path"] for c in chunks), "md 标题应落入 heading_path"
    assert all(
        c["embedding_id"] == f"item{data['item_id']}_chunk{c['chunk_index']}"
        for c in chunks
    )


def test_upload_scan_file_failed_fixed_message(
    app_client: Any, user_a: dict[str, Any], offline_embedding: None
) -> None:
    """扫描件（全标点无有效字符）→ failed + 固定文案（逐字）。"""
    resp = app_client.post(
        "/api/v1/knowledge/upload",
        files={"file": ("扫描件.txt", ("！？……\n\n".encode("utf-8")) * 50)},
        headers=user_a["headers"],
    )
    assert resp.status_code == 200, resp.text
    item_id = resp.json()["data"]["item_id"]
    item = _get_item(app_client, user_a, item_id)
    assert item["status"] == "failed"
    assert item["error_msg"] == SCAN_FILE_ERROR_MSG
    assert item["chunk_count"] == 0
    chunks_resp = app_client.get(
        f"/api/v1/knowledge/items/{item_id}/chunks", headers=user_a["headers"]
    )
    assert chunks_resp.status_code == 200
    assert chunks_resp.json()["data"] == []