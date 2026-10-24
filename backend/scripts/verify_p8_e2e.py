"""P8 知识库端到端集成验收（tasks.md 组 7，spec 附录 6 场景 API 级覆盖）。

场景对齐（沙箱可执行部分；浏览器交互项留给用户本机走查）：
- 场景 1：上传中文文档全链路 pending→parsing→indexed、chunk_count
  与分块接口条数一致、error_msg 为空；
- 场景 2：检索「Transformer 的注意力机制」Top-1 命中 ml_basics
  第六章 QKV 分块且分数最高（离线兜底模式；在线模式用户本机已实测）；
- 场景 3：30MB 超限（1001）与 .exe 白名单外（2000）均拒绝且不建档；
- 场景 4：Embedding 不可用降级——上传仍 indexed、检索 mode=offline；
- 场景 5：扫描件 failed 固定文案 + chunk_count=0 + 重索引可重试闭环；
- 场景 6：列表字段完整性（chunk_count/file_size/error_msg/scope/status，
  对齐用户实测口径：演示文档重索引后 9/8/8/8 与文件大小展示）；
- 组 8.1 既有接口回归：/health、列表分页结构、详情 404 防枚举、
  /knowledge-chunks 全局端点零改动。

隔离口径：临时 SQLite + 临时 Chroma 目录 + 临时上传目录（复用
tests/conftest.py 同构手法），全程不触碰 data/smartlearn.db 与
data/chroma/。沙箱网络口径：在线 Embedding 一律 mock 不可用
（本地兜底真实执行——与 pytest 同口径）。
"""

from __future__ import annotations

import importlib.util
import os
import sys
import tempfile
from pathlib import Path
from typing import Any

BACKEND_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_ROOT))

_TEST_ROOT = Path(tempfile.mkdtemp(prefix="p8_e2e_"))
os.environ["DATABASE_URL"] = f"sqlite:///{(_TEST_ROOT / 'e2e.db').as_posix()}"

_SANDBOX_PATCH = BACKEND_ROOT / "scripts" / "_sandbox_patch.py"
if _SANDBOX_PATCH.is_file():
    _spec = importlib.util.spec_from_file_location("_sandbox_patch", _SANDBOX_PATCH)
    if _spec is not None and _spec.loader is not None:
        _module = importlib.util.module_from_spec(_spec)
        _spec.loader.exec_module(_module)

import asyncio  # noqa: E402

from fastapi.testclient import TestClient  # noqa: E402

from app.core.config import settings  # noqa: E402
from app.core.response import BizException  # noqa: E402
import app.rag.embedding as embedding_module  # noqa: E402
from app.main import app  # noqa: E402
from app.rag import vectorstore  # noqa: E402

PASS: list[str] = []
FAIL: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    """记录单条断言结果。"""
    (PASS if ok else FAIL).append(name if ok else f"{name} <-- {detail}")
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f"  ({detail})" if detail and not ok else ""))


def _mock_offline() -> None:
    """把在线向量化 mock 为不可用（沙箱口径：兜底真实执行）。"""

    def _unavailable() -> Any:
        raise BizException(3000, "AI 服务未配置", http_status=502)

    embedding_module.get_embedding_client = _unavailable  # type: ignore[assignment]


_MD_DOC = (
    "# 机器学习讲义\n\n"
    "监督学习从标注数据中学习映射，线性回归是最基础的回归模型。\n\n"
    "## 神经网络\n\n"
    "多层感知机由输入层、隐藏层与输出层构成，反向传播算法逐层更新权重。\n\n"
    "## 注意力机制\n\n"
    "自注意力 Self-Attention 将每个位置映射为 QKV 三组向量，通过缩放点积\n"
    "计算相关性权重，使模型能够聚焦重要信息，是 Transformer 的核心组件。\n"
).encode("utf-8")


def main() -> None:
    """执行全部端到端场景断言。"""
    settings.CHROMA_DIR = str(_TEST_ROOT / "chroma")
    settings.UPLOAD_DIR = str(_TEST_ROOT / "uploads")
    vectorstore._reset_vector_store()
    _mock_offline()

    from app.db.session import engine
    from app.models.base import Base

    Base.metadata.create_all(engine)

    def seed_demo_docs(user_id: int) -> None:
        """把 4 篇演示文档播种到指定用户的个人库并跑真实离线流水线。"""
        from app.db.session import SessionLocal
        from app.models.enums import (
            KnowledgeItemStatus,
            KnowledgeScope,
            KnowledgeSourceType,
        )
        from app.models.knowledge import KnowledgeItem
        from app.services.knowledge import process_document

        seed_dir = BACKEND_ROOT.parent / "data" / "uploads" / "1"
        names = [
            "1_ml_basics.md",
            "2_linear_algebra_notes.md",
            "3_probability_formulas.md",
            "4_ds_cheatsheet.md",
        ]
        files = [seed_dir / name for name in names]
        item_ids: list[int] = []
        with SessionLocal() as db:
            for md_file in files:
                item = KnowledgeItem(
                    user_id=user_id,
                    title=md_file.stem.split("_", 1)[-1],
                    source_type=KnowledgeSourceType.MD,
                    file_path=f"data/uploads/1/{md_file.name}",
                    scope=KnowledgeScope.PERSONAL,
                    status=KnowledgeItemStatus.PENDING,
                    chunk_count=0,
                    file_size=md_file.stat().st_size,
                )
                db.add(item)
                db.flush()
                item_ids.append(item.id)
            db.commit()
        for item_id in item_ids:
            asyncio.run(process_document(item_id))

    with TestClient(app) as client:
        # ------------------------------------------------------------------
        # 用户注册
        # ------------------------------------------------------------------
        resp = client.post(
            "/api/v1/auth/register",
            json={"username": "e2e_user", "password": "Passw0rd123!", "confirm_password": "Passw0rd123!"},
        )
        assert resp.status_code == 200, resp.text
        headers = {"Authorization": f"Bearer {resp.json()['data']['access_token']}"}
        user_id = client.get("/api/v1/auth/me", headers=headers).json()["data"]["id"]

        # ------------------------------------------------------------------
        # 场景 6 前置：播种 4 篇演示文档到当前用户个人库
        # ------------------------------------------------------------------
        print("场景 6 前置：播种 4 篇演示文档（真实离线流水线，仅个人库）")
        seed_demo_docs(user_id)

        # ------------------------------------------------------------------
        # 场景 6：列表字段完整性（演示文档重索引后）
        # ------------------------------------------------------------------
        print("\n场景 6：演示文档列表字段（chunk_count / file_size / scope / status）")
        resp = client.get("/api/v1/knowledge/items?page=1&page_size=50", headers=headers)
        data = resp.json()["data"]
        demo_rows = [r for r in data["items"] if r["scope"] == "personal"]
        check("演示文档 4 篇可见", len(demo_rows) == 4, f"got {len(demo_rows)}")
        check("全部 indexed", all(r["status"] == "indexed" for r in demo_rows))
        check("chunk_count 全部 > 0（真实分块数 8~12）", all(8 <= r["chunk_count"] <= 12 for r in demo_rows), str([(r["title"], r["chunk_count"]) for r in demo_rows]))
        check("file_size 全部非空（前端展示大小列）", all(r["file_size"] and r["file_size"] > 0 for r in demo_rows))
        check("error_msg 全部为空", all(r["error_msg"] is None for r in demo_rows))
        ml = next(r for r in demo_rows if r["title"] == "ml_basics")
        ds = next(r for r in demo_rows if r["title"] == "ds_cheatsheet")
        check("chunk_count 分布 == 用户实测 9/8/8/8（9 属数据结构速查）", ds["chunk_count"] == 9 and ml["chunk_count"] == 8, f"ds={ds['chunk_count']} ml={ml['chunk_count']}")

        # ------------------------------------------------------------------
        # 场景 1：上传中文文档全链路
        # ------------------------------------------------------------------
        print("\n场景 1：上传中文文档全链路（pending → parsing → indexed）")
        resp = client.post(
            "/api/v1/knowledge/upload",
            files={"file": ("机器学习讲义.md", _MD_DOC)},
            headers=headers,
        )
        check("受理即时返回 200", resp.status_code == 200, resp.text)
        accepted = resp.json()["data"]
        check("受理响应 status == pending", accepted["status"] == "pending", str(accepted))
        item_id = accepted["item_id"]

        detail = client.get(f"/api/v1/knowledge/items/{item_id}", headers=headers).json()["data"]
        check("流水线终态 indexed（TestClient 同步执行后台任务）", detail["status"] == "indexed", str(detail["status"]))
        check("chunk_count > 0", detail["chunk_count"] > 0, str(detail["chunk_count"]))
        check("error_msg 为空", detail["error_msg"] is None)
        check("file_size == 上传字节数", detail["file_size"] == len(_MD_DOC))

        chunks = client.get(f"/api/v1/knowledge/items/{item_id}/chunks", headers=headers).json()["data"]
        check("分块接口条数 == chunk_count", len(chunks) == detail["chunk_count"], f"{len(chunks)} != {detail['chunk_count']}")
        check("分块含 heading_path 标题路径", any(c["heading_path"] for c in chunks))

        # ------------------------------------------------------------------
        # 场景 2：检索「Transformer 的注意力机制」Top-1 命中第六章
        # （独立用户：只播种演示文档，排除场景 1 上传文档的词面竞争）
        # ------------------------------------------------------------------
        print("\n场景 2：语义检索 Top-1 命中（离线兜底模式）")
        resp = client.post(
            "/api/v1/auth/register",
            json={"username": "e2e_searcher", "password": "Passw0rd123!", "confirm_password": "Passw0rd123!"},
        )
        search_headers = {"Authorization": f"Bearer {resp.json()['data']['access_token']}"}
        searcher_id = client.get(
            "/api/v1/auth/me", headers=search_headers
        ).json()["data"]["id"]
        seed_demo_docs(searcher_id)
        resp = client.post(
            "/api/v1/knowledge/search",
            json={"query": "Transformer 的注意力机制", "top_k": 5},
            headers=search_headers,
        )
        data = resp.json()["data"]
        check("检索 200 且 mode=offline（沙箱口径）", data["mode"] == "offline", str(data["mode"]))
        results = data["results"]
        check("结果非空", len(results) > 0)
        top = results[0]
        check("Top-1 命中第六章标题路径", "六、Transformer 与注意力机制" in top["source_title"], top["source_title"])
        check("Top-1 内容含 QKV/注意力语义", ("QKV" in top["content"]) or ("注意力" in top["content"]))
        scores = [r["score"] for r in results]
        check("Top-1 分数为全部结果中最高", top["score"] == max(scores))
        check("score 保留 4 位小数口径（数值型）", all(isinstance(r["score"], float) for r in results))

        # ------------------------------------------------------------------
        # 场景 3：非法文件拒绝
        # ------------------------------------------------------------------
        print("\n场景 3：非法文件拒绝（30MB 超限 + .exe 白名单外）")
        resp = client.post(
            "/api/v1/knowledge/upload",
            files={"file": ("big.txt", b"0" * (30 * 1024 * 1024))},
            headers=headers,
        )
        check("30MB → HTTP 422 + code=1001", resp.status_code == 422 and resp.json()["code"] == 1001, resp.text[:120])
        resp = client.post(
            "/api/v1/knowledge/upload",
            files={"file": ("tool.exe", b"MZ" + b"\x00" * 64)},
            headers=headers,
        )
        check(".exe → HTTP 400 + code=2000", resp.status_code == 400 and resp.json()["code"] == 2000, resp.text[:120])
        listing = client.get("/api/v1/knowledge/items?page=1&page_size=50", headers=headers).json()["data"]
        titles = {r["title"] for r in listing["items"]}
        check("两次拒绝均不建档", "big" not in titles and "tool" not in titles, str(titles))
        upload_dir = _TEST_ROOT / "uploads"
        leftover = [p for p in upload_dir.rglob("*") if p.is_file()] if upload_dir.is_dir() else []
        check("拒绝文件不落盘（无 big/tool 命名残留）", all("big" not in p.name and "tool" not in p.name for p in leftover), str([p.name for p in leftover]))

        # ------------------------------------------------------------------
        # 场景 4：Embedding 不可用自动降级
        # ------------------------------------------------------------------
        print("\n场景 4：Embedding 不可用降级（沙箱天然 mock，上传/检索不中断）")
        resp = client.post(
            "/api/v1/knowledge/upload",
            files={"file": ("降级验证.md", _MD_DOC)},
            headers=headers,
        )
        check("降级期上传仍受理 200", resp.status_code == 200, resp.text[:120])
        degrade_id = resp.json()["data"]["item_id"]
        detail = client.get(f"/api/v1/knowledge/items/{degrade_id}", headers=headers).json()["data"]
        check("兜底向量化入库 → indexed（不得 failed）", detail["status"] == "indexed", str(detail["status"]))
        resp = client.post(
            "/api/v1/knowledge/search",
            json={"query": "注意力机制", "top_k": 3},
            headers=headers,
        )
        data = resp.json()["data"]
        check("降级期检索 mode=offline", data["mode"] == "offline")
        check("降级期检索结果正常返回", len(data["results"]) > 0)
        check("每条结果带相似度分数（前端警示+分数三件套的数据来源）", all("score" in r for r in data["results"]))

        # ------------------------------------------------------------------
        # 场景 5：扫描件识别 failed + 重索引重试闭环
        # ------------------------------------------------------------------
        print("\n场景 5：扫描件 failed 固定文案 + 重试闭环")
        resp = client.post(
            "/api/v1/knowledge/upload",
            files={"file": ("扫描件.txt", ("！？……\n\n".encode("utf-8")) * 50)},
            headers=headers,
        )
        scan_id = resp.json()["data"]["item_id"]
        detail = client.get(f"/api/v1/knowledge/items/{scan_id}", headers=headers).json()["data"]
        check("扫描件 → failed（非 indexed 非 0 分块静默成功）", detail["status"] == "failed", str(detail["status"]))
        check("error_msg 逐字为固定文案", detail["error_msg"] == "该文件可能是扫描件，未提取到文字（当前版本不支持 OCR）", str(detail["error_msg"]))
        check("chunk_count == 0", detail["chunk_count"] == 0)
        resp = client.post(f"/api/v1/knowledge/items/{scan_id}/reindex", headers=headers)
        check("failed 文档重索引受理 200（parsing）", resp.status_code == 200 and resp.json()["data"]["status"] == "parsing", resp.text[:120])
        detail = client.get(f"/api/v1/knowledge/items/{scan_id}", headers=headers).json()["data"]
        check("重索引后再次 failed（可重试闭环）", detail["status"] == "failed", str(detail["status"]))

        # ------------------------------------------------------------------
        # 组 8.1：既有接口回归
        # ------------------------------------------------------------------
        print("\n组 8.1：既有接口回归")
        resp = client.get("/health")
        check("/health 正常", resp.status_code == 200 and resp.json()["code"] == 0, resp.text[:120])
        resp = client.get("/api/v1/knowledge/items?page=1&page_size=2", headers=headers)
        data = resp.json()["data"]
        check("列表分页结构 {items,total,page,page_size} 不变", set(data.keys()) == {"items", "total", "page", "page_size"}, str(data.keys()))
        check("page_size=2 生效", len(data["items"]) == 2 and data["page_size"] == 2)
        resp = client.get("/api/v1/knowledge/items/99999", headers=headers)
        check("详情防枚举 404/1005", resp.status_code == 404 and resp.json()["code"] == 1005, resp.text[:120])
        resp = client.get("/api/v1/knowledge-chunks?page=1&page_size=5", headers=headers)
        check("全局 /knowledge-chunks 零改动可用", resp.status_code == 200 and "items" in resp.json()["data"], resp.text[:120])
        resp = client.get("/api/v1/knowledge/items")
        check("未登录 401/1003（既有鉴权口径）", resp.status_code == 401 and resp.json()["code"] == 1003, resp.text[:120])

    print(f"\n{'=' * 60}")
    print(f"PASS={len(PASS)}  FAIL={len(FAIL)}")
    for line in FAIL:
        print("  FAILED:", line)
    raise SystemExit(1 if FAIL else 0)


if __name__ == "__main__":
    main()