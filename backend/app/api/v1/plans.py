# TODO(P3): 认证阶段为全部业务端点补挂 get_current_user
"""学习计划只读路由。

路径演进契约：``/api/v1/plans`` 为最终正式路径，P3+ 的写方法
（含 ``/plans/generate``、``/plans/{id}/adjust``、``/plans/{id}/diff``）
在本文件同路径扩展。
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.core.response import success
from app.models.plan import LearningPlan
from app.schemas.common import PaginationParams
from app.schemas.plan import PlanOut
from app.services.readonly import get_by_id_or_404, paginate

router: APIRouter = APIRouter(prefix="/plans", tags=["学习计划"])


@router.get("", summary="学习计划列表（分页）")
def list_plans(
    page_params: Annotated[PaginationParams, Query()],
    db: Annotated[Session, Depends(get_db)],
) -> dict[str, Any]:
    """分页查询学习计划版本列表（按 id 升序）。

    Args:
        page_params: 分页参数。
        db: 数据库会话（依赖注入）。

    Returns:
        dict[str, Any]: 统一响应体，data 为 {items, total, page, page_size}。
    """
    return success(
        data=paginate(
            db,
            LearningPlan,
            PlanOut,
            page=page_params.page,
            page_size=page_params.page_size,
        )
    )


@router.get("/{plan_id}", summary="学习计划详情")
def get_plan(
    plan_id: int,
    db: Annotated[Session, Depends(get_db)],
) -> dict[str, Any]:
    """按 id 获取学习计划详情。

    Args:
        plan_id: 计划 id。
        db: 数据库会话（依赖注入）。

    Returns:
        dict[str, Any]: 统一响应体，data 为计划对象；不存在时
        返回 HTTP 404 + code=1005。
    """
    return success(data=get_by_id_or_404(db, LearningPlan, plan_id, PlanOut))