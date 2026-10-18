"""学习目标路由（需登录，按当前用户隔离数据）。

路径演进契约：``/api/v1/goals`` 为最终正式路径，P4 在本文件完成
全部写方法扩展（CRUD + ``POST /goals/{id}/breakdown`` AI 拆解 +
``GET /goals/{id}/roadmap`` 知识树查询）。

分层契约：本层只做「参数接收 + 鉴权注入 + 调用 service + 统一响应
包装」，业务规则全部在 ``services/goal.py``。
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.core.response import success
from app.models.enums import GoalStatus
from app.models.goal import LearningGoal
from app.models.user import User

from app.schemas.goal import GoalCreate, GoalOut, GoalUpdate
from app.services import goal as goal_service
from app.services.readonly import get_by_id_or_404, paginate

router: APIRouter = APIRouter(prefix="/goals", tags=["学习目标"])


@router.get("", summary="学习目标列表（分页 + 状态筛选，仅当前用户）")
def list_goals(
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    page: Annotated[int, Query(ge=1, description="页码，从 1 开始")] = 1,
    page_size: Annotated[
        int, Query(ge=1, le=100, description="每页条数，1~100")
    ] = 10,
    status: Annotated[
        GoalStatus | None, Query(description="按状态筛选")
    ] = None,
) -> dict[str, Any]:
    """分页查询**当前用户**的学习目标列表（按 id 升序）。

    实现约束：本端点不用 ``Annotated[PaginationParams, Query()]``
    查询参数模型——当前 FastAPI（0.143.2）仅在查询参数模型是**唯一**
    query 字段时才展开（``dependencies/utils.py`` 的 ``len(fields) == 1``
    分支）；混入 status 标量后模型不展开，page_params 会被误判为
    必填的单一 query 参数导致 422。故此处分页用标量参数展开声明，
    契约与 PaginationParams（page>=1、1<=page_size<=100）完全一致。

    Args:
        db: 数据库会话（依赖注入）。
        current_user: 当前登录用户（依赖注入）。
        page: 页码，从 1 开始。
        page_size: 每页条数，1~100。
        status: 可选状态筛选（active / completed / archived），
            非法值由 GoalStatus 枚举自动 422 / 1001。

    Returns:
        dict[str, Any]: 统一响应体，data 为 {items, total, page, page_size}；
        未登录返回 HTTP 401 + code=1003。
    """
    filters = [LearningGoal.user_id == current_user.id]
    if status is not None:
        filters.append(LearningGoal.status == status)
    return success(
        data=paginate(
            db,
            LearningGoal,
            GoalOut,
            page=page,
            page_size=page_size,
            filters=filters,
        )
    )


@router.post("", summary="新建学习目标")
def create_goal(
    body: GoalCreate,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> dict[str, Any]:
    """新建学习目标（status 固定 active、roadmap 初始为 null）。

    Args:
        body: 创建入参（title 必填 1~200；goal_type 须属 5 枚举）。
        db: 数据库会话（依赖注入）。
        current_user: 当前登录用户（依赖注入）。

    Returns:
        dict[str, Any]: 统一响应体，data 为新目标（GoalOut）。
    """
    return success(
        data=goal_service.create_goal(db, current_user.id, body),
        message="创建成功",
    )


@router.get("/{goal_id}", summary="学习目标详情")
def get_goal(
    goal_id: int,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> dict[str, Any]:
    """按 id 获取学习目标详情（仅限本人资源）。

    越权访问他人目标与不存在统一返回 HTTP 404 + code=1005，
    防止资源 ID 枚举。

    Args:
        goal_id: 目标 id。
        db: 数据库会话（依赖注入）。
        current_user: 当前登录用户（依赖注入）。

    Returns:
        dict[str, Any]: 统一响应体，data 为目标对象。
    """
    return success(
        data=get_by_id_or_404(
            db,
            LearningGoal,
            goal_id,
            GoalOut,
            filters=[LearningGoal.user_id == current_user.id],
        )
    )


@router.put("/{goal_id}", summary="编辑学习目标")
def update_goal(
    goal_id: int,
    body: GoalUpdate,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> dict[str, Any]:
    """编辑学习目标（字段级部分更新，禁止触碰 roadmap 字段）。

    Args:
        goal_id: 目标 id。
        body: 更新入参（仅提交要修改的字段）。
        db: 数据库会话（依赖注入）。
        current_user: 当前登录用户（依赖注入）。

    Returns:
        dict[str, Any]: 统一响应体，data 为更新后的目标（GoalOut）。
    """
    return success(
        data=goal_service.update_goal(db, current_user.id, goal_id, body),
        message="更新成功",
    )


@router.delete("/{goal_id}", summary="删除学习目标")
def delete_goal(
    goal_id: int,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> dict[str, Any]:
    """删除学习目标（关联任务/计划 goal_id 自动置空，掌握度保留）。

    Args:
        goal_id: 目标 id。
        db: 数据库会话（依赖注入）。
        current_user: 当前登录用户（依赖注入）。

    Returns:
        dict[str, Any]: 统一响应体，data 为被删除的目标（GoalOut）。
    """
    return success(
        data=goal_service.delete_goal(db, current_user.id, goal_id),
        message="删除成功",
    )


@router.post("/{goal_id}/breakdown", summary="AI 拆解目标为知识树")
async def breakdown_goal(
    goal_id: int,
    current_user: Annotated[User, Depends(get_current_user)],
) -> dict[str, Any]:
    """调用 LLM 把目标拆解为知识树（叶子节点初始化掌握度）。

    **async 路由且不注入 get_db**：拆解全程可达 90s+，service 内部
    自管两段短会话（design 2.1.3-B），避免请求级 Session 长期占用
    连接池。同一目标并发拆解互斥（冲突 1007）。

    Args:
        goal_id: 目标 id。
        current_user: 当前登录用户（依赖注入）。

    Returns:
        dict[str, Any]: 统一响应体，data 为 RoadmapOut（含新知识树）。
    """
    data = await goal_service.breakdown_goal(current_user.id, goal_id)
    return success(data=data, message="拆解完成")


@router.get("/{goal_id}/roadmap", summary="目标知识树查询")
def get_goal_roadmap(
    goal_id: int,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> dict[str, Any]:
    """查询目标知识树（roadmap=null 表示从未拆解）。

    Args:
        goal_id: 目标 id。
        db: 数据库会话（依赖注入）。
        current_user: 当前登录用户（依赖注入）。

    Returns:
        dict[str, Any]: 统一响应体，data 为 RoadmapOut。
    """
    return success(
        data=goal_service.get_roadmap(db, current_user.id, goal_id)
    )