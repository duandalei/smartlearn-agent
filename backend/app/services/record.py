"""学习记录业务编排（CRUD + 掌握度重放触发 + 任务时长回填 + 聚合查询）。

事务边界（design 2.1.3-C，spec 4.2.1）：三个写操作共用同一结构——
「校验 → 记录变更 + flush → 掌握度重放 → 任务回填 → 单次 commit」；
commit 权唯一收敛在本模块（mastery 重放与任务回填助手均**纯操作不
commit**），构造上保证「学习记录 / 掌握度 / 任务回填」三部分原子。
``autoflush=False``（db/session.py）下，重放查询要求读到变更后的
数据状态（新增记录的 id、修改后的新值、删除后不可见），变更与重放
之间必须显式 ``db.flush()``。

并发兜底（spec 5.6.3 场景 1 / design 2.1.3-A）：两条记录几乎同时
触达同一知识点时，``(user_id, knowledge_point)`` 唯一约束在 commit
处暴露冲突 → 整体回滚后按「已存在」语义重做一次（复用 goal.py 的
兜底模式）；重放为全量重放，串行执行后天然收敛。

P7 消费口径（交叉引用 ``services/mastery.py``）：``source=
'goal_breakdown'`` 且 ``mastery_score=0`` 的零分待学点是目标拆解的
正常产物，本模块的列表/统计接口不过滤；P7 Dashboard 薄弱点分析
消费时必须排除（PROJECT_CONTEXT §6.12）。

时区口径：统计与日期校验按北京时间自然日 / 自然周（周一起）计算，
``TZ_BEIJING`` 复用 ``services/task.py``（单向依赖，无环）。
"""

from __future__ import annotations

import json
from datetime import date, timedelta
from typing import Any

from sqlalchemy import ColumnElement, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.response import (
    CODE_NOT_FOUND,
    CODE_PARAM_INVALID,
    BizException,
)
from app.models.base import utc_now
from app.models.course import Course
from app.models.record import LearningRecord
from app.models.task import Task
from app.schemas.record import (
    RecordCreate,
    RecordOut,
    RecordStatsOut,
    RecordUpdate,
    TimelineItemOut,
    TimelineOut,
)
from app.services.mastery import replay_knowledge_points
from app.services.readonly import paginate
from app.services.task import TZ_BEIJING

# ---------------------------------------------------------------------------
# 私有助手
# ---------------------------------------------------------------------------
def _get_record_or_404(db: Session, user_id: int, record_id: int) -> LearningRecord:
    """按 id + 归属查询学习记录；不存在或越权统一抛 404（防 ID 枚举）。

    Args:
        db: 数据库会话。
        user_id: 当前用户 id。
        record_id: 记录 id。

    Returns:
        LearningRecord: 记录 ORM 对象。

    Raises:
        BizException: code=1005 / HTTP 404。
    """
    record = db.scalar(
        select(LearningRecord).where(
            LearningRecord.id == record_id,
            LearningRecord.user_id == user_id,
        )
    )
    if record is None:
        raise BizException(CODE_NOT_FOUND, "资源不存在", http_status=404)
    return record


def _validate_task_ref(db: Session, user_id: int, task_id: int) -> None:
    """校验 task_id 属本人且存在（引用他人或不存在统一 404）。

    Args:
        db: 数据库会话。
        user_id: 当前用户 id。
        task_id: 待校验的任务 id。

    Raises:
        BizException: code=1005 / HTTP 404，提示「关联的学习任务不存在」。
    """
    exists = db.scalar(
        select(Task.id).where(Task.id == task_id, Task.user_id == user_id)
    )
    if exists is None:
        raise BizException(
            CODE_NOT_FOUND, "关联的学习任务不存在", http_status=404
        )


def _validate_course_ref(db: Session, user_id: int, course_id: int) -> None:
    """校验 course_id 属本人且存在（引用他人或不存在统一 404）。

    Args:
        db: 数据库会话。
        user_id: 当前用户 id。
        course_id: 待校验的课程 id。

    Raises:
        BizException: code=1005 / HTTP 404，提示「关联的课程不存在」。
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


def _validate_study_date(study_date: date) -> None:
    """校验学习日期不晚于北京时间「今天」（允许补记历史日期）。

    Args:
        study_date: 待校验的学习日期。

    Raises:
        BizException: code=1001 / HTTP 422，提示「学习日期不能晚于今天」。
    """
    today_bj = utc_now().astimezone(TZ_BEIJING).date()
    if study_date > today_bj:
        raise BizException(
            CODE_PARAM_INVALID, "学习日期不能晚于今天", http_status=422
        )


def _serialize_record(record: LearningRecord) -> dict:
    """把记录 ORM 对象序列化为 RecordOut 结构的 JSON dict。

    knowledge_points 由 JSONListType 读出永为 list[str]，各层禁止
    再手动 json.loads / json.dumps（PROJECT_CONTEXT 8.1）。
    """
    return RecordOut.model_validate(record).model_dump(mode="json")


def _recalc_task_actual_minutes(
    db: Session, user_id: int, task_ids: set[int]
) -> None:
    """任务实际时长回填：逐任务 SUM 全量重算（纯操作不 commit）。

    口径（design 2.1.3-D / spec 5.7.1）：
    - **有记录**：``actual_minutes = SUM(duration_minutes)``（≥0 整数）；
    - **删空 / 全部解除关联**：置 **NULL**（表示「未知」，与手动未填
      同语义；**禁止写 0**——0 会被统计理解为「这个任务只花了 0
      分钟」）；删空后再被记录触达，SUM 有行自然恢复系统口径；
    - **未触达任务**：根本不在入参集合内，P5 手动维护的值保持不变；
    - **任务已被删除**：记录的 task_id 已被外键 ``ondelete="SET NULL"``
      置空（值为 None 不入集合），查询不到时跳过（双保险）；
    - **幂等**：SUM 是全量重算而非增量修正，修改时长 / 改挂任务 /
      删除均直接得到正确终值。

    Args:
        db: 数据库会话（纯操作，不 commit——事务归编排函数）。
        user_id: 当前用户 id。
        task_ids: 受影响任务 id 集合（去重；空集合直接返回）。

    Returns:
        None: 结果经调用方 commit 生效。
    """
    for task_id in sorted(task_ids):
        total, has_row = db.execute(
            select(
                func.sum(LearningRecord.duration_minutes),
                func.count(),
            ).where(
                LearningRecord.user_id == user_id,
                LearningRecord.task_id == task_id,
            )
        ).one()
        task = db.scalar(
            select(Task).where(
                Task.id == task_id, Task.user_id == user_id
            )
        )
        if task is None:
            continue
        task.actual_minutes = (
            int(total) if has_row and total is not None else None
        )


# ---------------------------------------------------------------------------
# CRUD（三部分同事务：记录写入 + 掌握度重放 + 任务回填）
# ---------------------------------------------------------------------------
def create_record(db: Session, user_id: int, data: RecordCreate) -> dict:
    """新建学习记录（同事务触发掌握度重放与任务时长回填）。

    Args:
        db: 数据库会话（依赖注入）。
        user_id: 当前用户 id。
        data: 创建入参。

    Returns:
        dict: RecordOut 结构（含 id / created_at）。

    Raises:
        BizException: code=1005 / HTTP 404（task_id / course_id 引用
            他人或不存在）；code=1001 / HTTP 422（学习日期超前）。
    """
    if data.task_id is not None:
        _validate_task_ref(db, user_id, data.task_id)
    if data.course_id is not None:
        _validate_course_ref(db, user_id, data.course_id)
    _validate_study_date(data.study_date)

    def _do() -> LearningRecord:
        """变更 + 重放 + 回填 + commit（并发冲突时整体重做一次）。"""
        record = LearningRecord(
            user_id=user_id,
            task_id=data.task_id,
            course_id=data.course_id,
            content=data.content,
            duration_minutes=data.duration_minutes,
            achievement=data.achievement,
            problems=data.problems,
            knowledge_points=data.knowledge_points,
            mastery_level=data.mastery_level,
            study_date=data.study_date,
        )
        db.add(record)
        # autoflush=False：重放按 (study_date, id) 排序需新记录 id。
        db.flush()
        affected_kps: set[str] = (
            set(data.knowledge_points)
            if data.mastery_level is not None
            else set()
        )
        replay_knowledge_points(db, user_id, affected_kps)
        _recalc_task_actual_minutes(
            db,
            user_id,
            {data.task_id} if data.task_id is not None else set(),
        )
        db.commit()
        return record

    try:
        record = _do()
    except IntegrityError:
        # (user_id, knowledge_point) 唯一约束并发冲突 → 整体回滚后按
        # 「已存在」语义重做（goal.py 兜底模式，spec 5.6.3 场景 1）。
        db.rollback()
        record = _do()
    db.refresh(record)
    return _serialize_record(record)


def update_record(
    db: Session, user_id: int, record_id: int, data: RecordUpdate
) -> dict:
    """编辑学习记录（exclude_unset 部分更新，显式 null 生效）。

    语义（spec 5.5.1 规则 1/6）：提交即生效（**含显式 null**），未提交
    保持原值——``mastery_level`` 置 null 表达「该记录退出掌握度聚合」、
    ``task_id`` 置 null 表达「解除任务关联」（前后任务都重算）。受影响
    知识点 = 前后并集（mastery_level 空值侧不纳入），受影响任务 =
    前后 task_id 并集（去 None）。

    Args:
        db: 数据库会话（依赖注入）。
        user_id: 当前用户 id。
        record_id: 记录 id。
        data: 更新入参（仅提交要修改的字段）。

    Returns:
        dict: 更新后的 RecordOut 结构。

    Raises:
        BizException: code=1005 / HTTP 404（记录不存在 / 越权 / 引用
            非法）；code=1001 / HTTP 422（必填字段显式 null、日期超前）。
    """
    updates: dict[str, Any] = data.model_dump(exclude_unset=True)
    for field, message in (
        ("content", "学习内容不能为空"),
        ("duration_minutes", "学习时长不能为空"),
        ("study_date", "学习日期不能为空"),
    ):
        if field in updates and updates[field] is None:
            raise BizException(CODE_PARAM_INVALID, message, http_status=422)
    if updates.get("task_id") is not None:
        _validate_task_ref(db, user_id, updates["task_id"])
    if updates.get("course_id") is not None:
        _validate_course_ref(db, user_id, updates["course_id"])
    if updates.get("study_date") is not None:
        _validate_study_date(updates["study_date"])

    def _do() -> LearningRecord:
        """变更 + 前后并集重放 + 回填 + commit（冲突时整体重做一次）。"""
        record = _get_record_or_404(db, user_id, record_id)
        old_kps = list(record.knowledge_points or [])
        old_mastery = record.mastery_level
        old_task_id = record.task_id
        for key, value in updates.items():
            setattr(record, key, value)
        db.flush()
        new_kps = list(record.knowledge_points or [])
        new_mastery = record.mastery_level
        new_task_id = record.task_id
        affected_kps: set[str] = set()
        if old_mastery is not None:
            affected_kps.update(old_kps)
        if new_mastery is not None:
            affected_kps.update(new_kps)
        affected_tasks = {
            t for t in (old_task_id, new_task_id) if t is not None
        }
        replay_knowledge_points(db, user_id, affected_kps)
        _recalc_task_actual_minutes(db, user_id, affected_tasks)
        db.commit()
        return record

    try:
        record = _do()
    except IntegrityError:
        db.rollback()
        record = _do()
    db.refresh(record)
    return _serialize_record(record)


def delete_record(db: Session, user_id: int, record_id: int) -> dict:
    """删除学习记录（同事务重放受影响知识点 + 重算受影响任务）。

    任务下最后一条记录被删除时，该任务 ``actual_minutes`` 置 NULL
    （表示「未知」，禁止写 0）；受影响知识点按剩余记录重放（记录
    删空的知识点回到 0 分）。

    Args:
        db: 数据库会话（依赖注入）。
        user_id: 当前用户 id。
        record_id: 记录 id。

    Returns:
        dict: 被删记录的 RecordOut 快照（P4/P5 惯例）。

    Raises:
        BizException: code=1005 / HTTP 404（不存在或越权）。
    """

    def _do() -> dict:
        """快照 → 删除 + flush → 重放 → 回填 → commit。"""
        record = _get_record_or_404(db, user_id, record_id)
        snapshot = _serialize_record(record)
        old_kps = list(record.knowledge_points or [])
        old_mastery = record.mastery_level
        old_task_id = record.task_id
        db.delete(record)
        db.flush()
        affected_kps: set[str] = (
            set(old_kps) if old_mastery is not None else set()
        )
        affected_tasks = (
            {old_task_id} if old_task_id is not None else set()
        )
        replay_knowledge_points(db, user_id, affected_kps)
        _recalc_task_actual_minutes(db, user_id, affected_tasks)
        db.commit()
        return snapshot

    try:
        return _do()
    except IntegrityError:
        db.rollback()
        return _do()


# ---------------------------------------------------------------------------
# 列表查询（分页 + 4 筛选）
# ---------------------------------------------------------------------------
def list_records(
    db: Session,
    user_id: int,
    *,
    page: int,
    page_size: int,
    start_date: date | None = None,
    end_date: date | None = None,
    course_id: int | None = None,
    knowledge_point: str | None = None,
) -> dict:
    """分页查询当前用户学习记录（study_date desc + id desc，既有口径）。

    筛选全部可选、AND 组合：``start_date`` / ``end_date`` 闭区间
    （study_date BETWEEN 含边界）、``course_id`` 精确匹配、
    ``knowledge_point`` JSON 引号边界匹配（平移 task 裁定⑩：在
    ``["Multi-Head Attention"]`` 中不误命中 ``"Attention"``；
    ``json.dumps`` 仅为构造带引号边界的匹配串，非字段序列化）。

    Args:
        db: 数据库会话（依赖注入）。
        user_id: 当前用户 id。
        page: 页码（从 1 开始）。
        page_size: 每页条数（1~100）。
        start_date: 学习日期下界（含）。
        end_date: 学习日期上界（含）。
        course_id: 课程 id 精确匹配。
        knowledge_point: 知识点精确匹配（JSON 数组元素级）。

    Returns:
        dict: ``{items, total, page, page_size}``。

    Raises:
        BizException: code=1001 / HTTP 422（start_date 晚于 end_date）。
    """
    if start_date is not None and end_date is not None:
        if start_date > end_date:
            raise BizException(
                CODE_PARAM_INVALID,
                "开始日期不能晚于结束日期",
                http_status=422,
            )
    filters: list[ColumnElement[bool]] = [
        LearningRecord.user_id == user_id
    ]
    if start_date is not None:
        filters.append(LearningRecord.study_date >= start_date)
    if end_date is not None:
        filters.append(LearningRecord.study_date <= end_date)
    if course_id is not None:
        filters.append(LearningRecord.course_id == course_id)
    if knowledge_point is not None:
        filters.append(
            func.instr(
                LearningRecord.knowledge_points,
                json.dumps(knowledge_point, ensure_ascii=False),
            )
            > 0
        )
    return paginate(
        db,
        LearningRecord,
        RecordOut,
        page=page,
        page_size=page_size,
        order_by=[
            LearningRecord.study_date.desc(),
            LearningRecord.id.desc(),
        ],
        filters=filters,
    )


# ---------------------------------------------------------------------------
# 聚合查询（timeline / stats）
# ---------------------------------------------------------------------------
def get_timeline(db: Session, user_id: int, days: int) -> dict:
    """按天聚合的学习时长序列（无记录的天补 0，验收③）。

    Args:
        db: 数据库会话（依赖注入）。
        user_id: 当前用户 id。
        days: 天数（1~365，路由层 Query 校验）。

    Returns:
        dict: TimelineOut 结构——恰 ``days`` 条、date 升序、首条为
        ``end_date − (days−1)``、末条为北京今天；无任何记录返回全 0
        序列不报错；同日多条记录（跨任务跨课程）合计。
    """
    end_date = utc_now().astimezone(TZ_BEIJING).date()
    start_date = end_date - timedelta(days=days - 1)
    rows = db.execute(
        select(
            LearningRecord.study_date,
            func.sum(LearningRecord.duration_minutes),
        )
        .where(
            LearningRecord.user_id == user_id,
            LearningRecord.study_date.between(start_date, end_date),
        )
        .group_by(LearningRecord.study_date)
    ).all()
    found: dict[date, int] = {d: int(m or 0) for d, m in rows}
    items: list[TimelineItemOut] = []
    current = start_date
    while current <= end_date:
        items.append(TimelineItemOut(date=current, minutes=found.get(current, 0)))
        current += timedelta(days=1)
    return TimelineOut(
        days=days,
        start_date=start_date,
        end_date=end_date,
        items=items,
    ).model_dump(mode="json")


def get_stats(db: Session, user_id: int) -> dict:
    """学习统计：本周学习时长 / 连续学习天数 / 记录条数。

    口径（design 2.1.3-E，北京时间）：
    - ``weekly_minutes``：北京本周一 ≤ study_date ≤ 北京今天的 SUM
      （study_date 为 Date 型直接比较，不做 UTC 换算）；
    - ``streak_days``：DISTINCT study_date 集合上，anchor 取今天
      （今天无记录则取昨天，不清零——学生早上打开页面不会看到连续
      天数被抹）向前逐日连续计数，无记录为 0；
    - ``total_count``：COUNT(*)。
    三个数值全部后端计算，前端零本地计算（spec 5.4.1 规则 4）。

    Args:
        db: 数据库会话（依赖注入）。
        user_id: 当前用户 id。

    Returns:
        dict: RecordStatsOut 结构。
    """
    today_bj = utc_now().astimezone(TZ_BEIJING).date()
    monday_bj = today_bj - timedelta(days=today_bj.weekday())

    weekly_minutes = db.scalar(
        select(func.sum(LearningRecord.duration_minutes)).where(
            LearningRecord.user_id == user_id,
            LearningRecord.study_date.between(monday_bj, today_bj),
        )
    )
    study_dates = set(
        db.scalars(
            select(LearningRecord.study_date)
            .where(LearningRecord.user_id == user_id)
            .distinct()
        )
    )
    anchor = today_bj if today_bj in study_dates else today_bj - timedelta(
        days=1
    )
    streak_days = 0
    while anchor in study_dates:
        streak_days += 1
        anchor -= timedelta(days=1)
    total_count = (
        db.scalar(
            select(func.count())
            .select_from(LearningRecord)
            .where(LearningRecord.user_id == user_id)
        )
        or 0
    )
    return RecordStatsOut(
        weekly_minutes=int(weekly_minutes or 0),
        streak_days=streak_days,
        total_count=int(total_count),
    ).model_dump(mode="json")