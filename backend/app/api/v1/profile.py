"""用户学习档案路由（GET / PUT /api/v1/profile）。

仅作用于**当前登录用户本人**的档案（一人一档）；PUT 为字段级
部分更新：对未提交字段保持原值，不接受通过 null 清空字段
（PROJECT_CONTEXT 7.2 锁定 PUT 路径，不提供 PATCH）。
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.core.response import success
from app.models.user import User
from app.schemas.user import UserProfileUpdate
from app.services import profile as profile_service

router: APIRouter = APIRouter(prefix="/profile", tags=["用户档案"])


@router.get("", summary="获取当前用户档案")
def get_profile(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> dict[str, Any]:
    """获取当前登录用户的学习档案；无档案时惰性创建空档案。

    Args:
        current_user: 当前登录用户（依赖注入）。
        db: 数据库会话（依赖注入）。

    Returns:
        dict[str, Any]: 统一响应体，data 为档案对象（含
        ``daily_study_minutes``，默认 60）；未登录返回
        HTTP 401 + code=1003。
    """
    return success(data=profile_service.get_profile(db, current_user))


@router.put("", summary="更新当前用户档案（字段级部分更新）")
def update_profile(
    body: UserProfileUpdate,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> dict[str, Any]:
    """更新当前登录用户的学习档案。

    仅更新已提交且非 null 的字段；未提交字段保持原值，
    不接受通过 null 清空字段。

    Args:
        body: 更新入参（姓名 / 学校 / 专业 / 年级 / 目标类型 /
            兴趣方向 / 每日可学习时长 15–600）。
        current_user: 当前登录用户（依赖注入）。
        db: 数据库会话（依赖注入）。

    Returns:
        dict[str, Any]: 统一响应体，data 为更新后的档案对象。
    """
    return success(
        data=profile_service.update_profile(db, current_user, body),
        message="档案已更新",
    )