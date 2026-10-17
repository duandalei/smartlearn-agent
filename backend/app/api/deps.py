"""api 层公共依赖注入。

- ``get_db``：数据库会话（请求级）。
- ``get_current_user``：解析 ``Authorization: Bearer <token>``，
  校验 JWT 并返回当前用户 ORM 对象；未登录 / 令牌无效 / 已过期 /
  用户不存在或被禁用统一抛 ``BizException(1003, 401)``，响应体仍走
  统一格式，不抛 500。
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.response import CODE_TOKEN_INVALID, BizException
from app.core.security import TokenError, verify_access_token
from app.db.session import get_db
from app.models.user import User

# auto_error=False：缺少 Authorization 头时返回 None 而非框架默认 403，
# 由本依赖统一转换为 401 + 1003 的中文统一响应体。
_bearer_scheme = HTTPBearer(auto_error=False, description="Bearer Token")


def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer_scheme)],
    db: Annotated[Session, Depends(get_db)],
) -> User:
    """解析 Bearer Token 并返回当前登录用户。

    Args:
        credentials: HTTPBearer 提取的凭证（可能为 None）。
        db: 数据库会话（依赖注入）。

    Returns:
        User: 当前用户 ORM 对象。

    Raises:
        BizException: code=1003 / HTTP 401，未携带 Token、Token
            无效或已过期、用户不存在或已被禁用。
    """
    if credentials is None or not credentials.credentials:
        raise BizException(
            CODE_TOKEN_INVALID, "未登录或缺少认证信息", http_status=401
        )
    try:
        user_id = verify_access_token(credentials.credentials)
    except TokenError:
        raise BizException(
            CODE_TOKEN_INVALID, "Token 无效或已过期", http_status=401
        ) from None
    user = db.get(User, user_id)
    if user is None or not user.is_active:
        # 用户已删除 / 被禁用：与令牌无效同口径，不区分提示。
        raise BizException(
            CODE_TOKEN_INVALID, "Token 无效或已过期", http_status=401
        )
    return user


__all__ = ["get_current_user", "get_db"]