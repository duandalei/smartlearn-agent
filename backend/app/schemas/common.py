"""通用分页查询参数与分页响应模型（PROJECT_CONTEXT 5.3）。"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


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