"""学习计划条目只读路由（需登录；间接归属：经所属计划按当前用户过滤）。

条目本身无 ``user_id``，归属链为
``learning_plan_items.plan_id -> learning_plans.user_id``；表名
kebab-case 路径，即最终正式路径。
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.core.response import success
from app.models.plan import LearningPlan, LearningPlanItem
from app.models.user import User
from app.schemas.common import PaginationParams
from app.schemas.plan import PlanItemOut
from app.services import plan as plan_service
from app.services.readonly import get_by_id_or_404, paginate

router: APIRouter = APIRouter(prefix="/learning-plan-items", tags=["计划条目"])


def _ownership_filters(current_user: User) -> list[Any]:
    """构造条目归属过滤条件：所属计划属于当前用户。"""
    return [
        LearningPlanItem.plan_id.in_(
            select(LearningPlan.id).where(LearningPlan.user_id == current_user.id)
        )
    ]


@router.get("", summary="计划条目列表（分页，仅当前用户的计划）")
def list_plan_items(
    page_params: Annotated[PaginationParams, Query()],
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> dict[str, Any]:
    """分页查询**当前用户**的学习计划条目列表（按 id 升序）。

    Args:
        page_params: 分页参数。
        db: 数据库会话（依赖注入）。
        current_user: 当前登录用户（依赖注入）。

    Returns:
        dict[str, Any]: 统一响应体，data 为 {items, total, page, page_size}；
        未登录返回 HTTP 401 + code=1003。
    """
    data = paginate(
        db,
        LearningPlanItem,
        PlanItemOut,
        page=page_params.page,
        page_size=page_params.page_size,
        filters=_ownership_filters(current_user),
    )
    # 与 /plans/current|upcoming 同一口径：关联任务已完成 → 条目展示 done
    plan_service.apply_task_completion(db, data["items"])
    return success(data=data)


@router.get("/{item_id}", summary="计划条目详情")
def get_plan_item(
    item_id: int,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> dict[str, Any]:
    """按 id 获取学习计划条目详情（仅限本人计划内的条目）。

    越权访问他人计划的条目与不存在统一返回 HTTP 404 + code=1005。

    Args:
        item_id: 条目 id。
        db: 数据库会话（依赖注入）。
        current_user: 当前登录用户（依赖注入）。

    Returns:
        dict[str, Any]: 统一响应体，data 为条目对象。
    """
    data = get_by_id_or_404(
        db,
        LearningPlanItem,
        item_id,
        PlanItemOut,
        filters=_ownership_filters(current_user),
    )
    plan_service.apply_task_completion(db, [data])
    return success(data=data)