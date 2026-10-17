"""认证路由（注册 / 登录 / 当前用户信息）。

白名单：``/api/v1/auth/register`` 与 ``/api/v1/auth/login`` 为
公开端点（PROJECT_CONTEXT 收编裁决：除 /health、register、login
外全部需登录）；``GET /api/v1/auth/me`` 依赖 ``get_current_user``。
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.core.response import success
from app.models.user import User
from app.schemas.auth import LoginIn, RegisterIn
from app.schemas.user import UserOut
from app.services import auth as auth_service

router: APIRouter = APIRouter(prefix="/auth", tags=["认证"])


@router.post("/register", summary="注册（成功即登录）")
def register(
    body: RegisterIn,
    db: Annotated[Session, Depends(get_db)],
) -> dict[str, Any]:
    """注册新用户：自动创建空档案并返回与登录一致的 token 结构。

    Args:
        body: 注册入参（用户名 / 密码≥6位 / 确认密码）。
        db: 数据库会话（依赖注入）。

    Returns:
        dict[str, Any]: 统一响应体，data 为
        ``{access_token, token_type, user}``；用户名已存在返回
        HTTP 409 + code=1006。
    """
    return success(data=auth_service.register_user(db, body), message="注册成功")


@router.post("/login", summary="登录")
def login(
    body: LoginIn,
    db: Annotated[Session, Depends(get_db)],
) -> dict[str, Any]:
    """用户名 + 密码登录，签发 7 天有效期的 JWT。

    Args:
        body: 登录入参。
        db: 数据库会话（依赖注入）。

    Returns:
        dict[str, Any]: 统一响应体，data 为
        ``{access_token, token_type, user}``；认证失败统一返回
        HTTP 401 + code=1002「用户名或密码错误」（不区分用户名
        不存在与密码错误）。
    """
    return success(data=auth_service.login_user(db, body), message="登录成功")


@router.get("/me", summary="当前登录用户信息")
def me(
    current_user: Annotated[User, Depends(get_current_user)],
) -> dict[str, Any]:
    """返回当前登录用户信息（需携带有效 Bearer Token）。

    Args:
        current_user: 当前登录用户（依赖注入）。

    Returns:
        dict[str, Any]: 统一响应体，data 为 UserOut（不含密码哈希）；
        未登录 / Token 无效返回 HTTP 401 + code=1003。
    """
    return success(data=UserOut.model_validate(current_user).model_dump(mode="json"))