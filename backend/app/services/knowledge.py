"""知识库业务编排服务：上传受理 / 异步流水线 / 删除 / 重索引 / 检索。

职责边界（PROJECT_CONTEXT §4 分层铁律）：本模块承载知识库全部业务
规则与事务边界，api 层只做参数解析 + 鉴权注入 + 调用本模块 +
``success()`` 包装；rag 四模块为纯能力层，由本模块编排。

核心设计落点（全部回链 design.md）：
- 上传受理（2.2.2-1）：白名单/大小校验 → 落盘 → 建档(pending)；
- 异步流水线 ``process_document``（2.1.3-A/B）：BackgroundTasks +
  ``asyncio.to_thread`` 卸载解析 CPU 段（单进程 uvicorn 下保证
  上传/检索接口不被阻塞，spec 4.2 规则 4）；每次状态变更用自建
  ``SessionLocal()`` 独立短事务提交（前端轮询立即可见中间态，
  且避免与请求会话争 SQLite 锁）；
- 写序（2.1.3-C）：固定「先向量库后关系库，状态最后」——反向顺序
  失败会产生更差的「已 indexed 但向量缺失」态；本侧先写产生的
  幽灵向量在确定性 id + upsert 幂等下天然自愈（重索引覆盖 /
  删除清理均收敛一致）；
- 向量双写（2.4.1）：兜底向量无条件计算并写 ``_local`` 库，在线
  模式成功时另写在线库（文档级模式锁定）；
- 删除（2.2.2-2）：请求事务内同步删 SQLite（列表立即不可见、
  检索不再命中的强感知），向量与原件清理放 background_tasks
  best-effort 执行（失败仅 warning 不回滚，design.md 2.1.3-C）；
- 重索引（2.2.2-3）：``pending/parsing`` 拒绝（1007，封死「受理后
  任务尚未启动」的竞态窗口）；
- 检索编排（2.2.2-5）：查询向量化（在线→兜底）→ 同空间「本人
  个人库」collection 检索；mode 只随响应透出
  **不落库**（可用性是瞬时状态，落库会过期误导，design.md 2.4.3）；
  本函数是 P9 Agent 工具 ``search_knowledge_base`` 的业务底座，
  签名保持稳定。

error_msg 阶段化前缀规范（spec 4.4 规则 2 / design.md 2.7-B）：
一律「``{环节}失败：{原因}``」，环节 ∈ {解析, 切分, 向量化,
向量入库, 分块落库}；异常摘要取 ``str(exc)[:120]``（防长堆栈
刷屏），完整堆栈进日志。两条例外文案（spec/design 逐字锁定）：
- 扫描件：「该文件可能是扫描件，未提取到文字（当前版本不支持
  OCR）」（rag/loader.SCAN_FILE_ERROR_MSG）；
- 原件丢失：「文件不存在或不可读」。
"""

from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path
from typing import Any, Literal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import PROJECT_ROOT, settings
from app.core.response import (
    CODE_BIZ_CONFLICT,
    CODE_LLM_FAILED,
    CODE_NOT_FOUND,
    CODE_PARAM_INVALID,
    CODE_VECTOR_FAILED,
    CODE_FILE_TYPE_UNSUPPORTED,
    BizException,
)
from app.db.session import SessionLocal
from app.models.enums import KnowledgeItemStatus, KnowledgeScope, KnowledgeSourceType
from app.models.knowledge import KnowledgeChunk, KnowledgeItem
from app.models.user import User
from app.rag.embedding import (
    EmbedMode,
    embed_texts_local,
    embed_texts_with_fallback,
    embed_query_with_fallback,
)
from app.rag.loader import SCAN_FILE_ERROR_MSG, ScanFileError, load_document
from app.rag.splitter import Chunk, split_document
from app.rag.vectorstore import delete_item_vectors, query_visible, upsert_chunks
from app.schemas.knowledge import KnowledgeChunkOut, KnowledgeSearchHit, KnowledgeSearchOut

logger = logging.getLogger(__name__)

# 上传大小上限（spec 5.1.1 规则 2：20MB，按实际读入字节判定）。
MAX_UPLOAD_BYTES: int = 20 * 1024 * 1024

# 上传扩展名白名单（小写判定，大小写不敏感；note 类型仅种子使用）。
_ALLOWED_SUFFIXES: frozenset[str] = frozenset({"pdf", "docx", "pptx", "md", "txt"})

# 异常摘要进 error_msg 的最大长度（design.md 2.7-B）。
_ERROR_SUMMARY_LIMIT: int = 120


def _enum_value(value: Any) -> str:
    """取枚举的落库值（枚举 → ``.value``；裸字符串原样返回）。

    ``class X(str, Enum)`` 的 ``str()`` 返回 ``'X.MEMBER'`` 而非
    成员值（Python 3.13 实测），collection 命名与 where 过滤必须
    用本辅助取 ``'personal'`` 这类落库口径值。

    Args:
        value: 枚举成员或裸字符串。

    Returns:
        str: 落库口径的字符串值。
    """
    return getattr(value, "value", value)


# ---------------------------------------------------------------------------
# 可见性口径（单一来源：api 层与本模块共用，防越权与防枚举）
# ---------------------------------------------------------------------------


def visibility_filters(user_id: int) -> list[Any]:
    """构造知识库可见性过滤条件：仅本人文档（公共库已移除）。

    api 层存量端点（列表/详情）与本模块写操作端点（删除/重索引/
    分块查看）共用同一口径——「不可见即不存在」防 ID 枚举的单一
    实现（design.md 1.2-1：分层约束下本函数下沉 services，api 层
    ``_visibility_filters`` 薄委托此处）。

    Args:
        user_id: 当前用户 id。

    Returns:
        list[Any]: SQLAlchemy 过滤条件列表。
    """
    return [KnowledgeItem.user_id == user_id]


def _get_visible_item(db: Session, user: User, item_id: int) -> KnowledgeItem:
    """按可见性口径取文档；不可见或不存在统一 1005/404（防枚举）。

    Args:
        db: 请求级数据库会话。
        user: 当前登录用户。
        item_id: 文档 id。

    Returns:
        KnowledgeItem: 可见文档的 ORM 对象。

    Raises:
        BizException: code=1005 / HTTP 404。
    """
    stmt = (
        select(KnowledgeItem)
        .where(KnowledgeItem.id == item_id)
        .where(*visibility_filters(user.id))
    )
    item = db.scalar(stmt)
    if item is None:
        raise BizException(CODE_NOT_FOUND, "资源不存在", http_status=404)
    return item


# ---------------------------------------------------------------------------
# 上传受理（design.md 2.2.2-1）
# ---------------------------------------------------------------------------


async def create_item_from_upload(
    db: Session, user: User, filename: str, content: bytes
) -> KnowledgeItem:
    """上传受理：校验白名单与大小 → 落盘 → 建档(pending)。

    错误码取舍（design.md 2.9 决策 #8）：2000 语义锁定「文件类型
    不支持」（spec 5.1.3 场景 1 明确指定）；大小超限属上传参数
    校验范畴归 1001（spec 场景 2 仅要求「明确提示」未指定码位）。

    Args:
        db: 请求级数据库会话（受理事务由本函数提交）。
        user: 当前登录用户（个人库归属者）。
        filename: 上传原始文件名（经 ``Path(filename).name`` 清洗
            防路径穿越）。
        content: 文件完整字节（大小按 ``len(content)`` 实际判定，
            杜绝只信 Content-Length 头）。

    Returns:
        KnowledgeItem: 已建档的文档（status=pending）；调用方负责
        ``background_tasks.add_task(process_document, item.id)``
        入队异步流水线。

    Raises:
        BizException: code=2000 / HTTP 400，扩展名不在白名单；
            code=1001 / HTTP 422，大小超过 20MB。
    """
    # ① 文件名清洗：仅保留 basename，杜绝 ``../`` 类路径穿越。
    safe_name = os.path.basename(filename.replace("\\", "/"))
    suffix = os.path.splitext(safe_name)[1].lower().lstrip(".")
    if suffix not in _ALLOWED_SUFFIXES:
        raise BizException(
            CODE_FILE_TYPE_UNSUPPORTED,
            "不支持的文件类型，仅支持 PDF/DOCX/PPTX/MD/TXT",
            http_status=400,
        )
    if len(content) > MAX_UPLOAD_BYTES:
        raise BizException(
            CODE_PARAM_INVALID,
            "文件过大（上限 20MB）",
            http_status=422,
        )
    stem = safe_name[: -len(suffix) - 1] if suffix else safe_name
    if not stem.strip():
        stem = "未命名文档"

    # ② 建档（flush 取 id 供落盘文件名前缀，防同名覆盖）。
    item = KnowledgeItem(
        user_id=user.id,
        title=stem,
        source_type=KnowledgeSourceType(suffix),
        scope=KnowledgeScope.PERSONAL,
        status=KnowledgeItemStatus.PENDING,
        chunk_count=0,
        file_size=len(content),
    )
    db.add(item)
    db.flush()

    # ③ 落盘：路径从 ``settings.UPLOAD_DIR`` 派生（可被测试环境
    # 覆盖隔离）；``file_path`` 存相对项目根 POSIX 路径（与演示文档
    # 种子同口径，运行时以 PROJECT_ROOT 拼接解析）；UPLOAD_DIR 被
    # 指到项目外（测试隔离）时退化为绝对路径——pathlib 的
    # ``PROJECT_ROOT / 绝对路径`` 语义天然兼容，解析口径不二分。
    upload_dir = Path(settings.UPLOAD_DIR)
    target = upload_dir / str(user.id) / f"{item.id}_{safe_name}"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(content)
    try:
        item.file_path = target.resolve().relative_to(PROJECT_ROOT).as_posix()
    except ValueError:
        item.file_path = target.resolve().as_posix()
    db.commit()
    logger.info(
        "知识库文档受理: item_id=%s user_id=%s size=%d",
        item.id,
        user.id,
        len(content),
    )
    return item


# ---------------------------------------------------------------------------
# 异步流水线（design.md 2.1.3-A/B 状态机与活动图）
# ---------------------------------------------------------------------------


def _mark_failed(item_id: int, error_msg: str) -> None:
    """把文档置为 failed 并写入中文原因（独立短事务）。

    Args:
        item_id: 文档 id。
        error_msg: 阶段化中文原因（「{环节}失败：{摘要}」格式或
            逐字锁定的例外文案）。
    """
    with SessionLocal() as db:
        item = db.get(KnowledgeItem, item_id)
        if item is None:
            return
        item.status = KnowledgeItemStatus.FAILED
        item.error_msg = error_msg
        db.commit()
    logger.warning("知识库文档处理失败: item_id=%s reason=%s", item_id, error_msg)


async def process_document(item_id: int) -> None:
    """后台异步流水线：解析 → 切分 → 向量化 → 向量入库 → 分块落库。

    BackgroundTasks 目标（Starlette 在响应返回后调度）。每次状态
    变更用自建 ``SessionLocal()`` 独立短事务提交，保证前端轮询
    ``GET /items`` 立即可见中间态；同步 CPU 段（文档解析）经
    ``asyncio.to_thread`` 卸载到线程池（design.md 2.1.3-B）。

    幂等性：Chroma 记录 id 确定性（``item{id}_chunk{idx}``），upsert
    前统一先按 ``where={"item_id": id}`` 清全量旧向量再写入（首次
    路径为空操作），保证「向量数 = chunk_count = 分块行数」三方
    一致（design.md 2.2.2-3 幂等性论证）。

    Args:
        item_id: 文档 id。
    """
    # ① 入口二次校验（防 TOCTOU，design.md 2.7-C-1）：pending 置
    # parsing；既非 pending 也非 parsing（已删除/异常态）直接退出。
    with SessionLocal() as db:
        item = db.get(KnowledgeItem, item_id)
        if item is None:
            return
        if item.status == KnowledgeItemStatus.PENDING:
            item.status = KnowledgeItemStatus.PARSING
            db.commit()
        elif item.status != KnowledgeItemStatus.PARSING:
            logger.warning(
                "流水线入口状态异常，退出: item_id=%s status=%s",
                item_id,
                item.status,
            )
            return
        # 提取 detached 元数据（expire_on_commit=False，属性可访问）。
        owner_id: int | None = item.user_id
        scope: str = _enum_value(item.scope)
        file_path: str | None = item.file_path
        source_type: str = _enum_value(item.source_type)
        title: str = item.title
        pipeline_item = item

    # ② 原件存在检查。
    if not file_path or not (PROJECT_ROOT / file_path).is_file():
        _mark_failed(item_id, "文件不存在或不可读")
        return

    # ③ 解析（CPU 段卸载线程池；异常 → failed「解析失败：{摘要}」）。
    try:
        parsed = await asyncio.to_thread(
            load_document, PROJECT_ROOT / file_path, source_type
        )
    except ScanFileError:
        # 空文本检测红线：固定文案（唯一不带「失败」前缀的例外）。
        _mark_failed(item_id, SCAN_FILE_ERROR_MSG)
        return
    except ValueError as exc:
        summary = str(exc)[:_ERROR_SUMMARY_LIMIT]
        if "编码" in summary:
            _mark_failed(item_id, "解析失败：文件编码无法识别")
        else:
            _mark_failed(item_id, f"解析失败：{summary}")
        return
    except Exception as exc:  # noqa: BLE001 - 阶段化兜底，原文案规范
        logger.warning(
            "文档解析异常: item_id=%s type=%s", item_id, type(exc).__name__
        )
        _mark_failed(item_id, f"解析失败：{str(exc)[:_ERROR_SUMMARY_LIMIT]}")
        return

    # ④⑤ 切分（标题/段落 + 滑窗；空产物按切分失败口径）。
    try:
        chunks: list[Chunk] = split_document(parsed)
        if not chunks:
            _mark_failed(item_id, "切分失败：未产生有效分块")
            return
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "文档切分异常: item_id=%s type=%s", item_id, type(exc).__name__
        )
        _mark_failed(item_id, f"切分失败：{str(exc)[:_ERROR_SUMMARY_LIMIT]}")
        return

    # ⑥ 向量化（双模式编排：兜底无条件 + 在线带降级；在线失败已
    # 在 embedding 层内部降级，此处仅兜底也异常的防御性分支）。
    contents = [chunk["content"] for chunk in chunks]
    try:
        local_vectors = embed_texts_local(contents)
        online_vectors, mode = await embed_texts_with_fallback(contents)
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "向量化彻底失败: item_id=%s type=%s", item_id, type(exc).__name__
        )
        _mark_failed(item_id, f"向量化失败：{str(exc)[:_ERROR_SUMMARY_LIMIT]}")
        return

    # ⑦ 向量入库（先清全量旧向量再写入：重索引幂等对齐；写序
    # 「先向量库后关系库」，design.md 2.1.3-C）。
    try:
        delete_item_vectors(item_id, scope, owner_id)
        upsert_chunks(pipeline_item, chunks, local_vectors, "offline")
        if mode == "online":
            upsert_chunks(pipeline_item, chunks, online_vectors, "online")
    except BizException as exc:
        # chromadb 导入失败等已包装好的业务异常（3001 口径）。
        logger.warning("向量入库失败: item_id=%s code=%s", item_id, exc.code)
        _mark_failed(item_id, f"向量入库失败：{str(exc)[:_ERROR_SUMMARY_LIMIT]}")
        return
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "向量入库异常: item_id=%s type=%s", item_id, type(exc).__name__
        )
        _mark_failed(item_id, f"向量入库失败：{str(exc)[:_ERROR_SUMMARY_LIMIT]}")
        return

    # ⑧ SQLite 单事务：删旧 chunks → 写新 chunks（回填 embedding_id
    # 与 heading_path、user_id 冗余归属）→ item 置 indexed +
    # chunk_count=N + error_msg=None。
    try:
        with SessionLocal() as db:
            item = db.get(KnowledgeItem, item_id)
            if item is None:
                return
            db.query(KnowledgeChunk).filter(
                KnowledgeChunk.item_id == item_id
            ).delete(synchronize_session=False)
            for chunk in chunks:
                db.add(
                    KnowledgeChunk(
                        item_id=item_id,
                        user_id=item.user_id,
                        chunk_index=chunk["chunk_index"],
                        content=chunk["content"],
                        heading_path=chunk["heading_path"] or None,
                        embedding_id=f"item{item_id}_chunk{chunk['chunk_index']}",
                    )
                )
            item.status = KnowledgeItemStatus.INDEXED
            item.chunk_count = len(chunks)
            item.error_msg = None
            db.commit()
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "分块落库异常: item_id=%s type=%s", item_id, type(exc).__name__
        )
        _mark_failed(item_id, f"分块落库失败：{str(exc)[:_ERROR_SUMMARY_LIMIT]}")
        # 幽灵向量缓解（design.md 2.1.3-C）：best-effort 清理已写入
        # 的向量；清理失败不掩盖主错误（确定性 id 下重索引/删除
        # 亦会收敛，容忍残留）。
        try:
            delete_item_vectors(item_id, scope, owner_id)
        except Exception:  # noqa: BLE001
            logger.warning("幽灵向量清理失败(容忍): item_id=%s", item_id)
        return
    logger.info(
        "知识库文档索引完成: item_id=%s title=%s chunks=%d mode=%s",
        item_id,
        title,
        len(chunks),
        mode,
    )


# ---------------------------------------------------------------------------
# 删除与重索引（design.md 2.2.2-2/3）
# ---------------------------------------------------------------------------


def cleanup_after_delete(
    item_id: int, scope: str, user_id: int | None, file_path: str | None
) -> None:
    """删除文档后的 best-effort 清理（BackgroundTasks 目标）。

    删除路径的资源收敛（design.md 2.1.3-C）：SQLite 已在请求事务
    内同步删除（列表立即不可见、检索不再命中的强感知）；本函数
    负责向量库双空间清理与原件删除——失败仅 warning 日志
    不回滚（原件已不可达，属可接受的最终一致）。

    Args:
        item_id: 文档 id。
        scope: 归属作用域（当前恒为 personal）。
        user_id: 归属用户 id。
        file_path: 原件相对项目根路径（可能为 None）。
    """
    try:
        delete_item_vectors(item_id, scope, user_id)
    except Exception as exc:  # noqa: BLE001 - best-effort 语义
        logger.warning(
            "向量清理失败(容忍): item_id=%s type=%s",
            item_id,
            type(exc).__name__,
        )
    if file_path:
        abs_path = PROJECT_ROOT / file_path
        try:
            os.remove(abs_path)
        except FileNotFoundError:
            pass
        except Exception as exc:  # noqa: BLE001 - best-effort 语义
            logger.warning(
                "原件删除失败(容忍): path=%s type=%s",
                file_path,
                type(exc).__name__,
            )


def delete_item(db: Session, user: User, item_id: int) -> dict[str, Any]:
    """删除个人库文档（可见性校验 → 级联删除）。

    请求事务内同步删除 SQLite 行（chunks 由 session 级
    ``delete-orphan`` + SQLite FK CASCADE 双保险级联清理）；向量与
    原件清理交由调用方 ``background_tasks`` 调
    :func:`cleanup_after_delete` 异步 best-effort 执行。

    Args:
        db: 请求级数据库会话。
        user: 当前登录用户。
        item_id: 文档 id。

    Returns:
        dict[str, Any]: 清理参数 ``{"item_id", "scope", "user_id",
        "file_path"}``，供路由层交给 background_tasks。

    Raises:
        BizException: code=1005 / HTTP 404（不可见或不存在）。
    """
    item = _get_visible_item(db, user, item_id)
    cleanup = {
        "item_id": item_id,
        "scope": _enum_value(item.scope),
        "user_id": item.user_id,
        "file_path": item.file_path,
    }
    db.delete(item)
    db.commit()
    logger.info("知识库文档删除: item_id=%s user_id=%s", item_id, user.id)
    return cleanup


def reindex_item(db: Session, user: User, item_id: int) -> KnowledgeItem:
    """触发重新索引（幂等重跑）。

    并发防护：``status ∈ {pending, parsing}`` 拒绝（1007）——封死
    「受理后任务尚未启动」的竞态窗口（spec 5.4.3 场景 3 口径：
    pending 一并拒绝）。重索引是幂等重跑而非内容修改。

    旧向量不在此预删——由流水线 upsert 前的统一清理 + 确定性 id
    覆盖收敛（design.md 2.2.2-3 幂等性论证）。

    Args:
        db: 请求级数据库会话。
        user: 当前登录用户。
        item_id: 文档 id。

    Returns:
        KnowledgeItem: 已置 parsing 的文档；调用方负责
        ``background_tasks.add_task(process_document, item_id)``。

    Raises:
        BizException: code=1005 / HTTP 404；code=1007 / HTTP 400
            （文档正在处理中）。
    """
    item = _get_visible_item(db, user, item_id)
    if item.status in (
        KnowledgeItemStatus.PENDING,
        KnowledgeItemStatus.PARSING,
    ):
        raise BizException(
            CODE_BIZ_CONFLICT,
            "文档正在处理中，请稍后再试",
            http_status=400,
        )
    db.query(KnowledgeChunk).filter(
        KnowledgeChunk.item_id == item_id
    ).delete(synchronize_session=False)
    item.status = KnowledgeItemStatus.PARSING
    item.error_msg = None
    item.chunk_count = 0
    db.commit()
    logger.info(
        "知识库文档重新索引: item_id=%s user_id=%s", item_id, user.id
    )
    return item


# ---------------------------------------------------------------------------
# 分块查看与检索编排（design.md 2.2.2-4/5）
# ---------------------------------------------------------------------------


def list_chunks_by_item(
    db: Session, user: User, item_id: int
) -> list[dict[str, Any]]:
    """按文档查看全部分块（chunk_index 升序，全量不分页）。

    单文档分块数受「20MB 原件 + 500 字符/块」约束，量级数百以内
    （演示文档实测 8~12 块），JSON 体积可控（design.md 2.2.2-4
    取舍）。可见性判定单一来源在 item 层（先判文档可见再取分块）。

    Args:
        db: 请求级数据库会话。
        user: 当前登录用户。
        item_id: 文档 id。

    Returns:
        list[dict[str, Any]]: ``KnowledgeChunkOut`` 序列化列表。

    Raises:
        BizException: code=1005 / HTTP 404（不可见或不存在）。
    """
    _get_visible_item(db, user, item_id)
    chunks = db.scalars(
        select(KnowledgeChunk)
        .where(KnowledgeChunk.item_id == item_id)
        .order_by(KnowledgeChunk.chunk_index.asc())
    ).all()
    return [
        KnowledgeChunkOut.model_validate(chunk).model_dump(mode="json")
        for chunk in chunks
    ]


async def search_knowledge(
    db: Session,
    user_id: int,
    query: str,
    top_k: int,
) -> dict[str, Any]:
    """知识库语义检索（个人库；公共库能力已移除）。

    编排（design.md 2.2.2-5）：查询向量化（在线失败重试后降级
    兜底，mode 判定）→ ``query_visible`` 在**与查询向量同空间**的
    个人 collection 检索 → hit 经 ``KnowledgeSearchHit.model_validate``
    强类型化（禁止裸 dict 出 services 边界）→ 按 score 降序、
    条数 ≤ top_k。

    mode 不落库的原因（design.md 2.4.3）：可用性是瞬时状态，落库
    会过期误导；mode 只随本次响应透出，是前端渲染离线警示条的
    唯一权威信号。

    Args:
        db: 请求级数据库会话（当前实现检索路径不触达关系库，参数
            保留以满足 Agent 工具的统一调用形态）。
        user_id: 当前用户 id（个人库 collection 选择依据）。
        query: 检索问题文本（非空，≤500 字符，入参已校验）。
        top_k: 期望命中条数（1~20，入参已校验）。

    Returns:
        dict[str, Any]: ``KnowledgeSearchOut`` 序列化结构
            ``{"mode": "online"|"offline", "results": [...]}``（每条
            含 content / source_title / score / item_id / chunk_index /
            scope 六字段）；空库返回 ``{"mode": ..., "results": []}``
            不报错。

    Raises:
        BizException: code=3000 / HTTP 502（查询向量化彻底失败，
            兜底也异常的防御性分支）；code=3001 / HTTP 500（向量库
            查询异常）。
    """
    try:
        query_vector, mode = await embed_query_with_fallback(query)
    except Exception as exc:  # noqa: BLE001 - 兜底也失败的防御分支
        logger.warning(
            "查询向量化彻底失败: user_id=%s type=%s",
            user_id,
            type(exc).__name__,
        )
        raise BizException(
            CODE_LLM_FAILED,
            "AI 服务暂时不可用，请稍后重试",
            http_status=502,
        ) from None

    try:
        hits = query_visible(user_id, query_vector, top_k, mode)
    except BizException:
        raise
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "向量库查询异常: user_id=%s type=%s",
            user_id,
            type(exc).__name__,
        )
        raise BizException(
            CODE_VECTOR_FAILED,
            "检索失败请稍后重试",
            http_status=500,
        ) from None

    results: list[dict[str, Any]] = []
    for hit in hits:
        source_title = str(hit.get("title", ""))
        heading_path = str(hit.get("heading_path") or "")
        if heading_path:
            source_title = f"{source_title} » {heading_path}"
        validated = KnowledgeSearchHit.model_validate(
            {
                "content": hit.get("content", ""),
                "source_title": source_title,
                "score": float(hit.get("score", 0.0)),
                "item_id": hit.get("item_id"),
                "chunk_index": hit.get("chunk_index"),
                "scope": hit.get("scope"),
            }
        )
        results.append(validated.model_dump(mode="json"))
    return KnowledgeSearchOut(mode=mode, results=results).model_dump(
        mode="json"
    )