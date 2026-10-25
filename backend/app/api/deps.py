"""api 层公共依赖注入。

- ``get_db``：数据库会话（请求级）。
- ``get_current_user``：本地单用户模式，直接返回本地用户；
  项目不再提供登录 / 注册 / 多用户，也不再解析 Token。
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.user import User
from app.services.local_user import ensure_local_user


def get_current_user(db: Annotated[Session, Depends(get_db)]) -> User:
    """返回本地用户（不存在时自动创建）。

    Args:
        db: 数据库会话（依赖注入）。

    Returns:
        User: 本地用户 ORM 对象。
    """
    return ensure_local_user(db)


__all__ = ["get_current_user", "get_db"]