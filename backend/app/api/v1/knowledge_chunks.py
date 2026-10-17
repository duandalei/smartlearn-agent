"""知识分块只读路由（需登录；可见性跟随所属文档：个人库分块仅本人可见，公共库分块全员可见）。

``knowledge_chunks.user_id`` 为冗余归属列（personal 记录归属用户、
public 记录为 NULL），据此过滤；表名 kebab-case 路径，即最终正式路径。
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.core.response import success
from app.models.knowledge import KnowledgeChunk
from app.models.user import User
from app.schemas.common import PaginationParams
from app.schemas.knowledge import KnowledgeChunkOut
from app.services.readonly import get_by_id_or_404, paginate

router: APIRouter = APIRouter(prefix="/knowledge-chunks", tags=["知识分块"])


def _visibility_filters(current_user: User) -> list[Any]:
    """构造分块可见性过滤条件：本人个人库分块 ∪ 公共库分块（user_id 为 NULL）。"""
    return [
        or_(
            KnowledgeChunk.user_id == current_user.id,
            KnowledgeChunk.user_id.is_(None),
        )
    ]


@router.get("", summary="知识分块列表（分页，本人个人库 + 公共库）")
def list_knowledge_chunks(
    page_params: Annotated[PaginationParams, Query()],
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> dict[str, Any]:
    """分页查询当前用户可见的知识分块（按 id 升序）。

    Args:
        page_params: 分页参数。
        db: 数据库会话（依赖注入）。
        current_user: 当前登录用户（依赖注入）。

    Returns:
        dict[str, Any]: 统一响应体，data 为 {items, total, page, page_size}；
        未登录返回 HTTP 401 + code=1003。
    """
    return success(
        data=paginate(
            db,
            KnowledgeChunk,
            KnowledgeChunkOut,
            page=page_params.page,
            page_size=page_params.page_size,
            filters=_visibility_filters(current_user),
        )
    )


@router.get("/{chunk_id}", summary="知识分块详情")
def get_knowledge_chunk(
    chunk_id: int,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> dict[str, Any]:
    """按 id 获取知识分块详情（仅限本人个人库与公共库分块）。

    访问他人个人库分块与不存在统一返回 HTTP 404 + code=1005。

    Args:
        chunk_id: 分块 id。
        db: 数据库会话（依赖注入）。
        current_user: 当前登录用户（依赖注入）。

    Returns:
        dict[str, Any]: 统一响应体，data 为分块对象。
    """
    return success(
        data=get_by_id_or_404(
            db,
            KnowledgeChunk,
            chunk_id,
            KnowledgeChunkOut,
            filters=_visibility_filters(current_user),
        )
    )