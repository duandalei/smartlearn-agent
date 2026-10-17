"""健康检查接口。

按 PROJECT_CONTEXT 5.1，健康检查**不带** ``/api/v1`` 前缀，路径固定为
``GET /health``。返回统一响应体，用于探活与联调自检。
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from app.core.response import success

router: APIRouter = APIRouter(tags=["health"])


@router.get("/health", summary="健康检查")
def health_check() -> dict[str, Any]:
    """返回服务健康状态。

    用于容器探活、前端联调自检以及部署验证。

    Returns:
        dict: 统一响应体，``data`` 为 ``{"status": "healthy"}``。

    Example:
        >>> # GET /health
        >>> {"code": 0, "message": "ok", "data": {"status": "healthy"}}
    """
    return success(data={"status": "healthy"}, message="ok")