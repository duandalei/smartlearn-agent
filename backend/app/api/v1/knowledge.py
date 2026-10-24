"""知识库文档路由（需登录；个人库仅本人可见）。

可见性规则（PROJECT_CONTEXT §6.9 知识库）：
- ``scope=personal``（``user_id`` 为本人）：仅本人可见；公共库能力已移除。

P8 扩展（design.md 2.2.1 接口总表）：在既有 2 个只读端点基础上
追加 5 个端点（上传受理 / 删除 / 重索引 / 分块查看 / 语义检索），
全部同前缀同鉴权；路由层只做「参数解析 + 鉴权注入 + 调 service +
``success()`` 包装」（契约 §4 分层铁律），业务规则一律下沉
``services/knowledge.py``。

业务码映射总表见 design.md 2.7-A：2000 类型不支持 / 1001 大小
超限 / 1005 不可见即不存在 / 1007 处理中拒绝
/ 3000 向量化不可用 / 3001 向量库失败。
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, BackgroundTasks, Depends, File, Query, UploadFile
from sqlalchemy import ColumnElement, desc
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.core.response import success
from app.models.knowledge import KnowledgeItem
from app.models.user import User
from app.schemas.common import PaginationParams
from app.schemas.knowledge import (
    KnowledgeItemOut,
    KnowledgeSearchIn,
    KnowledgeUploadOut,
)
from app.services.knowledge import (
    cleanup_after_delete,
    create_item_from_upload,
    delete_item,
    list_chunks_by_item,
    process_document,
    reindex_item,
    search_knowledge,
    visibility_filters,
)
from app.services.readonly import get_by_id_or_404, paginate

router: APIRouter = APIRouter(prefix="/knowledge", tags=["知识库"])


def _visibility_filters(current_user: User) -> list[Any]:
    """构造知识库可见性过滤条件：仅本人个人库。

    薄委托 ``services/knowledge.visibility_filters``——写操作端点
    （删除/重索引/分块查看）与只读端点共用同一口径，「不可见即
    不存在」防 ID 枚举单一实现（design.md 1.2-1；分层约束下实现
    下沉 services，本函数保留存量端点的调用兼容）。
    """
    return visibility_filters(current_user.id)


@router.get("/items", summary="知识库文档列表（分页，仅本人个人库）")
def list_knowledge_items(
    page_params: Annotated[PaginationParams, Query()],
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> dict[str, Any]:
    """分页查询当前用户可见的知识库文档（仅本人个人库）。

    排序按 id 降序（P8 微调，design.md 2.9 决策 #13）：上传轮询
    场景下新上传文档立即可见置顶；响应结构与分页口径不变
    （spec 4.5 规则 3 兼容性）。

    Args:
        page_params: 分页参数。
        db: 数据库会话（依赖注入）。
        current_user: 当前登录用户（依赖注入）。

    Returns:
        dict[str, Any]: 统一响应体，data 为 {items, total, page, page_size}；
        未登录返回 HTTP 401 + code=1003。
    """
    order_by: list[ColumnElement[Any]] = [desc(KnowledgeItem.id)]
    return success(
        data=paginate(
            db,
            KnowledgeItem,
            KnowledgeItemOut,
            page=page_params.page,
            page_size=page_params.page_size,
            order_by=order_by,
            filters=_visibility_filters(current_user),
        )
    )


@router.get("/items/{item_id}", summary="知识库文档详情")
def get_knowledge_item(
    item_id: int,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> dict[str, Any]:
    """按 id 获取知识库文档详情（仅限本人个人库文档）。

    访问他人个人库文档与不存在统一返回 HTTP 404 + code=1005。

    Args:
        item_id: 文档 id。
        db: 数据库会话（依赖注入）。
        current_user: 当前登录用户（依赖注入）。

    Returns:
        dict[str, Any]: 统一响应体，data 为文档对象。
    """
    return success(
        data=get_by_id_or_404(
            db,
            KnowledgeItem,
            item_id,
            KnowledgeItemOut,
            filters=_visibility_filters(current_user),
        )
    )


@router.post("/upload", summary="上传学习文档（异步受理，立即返回 item_id）")
async def upload_knowledge_document(
    background_tasks: BackgroundTasks,
    file: Annotated[UploadFile, File(description="PDF/DOCX/PPTX/MD/TXT，≤20MB")],
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> dict[str, Any]:
    """上传受理：校验落盘建档后立即返回，解析在后台流水线执行。

    同步段仅校验 + 落盘 + 建档（远小于 2 秒，spec 5.1.1 规则 3）。
    业务码映射（design.md 2.7-A 场景 1/2）：扩展名不在白名单 →
    2000/400；大小超 20MB → 1001/422。

    Args:
        background_tasks: 后台任务队列（受理成功后入队流水线）。
        file: 上传文件（multipart 字段名 file）。
        db: 数据库会话（依赖注入）。
        current_user: 当前登录用户（依赖注入）。

    Returns:
        dict[str, Any]: 统一响应体，data 为 {item_id, status}
        （KnowledgeUploadOut；status 恒为 pending，后续流转由前端
        轮询列表观察）。
    """
    content = await file.read()
    filename = file.filename or "未命名文档"
    item = await create_item_from_upload(db, current_user, filename, content)
    background_tasks.add_task(process_document, item.id)
    payload = KnowledgeUploadOut(
        item_id=item.id,
        status=getattr(item.status, "value", item.status),
    )
    return success(data=payload.model_dump(mode="json"))


@router.delete("/items/{item_id}", summary="删除个人库文档（级联清理）")
async def delete_knowledge_item(
    item_id: int,
    background_tasks: BackgroundTasks,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> dict[str, Any]:
    """删除个人库文档：SQLite 同步级联删除，向量与原件异步清理。

    业务码映射（design.md 2.7-A 场景 9/10）：不可见或不存在 →
    1005/404（防 ID 枚举）。删除后
    列表立即可见消失、检索不再命中（请求事务内完成 SQLite 删除）；
    向量库与原件清理经 background_tasks best-effort 执行。

    Args:
        item_id: 文档 id。
        background_tasks: 后台任务队列（清理向量与原件）。
        db: 数据库会话（依赖注入）。
        current_user: 当前登录用户（依赖注入）。

    Returns:
        dict[str, Any]: 统一响应体，data 为 null。
    """
    cleanup = delete_item(db, current_user, item_id)
    background_tasks.add_task(
        cleanup_after_delete,
        cleanup["item_id"],
        cleanup["scope"],
        cleanup["user_id"],
        cleanup["file_path"],
    )
    return success(data=None)


@router.post("/items/{item_id}/reindex", summary="重新索引文档（幂等重跑）")
async def reindex_knowledge_item(
    item_id: int,
    background_tasks: BackgroundTasks,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> dict[str, Any]:
    """触发重新索引：清旧分块置 parsing，流水线幂等重跑。

    本人个人库可见文档均可触发。业务码映射（design.md
    2.7-A 场景 11）：pending/parsing 状态 → 1007/400（封死「受理
    后任务尚未启动」的竞态窗口）；不可见或不存在 → 1005/404。

    Args:
        item_id: 文档 id。
        background_tasks: 后台任务队列（入队流水线）。
        db: 数据库会话（依赖注入）。
        current_user: 当前登录用户（依赖注入）。

    Returns:
        dict[str, Any]: 统一响应体，data 为 {item_id, status}
        （status 恒为 parsing）。
    """
    item = reindex_item(db, current_user, item_id)
    background_tasks.add_task(process_document, item.id)
    payload = KnowledgeUploadOut(
        item_id=item.id,
        status=getattr(item.status, "value", item.status),
    )
    return success(data=payload.model_dump(mode="json"))


@router.get("/items/{item_id}/chunks", summary="查看文档全部分块（含标题路径）")
async def list_item_chunks(
    item_id: int,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> dict[str, Any]:
    """按文档查看全部分块（chunk_index 升序，全量不分页）。

    可见性先判 item（复用同一 ``_visibility_filters`` 口径）再取
    分块；不可见或不存在统一 1005/404（design.md 2.2.2-4）。

    Args:
        item_id: 文档 id。
        db: 数据库会话（依赖注入）。
        current_user: 当前登录用户（依赖注入）。

    Returns:
        dict[str, Any]: 统一响应体，data 为 KnowledgeChunkOut 列表。
    """
    return success(data=list_chunks_by_item(db, current_user, item_id))


@router.post("/search", summary="知识库语义检索（Top-K 片段 + 来源 + 相似度）")
async def search_knowledge_endpoint(
    payload: KnowledgeSearchIn,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> dict[str, Any]:
    """语义检索：查询向量化 → 本人个人库排序。

    检索范围 = 与查询向量同空间的本人个人库；
    响应含 mode 字段（online/offline，Embedding 可用性瞬时判定，
    不落库——offline 时前端渲染常驻警示条，design.md 2.6.2-D）。
    业务码映射（design.md 2.7-A 场景 12/13）：参数非法 → 1001/422
    （Pydantic 自动生效）；空库返回空 results 不报错；向量化彻底
    失败 → 3000/502；向量库查询异常 → 3001/500。

    Args:
        payload: 检索入参（query 非空 ≤500 字符；top_k 1~20 默认 5）。
        db: 数据库会话（依赖注入）。
        current_user: 当前登录用户（依赖注入）。

    Returns:
        dict[str, Any]: 统一响应体，data 为 {mode, results}
        （KnowledgeSearchOut；results 每条含 content / source_title /
        score，按 score 降序）。
    """
    data = await search_knowledge(
        db,
        user_id=current_user.id,
        query=payload.query,
        top_k=payload.top_k,
    )
    return success(data=data)