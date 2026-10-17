"""学习成长报告只读路由（需登录，按当前用户隔离数据）。

路径演进契约：``/api/v1/reports`` 为最终正式路径（PROJECT_CONTEXT
7.2），P3+ 的 ``POST /reports/generate`` 在本文件同路径扩展。
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.core.response import success
from app.models.report import LearningReport
from app.models.user import User
from app.schemas.common import PaginationParams
from app.schemas.report import ReportOut
from app.services.readonly import get_by_id_or_404, paginate

router: APIRouter = APIRouter(prefix="/reports", tags=["学习报告"])


@router.get("", summary="学习报告列表（分页，仅当前用户）")
def list_reports(
    page_params: Annotated[PaginationParams, Query()],
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> dict[str, Any]:
    """分页查询**当前用户**的学习报告列表（按 id 升序）。

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
            LearningReport,
            ReportOut,
            page=page_params.page,
            page_size=page_params.page_size,
            filters=[LearningReport.user_id == current_user.id],
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