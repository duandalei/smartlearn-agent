"""认证业务逻辑（注册 / 登录）。

安全约定：
- 密码只经 ``core/security.hash_password`` 落库哈希，任何路径不落明文、
  不写日志；
- 登录失败统一 1002「用户名或密码错误」，不区分「用户不存在」与
  「密码错误」，且对不存在的用户名也执行一次哈希校验（哑哈希），
  抹平响应时间差，防时序侧信道探测用户名；
- 注册成功自动创建空档案（``daily_study_minutes`` 默认 60），
  并返回与登录完全一致的 token 结构（注册即登录）。
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.response import CODE_ALREADY_EXISTS, CODE_AUTH_FAILED, BizException
from app.core.security import create_access_token, hash_password, verify_password
from app.models.user import User, UserProfile
from app.schemas.auth import LoginIn, RegisterIn
from app.schemas.user import UserOut

# 哑哈希：用户名不存在时仍执行一次同代价校验，抹平响应时间差。
_DUMMY_HASH: str = hash_password("timing-attack-dummy")


def _build_auth_result(user: User) -> dict:
    """构造登录 / 注册一致的响应 data（token + 用户信息）。"""
    from app.schemas.auth import AuthResult  # 局部导入避免循环依赖

    result = AuthResult(
        access_token=create_access_token(user.id),
        token_type="bearer",
        user=UserOut.model_validate(user),
    )
    return result.model_dump(mode="json")


def register_user(db: Session, data: RegisterIn) -> dict:
    """注册新用户并自动创建空档案。

    Args:
        db: 数据库会话。
        data: 注册入参（用户名 / 密码 / 确认密码）。

    Returns:
        dict: AuthResult 结构（access_token / token_type / user）。

    Raises:
        BizException: code=1006 / HTTP 409，用户名已存在。
    """
    existing = db.scalar(select(User).where(User.username == data.username))
    if existing is not None:
        raise BizException(
            CODE_ALREADY_EXISTS, "用户名已存在", http_status=409
        )
    user = User(
        username=data.username,
        email=None,
        hashed_password=hash_password(data.password),
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
    return _build_auth_result(user)


def login_user(db: Session, data: LoginIn) -> dict:
    """用户名 + 密码登录。

    失败语义：用户不存在、密码错误、账号被禁用统一返回
    1002「用户名或密码错误」（不泄露具体原因）。

    Args:
        db: 数据库会话。
        data: 登录入参。

    Returns:
        dict: AuthResult 结构（access_token / token_type / user）。

    Raises:
        BizException: code=1002 / HTTP 401，认证失败。
    """
    user = db.scalar(select(User).where(User.username == data.username))
    if user is None:
        verify_password(data.password, _DUMMY_HASH)
        raise BizException(
            CODE_AUTH_FAILED, "用户名或密码错误", http_status=401
        )
    if not verify_password(data.password, user.hashed_password) or not user.is_active:
        raise BizException(
            CODE_AUTH_FAILED, "用户名或密码错误", http_status=401
        )
    return _build_auth_result(user)