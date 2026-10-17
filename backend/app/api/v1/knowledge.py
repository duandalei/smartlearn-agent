"""知识库文档只读路由（需登录；个人库仅本人可见，公共库全员可见）。

可见性规则（PROJECT_CONTEXT §6.9 双层知识库）：
- ``scope=personal``（``user_id`` 为本人）：仅本人可见；
- ``scope=public``（``user_id`` 为 NULL）：系统预置，所有登录用户可见。

路径演进契约：``/api/v1/knowledge/items`` 为最终正式路径
（PROJECT_CONTEXT 7.2），P3+ 的 ``/knowledge/upload``、
``/knowledge/search`` 在本文件同前缀扩展。
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.core.response import success
from app.models.enums import KnowledgeScope
from app.models.knowledge import KnowledgeItem
from app.models.user import User
from app.schemas.common import PaginationParams
from app.schemas.knowledge import KnowledgeItemOut
from app.services.readonly import get_by_id_or_404, paginate

router: APIRouter = APIRouter(prefix="/knowledge", tags=["知识库"])


def _visibility_filters(current_user: User) -> list[Any]:
    """构造知识库可见性过滤条件：本人个人库 ∪ 全部公共库。"""
    return [
        or_(
            KnowledgeItem.user_id == current_user.id,
            KnowledgeItem.scope == KnowledgeScope.PUBLIC,
        )
    ]


@router.get("/items", summary="知识库文档列表（分页，本人个人库 + 公共库）")
def list_knowledge_items(
    page_params: Annotated[PaginationParams, Query()],
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> dict[str, Any]:
    """分页查询当前用户可见的知识库文档（本人个人库 + 全部公共库）。

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
            KnowledgeItem,
            KnowledgeItemOut,
            page=page_params.page,
            page_size=page_params.page_size,
            filters=_visibility_filters(current_user),
        )
    )


@router.get("/items/{item_id}", summary="知识库文档详情")
def get_knowledge_item(
    item_id: int,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> dict[str, Any]:
    """按 id 获取知识库文档详情（仅限本人个人库与公共库文档）。

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