# TODO(P3): 认证阶段为全部业务端点补挂 get_current_user
"""知识掌握度只读路由（表名 kebab-case 路径，即最终正式路径）。"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.core.response import success
from app.models.mastery import KnowledgeMastery
from app.schemas.common import PaginationParams
from app.schemas.mastery import MasteryOut
from app.services.readonly import get_by_id_or_404, paginate

router: APIRouter = APIRouter(prefix="/knowledge-mastery", tags=["知识掌握度"])


@router.get("", summary="知识掌握度列表（分页）")
def list_knowledge_mastery(
    page_params: Annotated[PaginationParams, Query()],
    db: Annotated[Session, Depends(get_db)],
) -> dict[str, Any]:
    """分页查询知识点掌握度列表（按 id 升序）。

    Args:
        page_params: 分页参数。
        db: 数据库会话（依赖注入）。

    Returns:
        dict[str, Any]: 统一响应体，data 为 {items, total, page, page_size}。
    """
    return success(
        data=paginate(
            db,
            KnowledgeMastery,
            MasteryOut,
            page=page_params.page,
            page_size=page_params.page_size,
        )
    )


@router.get("/{mastery_id}", summary="知识掌握度详情")
def get_knowledge_mastery(
    mastery_id: int,
    db: Annotated[Session, Depends(get_db)],
) -> dict[str, Any]:
    """按 id 获取单个知识点掌握度。

    Args:
        mastery_id: 掌握度记录 id。
        db: 数据库会话（依赖注入）。

    Returns:
        dict[str, Any]: 统一响应体，data 为掌握度对象；不存在时
        返回 HTTP 404 + code=1005。
    """
    return success(
        data=get_by_id_or_404(db, KnowledgeMastery, mastery_id, MasteryOut)
    )