# TODO(P3): 认证阶段为全部业务端点补挂 get_current_user
"""学习任务只读路由。

路径演进契约：``/api/v1/tasks`` 为最终正式路径，P3+ 的写方法
（POST / PUT / PATCH / DELETE）在本文件同路径扩展。
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.core.response import success
from app.models.task import Task
from app.schemas.common import PaginationParams
from app.schemas.task import TaskOut
from app.services.readonly import get_by_id_or_404, paginate

router: APIRouter = APIRouter(prefix="/tasks", tags=["学习任务"])


@router.get("", summary="任务列表（分页）")
def list_tasks(
    page_params: Annotated[PaginationParams, Query()],
    db: Annotated[Session, Depends(get_db)],
) -> dict[str, Any]:
    """分页查询任务列表（按 id 升序）。

    Args:
        page_params: 分页参数（page >= 1，1 <= page_size <= 100）。
        db: 数据库会话（依赖注入）。

    Returns:
        dict[str, Any]: 统一响应体，data 为 {items, total, page, page_size}。
    """
    return success(
        data=paginate(
            db,
            Task,
            TaskOut,
            page=page_params.page,
            page_size=page_params.page_size,
        )
    )


@router.get("/{task_id}", summary="任务详情")
def get_task(
    task_id: int,
    db: Annotated[Session, Depends(get_db)],
) -> dict[str, Any]:
    """按 id 获取任务详情。

    Args:
        task_id: 任务 id。
        db: 数据库会话（依赖注入）。

    Returns:
        dict[str, Any]: 统一响应体，data 为任务对象；不存在时
        返回 HTTP 404 + code=1005。
    """
    return success(data=get_by_id_or_404(db, Task, task_id, TaskOut))