# TODO(P3): 认证阶段为全部业务端点补挂 get_current_user
"""错题只读路由（表名 kebab-case 路径，即最终正式路径）。

错题系统完整功能属 V2；MVP 数据由 init_db 种子提供，本阶段只读。
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.core.response import success
from app.models.mistake import Mistake
from app.schemas.common import PaginationParams
from app.schemas.mistake import MistakeOut
from app.services.readonly import get_by_id_or_404, paginate

router: APIRouter = APIRouter(prefix="/mistakes", tags=["错题"])


@router.get("", summary="错题列表（分页）")
def list_mistakes(
    page_params: Annotated[PaginationParams, Query()],
    db: Annotated[Session, Depends(get_db)],
) -> dict[str, Any]:
    """分页查询错题列表（按 id 升序）。

    Args:
        page_params: 分页参数。
        db: 数据库会话（依赖注入）。

    Returns:
        dict[str, Any]: 统一响应体，data 为 {items, total, page, page_size}。
    """
    return success(
        data=paginate(
            db,
            Mistake,
            MistakeOut,
            page=page_params.page,
            page_size=page_params.page_size,
        )
    )


@router.get("/{mistake_id}", summary="错题详情")
def get_mistake(
    mistake_id: int,
    db: Annotated[Session, Depends(get_db)],
) -> dict[str, Any]:
    """按 id 获取错题详情。

    Args:
        mistake_id: 错题 id。
        db: 数据库会话（依赖注入）。

    Returns:
        dict[str, Any]: 统一响应体，data 为错题对象；不存在时
        返回 HTTP 404 + code=1005。
    """
    return success(data=get_by_id_or_404(db, Mistake, mistake_id, MistakeOut))