"""学习计划路由（需登录，按当前用户隔离数据）。

P12 扩展：``POST /plans/generate``（生成下一完整自然周计划）、
``GET /plans/current``（当前 active 计划）、``POST /plans/{id}/adjust``
（动态调整）、``GET /plans/{id}/diff``（版本对比）。

路由注册顺序硬约束（design 1.2.3-③ 实测）：``/plans/generate`` 与
``/plans/current`` 字面量路由必须声明在 ``/plans/{plan_id}`` 之前
（FastAPI 按声明序匹配，否则被解析为 plan_id → 422）。

路径演进契约：``/api/v1/plans`` 为最终正式路径（PROJECT_CONTEXT
7.2），全部写方法在本文件同路径扩展；路由层零业务逻辑（薄委托
services/plan.py，404/1005/1007 由服务层 BizException → 全局
处理器转换）。
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.core.response import success
from app.models.plan import LearningPlan
from app.models.user import User
from app.schemas.common import PaginationParams
from app.schemas.plan import PlanAdjustIn, PlanGenerateIn, PlanOut
from app.services import plan as plan_service
from app.services.readonly import get_by_id_or_404, paginate

router: APIRouter = APIRouter(prefix="/plans", tags=["学习计划"])


@router.get("", summary="学习计划列表（分页，仅当前用户）")
def list_plans(
    page_params: Annotated[PaginationParams, Query()],
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> dict[str, Any]:
    """分页查询**当前用户**的学习计划版本列表（按 id 升序）。

    Args:
        page_params: 分页参数。
        db: 数据库会话（依赖注入）。
        current_user: 当前登录用户（依赖注入）。

    Returns:
        dict[str, Any]: 统一响应体，data 为 {items, total, page, page_size}；
        未登录返回 HTTP 401 + code=1003。
    """
    return success(
        data=paginate(
            db,
            LearningPlan,
            PlanOut,
            page=page_params.page,
            page_size=page_params.page_size,
            filters=[LearningPlan.user_id == current_user.id],
        )
    )


@router.post("/generate", summary="生成下一个完整自然周学习计划")
async def generate_plan(
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    payload: PlanGenerateIn,
) -> dict[str, Any]:
    """生成下周一~下周日的学习计划（混合模式：LLM 选内容 + 引擎排时）。

    周期语义：恒为**下一个完整自然周**；同周期已有 active 计划时
    归档旧版重新生成（幽灵任务清理）；与既有 active 部分 overlap
    返回 400 + code=1007。规划 LLM 失败自动降级纯规则模式
    （generated_by="rules"），仍返回可用计划。

    Args:
        db: 数据库会话（依赖注入）。
        current_user: 当前登录用户（依赖注入）。
        payload: 请求体（零字段）。

    Returns:
        dict[str, Any]: 统一响应体，data 为
        {plan, items, unplaced_tasks, generated_by}。
    """
    return success(
        data=await plan_service.generate_plan(db, current_user.id)
    )


@router.get("/current", summary="当前生效的学习计划及条目")
def get_current_plan(
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> dict[str, Any]:
    """获取 ``start_date <= 今天 <= end_date`` 且 active 的计划及条目。

    空态语义：无匹配计划返回 200 且 data=null（**非 404**——
    Dashboard 空态依赖，裁决 #8）。

    Args:
        db: 数据库会话（依赖注入）。
        current_user: 当前登录用户（依赖注入）。

    Returns:
        dict[str, Any]: 统一响应体，data 为 {plan, items} 或 null。
    """
    return success(
        data=plan_service.get_current_plan(db, current_user.id)
    )


@router.post("/{plan_id}/adjust", summary="动态调整学习计划（生成新版本）")
async def adjust_plan(
    plan_id: int,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    payload: PlanAdjustIn,
) -> dict[str, Any]:
    """动态调整学习计划（核心差异化能力，纯确定性零 LLM）。

    三条件评估（未完成 ∧ (截止临近 ∨ 时长不足)）→ 新建版本
    （parent_plan_id 指向旧版，形成备份链）+ 具体 adjust_reason +
    结构化 diff 随返；无可调整项时返回 adjusted=false 不新建版本。

    Args:
        plan_id: 目标计划 id（仅限本人，越权 404/1005）。
        db: 数据库会话（依赖注入）。
        current_user: 当前登录用户（依赖注入）。
        payload: 请求体（零字段）。

    Returns:
        dict[str, Any]: 统一响应体，data 为
        {plan, adjust_reason, diff, adjusted}。
    """
    return success(
        data=await plan_service.adjust_plan(db, current_user.id, plan_id)
    )


@router.get("/{plan_id}/diff", summary="计划版本对比（幂等重算）")
def get_plan_diff(
    plan_id: int,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> dict[str, Any]:
    """对比该计划与 parent_plan_id 指向版本的条目（现值重算）。

    首版（parent_plan_id=null）返回空结构 {base_plan_id: null,
    moved: [], added: [], removed: []}（200，裁决 #9）。

    Args:
        plan_id: 目标计划 id（仅限本人，越权 404/1005）。
        db: 数据库会话（依赖注入）。
        current_user: 当前登录用户（依赖注入）。

    Returns:
        dict[str, Any]: 统一响应体，data 为
        {base_plan_id, moved, added, removed}。
    """
    return success(
        data=plan_service.get_plan_diff(db, current_user.id, plan_id)
    )


@router.get("/{plan_id}", summary="学习计划详情")
def get_plan(
    plan_id: int,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> dict[str, Any]:
    """按 id 获取学习计划详情（仅限本人资源）。

    越权访问他人计划与不存在统一返回 HTTP 404 + code=1005。

    Args:
        plan_id: 计划 id。
        db: 数据库会话（依赖注入）。
        current_user: 当前登录用户（依赖注入）。

    Returns:
        dict[str, Any]: 统一响应体，data 为计划对象。
    """
    return success(
        data=get_by_id_or_404(
            db,
            LearningPlan,
            plan_id,
            PlanOut,
            filters=[LearningPlan.user_id == current_user.id],
        )
    )