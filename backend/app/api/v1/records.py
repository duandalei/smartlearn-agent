"""学习记录路由（需登录，按当前用户隔离数据）。

路径演进契约：``/api/v1/records`` 为最终正式路径（PROJECT_CONTEXT
7.2 定稿），P6 在本文件完成全部写方法扩展（CRUD + ``/timeline``
时间线 + ``/stats`` 统计）。

分层契约：本层只做「参数接收 + 鉴权注入 + 调用 service + 统一响应
包装」，业务规则（归属校验、事务编排、掌握度重放、任务回填、筛选
条件构造、统计口径）全部在 ``services/record.py`` / ``services/mastery.py``。

路由注册顺序（硬性约束，平移 tasks.py 教训）：``GET /timeline`` 与
``GET /stats`` 必须定义在 ``GET /{record_id}`` **之前**——FastAPI 按
注册顺序匹配，否则路径段 "timeline" / "stats" 会被 ``/{record_id}``
吞掉、转 int 失败返回 422。

分页实现约束（PROJECT_CONTEXT §5.3，FastAPI 0.143.2）：列表端点除
分页外还有 start_date / end_date / course_id / knowledge_point 四个
标量 Query 参数，**不得**混用 ``Annotated[PaginationParams, Query()]``
查询参数模型（模型不展开时被误判为必填的单一 query 参数导致 422），
分页参数逐个标量声明（写法平移 ``goals.py`` 的 list_goals）。
"""

from __future__ import annotations

from datetime import date
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.core.response import success
from app.models.user import User
from app.schemas.record import RecordCreate, RecordOut, RecordUpdate
from app.services import record as record_service
from app.services.readonly import get_by_id_or_404
from app.models.record import LearningRecord

router: APIRouter = APIRouter(prefix="/records", tags=["学习记录"])


@router.get("", summary="学习记录列表（分页 + 筛选，最近在前，仅当前用户）")
def list_records(
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    page: Annotated[int, Query(ge=1, description="页码，从 1 开始")] = 1,
    page_size: Annotated[
        int, Query(ge=1, le=100, description="每页条数，1~100")
    ] = 10,
    start_date: Annotated[
        date | None, Query(description="学习日期下界（含）")
    ] = None,
    end_date: Annotated[
        date | None, Query(description="学习日期上界（含）")
    ] = None,
    course_id: Annotated[
        int | None, Query(ge=1, description="课程 id 精确匹配")
    ] = None,
    knowledge_point: Annotated[
        str | None, Query(max_length=100, description="知识点精确匹配")
    ] = None,
) -> dict[str, Any]:
    """分页查询**当前用户**的学习记录列表（按 study_date 降序、id 降序）。

    实现约束：本端点不用 ``Annotated[PaginationParams, Query()]``
    查询参数模型——当前 FastAPI（0.143.2）仅在查询参数模型是**唯一**
    query 字段时才展开；混入筛选标量后模型不展开，page_params 会被
    误判为必填的单一 query 参数导致 422（P4 实测）。故 6 个参数全部
    逐个标量声明（分页校验口径与 PaginationParams 完全一致）。

    Args:
        db: 数据库会话（依赖注入）。
        current_user: 当前登录用户（依赖注入）。
        page: 页码，从 1 开始。
        page_size: 每页条数，1~100。
        start_date: 学习日期下界（含，YYYY-MM-DD）。
        end_date: 学习日期上界（含，YYYY-MM-DD）。
        course_id: 课程 id 精确匹配。
        knowledge_point: 知识点精确匹配（JSON 数组元素级）。

    Returns:
        dict[str, Any]: 统一响应体，data 为
        ``{items, total, page, page_size}``。
    """
    return success(
        data=record_service.list_records(
            db,
            current_user.id,
            page=page,
            page_size=page_size,
            start_date=start_date,
            end_date=end_date,
            course_id=course_id,
            knowledge_point=knowledge_point,
        )
    )


@router.post("", summary="新建学习记录（同事务触发掌握度重放与任务回填）")
def create_record(
    body: RecordCreate,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> dict[str, Any]:
    """新建学习记录。

    同一事务内完成三部分：记录落库 → 受影响知识点掌握度重放
    （知识点不存在则自动 INSERT，source='record'）→ 关联任务
    ``actual_minutes`` 回填（该任务下全部记录时长之和）。

    Args:
        body: 创建入参（content 必填 1~500；duration_minutes 1~1440；
            study_date 不得晚于北京今天；mastery_level 可空 0~100；
            不接收 user_id）。
        db: 数据库会话（依赖注入）。
        current_user: 当前登录用户（依赖注入）。

    Returns:
        dict[str, Any]: 统一响应体，data 为新建记录（RecordOut）。
    """
    return success(
        data=record_service.create_record(db, current_user.id, body),
        message="创建成功",
    )


@router.get("/timeline", summary="学习时间线（按天聚合补零，供图表使用）")
def get_timeline(
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    days: Annotated[
        int, Query(ge=1, le=365, description="统计天数，1~365")
    ] = 30,
) -> dict[str, Any]:
    """按天聚合的学习时长序列（无记录的天补 0）。

    Args:
        db: 数据库会话（依赖注入）。
        current_user: 当前登录用户（依赖注入）。
        days: 统计天数（1~365，默认 30）。

    Returns:
        dict[str, Any]: 统一响应体，data 为 TimelineOut 结构——恰
        ``days`` 条、date 升序、末条为北京今天；同日多条记录合计。
    """
    return success(
        data=record_service.get_timeline(db, current_user.id, days)
    )


@router.get("/stats", summary="学习统计（本周时长 / 连续天数 / 记录条数）")
def get_stats(
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> dict[str, Any]:
    """学习统计（三值全部后端计算，前端零本地计算）。

    口径：本周按北京自然周（周一起）；连续天数 anchor 取今天（今天
    无记录从昨天起算，不清零）；无任何记录时三值均为 0。

    Args:
        db: 数据库会话（依赖注入）。
        current_user: 当前登录用户（依赖注入）。

    Returns:
        dict[str, Any]: 统一响应体，data 为 RecordStatsOut 结构。
    """
    return success(data=record_service.get_stats(db, current_user.id))


@router.get("/{record_id}", summary="学习记录详情")
def get_record(
    record_id: int,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> dict[str, Any]:
    """按 id 获取学习记录详情（仅限本人资源）。

    越权访问他人记录与不存在统一返回 HTTP 404 + code=1005。

    Args:
        record_id: 记录 id。
        db: 数据库会话（依赖注入）。
        current_user: 当前登录用户（依赖注入）。

    Returns:
        dict[str, Any]: 统一响应体，data 为记录对象。
    """
    return success(
        data=get_by_id_or_404(
            db,
            LearningRecord,
            record_id,
            RecordOut,
            filters=[LearningRecord.user_id == current_user.id],
        )
    )


@router.put("/{record_id}", summary="编辑学习记录（部分更新，显式 null 生效）")
def update_record(
    record_id: int,
    body: RecordUpdate,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> dict[str, Any]:
    """编辑学习记录（仅提交要修改的字段；显式 null 按字段语义生效）。

    ``mastery_level: null`` → 该记录退出掌握度聚合（分数按剩余记录
    回落）；``task_id: null`` → 解除任务关联（前后任务都重算）；
    受影响知识点取前后并集在同一事务内重放。

    Args:
        record_id: 记录 id。
        body: 更新入参。
        db: 数据库会话（依赖注入）。
        current_user: 当前登录用户（依赖注入）。

    Returns:
        dict[str, Any]: 统一响应体，data 为更新后的记录（RecordOut）。
    """
    return success(
        data=record_service.update_record(
            db, current_user.id, record_id, body
        ),
        message="更新成功",
    )


@router.delete("/{record_id}", summary="删除学习记录")
def delete_record(
    record_id: int,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> dict[str, Any]:
    """删除学习记录（同事务重放受影响知识点、重算受影响任务）。

    任务下最后一条记录被删除时，该任务 ``actual_minutes`` 置 NULL
    （表示「未知」，禁止写 0）。

    Args:
        record_id: 记录 id。
        db: 数据库会话（依赖注入）。
        current_user: 当前登录用户（依赖注入）。

    Returns:
        dict[str, Any]: 统一响应体，data 为被删记录快照（RecordOut）。
    """
    return success(
        data=record_service.delete_record(db, current_user.id, record_id),
        message="删除成功",
    )