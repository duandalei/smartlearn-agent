"""AI 学习问答路由（SSE 流式问答 + 历史分页）。

职责（design.md 2.2.1 / 2.2.2 / 决策 D2）：鉴权注入、请求体解析、
SSE 文本格式化（``data: {JSON}\\n\\n``）与 StreamingResponse 头部、
历史端点 ``success()`` 包装——路由层零业务逻辑；**SSE 格式化必须在
api 层**（契约 §4：services 禁止拼接 HTTP 响应）。

与统一响应体铁律的协调（裁决 #10，「以流是否开始为分界」）：
- **受理阶段**（流未开始）：鉴权失败 / Pydantic 校验失败由既有
  全局异常处理器自动产出统一 JSON（HTTP 401 + code 1003 /
  HTTP 422 + code 1001）——``StreamingResponse`` 构造发生在受理
  检查之后，路由函数正常声明 ``Depends`` 与请求体模型即可，
  **零额外代码**；
- **流内阶段**（HTTP 200 已发送）：检索 / LLM 失败走 SSE
  error 事件带内信令（SSE 语义下唯一可读错误通道）；落库失败
  不走 error——正常 done 收尾（``history_id=null``，裁定③）。

心跳注释行（决策 D6）：本地 uvicorn 直连无中间层缓冲
（Cache-Control 已设），不追加 keep-alive；若后续引入反向代理
出现缓冲，再议每 15s yield ``: keep-alive`` 的扩展方案。
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.core.response import success
from app.models.user import User
from app.schemas.chat import ChatQAIn
from app.schemas.common import PaginationParams
from app.services.chat import list_qa_history, qa_stream

router = APIRouter(prefix="/chat", tags=["chat"])


@router.post(
    "/qa",
    summary="AI 学习问答（SSE 流式）",
    response_class=StreamingResponse,
)
async def chat_qa(
    payload: ChatQAIn,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> StreamingResponse:
    """SSE 流式问答端点（本项目首个 SSE 端点）。

    事件序列（四事件契约，spec 5.6.2）：``sources``（恰 1 次）→
    ``delta``（0..n 次，逐片即时转发，**真实流式禁先算后发**）→
    ``done``（四字段 data：is_grounded / mode / intent /
    history_id）| ``error``（仅检索 / LLM 失败）。

    user_id 取认证结果，禁收客户端传入的 user_id / item_id 作为
    检索边界（spec 4.3 规则 2）。

    Args:
        payload: 请求体（question；公共库已移除，无 scope）。
        db: 数据库会话（依赖注入；qa_stream 生成器持有请求级会话）。
        current_user: 当前登录用户（依赖注入）。

    Returns:
        StreamingResponse: ``text/event-stream`` 流式响应
        （``Cache-Control: no-cache``，spec 4.3 规则 5）。
    """
    events = qa_stream(db, current_user.id, payload.question)

    async def _sse_format(
        event_stream: AsyncIterator[dict[str, Any]],
    ) -> AsyncIterator[str]:
        """把事件 dict 流格式化为 SSE 文本（``data: {JSON}\\n\\n``）。

        ``json.dumps(..., ensure_ascii=False)`` 保证中文原样传输。
        """
        async for event in event_stream:
            yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        _sse_format(events),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache"},
    )


@router.get("/history", summary="历史问答记录（分页，仅本人）")
def list_chat_history(
    page_params: Annotated[PaginationParams, Query()],
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> dict[str, Any]:
    """分页查询当前用户的历史问答（created_at 倒序，统一响应体）。

    历史接口严格走统一响应体（与 SSE 通道分离，裁决 #10）；
    恒带 user_id 过滤（「不可见即不存在」）；无历史返回
    ``{items: [], total: 0}`` 不报错。

    Args:
        page_params: 分页查询参数（page / page_size）。
        db: 数据库会话（依赖注入）。
        current_user: 当前登录用户（依赖注入）。

    Returns:
        dict[str, Any]: 统一响应体，data 为
        ``{items, total, page, page_size}``；items 每条含 intent
        （回放双信号样式判定前置）。
    """
    return success(
        data=list_qa_history(
            db,
            current_user.id,
            page_params.page,
            page_params.page_size,
        )
    )