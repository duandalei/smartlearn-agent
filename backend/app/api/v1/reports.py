"""学习成长报告路由（需登录，按当前用户隔离数据）。

P12 扩展：``POST /reports/generate``（报告生成——LLM 总结 + 模板
降级）与 ``GET /reports`` 列表改写（**created_at 倒序 + report_type
过滤 + 标量分页**，SPEC 裁决 #7 计划内行为变更——O2「取最新一条」
语义依赖倒序）。

路径演进契约：``/api/v1/reports`` 为最终正式路径（PROJECT_CONTEXT
7.2）；既有 ``GET /reports/{id}`` 详情端点零行为变更。
"""

from __future__ import annotations

from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy import desc
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.core.response import success
from app.models.report import LearningReport
from app.models.user import User
from app.schemas.report import ReportGenerateIn, ReportOut
from app.services import report as report_service
from app.services.readonly import get_by_id_or_404, paginate

router: APIRouter = APIRouter(prefix="/reports", tags=["学习报告"])


@router.post("/generate", summary="生成学习成长报告（日报/周报/月报）")
async def generate_report(
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    payload: ReportGenerateIn,
) -> dict[str, Any]:
    """生成学习成长报告（统计本地聚合 + LLM 总结，失败降级模板）。

    周期语义：``period_end`` 缺省取最近完整周期（daily=昨天 /
    weekly=上周日 / monthly=上月末）；``period_start`` 不接受传入
    （由类型与 period_end 推导）；``period_end`` 晚于今天由模型
    validator 拒绝（422/1001）。同一周期重复生成为 append 新行
    （O2 审计轨迹）。LLM 失败自动降级模板总结（仍含真实数字），
    不构成业务失败。

    Args:
        db: 数据库会话（依赖注入）。
        current_user: 当前登录用户（依赖注入）。
        payload: 请求体（report_type 必填；period_end 可选）。

    Returns:
        dict[str, Any]: 统一响应体，data 为报告对象
        （content 含七要素 + generated_by）。
    """
    return success(
        data=await report_service.generate_report(db, current_user.id, payload)
    )


@router.get("", summary="学习报告列表（分页，仅当前用户）")
def list_reports(
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    page: Annotated[int, Query(ge=1, description="页码，从 1 开始")] = 1,
    page_size: Annotated[
        int, Query(ge=1, le=100, description="每页条数，1~100")
    ] = 10,
    report_type: Annotated[
        Literal["daily", "weekly", "monthly"] | None,
        Query(description="按报告类型筛选"),
    ] = None,
) -> dict[str, Any]:
    """分页查询**当前用户**的学习报告列表（created_at 倒序，最新在前）。

    实现约束：本端点不用 ``Annotated[PaginationParams, Query()]``
    查询参数模型——当前 FastAPI（0.143.2）仅在查询参数模型是**唯一**
    query 字段时才展开（``dependencies/utils.py`` 的 ``len(fields) == 1``
    分支）；混入 ``report_type`` 标量后模型不展开，page_params 会被
    误判为必填的单一 query 参数导致 422。故此处分页用标量参数展开
    声明（逐字复刻 list_goals 惯例），契约与 PaginationParams
    （page>=1、1<=page_size<=100）完全一致。

    排序：``created_at`` 倒序 + ``id`` 倒序 tie-break（同秒并列时
    分页稳定）；SPEC 裁决 #7 计划内行为变更（O2「取最新一条」）。

    Args:
        db: 数据库会话（依赖注入）。
        current_user: 当前登录用户（依赖注入）。
        page: 页码，从 1 开始。
        page_size: 每页条数，1~100。
        report_type: 可选报告类型过滤（daily / weekly / monthly），
            非法值由 Literal 枚举自动 422 / 1001。

    Returns:
        dict[str, Any]: 统一响应体，data 为 {items, total, page, page_size}；
        未登录返回 HTTP 401 + code=1003。
    """
    filters = [LearningReport.user_id == current_user.id]
    if report_type is not None:
        filters.append(LearningReport.report_type == report_type)
    return success(
        data=paginate(
            db,
            LearningReport,
            ReportOut,
            page=page,
            page_size=page_size,
            filters=filters,
            order_by=[desc(LearningReport.created_at), desc(LearningReport.id)],
        )
    )


@router.get("/{report_id}", summary="学习报告详情")
def get_report(
    report_id: int,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> dict[str, Any]:
    """按 id 获取学习报告详情（仅限本人资源）。

    越权访问他人报告与不存在统一返回 HTTP 404 + code=1005。

    Args:
        report_id: 报告 id。
        db: 数据库会话（依赖注入）。
        current_user: 当前登录用户（依赖注入）。

    Returns:
        dict[str, Any]: 统一响应体，data 为报告对象。
    """
    return success(
        data=get_by_id_or_404(
            db,
            LearningReport,
            report_id,
            ReportOut,
            filters=[LearningReport.user_id == current_user.id],
        )
    )