# TODO(P3): 认证阶段为全部业务端点补挂 get_current_user
"""知识库文档只读路由。

路径演进契约：``/api/v1/knowledge/items`` 为最终正式路径
（PROJECT_CONTEXT 7.2），P3+ 的 ``/knowledge/upload``、
``/knowledge/search`` 在本文件同前缀扩展。
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.core.response import success
from app.models.knowledge import KnowledgeItem
from app.schemas.common import PaginationParams
from app.schemas.knowledge import KnowledgeItemOut
from app.services.readonly import get_by_id_or_404, paginate

router: APIRouter = APIRouter(prefix="/knowledge", tags=["知识库"])


@router.get("/items", summary="知识库文档列表（分页）")
def list_knowledge_items(
    page_params: Annotated[PaginationParams, Query()],
    db: Annotated[Session, Depends(get_db)],
) -> dict[str, Any]:
    """分页查询知识库文档列表（按 id 升序）。

    Args:
        page_params: 分页参数。
        db: 数据库会话（依赖注入）。

    Returns:
        dict[str, Any]: 统一响应体，data 为 {items, total, page, page_size}。
    """
    return success(
        data=paginate(
            db,
            KnowledgeItem,
            KnowledgeItemOut,
            page=page_params.page,
            page_size=page_params.page_size,
        )
    )


@router.get("/items/{item_id}", summary="知识库文档详情")
def get_knowledge_item(
    item_id: int,
    db: Annotated[Session, Depends(get_db)],
) -> dict[str, Any]:
    """按 id 获取知识库文档详情。

    Args:
        item_id: 文档 id。
        db: 数据库会话（依赖注入）。

    Returns:
        dict[str, Any]: 统一响应体，data 为文档对象；不存在时
        返回 HTTP 404 + code=1005。
    """
    return success(
        data=get_by_id_or_404(db, KnowledgeItem, item_id, KnowledgeItemOut)
    )