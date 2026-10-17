# TODO(P3): 认证阶段为全部业务端点补挂 get_current_user
"""用户账号只读路由（表名 kebab-case 路径，即最终正式路径）。

出参不含 ``hashed_password``（UserOut 已排除）。
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.core.response import success
from app.models.user import User
from app.schemas.common import PaginationParams
from app.schemas.user import UserOut
from app.services.readonly import get_by_id_or_404, paginate

router: APIRouter = APIRouter(prefix="/users", tags=["用户"])


@router.get("", summary="用户列表（分页）")
def list_users(
    page_params: Annotated[PaginationParams, Query()],
    db: Annotated[Session, Depends(get_db)],
) -> dict[str, Any]:
    """分页查询用户列表（按 id 升序，不含密码哈希）。

    Args:
        page_params: 分页参数。
        db: 数据库会话（依赖注入）。

    Returns:
        dict[str, Any]: 统一响应体，data 为 {items, total, page, page_size}。
    """
    return success(
        data=paginate(
            db,
            User,
            UserOut,
            page=page_params.page,
            page_size=page_params.page_size,
        )
    )


@router.get("/{user_id}", summary="用户详情")
def get_user(
    user_id: int,
    db: Annotated[Session, Depends(get_db)],
) -> dict[str, Any]:
    """按 id 获取用户详情（不含密码哈希）。

    Args:
        user_id: 用户 id。
        db: 数据库会话（依赖注入）。

    Returns:
        dict[str, Any]: 统一响应体，data 为用户对象；不存在时
        返回 HTTP 404 + code=1005。
    """
    return success(data=get_by_id_or_404(db, User, user_id, UserOut))