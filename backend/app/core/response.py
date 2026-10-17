"""统一响应体与全局异常处理。

PROJECT_CONTEXT 5.2 规定：所有接口（含错误）必须返回统一结构::

    {"code": 0, "message": "success", "data": {}}

本模块提供：
1. ``BizException``：业务异常，携带业务码与 HTTP 状态码；``code`` 取值见
   PROJECT_CONTEXT 5.4 错误码表。
2. ``success`` / ``error``：构造统一响应体的工具函数。
3. ``register_exception_handlers``：把 HTTPException、Pydantic 校验错误、
   自定义业务异常与未捕获异常统一转换为统一响应体，保证不出现裸结构。
"""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

# ---------------------------------------------------------------------------
# 业务错误码（PROJECT_CONTEXT 5.4）
# ---------------------------------------------------------------------------
CODE_SUCCESS: int = 0
CODE_PARAM_INVALID: int = 1001          # 参数校验失败 -> 422
CODE_AUTH_FAILED: int = 1002            # 用户名或密码错误 -> 401
CODE_TOKEN_INVALID: int = 1003          # Token 无效或已过期 -> 401
CODE_FORBIDDEN: int = 1004              # 无权限访问该资源 -> 403
CODE_NOT_FOUND: int = 1005              # 资源不存在 -> 404
CODE_ALREADY_EXISTS: int = 1006         # 资源已存在（唯一冲突） -> 409
CODE_BIZ_CONFLICT: int = 1007           # 业务规则冲突 -> 400
CODE_FILE_TYPE_UNSUPPORTED: int = 2000  # 文件类型不支持 -> 400
CODE_DOC_PARSE_FAILED: int = 2001       # 文档解析失败 -> 500
CODE_LLM_FAILED: int = 3000             # LLM 调用失败 -> 502
CODE_VECTOR_FAILED: int = 3001          # 向量库/检索失败 -> 500
CODE_INTERNAL_ERROR: int = 5000         # 服务器内部错误 -> 500

# HTTP 状态码 <-> 业务码 默认映射，供 HTTPException 兜底转换使用。
_HTTP_STATUS_TO_CODE: dict[int, int] = {
    status.HTTP_400_BAD_REQUEST: CODE_BIZ_CONFLICT,
    status.HTTP_401_UNAUTHORIZED: CODE_TOKEN_INVALID,
    status.HTTP_403_FORBIDDEN: CODE_FORBIDDEN,
    status.HTTP_404_NOT_FOUND: CODE_NOT_FOUND,
    status.HTTP_409_CONFLICT: CODE_ALREADY_EXISTS,
    status.HTTP_422_UNPROCESSABLE_ENTITY: CODE_PARAM_INVALID,
    status.HTTP_500_INTERNAL_SERVER_ERROR: CODE_INTERNAL_ERROR,
    status.HTTP_502_BAD_GATEWAY: CODE_LLM_FAILED,
}


class BizException(Exception):
    """业务异常。

    业务层（services）抛出本异常，由全局异常处理器统一转换为响应体。

    Attributes:
        code: 业务状态码（非 0），取值见 PROJECT_CONTEXT 5.4。
        message: 面向用户的错误提示。
        http_status: 对应的 HTTP 状态码。
        data: 附加数据，通常为 None。

    Example:
        >>> raise BizException(CODE_NOT_FOUND, "目标不存在")
    """

    def __init__(
        self,
        code: int,
        message: str,
        http_status: int = status.HTTP_400_BAD_REQUEST,
        data: Any = None,
    ) -> None:
        """初始化业务异常。

        Args:
            code: 业务状态码。
            message: 错误提示。
            http_status: 对应 HTTP 状态码，默认 400。
            data: 附加数据。
        """
        super().__init__(message)
        self.code: int = code
        self.message: str = message
        self.http_status: int = http_status
        self.data: Any = data


def success(data: Any = None, message: str = "success") -> dict[str, Any]:
    """构造成功响应体。

    Args:
        data: 业务数据，无数据时为 None。
        message: 成功提示，默认 "success"。

    Returns:
        dict: ``{"code": 0, "message": message, "data": data}``。
    """
    return {"code": CODE_SUCCESS, "message": message, "data": data}


def error(
    code: int,
    message: str,
    data: Any = None,
) -> dict[str, Any]:
    """构造失败响应体。

    Args:
        code: 非 0 业务状态码。
        message: 错误提示。
        data: 附加数据。

    Returns:
        dict: ``{"code": code, "message": message, "data": data}``。
    """
    return {"code": code, "message": message, "data": data}


def register_exception_handlers(app: FastAPI) -> None:
    """为 FastAPI 应用注册全局异常处理器。

    统一拦截以下异常并按 ``{code, message, data}`` 结构返回：
    1. ``BizException``：业务异常，按自带 code / http_status 返回。
    2. ``RequestValidationError``：Pydantic 入参校验失败 -> 1001 / 422。
    3. ``StarletteHTTPException``：框架抛出的 HTTP 异常（如 404）。
    4. ``Exception``：兜底未捕获异常 -> 5000 / 500。

    Args:
        app: FastAPI 应用实例。

    Returns:
        None
    """

    @app.exception_handler(BizException)
    async def _handle_biz_exception(
        request: Request, exc: BizException
    ) -> JSONResponse:
        """处理业务异常。"""
        return JSONResponse(
            status_code=exc.http_status,
            content=error(exc.code, exc.message, exc.data),
        )

    @app.exception_handler(RequestValidationError)
    async def _handle_validation_error(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        """处理 Pydantic 入参校验失败。"""
        # 汇总首个错误信息，保证提示可读。
        errors = exc.errors()
        if errors:
            first = errors[0]
            loc = ".".join(str(part) for part in first.get("loc", []))
            detail = first.get("msg", "参数校验失败")
            message = f"参数校验失败: {loc} {detail}".strip()
        else:
            message = "参数校验失败"
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content=error(CODE_PARAM_INVALID, message, errors),
        )

    @app.exception_handler(StarletteHTTPException)
    async def _handle_http_exception(
        request: Request, exc: StarletteHTTPException
    ) -> JSONResponse:
        """处理框架 HTTPException（如路由 404、方法 405）。"""
        code = _HTTP_STATUS_TO_CODE.get(exc.status_code, CODE_INTERNAL_ERROR)
        return JSONResponse(
            status_code=exc.status_code,
            content=error(code, str(exc.detail)),
        )

    @app.exception_handler(Exception)
    async def _handle_unexpected_exception(
        request: Request, exc: Exception
    ) -> JSONResponse:
        """兜底处理未捕获异常，避免返回裸 500。"""
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=error(CODE_INTERNAL_ERROR, f"服务器内部错误: {exc}"),
        )