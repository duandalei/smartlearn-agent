"""用户账号只读路由（需登录；仅能查看**当前登录用户本人**）。

出参不含 ``hashed_password``（UserOut 已排除）；列表恒只包含
本人一条记录，详情仅本人可见，防用户枚举。
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.core.response import success
from app.models.user import User
from app.schemas.common import PaginationParams
from app.schemas.user import UserOut
from app.services.readonly import get_by_id_or_404, paginate

router: APIRouter = APIRouter(prefix="/users", tags=["用户"])


@router.get("", summary="用户列表（分页，仅本人）")
def list_users(
    page_params: Annotated[PaginationParams, Query()],
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> dict[str, Any]:
    """分页查询用户列表（数据隔离：恒只返回当前登录用户本人，不含密码哈希）。

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
            User,
            UserOut,
            page=page_params.page,
            page_size=page_params.page_size,
            filters=[User.id == current_user.id],
        )
    )


@router.get("/{user_id}", summary="用户详情（仅本人）")
def get_user(
    user_id: int,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> dict[str, Any]:
    """按 id 获取用户详情（仅限本人，不含密码哈希）。

    访问他人 id 与不存在统一返回 HTTP 404 + code=1005，
    防止用户枚举。

    Args:
        user_id: 用户 id。
        db: 数据库会话（依赖注入）。
        current_user: 当前登录用户（依赖注入）。

    Returns:
        dict[str, Any]: 统一响应体，data 为用户对象。
    """
    return success(
        data=get_by_id_or_404(
            db,
            User,
            user_id,
            UserOut,
            filters=[User.id == current_user.id],
        )
    )