# TODO(P3): 认证阶段为全部业务端点补挂 get_current_user
"""用户学习档案只读路由（表名 kebab-case 路径，即最终正式路径）。"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.core.response import success
from app.models.user import UserProfile
from app.schemas.common import PaginationParams
from app.schemas.user import UserProfileOut
from app.services.readonly import get_by_id_or_404, paginate

router: APIRouter = APIRouter(prefix="/user-profiles", tags=["用户档案"])


@router.get("", summary="用户档案列表（分页）")
def list_user_profiles(
    page_params: Annotated[PaginationParams, Query()],
    db: Annotated[Session, Depends(get_db)],
) -> dict[str, Any]:
    """分页查询用户档案列表（按 id 升序）。

    Args:
        page_params: 分页参数。
        db: 数据库会话（依赖注入）。

    Returns:
        dict[str, Any]: 统一响应体，data 为 {items, total, page, page_size}。
    """
    return success(
        data=paginate(
            db,
            UserProfile,
            UserProfileOut,
            page=page_params.page,
            page_size=page_params.page_size,
        )
    )


@router.get("/{profile_id}", summary="用户档案详情")
def get_user_profile(
    profile_id: int,
    db: Annotated[Session, Depends(get_db)],
) -> dict[str, Any]:
    """按 id 获取用户档案详情。

    Args:
        profile_id: 档案 id。
        db: 数据库会话（依赖注入）。

    Returns:
        dict[str, Any]: 统一响应体，data 为档案对象；不存在时
        返回 HTTP 404 + code=1005。
    """
    return success(
        data=get_by_id_or_404(db, UserProfile, profile_id, UserProfileOut)
    )