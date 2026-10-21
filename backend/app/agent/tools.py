"""AI Agent 工具实现（P10）：8 个工具 + 横切校验设施。

职责与契约（design.md 2.1.2）：
- 统一签名协议：``(db: Session, user_id: int, arguments: dict) -> dict``，
  全 async（``search_knowledge`` 为 async 的事实决定 TOOL_MAP 类型单一）；
- user_id 由调用方（P11 执行器 / 测试脚本）注入，参数模型结构性不含
  user_id —— LLM 传入时 ``extra="forbid"`` 拒绝并输出注入特例文案；
- 一切数据访问经 services / analytics 既有函数（PROJECT_CONTEXT §4
  铁律：agent 层禁 SQL / 禁 ORM）；
- 成功返回结构化 dict（service 出参已是 ``model_dump(mode="json")``
  产物），一切失败返回 ``{"error": "<中文提示>"}`` 恰好单键、不抛
  异常——LLM 需要看到错误才能自我纠正（spec 5.2）。

本文件不含任何注册信息（TOOLS_SCHEMA / TOOL_MAP 属 registry.py）。
"""

from __future__ import annotations

import functools
import logging
from datetime import date, datetime, time, timedelta, timezone
from time import perf_counter
from typing import Any, Awaitable, Callable, Literal, TypeAlias

from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sqlalchemy.orm import Session

from app.analytics.statistics import get_overview
from app.analytics.trend import get_trend
from app.analytics.weakness import get_mastery_list
from app.core.response import CODE_PARAM_INVALID, BizException
from app.models.base import utc_now
from app.models.enums import Priority, TaskSource
from app.schemas.task import TaskCreate, TaskUpdate
from app.services.knowledge import search_knowledge
from app.services.profile import get_profile_by_user_id
from app.services.record import list_records
from app.services.task import (
    TZ_BEIJING,
    create_task as create_task_service,
    get_board,
    update_task as update_task_service,
)

logger = logging.getLogger(__name__)

#: 工具结果类型别名：成功业务结构或 ``{"error": str}``（键侧恒 str）。
ToolResult: TypeAlias = dict[str, Any]

#: 工具函数类型别名（派发契约，P11 执行器与测试脚本共用）。
ToolFunc: TypeAlias = Callable[[Session, int, dict[str, Any]], Awaitable[ToolResult]]

#: 慢日志阈值（毫秒，spec 锁定值，不做环境变量化）。
SLOW_TOOL_MS: int = 300

#: 工具主体类型别名：装饰器内部视角（收已校验的强类型 params）。
_ToolImpl: TypeAlias = Callable[..., Awaitable[ToolResult]]


# ---------------------------------------------------------------------------
# 横切私有区：ValidationError 中文转换器（8 工具共用）
# ---------------------------------------------------------------------------


def _field_bounds(
    params_model: type[BaseModel], field: str
) -> tuple[int | None, int | None]:
    """读取参数模型某字段的 ge / le 数值边界（单一事实来源）。

    Args:
        params_model: 工具参数模型。
        field: 字段名（顶层，不含嵌套路径）。

    Returns:
        tuple[int | None, int | None]: ``(ge, le)``，无约束时为
            ``(None, None)``。
    """
    info = params_model.model_fields.get(field)
    if info is None:
        return (None, None)
    ge: int | None = None
    le: int | None = None
    for meta in info.metadata:
        ge = getattr(meta, "ge", None) or ge
        le = getattr(meta, "le", None) or le
    return (ge, le)


def _field_str_bounds(
    params_model: type[BaseModel], field: str
) -> tuple[int | None, int | None]:
    """读取参数模型某字符串字段的 min_length / max_length 约束。

    Args:
        params_model: 工具参数模型。
        field: 字段名（顶层）。

    Returns:
        tuple[int | None, int | None]: ``(min_length, max_length)``，
            无约束时为 ``(None, None)``。
    """
    info = params_model.model_fields.get(field)
    if info is None:
        return (None, None)
    min_len: int | None = None
    max_len: int | None = None
    for meta in info.metadata:
        min_len = getattr(meta, "min_length", None) or min_len
        max_len = getattr(meta, "max_length", None) or max_len
    return (min_len, max_len)


def _validation_error_message(
    exc: ValidationError, tool_name: str, params_model: type[BaseModel]
) -> str:
    """把 Pydantic ValidationError 转为含参数名与合法值的中文提示。

    映射表见 design.md 2.2.2-9；字段列表从 ``params_model.model_fields``
    动态读取（与 schema properties / 白名单同源的单一事实来源）。

    Args:
        exc: ``model_validate`` 抛出的校验异常。
        tool_name: 工具名（错误文案中提示合法参数集）。
        params_model: 该工具的参数模型。

    Returns:
        str: 面向 LLM 的中文错误提示。
    """
    errors = exc.errors()
    if not errors:
        return f"{tool_name} 参数校验失败"
    err = errors[0]
    field = ".".join(str(loc) for loc in err.get("loc", ()))
    top = field.split(".")[0]
    etype = err.get("type", "")
    ctx: dict[str, Any] = err.get("ctx") or {}
    fields = list(params_model.model_fields)

    if etype == "extra_forbidden":
        if field == "user_id":
            return "user_id 由系统注入，禁止传入"
        if tool_name == "update_task" and field == "status":
            message = (
                "update_task 不支持字段 status；任务状态流转请由用户在"
                "任务页操作，本工具不支持修改 status"
            )
            if fields:
                message += f"；可更新字段为 {' / '.join(fields)}"
            return message
        if fields:
            return (
                f"{tool_name} 不接受参数 {field}；"
                f"该工具合法参数为 {' / '.join(fields)}"
            )
        return f"{tool_name} 不接受任何参数"

    if etype == "literal_error" or etype == "enum":
        expected = str(ctx.get("expected", "")).replace("'", "").replace(",", " /")
        return f"{field} 必须为 {expected.strip()} 之一"

    if etype in ("greater_than_equal", "less_than_equal", "int_parsing", "int_type"):
        ge, le = _field_bounds(params_model, top)
        if etype in ("greater_than_equal", "less_than_equal"):
            ge = ctx.get("ge", ge)
            le = ctx.get("le", le)
        if ge is not None and le is not None:
            return f"{field} 必须为 {ge}–{le} 的整数"
        if ge is not None:
            if ge == 1:
                return f"{field} 必须为正整数"
            return f"{field} 必须为 ≥{ge} 的整数"
        if le is not None:
            return f"{field} 必须为 ≤{le} 的整数"
        return f"{field} 必须为整数"

    if etype in ("string_too_short", "string_too_long"):
        if top == "topic":
            return f"{field} 必须为非空字符串；如需全量列表请省略该参数"
        min_len = ctx.get("min_length")
        max_len = ctx.get("max_length")
        meta_min, meta_max = _field_str_bounds(params_model, top)
        if min_len is None:
            min_len = meta_min
        if max_len is None:
            max_len = meta_max
        return f"{field} 必填且长度 {min_len}–{max_len} 字符"

    if etype == "string_type":
        if top == "topic":
            return f"{field} 必须为非空字符串；如需全量列表请省略该参数"
        return f"{field} 必须为非空字符串"

    if etype == "too_long":
        max_len = ctx.get("max_length")
        if isinstance(err.get("input"), list):
            return f"{field} 最多 {max_len} 个"
        return f"{field} 必填且长度不超过 {max_len} 字符"

    if etype == "value_error":
        message = str(err.get("msg", ""))
        prefix = "Value error, "
        if message.startswith(prefix):
            message = message[len(prefix) :]
        return message

    if etype == "missing":
        return f"{field} 为必填参数"

    return f"参数 {field} 校验失败"


# ---------------------------------------------------------------------------
# 横切私有区：ISO 日期时间解析助手（全文件仅有的两处时区裁定集中点）
# ---------------------------------------------------------------------------


def _parse_cutoff(value: str, field: str) -> datetime:
    """解析 LLM 传入的截止时刻字符串（due_before / deadline 输入侧）。

    口径（design.md 2.2.2-3）：纯日期形式（``2026-10-21``）→ 北京该
    自然日结束时刻（次日 00:00 北京时间）；naive datetime → 视为北京
    时间；带时区（``Z`` / ``+08:00``）→ 原样；统一转 aware UTC。

    Args:
        value: ISO 8601 日期或日期时间字符串。
        field: 字段名（错误文案用）。

    Returns:
        datetime: aware UTC 时刻。

    Raises:
        BizException: code=1001 / HTTP 422，解析失败时抛出（消息含
            格式示例，交由装饰器转 error 信封）。
    """
    try:
        pure_date = date.fromisoformat(value)
        return (
            datetime.combine(
                pure_date + timedelta(days=1), time.min, tzinfo=TZ_BEIJING
            )
            .astimezone(timezone.utc)
        )
    except (TypeError, ValueError):
        pass
    try:
        parsed = datetime.fromisoformat(value)
    except (TypeError, ValueError):
        raise BizException(
            CODE_PARAM_INVALID,
            f"{field} 必须为 ISO 8601 格式，如 2026-10-21 或 2026-10-21T23:59:59",
            http_status=422,
        ) from None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=TZ_BEIJING).astimezone(timezone.utc)
    return parsed.astimezone(timezone.utc)


def _parse_deadline(value: str) -> datetime:
    """解析 TaskOut 读出的 deadline 字符串为 aware UTC（读出侧）。

    库内 UTC 存储口径：naive（无时区后缀）→ 视为 UTC；aware → 原样
    转 UTC。统一 aware 参与比较，规避 naive vs aware 比较异常与 ISO
    字符串字典序错序。

    Args:
        value: TaskOut 序列化的 deadline ISO 字符串。

    Returns:
        datetime: aware UTC 时刻。
    """
    parsed = datetime.fromisoformat(str(value))
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _parse_scheduled_date(value: str) -> date:
    """解析计划执行日期（ISO 日期形式）。

    Args:
        value: ISO 日期字符串（如 ``2026-10-21``）。

    Returns:
        date: 解析后的日期。

    Raises:
        BizException: code=1001 / HTTP 422，解析失败时抛出（消息含
            格式示例）。
    """
    try:
        return date.fromisoformat(value)
    except (TypeError, ValueError):
        raise BizException(
            CODE_PARAM_INVALID,
            "scheduled_date 必须为 ISO 日期格式，如 2026-10-21",
            http_status=422,
        ) from None


# ---------------------------------------------------------------------------
# 横切私有区：BizException 文案改写助手（防 ID 枚举的合并表述）
# ---------------------------------------------------------------------------

#: 任务类 1005 message → 合并表述（「不存在」与「不属于本人」不可区分）。
_REWRITE_RULES: dict[str, str] = {
    "关联的学习目标不存在": "关联的学习目标不存在或不属于当前用户",
    "关联的课程不存在": "关联的课程不存在或不属于当前用户",
    "资源不存在": "任务不存在或不属于当前用户，请先调用 get_tasks 获取有效任务 id",
}


def _rewrite_task_biz_error(exc: BizException) -> BizException:
    """把任务服务 1005 类 message 改写为合并表述后重抛。

    Args:
        exc: service 层抛出的业务异常。

    Returns:
        BizException: message 改写后的新异常（未命中规则时原样返回）。
    """
    rewritten = _REWRITE_RULES.get(exc.message)
    if rewritten is None:
        return exc
    return BizException(exc.code, rewritten, http_status=exc.http_status)


# ---------------------------------------------------------------------------
# 横切私有区：tool_endpoint 装饰器（校验 → 执行 → 异常转信封 → 慢日志）
# ---------------------------------------------------------------------------


def tool_endpoint(
    name: str, params_model: type[BaseModel]
) -> Callable[[_ToolImpl], ToolFunc]:
    """工具横切装饰器工厂（design.md 2.1.3-A 状态机的唯一实现）。

    对外暴露 ToolFunc 签名 ``(db, user_id, arguments)``，内部顺序：
    arguments dict 防御 → 计时 → ``params_model.model_validate`` →
    调用工具主体（收强类型 params）→ 三类异常捕获转 error 信封 →
    finally 慢日志（``elapsed_ms > 300`` 时 warning，三字段固定、
    不打参数与业务数据——日志脱敏红线）。

    Args:
        name: 工具名（日志与错误文案标识）。
        params_model: 该工具的参数模型（白名单单一事实来源）。

    Returns:
        Callable[[_ToolImpl], ToolFunc]: 装饰器。
    """

    def decorator(impl: _ToolImpl) -> ToolFunc:
        @functools.wraps(impl)
        async def wrapper(
            db: Session, user_id: int, arguments: dict[str, Any]
        ) -> ToolResult:
            if not isinstance(arguments, dict):
                return {"error": "参数格式错误，请重新生成合法的 JSON 参数"}
            start = perf_counter()
            try:
                params = params_model.model_validate(arguments)
                return await impl(db, user_id, params)
            except ValidationError as exc:
                return {
                    "error": _validation_error_message(exc, name, params_model)
                }
            except BizException as exc:
                return {"error": exc.message}
            except Exception as exc:  # noqa: BLE001 - 不抛异常红线
                logger.error(
                    "agent_tool_error tool_name=%s user_id=%s type=%s summary=%s",
                    name,
                    user_id,
                    type(exc).__name__,
                    str(exc)[:200],
                )
                return {"error": "工具执行失败，请稍后重试"}
            finally:
                elapsed_ms = int((perf_counter() - start) * 1000)
                if elapsed_ms > SLOW_TOOL_MS:
                    logger.warning(
                        "agent_tool_slow tool_name=%s user_id=%s elapsed_ms=%d",
                        name,
                        user_id,
                        elapsed_ms,
                    )

        return wrapper

    return decorator


# ---------------------------------------------------------------------------
# 参数模型（extra="forbid" 白名单；Field description 进 schema 供 LLM 阅读）
# ---------------------------------------------------------------------------


class GetUserProfileParams(BaseModel):
    """get_user_profile 参数模型（零字段，白名单为空集）。"""

    model_config = ConfigDict(extra="forbid")


class GetLearningRecordsParams(BaseModel):
    """get_learning_records 参数模型。"""

    model_config = ConfigDict(extra="forbid")

    days: int = Field(
        default=7,
        ge=1,
        le=365,
        description="查询最近 N 天（自然日，含今天）",
    )
    course_id: int | None = Field(
        default=None,
        ge=1,
        description="课程 id 过滤（可选，只看某门课程的记录）",
    )


class GetTasksParams(BaseModel):
    """get_tasks 参数模型。"""

    model_config = ConfigDict(extra="forbid")

    status: Literal["todo", "in_progress", "done", "review"] | None = Field(
        default=None,
        description="状态过滤（可选：todo 待办 / in_progress 进行中 / done 已完成 / review 待复盘，缺省为全部状态）",
    )
    due_before: str | None = Field(
        default=None,
        description="截止时刻上界（可选，ISO 8601 日期或日期时间，如 2026-10-21 或 2026-10-21T23:59:59；指定后没有截止时间的任务不会返回）",
    )


class GetKnowledgeMasteryParams(BaseModel):
    """get_knowledge_mastery 参数模型。"""

    model_config = ConfigDict(extra="forbid")

    topic: str | None = Field(
        default=None,
        min_length=1,
        description="知识点名称（可选，精确匹配；省略返回全部知识点）",
    )


class GetLearningStatisticsParams(BaseModel):
    """get_learning_statistics 参数模型。"""

    model_config = ConfigDict(extra="forbid")

    days: int = Field(
        default=7,
        ge=1,
        le=365,
        description="趋势窗口天数（可选，1–365，默认 7）",
    )


class SearchKnowledgeBaseParams(BaseModel):
    """search_knowledge_base 参数模型。"""

    model_config = ConfigDict(extra="forbid")

    query: str = Field(
        min_length=1,
        max_length=500,
        description="检索问题文本（必填，自然语言描述要查的内容）",
    )
    top_k: int = Field(
        default=5,
        ge=1,
        le=20,
        description="期望返回条数（可选，1–20，默认 5）",
    )
    scope: Literal["personal", "public", "all"] = Field(
        default="all",
        description="检索范围（可选：personal 仅个人库 / public 仅公共库 / all 两者合并，默认 all）",
    )


class CreateTaskParams(BaseModel):
    """create_task 参数模型（8 字段，与 spec 5.9.1 白名单一一对应）。

    不含 status / source / user_id / actual_minutes / completed_at /
    scheduled_date（extra="forbid" 即白名单拒绝；source 由工具层固定
    传入，LLM 不得伪造来源）。
    """

    model_config = ConfigDict(extra="forbid")

    title: str = Field(
        min_length=1, max_length=200, description="任务名称（必填，1–200 字符）"
    )
    description: str | None = Field(
        default=None, description="任务描述（可选）"
    )
    goal_id: int | None = Field(
        default=None, ge=1, description="关联学习目标 id（可选，须属本人）"
    )
    course_id: int | None = Field(
        default=None, ge=1, description="关联课程 id（可选，须属本人）"
    )
    knowledge_points: list[str] = Field(
        default=[],
        max_length=20,
        description="知识点标签（可选字符串数组，最多 20 个）",
    )
    priority: Literal["low", "medium", "high"] = Field(
        default="medium",
        description="优先级（可选：low / medium / high，默认 medium）",
    )
    estimated_minutes: int | None = Field(
        default=None, ge=1, description="预计耗时分钟（可选整数 ≥1）"
    )
    deadline: str | None = Field(
        default=None,
        description="截止时间（可选，ISO 8601 格式，如 2026-10-21T23:59:59）",
    )


class UpdateTaskParams(BaseModel):
    """update_task 参数模型（task_id + 10 个可更新字段）。

    不含 status / source / user_id / completed_at / created_at（裁定②：
    状态流转唯一合法通道是任务页状态接口；Agent 变更状态须走
    transition_task_status，本阶段不提供该能力，留待 P12）。
    """

    model_config = ConfigDict(extra="forbid")

    task_id: int = Field(ge=1, description="目标任务 id（必填正整数）")
    title: str | None = Field(
        default=None, min_length=1, max_length=200, description="任务名称"
    )
    description: str | None = Field(default=None, description="任务描述")
    goal_id: int | None = Field(
        default=None, ge=1, description="关联学习目标 id（须属本人）"
    )
    course_id: int | None = Field(
        default=None, ge=1, description="关联课程 id（须属本人）"
    )
    knowledge_points: list[str] | None = Field(
        default=None, max_length=20, description="知识点标签（≤20 个）"
    )
    priority: Literal["low", "medium", "high"] | None = Field(
        default=None, description="优先级（low / medium / high）"
    )
    estimated_minutes: int | None = Field(
        default=None, ge=1, description="预计耗时分钟（≥1）"
    )
    actual_minutes: int | None = Field(
        default=None, ge=0, description="实际耗时分钟（≥0）"
    )
    deadline: str | None = Field(
        default=None, description="截止时间（ISO 8601 格式）"
    )
    scheduled_date: str | None = Field(
        default=None, description="计划执行日期（ISO 日期格式，如 2026-10-21）"
    )


# ---------------------------------------------------------------------------
# 只读工具
# ---------------------------------------------------------------------------


@tool_endpoint("get_user_profile", GetUserProfileParams)
async def get_user_profile(
    db: Session, user_id: int, params: GetUserProfileParams
) -> ToolResult:
    """获取当前用户的学习画像基础信息（经 services 层薄封装）。"""
    return get_profile_by_user_id(db, user_id)


@tool_endpoint("get_learning_records", GetLearningRecordsParams)
async def get_learning_records(
    db: Session, user_id: int, params: GetLearningRecordsParams
) -> ToolResult:
    """查询当前用户近 N 天学习记录明细（复用 list_records）。"""
    end_date = utc_now().astimezone(TZ_BEIJING).date()
    start_date = end_date - timedelta(days=params.days - 1)
    data = list_records(
        db,
        user_id,
        page=1,
        page_size=100,
        start_date=start_date,
        end_date=end_date,
        course_id=params.course_id,
    )
    return {
        "days": params.days,
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
        "records": data["items"],
        "total": data["total"],
    }


@tool_endpoint("get_tasks", GetTasksParams)
async def get_tasks(
    db: Session, user_id: int, params: GetTasksParams
) -> ToolResult:
    """查询当前用户任务列表（get_board 全量摊平 + 内存过滤 / 排序 / 截断）。"""
    board = get_board(db, user_id)
    tasks: list[dict[str, Any]] = [
        task for bucket in board.values() for task in bucket
    ]
    if params.status is not None:
        tasks = [t for t in tasks if t["status"] == params.status]
    if params.due_before is not None:
        cutoff = _parse_cutoff(params.due_before, "due_before")
        # 裁定③：due_before 过滤排除无截止任务。
        tasks = [
            t
            for t in tasks
            if t["deadline"] is not None and _parse_deadline(t["deadline"]) < cutoff
        ]
    epoch = datetime.min.replace(tzinfo=timezone.utc)
    tasks.sort(
        key=lambda t: (
            t["deadline"] is None,
            _parse_deadline(t["deadline"]) if t["deadline"] is not None else epoch,
            -t["id"],
        )
    )
    return {"tasks": tasks[:100], "total": len(tasks)}


@tool_endpoint("get_knowledge_mastery", GetKnowledgeMasteryParams)
async def get_knowledge_mastery(
    db: Session, user_id: int, params: GetKnowledgeMasteryParams
) -> ToolResult:
    """查询当前用户知识点掌握度列表（复用 get_mastery_list 升序口径）。"""
    data = get_mastery_list(db, user_id)
    items: list[dict[str, Any]] = data["items"]
    if params.topic is not None:
        items = [it for it in items if it["knowledge_point"] == params.topic]
    return {"items": items, "total": len(items)}


@tool_endpoint("get_learning_statistics", GetLearningStatisticsParams)
async def get_learning_statistics(
    db: Session, user_id: int, params: GetLearningStatisticsParams
) -> ToolResult:
    """获取学习统计总览（七指标全量累计）与近 N 天趋势（双层口径）。"""
    overview = get_overview(db, user_id)
    trend = get_trend(db, user_id, params.days)
    return {**overview, "trend": trend}


@tool_endpoint("search_knowledge_base", SearchKnowledgeBaseParams)
async def search_knowledge_base(
    db: Session, user_id: int, params: SearchKnowledgeBaseParams
) -> ToolResult:
    """在个人 / 公共知识库中语义检索（P9 search_knowledge 直传直返）。"""
    return await search_knowledge(
        db, user_id, params.query, params.top_k, params.scope
    )


# ---------------------------------------------------------------------------
# 写工具
# ---------------------------------------------------------------------------


@tool_endpoint("create_task", CreateTaskParams)
async def create_task(
    db: Session, user_id: int, params: CreateTaskParams
) -> ToolResult:
    """为当前用户创建学习任务（source 由工具层固定为 agent，裁定①）。"""
    deadline = (
        _parse_cutoff(params.deadline, "deadline")
        if params.deadline is not None
        else None
    )
    task_data = TaskCreate(
        title=params.title,
        description=params.description,
        goal_id=params.goal_id,
        course_id=params.course_id,
        knowledge_points=params.knowledge_points,
        priority=Priority(params.priority),
        estimated_minutes=params.estimated_minutes,
        deadline=deadline,
    )
    try:
        return create_task_service(db, user_id, task_data, source=TaskSource.AGENT)
    except BizException as exc:
        raise _rewrite_task_biz_error(exc) from None


@tool_endpoint("update_task", UpdateTaskParams)
async def update_task(
    db: Session, user_id: int, params: UpdateTaskParams
) -> ToolResult:
    """修改当前用户已有学习任务（status 排除 + 空更新拒绝 + null 不清空）。"""
    provided = {k for k in params.model_fields_set if k != "task_id"}
    if not provided:
        return {"error": "除 task_id 外请至少提供一个待更新字段"}
    payload: dict[str, Any] = {}
    for key in provided:
        value = getattr(params, key)
        if key == "deadline" and value is not None:
            payload[key] = _parse_cutoff(value, "deadline")
        elif key == "scheduled_date" and value is not None:
            payload[key] = _parse_scheduled_date(value)
        else:
            payload[key] = value
    data = TaskUpdate(**payload)
    try:
        return update_task_service(db, user_id, params.task_id, data)
    except BizException as exc:
        raise _rewrite_task_biz_error(exc) from None