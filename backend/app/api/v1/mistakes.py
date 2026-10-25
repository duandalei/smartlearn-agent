"""错题只读路由（本地单用户；表名 kebab-case 路径，即最终正式路径）。

错题系统完整功能属 V2；当前无预置数据，空库时返回空列表。
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.core.response import success
from app.models.mistake import Mistake
from app.models.user import User
from app.schemas.common import PaginationParams
from app.schemas.mistake import MistakeOut
from app.services.readonly import get_by_id_or_404, paginate

router: APIRouter = APIRouter(prefix="/mistakes", tags=["错题"])


@router.get("", summary="错题列表（分页，仅当前用户）")
def list_mistakes(
    page_params: Annotated[PaginationParams, Query()],
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> dict[str, Any]:
    """分页查询**当前用户**的错题列表（按 id 升序）。

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
            Mistake,
            MistakeOut,
            page=page_params.page,
            page_size=page_params.page_size,
            filters=[Mistake.user_id == current_user.id],
        )
    )


@router.get("/{mistake_id}", summary="错题详情")
def get_mistake(
    mistake_id: int,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> dict[str, Any]:
    """按 id 获取错题详情（仅限本人资源）。

    越权访问他人错题与不存在统一返回 HTTP 404 + code=1005。

    Args:
        mistake_id: 错题 id。
        db: 数据库会话（依赖注入）。
        current_user: 当前登录用户（依赖注入）。

    Returns:
        dict[str, Any]: 统一响应体，data 为错题对象。
    """
    return success(
        data=get_by_id_or_404(
            db,
            Mistake,
            mistake_id,
            MistakeOut,
            filters=[Mistake.user_id == current_user.id],
        )
    )