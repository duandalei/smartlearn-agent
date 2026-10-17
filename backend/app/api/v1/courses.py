"""课程只读路由（需登录，按当前用户隔离数据；表名 kebab-case 路径，即最终正式路径）。"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.core.response import success
from app.models.course import Course
from app.models.user import User
from app.schemas.common import PaginationParams
from app.schemas.course import CourseOut
from app.services.readonly import get_by_id_or_404, paginate

router: APIRouter = APIRouter(prefix="/courses", tags=["课程"])


@router.get("", summary="课程列表（分页，仅当前用户）")
def list_courses(
    page_params: Annotated[PaginationParams, Query()],
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> dict[str, Any]:
    """分页查询**当前用户**的课程列表（按 id 升序）。

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
            Course,
            CourseOut,
            page=page_params.page,
            page_size=page_params.page_size,
            filters=[Course.user_id == current_user.id],
        )
    )


@router.get("/{course_id}", summary="课程详情")
def get_course(
    course_id: int,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> dict[str, Any]:
    """按 id 获取课程详情（仅限本人资源）。

    越权访问他人课程与不存在统一返回 HTTP 404 + code=1005。

    Args:
        course_id: 课程 id。
        db: 数据库会话（依赖注入）。
        current_user: 当前登录用户（依赖注入）。

    Returns:
        dict[str, Any]: 统一响应体，data 为课程对象。
    """
    return success(
        data=get_by_id_or_404(
            db,
            Course,
            course_id,
            CourseOut,
            filters=[Course.user_id == current_user.id],
        )
    )