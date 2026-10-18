"""学习任务业务逻辑（CRUD + 状态机流转 + 列表筛选 + 看板 + 统计）。

分层契约（PROJECT_CONTEXT 第 4 章）：本模块承载全部业务规则与事务，
不接收 FastAPI 的 Request/Response、不拼接 HTTP 响应。

状态机单点收敛（spec 5.3.1 规则 4 / 6.2.5）：全项目合法流转判定的
**唯一来源**是本模块的 ``TRANSITIONS`` 常量（5 条合法边）；路由层零
业务判断，前端 ``utils/task.ts`` 仅做其镜像（用于渲染可选项）。

时区口径（spec 6.3.4 / 裁定㉒）：数据库时间按 UTC 存储，「本周」
「今天」按北京时间（Asia/Shanghai）自然周 / 自然日计算——先用
标准库 ``zoneinfo`` 求北京边界再转 UTC 查库，禁止直接用 UTC 日期
（北京周一 00:00–08:00 = UTC 周日 16:00–24:00，直接按 UTC 周计算
会把该窗口错算进上一周，完成率失真）。
"""

from __future__ import annotations

import json
import logging
from datetime import date, datetime, time, timedelta, timezone, tzinfo
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import ColumnElement, and_, case, func, or_, select
from sqlalchemy.orm import Session

from app.core.response import CODE_BIZ_CONFLICT, CODE_NOT_FOUND, BizException
from app.models.base import utc_now
from app.models.course import Course
from app.models.enums import Priority, TaskSource, TaskStatus
from app.models.goal import LearningGoal
from app.models.task import Task
from app.schemas.task import TaskCreate, TaskOut, TaskStatsOut, TaskUpdate
from app.services.readonly import paginate

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 模块常量（状态机唯一判定来源，spec 6.2 / 裁定㉑）
# ---------------------------------------------------------------------------
#: 合法流转边有且仅有 5 条：正向 3 条 + 搁置回退 1 条 + 复盘闭环 1 条。
TRANSITIONS: dict[TaskStatus, frozenset[TaskStatus]] = {
    TaskStatus.TODO: frozenset({TaskStatus.IN_PROGRESS}),
    TaskStatus.IN_PROGRESS: frozenset({TaskStatus.DONE, TaskStatus.TODO}),
    TaskStatus.DONE: frozenset({TaskStatus.REVIEW}),
    TaskStatus.REVIEW: frozenset({TaskStatus.DONE}),
}

#: 状态中文名（1007 提示文案与前端镜像的数据源，spec 6.2.4）。
STATUS_LABELS: dict[TaskStatus, str] = {
    TaskStatus.TODO: "待办",
    TaskStatus.IN_PROGRESS: "进行中",
    TaskStatus.DONE: "已完成",
    TaskStatus.REVIEW: "待复盘",
}

#: 北京时间（统计自然周 / 自然日的口径时区）。优先标准库 ``zoneinfo``
#: 的 Asia/Shanghai；当运行环境无 IANA 时区数据库（Windows 未安装
#: tzdata 包且系统无 /usr/share/zoneinfo）时回退为固定偏移 UTC+8——
#: 中国自 1991 年起不实行夏令时，Asia/Shanghai 恒为 UTC+8，固定
#: 偏移在数学上与 ZoneInfo 完全等价（零新依赖，spec 裁定㉒）。
try:
    TZ_BEIJING: tzinfo = ZoneInfo("Asia/Shanghai")
except ZoneInfoNotFoundError:  # pragma: no cover —— Windows 无 tzdata 环境
    TZ_BEIJING = timezone(timedelta(hours=8), "+08:00")

#: 看板列内排序的优先级权重（high=0 < medium=1 < low=2）。
#: 陷阱规避：priority 落库为 VARCHAR，字典序为 high < low < medium，
#: 直接按列排序会得到 high→low→medium 错序，必须经 case 权重映射。
PRIORITY_WEIGHT = case(
    (Task.priority == Priority.HIGH, 0),
    (Task.priority == Priority.MEDIUM, 1),
    else_=2,
)


# ---------------------------------------------------------------------------
# 私有助手
# ---------------------------------------------------------------------------
def _get_task_or_404(db: Session, user_id: int, task_id: int) -> Task:
    """按 id + 归属查询任务；不存在或越权统一抛 404（防 ID 枚举）。

    Args:
        db: 数据库会话。
        user_id: 当前用户 id。
        task_id: 任务 id。

    Returns:
        Task: 任务 ORM 对象。

    Raises:
        BizException: code=1005 / HTTP 404。
    """
    task = db.scalar(
        select(Task).where(Task.id == task_id, Task.user_id == user_id)
    )
    if task is None:
        raise BizException(CODE_NOT_FOUND, "资源不存在", http_status=404)
    return task


def _validate_goal_ref(db: Session, user_id: int, goal_id: int) -> None:
    """校验 goal_id 属本人且存在（引用他人或不存在统一 404，裁定⑬）。

    Args:
        db: 数据库会话。
        user_id: 当前用户 id。
        goal_id: 待校验的目标 id。

    Raises:
        BizException: code=1005 / HTTP 404。
    """
    exists = db.scalar(
        select(LearningGoal.id).where(
            LearningGoal.id == goal_id, LearningGoal.user_id == user_id
        )
    )
    if exists is None:
        raise BizException(
            CODE_NOT_FOUND, "关联的学习目标不存在", http_status=404
        )


def _validate_course_ref(db: Session, user_id: int, course_id: int) -> None:
    """校验 course_id 属本人且存在（引用他人或不存在统一 404，裁定⑬）。

    Args:
        db: 数据库会话。
        user_id: 当前用户 id。
        course_id: 待校验的课程 id。

    Raises:
        BizException: code=1005 / HTTP 404。
    """
    exists = db.scalar(
        select(Course.id).where(
            Course.id == course_id, Course.user_id == user_id
        )
    )
    if exists is None:
        raise BizException(
            CODE_NOT_FOUND, "关联的课程不存在", http_status=404
        )


def _serialize_task(task: Task) -> dict:
    """把任务 ORM 对象序列化为 TaskOut 结构的 JSON dict。

    knowledge_points 由 JSONListType 读出永为 list[str]，各层禁止
    再手动 json.loads / json.dumps（PROJECT_CONTEXT 8.1）。
    """
    return TaskOut.model_validate(task).model_dump(mode="json")


def _escape_like(s: str) -> str:
    """转义 LIKE 通配符（``\\``、``%``、``_``），防用户输入穿透模糊匹配。

    Args:
        s: 原始关键词。

    Returns:
        str: 转义后的关键词（配合 ``ilike(..., escape="\\\\")`` 使用）。
    """
    for ch in ("\\", "%", "_"):
        s = s.replace(ch, f"\\{ch}")
    return s


def _build_list_filters(
    user_id: int,
    status: TaskStatus | None,
    priority: Priority | None,
    course_id: int | None,
    knowledge_point: str | None,
    overdue: bool | None,
    keyword: str | None,
    now: datetime,
) -> list[ColumnElement[bool]]:
    """构造列表查询条件（数据隔离 + 6 筛选 AND 组合，spec 6.4）。

    Args:
        user_id: 当前用户 id（数据隔离基线）。
        status: 状态筛选。
        priority: 优先级筛选。
        course_id: 课程精确匹配。
        knowledge_point: 知识点精确匹配（JSON 引号边界，裁定⑩）。
        overdue: True=仅逾期；False=仅未逾期（含无截止，SQL 三值逻辑）。
        keyword: 名称 / 描述模糊搜索（不区分大小写）。
        now: 本次请求统一时间基准（aware UTC，只取一次复用）。

    Returns:
        list[ColumnElement[bool]]: 供 paginate AND 拼接的条件序列。
    """
    filters: list[ColumnElement[bool]] = [Task.user_id == user_id]
    if status is not None:
        filters.append(Task.status == status)
    if priority is not None:
        filters.append(Task.priority == priority)
    if course_id is not None:
        filters.append(Task.course_id == course_id)
    if knowledge_point is not None:
        # JSON 元素精确匹配：json.dumps("Attention") -> '"Attention"'
        # （含双引号边界），在 ["Multi-Head Attention"] 中 instr 找不到
        # '"Attention"'（Attention 前是空格非引号）→ 不误命中；instr 为
        # 二进制比较，天然大小写敏感（裁定⑩）。
        filters.append(
            func.instr(
                Task.knowledge_points,
                json.dumps(knowledge_point, ensure_ascii=False),
            )
            > 0
        )
    if overdue is True:
        filters.append(
            and_(
                Task.deadline.is_not(None),
                Task.deadline < now,
                Task.status.in_([TaskStatus.TODO, TaskStatus.IN_PROGRESS]),
            )
        )
    elif overdue is False:
        # SQL 三值逻辑：deadline 为 NULL 时 `deadline < now` 为 NULL、
        # not_(NULL) 仍为 NULL 不命中——false 分支必须显式三分支 or_，
        # 与 true 分支互补覆盖全量行（design 2.1.3-B）。
        filters.append(
            or_(
                Task.deadline.is_(None),
                Task.deadline >= now,
                Task.status.in_([TaskStatus.DONE, TaskStatus.REVIEW]),
            )
        )
    if keyword:
        escaped = _escape_like(keyword)
        filters.append(
            or_(
                Task.title.ilike(f"%{escaped}%", escape="\\"),
                Task.description.ilike(f"%{escaped}%", escape="\\"),
            )
        )
    return filters


def _today_bounds_utc(now: datetime) -> tuple[date, datetime, datetime]:
    """北京时间「今天」边界：返回 (北京日期, 今日起始 UTC, 次日起始 UTC)。

    Args:
        now: 当前时刻（aware UTC）。

    Returns:
        tuple[date, datetime, datetime]: 北京今天日期与 UTC 区间端点
        （区间左闭右开，查库一律传 aware UTC datetime）。
    """
    today_bj = now.astimezone(TZ_BEIJING).date()
    start = datetime.combine(today_bj, time.min, tzinfo=TZ_BEIJING).astimezone(
        timezone.utc
    )
    return today_bj, start, start + timedelta(days=1)


def _week_bounds_utc(now: datetime) -> tuple[datetime, datetime]:
    """北京时间「本周」（周一起算）：返回 (周一 00:00 UTC, 下周一 00:00 UTC)。

    Args:
        now: 当前时刻（aware UTC）。

    Returns:
        tuple[datetime, datetime]: UTC 区间端点（左闭右开）。
    """
    today_bj = now.astimezone(TZ_BEIJING).date()
    monday_bj = today_bj - timedelta(days=today_bj.weekday())
    start = datetime.combine(
        monday_bj, time.min, tzinfo=TZ_BEIJING
    ).astimezone(timezone.utc)
    return start, start + timedelta(days=7)


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------
def create_task(db: Session, user_id: int, data: TaskCreate) -> dict:
    """创建学习任务（status 固定 todo、source 固定 manual，裁定⑦）。

    Args:
        db: 数据库会话（依赖注入）。
        user_id: 当前用户 id。
        data: 创建入参。

    Returns:
        dict: TaskOut 结构。

    Raises:
        BizException: code=1005 / HTTP 404，goal_id / course_id 引用
            他人或不存在时抛出。
    """
    if data.goal_id is not None:
        _validate_goal_ref(db, user_id, data.goal_id)
    if data.course_id is not None:
        _validate_course_ref(db, user_id, data.course_id)
    task = Task(
        user_id=user_id,
        goal_id=data.goal_id,
        course_id=data.course_id,
        title=data.title,
        description=data.description,
        knowledge_points=data.knowledge_points,
        priority=data.priority,
        estimated_minutes=data.estimated_minutes,
        deadline=data.deadline,
        status=TaskStatus.TODO,
        source=TaskSource.MANUAL,
        completed_at=None,
        actual_minutes=None,
    )
    db.add(task)
    db.commit()
    db.refresh(task)
    return _serialize_task(task)


def update_task(
    db: Session, user_id: int, task_id: int, data: TaskUpdate
) -> dict:
    """编辑学习任务（字段级部分更新，status 等四禁止字段不可触碰）。

    仅写入已提交且非 None 的字段（全站惯例：传 null 不清空、缺省保持
    原值；``knowledge_points=[]`` 为非 None 合法值可清空）。goal_id /
    course_id 提交值非 None 时做引用归属校验。

    Args:
        db: 数据库会话（依赖注入）。
        user_id: 当前用户 id。
        task_id: 任务 id。
        data: 更新入参。

    Returns:
        dict: 更新后的 TaskOut 结构。

    Raises:
        BizException: code=1005 / HTTP 404（不存在、越权或引用非法）。
    """
    task = _get_task_or_404(db, user_id, task_id)
    updates: dict[str, Any] = {
        k: v
        for k, v in data.model_dump(exclude_unset=True).items()
        if v is not None
    }
    if updates:
        if "goal_id" in updates:
            _validate_goal_ref(db, user_id, updates["goal_id"])
        if "course_id" in updates:
            _validate_course_ref(db, user_id, updates["course_id"])
        for key, value in updates.items():
            setattr(task, key, value)
        db.commit()
        db.refresh(task)
    return _serialize_task(task)


def delete_task(db: Session, user_id: int, task_id: int) -> dict:
    """删除学习任务（返回被删对象快照，P4 惯例）。

    关联学习记录 / 计划条目的 ``task_id`` 由数据库层
    ``ondelete="SET NULL"`` + ``PRAGMA foreign_keys=ON`` 自动置空，
    service 零级联代码（裁定⑱）。

    Args:
        db: 数据库会话（依赖注入）。
        user_id: 当前用户 id。
        task_id: 任务 id。

    Returns:
        dict: 被删任务的 TaskOut 结构。

    Raises:
        BizException: code=1005 / HTTP 404。
    """
    task = _get_task_or_404(db, user_id, task_id)
    snapshot = _serialize_task(task)
    db.delete(task)
    db.commit()
    return snapshot


# ---------------------------------------------------------------------------
# 列表查询（分页 + 6 条件筛选）
# ---------------------------------------------------------------------------
def list_tasks(
    db: Session,
    user_id: int,
    *,
    page: int,
    page_size: int,
    status: TaskStatus | None = None,
    priority: Priority | None = None,
    course_id: int | None = None,
    knowledge_point: str | None = None,
    overdue: bool | None = None,
    keyword: str | None = None,
) -> dict:
    """分页查询任务（6 筛选 AND 组合，默认 id 降序 = 新建在前，决策⑧）。

    筛选条件构造属业务规则，收敛在本函数（路由层零判断）；overdue
    的 NULL 三值逻辑、knowledge_point 的 JSON 引号边界匹配见
    :func:`_build_list_filters`。

    Args:
        db: 数据库会话（依赖注入）。
        user_id: 当前用户 id。
        page: 页码（从 1 开始）。
        page_size: 每页条数（1~100）。
        status: 状态筛选（可选）。
        priority: 优先级筛选（可选）。
        course_id: 课程精确匹配（可选）。
        knowledge_point: 知识点精确匹配（可选）。
        overdue: 是否逾期筛选（可选）。
        keyword: 名称 / 描述模糊搜索（可选）。

    Returns:
        dict: ``{items, total, page, page_size}``。
    """
    now = utc_now()
    filters = _build_list_filters(
        user_id,
        status,
        priority,
        course_id,
        knowledge_point,
        overdue,
        keyword,
        now,
    )
    return paginate(
        db,
        Task,
        TaskOut,
        page=page,
        page_size=page_size,
        order_by=[Task.id.desc()],
        filters=filters,
    )


# ---------------------------------------------------------------------------
# 状态机流转（本模块核心，spec 5.3.1 / 6.2）
# ---------------------------------------------------------------------------
def transition_task_status(
    db: Session, user_id: int, task_id: int, target: TaskStatus
) -> dict:
    """任务状态流转（状态机单点校验 + completed_at 首次语义）。

    非法流转（跳级 / done 后回退 / 同状态等不在 5 条合法边内的组合）
    在 commit 前 raise ``BizException(1007, 400)``，message 含前后状态
    中文名，任务原状态与 completed_at 均不变、天然不抛 500（spec
    4.2.1 / 5.3.1 规则 2b）。

    completed_at 首次语义（裁定⑤）：仅首次进入 done 时写入，review →
    done 不覆盖，搁置回 todo 与进入 review 不触碰；状态与 completed_at
    在**同一个 commit** 原子生效（spec 4.2.5）。

    Args:
        db: 数据库会话（依赖注入）。
        user_id: 当前用户 id。
        task_id: 任务 id。
        target: 目标状态（四枚举之一，非法枚举已在 schema 层 422）。

    Returns:
        dict: 流转后的 TaskOut 结构。

    Raises:
        BizException: code=1005 / HTTP 404（不存在或越权）；
            code=1007 / HTTP 400（非法流转）。
    """
    task = _get_task_or_404(db, user_id, task_id)
    if target not in TRANSITIONS.get(task.status, frozenset()):
        logger.warning(
            "task_id=%s 非法流转: %s -> %s",
            task_id,
            task.status.value,
            target.value,
        )
        raise BizException(
            CODE_BIZ_CONFLICT,
            f"任务状态不能从 {STATUS_LABELS[task.status]}"
            f" 直接变更为 {STATUS_LABELS[target]}",
            http_status=400,
        )
    task.status = target
    if target is TaskStatus.DONE and task.completed_at is None:
        task.completed_at = utc_now()
    db.commit()
    db.refresh(task)
    return _serialize_task(task)


# ---------------------------------------------------------------------------
# 看板分列
# ---------------------------------------------------------------------------
def get_board(db: Session, user_id: int) -> dict:
    """看板数据：单条查询全量拉取 + 按状态分桶（MVP 取舍，裁定⑪⑫）。

    看板全量返回（不分页不接筛选）为 MVP 取舍，数据规模增大后需改为
    按状态分页或虚拟滚动（spec 5.4.1 已注明）。列内排序：优先级降序
    （case 权重，规避 VARCHAR 字典序陷阱）→ 截止时间升序（未设置排
    最后）→ id 降序（同前两者时新建在前）。

    Args:
        db: 数据库会话（依赖注入）。
        user_id: 当前用户 id。

    Returns:
        dict: 固定四键 ``{todo, in_progress, done, review}``（键序 =
        状态机流转序），各值为 TaskOut 数组。
    """
    stmt = (
        select(Task)
        .where(Task.user_id == user_id)
        .order_by(
            PRIORITY_WEIGHT.asc(),
            Task.deadline.asc().nulls_last(),
            Task.id.desc(),
        )
    )
    board: dict[str, list[dict]] = {s.value: [] for s in TaskStatus}
    for task in db.scalars(stmt):
        board[task.status.value].append(_serialize_task(task))
    return board


# ---------------------------------------------------------------------------
# 统计聚合
# ---------------------------------------------------------------------------
def get_stats(db: Session, user_id: int) -> dict:
    """任务统计：总数 / 各状态数 / 逾期数 / 本周完成率 / 今日待办。

    时间口径（spec 6.3）：「本周」「今天」按北京时间自然周（周一起）/
    自然日计算，先求北京边界再转 UTC 查库（裁定㉒）；一次请求返回
    全部口径，禁止前端拼装（spec 5.5.1 规则 6）。完成率分子含 done
    与 review（裁定②）；分母 0 时取 0。

    Args:
        db: 数据库会话（依赖注入）。
        user_id: 当前用户 id。

    Returns:
        dict: TaskStatsOut 结构（status_counts 固定四键补零）。
    """
    now = utc_now()
    today_bj, today_start, today_end = _today_bounds_utc(now)
    week_start, week_end = _week_bounds_utc(now)

    rows = db.execute(
        select(Task.status, func.count())
        .where(Task.user_id == user_id)
        .group_by(Task.status)
    ).all()
    status_counts: dict[str, int] = {s.value: 0 for s in TaskStatus}
    for status, cnt in rows:
        status_counts[status.value] = cnt
    total = sum(status_counts.values())

    overdue_count = (
        db.scalar(
            select(func.count())
            .select_from(Task)
            .where(
                Task.user_id == user_id,
                Task.deadline.is_not(None),
                Task.deadline < now,
                Task.status.in_([TaskStatus.TODO, TaskStatus.IN_PROGRESS]),
            )
        )
        or 0
    )

    weekly_done = db.scalar(
        select(func.count())
        .select_from(Task)
        .where(
            Task.user_id == user_id,
            Task.status.in_([TaskStatus.DONE, TaskStatus.REVIEW]),
            Task.completed_at.is_not(None),
            Task.completed_at >= week_start,
            Task.completed_at < week_end,
        )
    )
    weekly_due = db.scalar(
        select(func.count())
        .select_from(Task)
        .where(
            Task.user_id == user_id,
            Task.deadline.is_not(None),
            Task.deadline >= week_start,
            Task.deadline < week_end,
        )
    )
    weekly_done_int = int(weekly_done or 0)
    weekly_due_int = int(weekly_due or 0)
    weekly_completion_rate: float = (
        round(weekly_done_int / weekly_due_int * 100, 1)
        if weekly_due_int
        else 0.0
    )

    today_todo_count = (
        db.scalar(
            select(func.count())
            .select_from(Task)
            .where(
                Task.user_id == user_id,
                Task.status.in_([TaskStatus.TODO, TaskStatus.IN_PROGRESS]),
                or_(
                    Task.scheduled_date == today_bj,
                    and_(
                        Task.deadline >= today_start,
                        Task.deadline < today_end,
                    ),
                ),
            )
        )
        or 0
    )

    return TaskStatsOut(
        total=total,
        status_counts=status_counts,
        overdue_count=int(overdue_count),
        weekly_completion_rate=weekly_completion_rate,
        today_todo_count=int(today_todo_count),
    ).model_dump(mode="json")