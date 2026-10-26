"""Agent 会话与对话路由（六端点：SSE 对话 + 会话管理，需登录）。

路径演进契约：``/api/v1/agent/conversations`` 为正式路径
（PROJECT_CONTEXT §7.2），P3 只读两端点在本文件同前缀扩展为六端点
（O1 裁定：纳入 POST 新建 + PATCH 重命名）。

与统一响应体铁律的协调（裁决 #10，「以流是否开始为分界」，P9 同款）：
- **受理阶段**（流未开始）：鉴权失败 / Pydantic 校验失败 / 会话
  404 由既有全局异常处理器自动产出统一 JSON（HTTP 401 + 1003 /
  422 + 1001 / 404 + 1005）——``StreamingResponse`` 构造发生在受理
  检查之后，路由正常声明 ``Depends`` 与请求体模型即可，零额外代码；
- **流内阶段**（HTTP 200 已发送）：LLM 失败 / 流中断走 SSE error
  事件带内信令；落库失败不走 error（正常 done 收尾 message_id=null）。

SSE 格式化必须在 api 层（契约 §4「services/agent 禁拼接 HTTP 响应」，
决策 A1）：``data: {JSON}\\n\\n``、``ensure_ascii=False`` 中文原样、
双响应头 ``text/event-stream`` + ``Cache-Control: no-cache``。

路由注册顺序：固定路径（``/conversations`` GET/POST、``/chat`` POST）
先注册、参数路径（``/conversations/{conversation_id}`` 及其子路径）
后注册。路由层零业务逻辑（薄委托）；user_id 一律取认证结果注入，
禁收客户端传入的 user_id（conversation_id 仅作会话定位并校验归属）。
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.agent import core, memory
from app.api.deps import get_current_user, get_db
from app.core.response import success
from app.core.sse import format_sse
from app.models.user import User
from app.schemas.agent import (
    AgentChatIn,
    ConversationCreateIn,
    ConversationOut,
    ConversationRenameIn,
)
from app.schemas.common import PaginationParams
from app.services.readonly import get_by_id_or_404
from app.models.agent import AgentConversation

router: APIRouter = APIRouter(prefix="/agent", tags=["AI Agent"])


@router.get("/conversations", summary="Agent 会话列表（分页，仅当前用户）")
def list_conversations(
    page_params: Annotated[PaginationParams, Query()],
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> dict[str, Any]:
    """分页查询**当前用户**的 Agent 会话列表（updated_at 倒序，O2 裁定）。

    对 P3 的 id 升序是**有意行为变更**（最近活跃在前；同秒并列由
    id 倒序 tie-break 保证分页稳定）。

    Args:
        page_params: 分页参数。
        db: 数据库会话（依赖注入）。
        current_user: 当前登录用户（依赖注入）。

    Returns:
        dict[str, Any]: 统一响应体，data 为 {items, total, page, page_size}；
        未登录返回 HTTP 401 + code=1003；空列表返回 items=[] 不报错。
    """
    return success(
        data=memory.list_conversations(
            db,
            current_user.id,
            page_params.page,
            page_params.page_size,
        )
    )


@router.post("/conversations", summary="新建 Agent 会话（显式新建）")
def create_conversation(
    payload: ConversationCreateIn,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> dict[str, Any]:
    """显式新建会话（O1 裁定纳入；与 chat 自动新建并存不冲突）。

    Args:
        payload: 请求体（title 可选；空/缺省时首条消息落库补 O4 截断标题）。
        db: 数据库会话（依赖注入）。
        current_user: 当前登录用户（依赖注入）。

    Returns:
        dict[str, Any]: 统一响应体，data 为新会话对象。
    """
    conversation = memory.create_conversation(
        db, current_user.id, payload.title
    )
    return success(
        data=ConversationOut.model_validate(conversation).model_dump(
            mode="json"
        )
    )


@router.post(
    "/chat",
    summary="Agent 对话（SSE 流式，ReAct + Function Calling）",
    response_class=StreamingResponse,
)
async def agent_chat(
    payload: AgentChatIn,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> StreamingResponse:
    """Agent 对话主循环 SSE 端点（六事件契约，spec §5.6.2）。

    事件序列：每轮 ``thinking``（恰 1 次轮次信号）→ 该轮 ``delta``*
    （文本增量实时转发）→ ``tool_call``*（解析后参数对象）→
    ``tool_result``*（耗时 + ≤500 字摘要）→ 跨轮循环 → ``done``（五
    字段，finish_reason 真实反映 normal / max_rounds / timeout）|
    ``error``（仅 LLM 失败 / 流中断，code=3000）。

    受理阶段：``conversation_id`` 携带时校验存在且属本人（404/1005，
    统一 JSON，流未开始）；未携带时自动新建会话（title 先置 None，
    生成器内首条 user 消息落库时补 O4 截断标题）。

    Args:
        payload: 请求体（message + conversation_id?，Pydantic 校验）。
        db: 数据库会话（依赖注入；生成器持有请求级会话）。
        current_user: 当前登录用户（依赖注入）。

    Returns:
        StreamingResponse: ``text/event-stream`` 流式响应
        （``Cache-Control: no-cache``）。
    """
    if payload.conversation_id is not None:
        conversation = memory.get_conversation_or_404(
            db, payload.conversation_id, current_user.id
        )
    else:
        conversation = memory.create_conversation(db, current_user.id, None)

    events = core.agent_chat_stream(
        db, current_user.id, conversation, payload.message
    )

    return StreamingResponse(
        format_sse(events),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache"},
    )


@router.get(
    "/conversations/{conversation_id}", summary="Agent 会话详情（P3 既有）"
)
def get_conversation(
    conversation_id: int,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> dict[str, Any]:
    """按 id 获取 Agent 会话详情（仅限本人资源，P3 既有行为保留）。

    越权访问他人会话与不存在统一返回 HTTP 404 + code=1005。

    Args:
        conversation_id: 会话 id。
        db: 数据库会话（依赖注入）。
        current_user: 当前登录用户（依赖注入）。

    Returns:
        dict[str, Any]: 统一响应体，data 为会话对象。
    """
    return success(
        data=get_by_id_or_404(
            db,
            AgentConversation,
            conversation_id,
            ConversationOut,
            filters=[AgentConversation.user_id == current_user.id],
        )
    )


@router.patch(
    "/conversations/{conversation_id}", summary="重命名 Agent 会话"
)
def rename_conversation(
    conversation_id: int,
    payload: ConversationRenameIn,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> dict[str, Any]:
    """重命名会话（O1 裁定纳入；title 1–200 字符，仅限本人）。

    Args:
        conversation_id: 会话 id。
        payload: 请求体（title 必填 1..200）。
        db: 数据库会话（依赖注入）。
        current_user: 当前登录用户（依赖注入）。

    Returns:
        dict[str, Any]: 统一响应体，data 为更新后会话对象；不存在或
        越权返回 HTTP 404 + code=1005；空标题 / 超 200 返回 422 + 1001。
    """
    return success(
        data=memory.rename_conversation(
            db, conversation_id, current_user.id, payload.title
        )
    )


@router.delete(
    "/conversations/{conversation_id}", summary="删除 Agent 会话（级联消息）"
)
def delete_conversation(
    conversation_id: int,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> dict[str, Any]:
    """删除会话并级联删除其全部消息（硬删除，仅限本人）。

    Args:
        conversation_id: 会话 id。
        db: 数据库会话（依赖注入）。
        current_user: 当前登录用户（依赖注入）。

    Returns:
        dict[str, Any]: 统一响应体（data=null）；不存在或越权返回
        HTTP 404 + code=1005。
    """
    memory.delete_conversation(db, conversation_id, current_user.id)
    return success(data=None)


@router.get(
    "/conversations/{conversation_id}/messages",
    summary="Agent 会话消息（全量，还原对话流）",
)
def list_conversation_messages(
    conversation_id: int,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> dict[str, Any]:
    """全量返回该会话全部消息（O3 裁定：不分页，id 升序）。

    404 语义先于空列表判定（会话不存在/越权 → 404/1005；存在无消息
    → data=[]）。消息含 role/tool_name/tool_calls/tool_call_id 全链，
    足以还原对话流与工具调用卡片（D4 服务端维度）。

    Args:
        conversation_id: 会话 id。
        db: 数据库会话（依赖注入）。
        current_user: 当前登录用户（依赖注入）。

    Returns:
        dict[str, Any]: 统一响应体，data 为 MessageOut 数组。
    """
    return success(
        data=memory.list_messages(db, conversation_id, current_user.id)
    )