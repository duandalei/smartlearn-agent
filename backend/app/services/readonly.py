"""泛型只读查询助手。

30 个只读端点的查询逻辑完全同构（COUNT + 排序 + LIMIT/OFFSET +
Pydantic 序列化 + 404 语义），本模块以 TypeVar 参数化「ORM 模型 +
出参模型」一处实现，消灭 30 份样板。

分层契约（PROJECT_CONTEXT 第 4 章）：路由层经本助手访问 ORM，
保持 ``api → services → models`` 单向依赖；本模块只做通用查询
编排，禁止业务规则。
"""

from __future__ import annotations

from typing import Any, Sequence, TypeVar

from pydantic import BaseModel
from sqlalchemy import ColumnElement, func, inspect, select
from sqlalchemy.orm import DeclarativeBase, Session

from app.core.response import CODE_NOT_FOUND, BizException

ModelT = TypeVar("ModelT", bound=DeclarativeBase)
SchemaT = TypeVar("SchemaT", bound=BaseModel)


def paginate(
    db: Session,
    model: type[ModelT],
    schema_class: type[SchemaT],
    *,
    page: int,
    page_size: int,
    order_by: Sequence[ColumnElement[Any]] | None = None,
) -> dict[str, Any]:
    """分页查询并序列化为 ``{items, total, page, page_size}``。

    Args:
        db: SQLAlchemy 会话。
        model: ORM 模型类。
        schema_class: Pydantic 出参模型类（须配置 from_attributes）。
        page: 页码（从 1 开始，调用前已由 PaginationParams 校验）。
        page_size: 每页条数（1~100）。
        order_by: 排序列序列；None 时按主键 id 升序。

    Returns:
        dict[str, Any]: 分页响应 data 结构，可直接被 JSON 化。
    """
    total: int = db.scalar(select(func.count()).select_from(model)) or 0

    stmt = select(model)
    if order_by:
        stmt = stmt.order_by(*order_by)
    else:
        pk = inspect(model).primary_key[0]
        stmt = stmt.order_by(pk.asc())
    stmt = stmt.offset((page - 1) * page_size).limit(page_size)

    rows = db.scalars(stmt).all()
    items = [
        schema_class.model_validate(row).model_dump(mode="json") for row in rows
    ]
    return {"items": items, "total": total, "page": page, "page_size": page_size}


def get_by_id_or_404(
    db: Session,
    model: type[ModelT],
    obj_id: int,
    schema_class: type[SchemaT],
) -> dict[str, Any]:
    """按主键查询单条记录并序列化；不存在时抛 404 业务异常。

    Args:
        db: SQLAlchemy 会话。
        model: ORM 模型类。
        obj_id: 主键 id。
        schema_class: Pydantic 出参模型类。

    Returns:
        dict[str, Any]: 出参模型的 JSON dict。

    Raises:
        BizException: code=1005 / HTTP 404，资源不存在时抛出。
    """
    obj = db.get(model, obj_id)
    if obj is None:
        raise BizException(
            CODE_NOT_FOUND,
            "资源不存在",
            http_status=404,
        )
    return schema_class.model_validate(obj).model_dump(mode="json")