"""用户学习档案业务逻辑（查询 / 字段级部分更新）。

约定：
- 一人一档：``GET /api/v1/profile`` 恒返回当前用户自己的档案；
- 惰性补建：存量无档案用户（含 P2 之前建库的历史数据）首次访问时
  自动创建空档案（``daily_study_minutes`` 默认 60），不视为错误；
- 更新语义：PUT 为字段级部分更新 —— 仅写入「已提交且非 null」的
  字段，未提交字段保持原值，不支持通过 null 清空字段；兴趣方向
  去重保序。
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.user import User, UserProfile
from app.schemas.user import UserProfileOut, UserProfileUpdate

# 空档案默认值（与 PROJECT_CONTEXT §6.2 一致）。
_DEFAULT_DAILY_MINUTES: int = 60


def _get_or_create_profile(db: Session, user: User) -> UserProfile:
    """获取当前用户档案；不存在时惰性创建空档案。

    Args:
        db: 数据库会话。
        user: 当前登录用户。

    Returns:
        UserProfile: 用户的档案 ORM 对象（仅供 service 内部使用）。
    """
    profile = db.scalar(
        select(UserProfile).where(UserProfile.user_id == user.id)
    )
    if profile is None:
        profile = UserProfile(
            user_id=user.id,
            name=None,
            school=None,
            major=None,
            grade=None,
            current_goal_type=None,
            interest_directions=[],
            daily_study_minutes=_DEFAULT_DAILY_MINUTES,
        )
        db.add(profile)
        db.commit()
        db.refresh(profile)
    return profile


def get_profile(db: Session, user: User) -> dict:
    """获取当前用户档案（序列化为出参 dict）。

    Args:
        db: 数据库会话。
        user: 当前登录用户。

    Returns:
        dict: UserProfileOut 结构。
    """
    profile = _get_or_create_profile(db, user)
    return UserProfileOut.model_validate(profile).model_dump(mode="json")


def update_profile(db: Session, user: User, data: UserProfileUpdate) -> dict:
    """更新当前用户档案（字段级部分更新）。

    仅写入「已提交且非 null」的字段；``{"name": null}`` 等价于
    未提交 name，保持原值不清空。

    Args:
        db: 数据库会话。
        user: 当前登录用户。
        data: 更新入参。

    Returns:
        dict: 更新后的 UserProfileOut 结构。
    """
    profile = _get_or_create_profile(db, user)
    updates: dict = {
        k: v for k, v in data.model_dump(exclude_unset=True).items() if v is not None
    }
    if "interest_directions" in updates:
        # 去重保序。
        seen: set[str] = set()
        updates["interest_directions"] = [
            item
            for item in updates["interest_directions"]
            if not (item in seen or seen.add(item))
        ]
    if updates:
        for key, value in updates.items():
            setattr(profile, key, value)
        db.commit()
        db.refresh(profile)
    return UserProfileOut.model_validate(profile).model_dump(mode="json")