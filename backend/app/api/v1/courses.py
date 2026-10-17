# TODO(P3): 认证阶段为全部业务端点补挂 get_current_user
"""课程只读路由（表名 kebab-case 路径，即最终正式路径）。"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.core.response import success
from app.models.course import Course
from app.schemas.common import PaginationParams
from app.schemas.course import CourseOut
from app.services.readonly import get_by_id_or_404, paginate

router: APIRouter = APIRouter(prefix="/courses", tags=["课程"])


@router.get("", summary="课程列表（分页）")
def list_courses(
    page_params: Annotated[PaginationParams, Query()],
    db: Annotated[Session, Depends(get_db)],
) -> dict[str, Any]:
    """分页查询课程列表（按 id 升序）。

    Args:
        page_params: 分页参数。
        db: 数据库会话（依赖注入）。

    Returns:
        dict[str, Any]: 统一响应体，data 为 {items, total, page, page_size}。
    """
    return success(
        data=paginate(
            db,
            Course,
            CourseOut,
            page=page_params.page,
            page_size=page_params.page_size,
        )
    )


@router.get("/{course_id}", summary="课程详情")
def get_course(
    course_id: int,
    db: Annotated[Session, Depends(get_db)],
) -> dict[str, Any]:
    """按 id 获取课程详情。

    Args:
        course_id: 课程 id。
        db: 数据库会话（依赖注入）。

    Returns:
        dict[str, Any]: 统一响应体，data 为课程对象；不存在时
        返回 HTTP 404 + code=1005。
    """
    return success(data=get_by_id_or_404(db, Course, course_id, CourseOut))