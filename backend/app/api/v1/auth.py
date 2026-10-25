"""本地用户信息路由。

项目为本地单用户模式，不再提供注册 / 登录；保留 ``GET /auth/me``
供前端启动时获取当前本地用户信息。
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends

from app.api.deps import get_current_user
from app.core.response import success
from app.models.user import User
from app.schemas.user import UserOut

router: APIRouter = APIRouter(prefix="/auth", tags=["认证"])


@router.get("/me", summary="当前本地用户信息")
def me(
    current_user: Annotated[User, Depends(get_current_user)],
) -> dict[str, Any]:
    """返回当前本地用户信息（无需 Token）。

    Args:
        current_user: 本地用户（依赖注入）。

    Returns:
        dict[str, Any]: 统一响应体，data 为 UserOut（不含密码哈希）。
    """
    return success(data=UserOut.model_validate(current_user).model_dump(mode="json"))
