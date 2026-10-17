"""学习任务只读路由（需登录，按当前用户隔离数据）。

路径演进契约：``/api/v1/tasks`` 为最终正式路径，P3+ 的写方法
（POST / PUT / PATCH / DELETE）在本文件同路径扩展。
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.core.response import success
from app.models.task import Task
from app.models.user import User
from app.schemas.common import PaginationParams
from app.schemas.task import TaskOut
from app.services.readonly import get_by_id_or_404, paginate

router: APIRouter = APIRouter(prefix="/tasks", tags=["学习任务"])


@router.get("", summary="任务列表（分页，仅当前用户）")
def list_tasks(
    page_params: Annotated[PaginationParams, Query()],
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> dict[str, Any]:
    """分页查询**当前用户**的任务列表（按 id 升序）。

    Args:
        page_params: 分页参数（page >= 1，1 <= page_size <= 100）。
        db: 数据库会话（依赖注入）。
        current_user: 当前登录用户（依赖注入）。

    Returns:
        dict[str, Any]: 统一响应体，data 为 {items, total, page, page_size}；
        未登录返回 HTTP 401 + code=1003。
    """
    return success(
        data=paginate(
            db,
            Task,
            TaskOut,
            page=page_params.page,
            page_size=page_params.page_size,
            filters=[Task.user_id == current_user.id],
        )
    )


@router.get("/{task_id}", summary="任务详情")
def get_task(
    task_id: int,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> dict[str, Any]:
    """按 id 获取任务详情（仅限本人资源）。

    越权访问他人任务与不存在统一返回 HTTP 404 + code=1005。

    Args:
        task_id: 任务 id。
        db: 数据库会话（依赖注入）。
        current_user: 当前登录用户（依赖注入）。

    Returns:
        dict[str, Any]: 统一响应体，data 为任务对象。
    """
    return success(
        data=get_by_id_or_404(
            db,
            Task,
            task_id,
            TaskOut,
            filters=[Task.user_id == current_user.id],
        )
    )