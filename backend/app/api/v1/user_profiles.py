"""用户学习档案只读路由（需登录；仅能查看**当前登录用户本人**的档案）。

表名 kebab-case 路径，即最终正式路径；业务入口为
``GET/PUT /api/v1/profile``（profile.py）。
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.core.response import success
from app.models.user import User, UserProfile
from app.schemas.common import PaginationParams
from app.schemas.user import UserProfileOut
from app.services.readonly import get_by_id_or_404, paginate

router: APIRouter = APIRouter(prefix="/user-profiles", tags=["用户档案"])


@router.get("", summary="用户档案列表（分页，仅本人）")
def list_user_profiles(
    page_params: Annotated[PaginationParams, Query()],
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> dict[str, Any]:
    """分页查询用户档案列表（数据隔离：恒只返回当前登录用户本人的档案）。

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
            UserProfile,
            UserProfileOut,
            page=page_params.page,
            page_size=page_params.page_size,
            filters=[UserProfile.user_id == current_user.id],
        )
    )


@router.get("/{profile_id}", summary="用户档案详情（仅本人）")
def get_user_profile(
    profile_id: int,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> dict[str, Any]:
    """按 id 获取用户档案详情（仅限本人资源）。

    访问他人档案与不存在统一返回 HTTP 404 + code=1005。

    Args:
        profile_id: 档案 id。
        db: 数据库会话（依赖注入）。
        current_user: 当前登录用户（依赖注入）。

    Returns:
        dict[str, Any]: 统一响应体，data 为档案对象。
    """
    return success(
        data=get_by_id_or_404(
            db,
            UserProfile,
            profile_id,
            UserProfileOut,
            filters=[UserProfile.user_id == current_user.id],
        )
    )