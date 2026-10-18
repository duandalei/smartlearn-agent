"""学习任务路由（需登录，按当前用户隔离数据）。

路径演进契约：``/api/v1/tasks`` 为最终正式路径，P5 在本文件完成
全部写方法扩展（CRUD + ``PATCH /{id}/status`` 状态流转 +
``GET /board`` 看板 + ``GET /stats`` 统计）。

分层契约：本层只做「参数接收 + 鉴权注入 + 调用 service + 统一响应
包装」，业务规则（状态机判定、筛选条件构造、统计口径）全部在
``services/task.py``。

路由注册顺序（硬性约束，design 2.2.1）：``GET /board`` 与
``GET /stats`` 必须定义在 ``GET /{task_id}`` **之前**——FastAPI 按
注册顺序匹配，否则路径段 "board" / "stats" 会被 ``/{task_id}``
吞掉、转 int 失败返回 422。
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.core.response import success
from app.models.enums import Priority, TaskStatus
from app.models.user import User
from app.schemas.task import (
    TaskCreate,
    TaskOut,
    TaskStatusUpdate,
    TaskUpdate,
)
from app.services import task as task_service
from app.services.readonly import get_by_id_or_404
from app.models.task import Task

router: APIRouter = APIRouter(prefix="/tasks", tags=["学习任务"])


@router.get("", summary="任务列表（分页 + 多条件筛选，仅当前用户）")
def list_tasks(
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    page: Annotated[int, Query(ge=1, description="页码，从 1 开始")] = 1,
    page_size: Annotated[
        int, Query(ge=1, le=100, description="每页条数，1~100")
    ] = 10,
    status: Annotated[TaskStatus | None, Query(description="状态筛选")] = None,
    priority: Annotated[
        Priority | None, Query(description="优先级筛选")
    ] = None,
    course_id: Annotated[
        int | None, Query(ge=1, description="所属课程 id 精确匹配")
    ] = None,
    knowledge_point: Annotated[
        str | None, Query(max_length=100, description="知识点精确匹配")
    ] = None,
    overdue: Annotated[
        bool | None,
        Query(description="true=仅逾期；false=仅未逾期（含无截止）"),
    ] = None,
    keyword: Annotated[
        str | None, Query(max_length=200, description="名称/描述模糊搜索")
    ] = None,
) -> dict[str, Any]:
    """分页查询**当前用户**的任务列表（默认 id 降序，新建在前）。

    实现约束：本端点不用 ``Annotated[PaginationParams, Query()]``
    查询参数模型——当前 FastAPI（0.143.2）仅在查询参数模型是**唯一**
    query 字段时才展开（``dependencies/utils.py`` 的 ``len(fields) == 1``
    分支）；混入筛选标量后模型不展开，page_params 会被误判为必填的
    单一 query 参数导致 422（P4 实测）。故 8 个参数全部逐个标量声明
    （写法平移 ``api/v1/goals.py`` 的 list_goals，分页校验口径与
    PaginationParams 完全一致）。

    Args:
        db: 数据库会话（依赖注入）。
        current_user: 当前登录用户（依赖注入）。
        page: 页码，从 1 开始。
        page_size: 每页条数，1~100。
        status: 状态筛选（todo / in_progress / done / review）。
        priority: 优先级筛选（low / medium / high）。
        course_id: 所属课程 id 精确匹配。
        knowledge_point: 知识点精确匹配（JSON 数组元素级）。
        overdue: 是否逾期筛选。
        keyword: 名称 / 描述模糊搜索（不区分大小写）。

    Returns:
        dict[str, Any]: 统一响应体，data 为
        ``{items, total, page, page_size}``。
    """
    return success(
        data=task_service.list_tasks(
            db,
            current_user.id,
            page=page,
            page_size=page_size,
            status=status,
            priority=priority,
            course_id=course_id,
            knowledge_point=knowledge_point,
            overdue=overdue,
            keyword=keyword,
        )
    )


@router.post("", summary="新建任务")
def create_task(
    body: TaskCreate,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> dict[str, Any]:
    """新建任务（status 固定 todo、source 固定 manual）。

    Args:
        body: 创建入参（title 必填 1~200；不接收 status /
            completed_at / source / user_id / scheduled_date）。
        db: 数据库会话（依赖注入）。
        current_user: 当前登录用户（依赖注入）。

    Returns:
        dict[str, Any]: 统一响应体，data 为新任务（TaskOut）。
    """
    return success(
        data=task_service.create_task(db, current_user.id, body),
        message="创建成功",
    )


@router.get("/board", summary="看板数据（按状态四列，全量 MVP）")
def get_board(
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> dict[str, Any]:
    """看板数据：``{todo, in_progress, done, review}`` 四列（全量返回）。

    全量返回为 MVP 取舍（数据规模增大后按状态分页或虚拟滚动）；
    列内排序：优先级降序 → 截止时间升序（未设置排最后）→ id 降序。

    Args:
        db: 数据库会话（依赖注入）。
        current_user: 当前登录用户（依赖注入）。

    Returns:
        dict[str, Any]: 统一响应体，data 为固定四键的看板结构。
    """
    return success(data=task_service.get_board(db, current_user.id))


@router.get("/stats", summary="任务统计")
def get_stats(
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> dict[str, Any]:
    """任务统计：总数 / 各状态数 / 逾期数 / 本周完成率 / 今日待办。

    口径：本周 / 今天按北京时间自然周（周一起）/ 自然日计算；
    完成率分子含 done 与 review；分母 0 时取 0；一次请求返回全部
    口径（数值全部来自本接口，前端零本地计算）。

    Args:
        db: 数据库会话（依赖注入）。
        current_user: 当前登录用户（依赖注入）。

    Returns:
        dict[str, Any]: 统一响应体，data 为 TaskStatsOut 结构。
    """
    return success(data=task_service.get_stats(db, current_user.id))


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


@router.put("/{task_id}", summary="编辑任务（部分字段更新，不含状态）")
def update_task(
    task_id: int,
    body: TaskUpdate,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> dict[str, Any]:
    """编辑任务（仅提交要修改的字段；status 等四禁止字段 422 拒绝）。

    Args:
        task_id: 任务 id。
        body: 更新入参。
        db: 数据库会话（依赖注入）。
        current_user: 当前登录用户（依赖注入）。

    Returns:
        dict[str, Any]: 统一响应体，data 为更新后的任务（TaskOut）。
    """
    return success(
        data=task_service.update_task(db, current_user.id, task_id, body),
        message="更新成功",
    )


@router.delete("/{task_id}", summary="删除任务")
def delete_task(
    task_id: int,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> dict[str, Any]:
    """删除任务（关联学习记录 / 计划条目的 task_id 由 DB 层自动置空）。

    Args:
        task_id: 任务 id。
        db: 数据库会话（依赖注入）。
        current_user: 当前登录用户（依赖注入）。

    Returns:
        dict[str, Any]: 统一响应体，data 为被删除的任务（TaskOut）。
    """
    return success(
        data=task_service.delete_task(db, current_user.id, task_id),
        message="删除成功",
    )


@router.patch("/{task_id}/status", summary="状态流转（状态机校验）")
def update_task_status(
    task_id: int,
    body: TaskStatusUpdate,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> dict[str, Any]:
    """任务状态流转（合法边仅 5 条，校验在 service 层单点完成）。

    非法流转返回 code=1007 / HTTP 400，message 含前后状态中文名
    （如「任务状态不能从 待办 直接变更为 已完成」），不抛 500。

    Args:
        task_id: 任务 id。
        body: 流转入参（status 必属四枚举，非法值 schema 层 422）。
        db: 数据库会话（依赖注入）。
        current_user: 当前登录用户（依赖注入）。

    Returns:
        dict[str, Any]: 统一响应体，data 为流转后的任务（TaskOut）。
    """
    return success(
        data=task_service.transition_task_status(
            db, current_user.id, task_id, body.status
        ),
        message="状态更新成功",
    )