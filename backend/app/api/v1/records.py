# TODO(P3): 认证阶段为全部业务端点补挂 get_current_user
"""学习记录只读路由。

路径演进契约：``/api/v1/records`` 为最终正式路径（PROJECT_CONTEXT
7.2 定稿），P3+ 的写方法在本文件同路径扩展。
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.core.response import success
from app.models.record import LearningRecord
from app.schemas.common import PaginationParams
from app.schemas.record import RecordOut
from app.services.readonly import get_by_id_or_404, paginate

router: APIRouter = APIRouter(prefix="/records", tags=["学习记录"])


@router.get("", summary="学习记录列表（分页，最近在前）")
def list_records(
    page_params: Annotated[PaginationParams, Query()],
    db: Annotated[Session, Depends(get_db)],
) -> dict[str, Any]:
    """分页查询学习记录列表（按 study_date 降序、id 降序，最近记录在前）。

    Args:
        page_params: 分页参数。
        db: 数据库会话（依赖注入）。

    Returns:
        dict[str, Any]: 统一响应体，data 为 {items, total, page, page_size}。
    """
    return success(
        data=paginate(
            db,
            LearningRecord,
            RecordOut,
            page=page_params.page,
            page_size=page_params.page_size,
            order_by=[
                LearningRecord.study_date.desc(),
                LearningRecord.id.desc(),
            ],
        )
    )


@router.get("/{record_id}", summary="学习记录详情")
def get_record(
    record_id: int,
    db: Annotated[Session, Depends(get_db)],
) -> dict[str, Any]:
    """按 id 获取学习记录详情。

    Args:
        record_id: 记录 id。
        db: 数据库会话（依赖注入）。

    Returns:
        dict[str, Any]: 统一响应体，data 为记录对象；不存在时
        返回 HTTP 404 + code=1005。
    """
    return success(
        data=get_by_id_or_404(db, LearningRecord, record_id, RecordOut)
    )