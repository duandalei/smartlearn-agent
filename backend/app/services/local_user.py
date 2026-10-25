"""本地单用户绑定。

项目定位为「个人 `git clone` 到本地使用」，不再提供登录 / 注册 /
多用户。所有请求统一归属同一个本地用户：

1. 库中已有用户时，复用 id 最小的那条（兼容升级前的数据）；
2. 空库时自动创建 ``local`` 用户及其空档案。

用户不可见「账号」概念；``user_id`` 仅作为业务表之间的内部外键。
"""

from __future__ import annotations

import threading

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.user import User, UserProfile

#: 本地用户名（仅数据库内部可见）。
LOCAL_USERNAME: str = "local"

#: 单进程内串行化首次创建，避免并发请求各建一条用户。
_CREATE_LOCK = threading.Lock()


def ensure_local_user(db: Session) -> User:
    """返回本地用户；不存在时创建一条。

    Args:
        db: 当前请求的数据库会话。

    Returns:
        User: 本地用户 ORM 对象。

    Note:
        ``hashed_password`` 仅用于满足非空约束，不参与任何登录校验。
    """
    user = _first_user(db)
    if user is not None:
        return user

    with _CREATE_LOCK:
        user = _first_user(db)
        if user is not None:
            return user
        user = User(
            username=LOCAL_USERNAME,
            email=None,
            hashed_password="!",
            is_active=True,
        )
        db.add(user)
        db.flush()
        db.add(
            UserProfile(
                user_id=user.id,
                name=None,
                school=None,
                major=None,
                grade=None,
                current_goal_type=None,
                interest_directions=[],
                daily_study_minutes=60,
            )
        )
        db.commit()
        db.refresh(user)
        return user


def _first_user(db: Session) -> User | None:
    """取库中 id 最小的用户（升级兼容：沿用已有数据的主人）。"""
    return db.scalar(select(User).order_by(User.id.asc()).limit(1))
