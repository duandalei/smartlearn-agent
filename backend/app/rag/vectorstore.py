"""向量库模块：Chroma 双向量空间四 collection 封装。

模块职责（design.md 2.3.2-B / 2.4.1）：
- ``PersistentClient`` 模块级懒加载单例（``settings.CHROMA_DIR``，
  目录幂等创建；chromadb client 线程安全，兼容后台任务与请求并发）；
- collection 按「归属 × 向量空间」划分四类：
  ``kb_user_{user_id}`` / ``kb_user_{user_id}_local`` /
  ``kb_public`` / ``kb_public_local``——个人库按 user_id 分
  collection 实现「物理隔离即权限隔离」（spec 4.2 规则 5：不存在
  跨用户查询路径）；公共库向量独立成 ``kb_public*``，与
  ``scope=public / user_id=NULL`` 的关系口径一一对应；
- 度量统一 cosine（Chroma 默认 l2，必须显式指定）；
  ``score = 1 - distance``（cosine distance ∈ [0,2] → score ∈
  [-1,1]），保留 4 位小数；
- 记录 id 确定性：``item{item_id}_chunk{chunk_index}``——upsert
  幂等是「幽灵向量自愈」机制的核心（design.md 2.1.3-C）。

**运行环境约束（本机实测裁决，双保险已落地）**：
- chromadb 0.6.3 与 posthog 7.x 不兼容（telemetry 上报报错）：
  requirements.txt 已把 posthog 锁 ``<4``；本模块构造 client 时
  显式传 ``Settings(anonymized_telemetry=False)`` 关闭遥测上报，
  两道防线叠加；
- Chroma collection 命名规则：3~63 字符、字母数字开头结尾、仅
  字母数字/下划线/连字符——四类命名均合规，禁止使用单字符或含
  点号的临时名。

**运维边界（design.md 2.3.2-B）**：更换 ``EMBEDDING_MODEL`` 导致
在线维度变化时，既有在线向量与新向量不可比，须对全量文档执行
重索引（``_local`` 库不受影响）——这是双空间设计的已知代价。
在线 collection 维度由首批写入自动锁定，本模块不硬编码维度。

**写序依据（design.md 2.1.3-C）**：调用方（services 流水线）固定
按「先向量库后关系库」写入——反向顺序失败时会出现更差的
「已 indexed 但向量缺失」态；而本侧先写产生的幽灵向量在确定性
id + upsert 幂等下天然自愈（重索引覆盖 / 删除清理均收敛）。

chromadb 做防御性导入：导入失败抛 ``BizException(3001)``（检索
路径转 3001 / 流水线路径置 failed，契约 §8.4 调用点失败兜底）。
运行时调用异常不在本模块包装，由 services 层统一转换错误码。
"""

from __future__ import annotations

import logging
import threading
from pathlib import Path
from typing import Any

from app.core.config import settings
from app.core.response import CODE_VECTOR_FAILED, BizException
from app.models.knowledge import KnowledgeItem
from app.rag.embedding import EmbedMode
from app.rag.splitter import Chunk

logger = logging.getLogger(__name__)

# collection 创建元数据：显式指定 cosine 度量（design.md 2.3.2-B）。
_COLLECTION_METADATA: dict[str, Any] = {"hnsw:space": "cosine"}

# 模块级懒加载单例与初始化锁（后台任务与请求并发安全）。
_vector_store: Any | None = None
_store_lock = threading.Lock()


def get_vector_store() -> Any:
    """获取 Chroma PersistentClient（懒加载线程安全单例）。

    目录不存在时 ``mkdir(parents=True, exist_ok=True)`` 幂等创建；
    构造参数显式关闭匿名遥测（chromadb 0.6.3 + posthog 不兼容的
    双保险第二道防线，见模块 docstring 运行环境约束）。

    Returns:
        Any: chromadb PersistentClient 单例（duck-typed，避免模块
        顶层 import 依赖，与防御性导入策略配套）。

    Raises:
        BizException: code=3001 / HTTP 500，chromadb 导入失败
            （部分安装损坏 / 二进制依赖缺失等运行时风险）。
    """
    global _vector_store
    if _vector_store is None:
        with _store_lock:
            if _vector_store is None:
                try:
                    import chromadb
                    from chromadb.config import Settings as ChromaSettings
                except ImportError as exc:  # pragma: no cover - 环境缺依赖防御
                    logger.error("chromadb 导入失败: %s", exc)
                    raise BizException(
                        CODE_VECTOR_FAILED,
                        "向量库依赖不可用，请联系管理员",
                        http_status=500,
                    ) from exc
                Path(settings.CHROMA_DIR).mkdir(parents=True, exist_ok=True)
                _vector_store = chromadb.PersistentClient(
                    path=settings.CHROMA_DIR,
                    settings=ChromaSettings(anonymized_telemetry=False),
                )
    return _vector_store


def _reset_vector_store() -> None:
    """清空 client 单例缓存。

    仅供测试注入独立 ``CHROMA_DIR`` 后重建使用（同
    ``services/llm.py`` 的 ``reset_clients`` 惯例），业务代码
    不得调用。
    """
    global _vector_store
    with _store_lock:
        _vector_store = None


def _collection_name(scope: str, user_id: int | None, mode: EmbedMode) -> str:
    """按「归属 × 向量空间」推导 collection 名。

    Args:
        scope: 归属作用域（"personal" / "public"，来自
            knowledge_items.scope）。
        user_id: 归属用户 id（personal 必填，public 恒 None）。
        mode: 向量空间模式（online=在线 embedding / offline=本地兜底）。

    Returns:
        str: collection 名（满足 Chroma 3-63 字符命名规则）。

    Raises:
        ValueError: personal 归属缺少 user_id（不可达防御分支）。
    """
    if scope == "public":
        return "kb_public" if mode == "online" else "kb_public_local"
    if user_id is None:
        raise ValueError("personal 归属的 collection 必须提供 user_id")
    return f"kb_user_{user_id}" if mode == "online" else f"kb_user_{user_id}_local"


def _collection(scope: str, user_id: int | None, mode: EmbedMode) -> Any:
    """获取（或创建）对应归属与模式的 collection。

    Args:
        scope: 归属作用域（"personal" / "public"）。
        user_id: 归属用户 id（public 传 None）。
        mode: 向量空间模式。

    Returns:
        Any: chromadb Collection（cosine 度量）。
    """
    return get_vector_store().get_or_create_collection(
        name=_collection_name(scope, user_id, mode),
        metadata=_COLLECTION_METADATA,
    )


def _chunk_metadata(item: KnowledgeItem, chunk: Chunk) -> dict[str, Any]:
    """组装单条向量记录的 metadata（Chroma 限标量类型）。

    Args:
        item: 归属文档（提供 id / scope / user_id / title）。
        chunk: 分块（提供 chunk_index / heading_path）。

    Returns:
        dict[str, Any]: item_id / chunk_index / scope / title /
        heading_path；个人库另含 user_id（design.md 2.3.2-B metadata
        约定——检索结果直接从命中 metadata 组装来源，免 SQL 回表）。
    """
    # scope 取落库口径值（str enum 的 str() 会返回类名，须取 .value）。
    scope_value = getattr(item.scope, "value", item.scope)
    metadata: dict[str, Any] = {
        "item_id": int(item.id),
        "chunk_index": int(chunk["chunk_index"]),
        "scope": scope_value,
        "title": str(item.title),
        "heading_path": str(chunk["heading_path"] or ""),
    }
    if item.user_id is not None:
        metadata["user_id"] = int(item.user_id)
    return metadata


def upsert_chunks(
    item: KnowledgeItem,
    chunks: list[Chunk],
    vectors: list[list[float]],
    mode: EmbedMode,
) -> None:
    """批量 upsert 分块向量到 mode 对应空间的 collection。

    记录 id 确定性（``item{item_id}_chunk{chunk_index}``）：同 id
    重复 upsert 直接覆盖旧值——重索引幂等、幽灵向量自愈均依赖
    此性质（design.md 2.1.3-C / 2.2.2-3 幂等性论证）。**调用方
    负责「入库无条件双写」编排**：兜底向量调本函数传
    ``mode="offline"``，在线模式成功时再调一次传 ``mode="online"``。

    Args:
        item: 归属文档。
        chunks: 分块列表。
        vectors: 与 chunks 逐条对齐的向量列表（维度以调用方为准，
            本模块不做维度断言）。
        mode: 向量空间模式（决定写入在线库或兜底库）。
    """
    if not chunks:
        return
    if len(vectors) != len(chunks):
        raise ValueError(
            f"向量数与分块数不一致: {len(vectors)} != {len(chunks)}"
        )
    # scope 取落库口径值（str enum 的 str() 返回类名，见 _chunk_metadata）。
    scope_value = getattr(item.scope, "value", item.scope)
    collection = _collection(scope_value, item.user_id, mode)
    ids = [f"item{item.id}_chunk{chunk['chunk_index']}" for chunk in chunks]
    collection.upsert(
        ids=ids,
        embeddings=[list(vector) for vector in vectors],
        documents=[chunk["content"] for chunk in chunks],
        metadatas=[_chunk_metadata(item, chunk) for chunk in chunks],
    )


def delete_item_vectors(item_id: int, scope: str, user_id: int | None) -> None:
    """删除某文档在两个向量空间 collection 中的全部向量。

    按 ``where={"item_id": id}`` 精确匹配删除；调用场景为删除
    文档的 best-effort 清理与流水线失败分支的幽灵向量缓解
    （design.md 2.1.3-C）。

    Args:
        item_id: 文档 id。
        scope: 归属作用域（"personal" / "public"）。
        user_id: 归属用户 id（public 传 None）。
    """
    for mode in ("online", "offline"):
        collection = _collection(scope, user_id, mode)
        collection.delete(where={"item_id": int(item_id)})


def query_visible(
    user_id: int,
    query_vector: list[float],
    top_k: int,
    mode: EmbedMode,
    scope: str = "all",
) -> list[dict[str, Any]]:
    """按检索范围档位在可见 collection 中检索并合并（P9 scope 扩展）。

    按 mode 选库（design.md 2.4.1 规则 2：查询向量与被查库必然
    同空间——online 查 ``kb_user_{uid}`` / ``kb_public``；offline
    查对应 ``_local`` 库）；**过滤发生在 collection 选择层**（P9
    design.md 2.5）而非 SQL where 或 Chroma where metadata——
    ``personal`` 仅查本人个人库、``public`` 仅查公共库、``all``
    维持两路合并（现状行为原样）。隔离红线结构性继承：双层知识库
    的物理隔离就是 collection 级（``kb_user_{uid}`` 分库即权限边界），
    personal 档在存储结构上不可能命中他用户内容（验收 D4 的结构性
    保证）。每库 ``n_results = min(top_k, count)`` 且 ``count()==0``
    直接跳过（空库查询防御）；命中合并后按 score 降序截断 top_k
    （单路档位时合并退化为恒等）。

    Args:
        user_id: 当前用户 id（决定个人库 collection，跨用户命中在
            存储结构上不可能）。
        query_vector: 查询向量（与 mode 同空间）。
        top_k: 期望命中条数上限。
        mode: 查询向量空间模式。
        scope: 检索范围三档（personal / public / all），默认 all
            （前向兼容：不传时行为与扩展前逐行一致）。

    Returns:
        list[dict[str, Any]]: 命中列表（content / item_id /
        chunk_index / scope / title / heading_path / score，按 score
        降序）；空库返回空列表。
    """
    if scope == "personal":
        targets: tuple[tuple[str, int | None], ...] = (
            ("personal", user_id),
        )
    elif scope == "public":
        targets = (("public", None),)
    else:
        targets = (("personal", user_id), ("public", None))
    hits: list[dict[str, Any]] = []
    for owner_scope, owner_id in targets:
        collection = _collection(owner_scope, owner_id, mode)
        total = collection.count()
        if total == 0:
            continue
        result = collection.query(
            query_embeddings=[list(query_vector)],
            n_results=min(top_k, total),
            include=["documents", "metadatas", "distances"],
        )
        documents = result["documents"][0]
        metadatas = result["metadatas"][0]
        distances = result["distances"][0]
        for document, metadata, distance in zip(documents, metadatas, distances):
            meta = metadata or {}
            hits.append(
                {
                    "content": document,
                    "item_id": meta.get("item_id"),
                    "chunk_index": meta.get("chunk_index"),
                    "scope": meta.get("scope", owner_scope),
                    "title": meta.get("title", ""),
                    "heading_path": meta.get("heading_path", ""),
                    "score": round(1.0 - float(distance), 4),
                }
            )
    hits.sort(key=lambda hit: hit["score"], reverse=True)
    return hits[:top_k]