"""通用分页查询参数与分页响应模型（PROJECT_CONTEXT 5.3）。"""

from __future__ import annotations

from typing import Generic, TypeVar

from pydantic import BaseModel, ConfigDict, Field

ItemT = TypeVar("ItemT")


class PaginationParams(BaseModel):
    """列表端点通用分页查询参数。

    Attributes:
        page: 页码，从 1 开始，默认 1。
        page_size: 每页条数，1~100，默认 10。
    """

    model_config = ConfigDict(extra="forbid")

    page: int = Field(default=1, ge=1, description="页码，从 1 开始")
    page_size: int = Field(
        default=10, ge=1, le=100, description="每页条数，1~100"
    )


class PageData(BaseModel, Generic[ItemT]):
    """列表端点 ``data`` 固定结构：``{items, total, page, page_size}``。

    Attributes:
        items: 当前页数据列表。
        total: 满足条件的总记录数。
        page: 当前页码。
        page_size: 每页条数。
    """

    items: list[ItemT]
    total: int
    page: int
    page_size: int