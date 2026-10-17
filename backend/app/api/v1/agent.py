# TODO(P3): 认证阶段为全部业务端点补挂 get_current_user
"""Agent 会话只读路由。

路径演进契约：``/api/v1/agent/conversations`` 为最终正式路径
（PROJECT_CONTEXT 7.2），P3+ 的重命名 / 删除 / 消息读取 / SSE
对话端点在本文件同前缀扩展。
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.core.response import success
from app.models.agent import AgentConversation
from app.schemas.agent import ConversationOut
from app.schemas.common import PaginationParams
from app.services.readonly import get_by_id_or_404, paginate

router: APIRouter = APIRouter(prefix="/agent", tags=["AI Agent"])


@router.get("/conversations", summary="Agent 会话列表（分页）")
def list_conversations(
    page_params: Annotated[PaginationParams, Query()],
    db: Annotated[Session, Depends(get_db)],
) -> dict[str, Any]:
    """分页查询 Agent 会话列表（按 id 升序）。

    Args:
        page_params: 分页参数。
        db: 数据库会话（依赖注入）。

    Returns:
        dict[str, Any]: 统一响应体，data 为 {items, total, page, page_size}。
    """
    return success(
        data=paginate(
            db,
            AgentConversation,
            ConversationOut,
            page=page_params.page,
            page_size=page_params.page_size,
        )
    )


@router.get("/conversations/{conversation_id}", summary="Agent 会话详情")
def get_conversation(
    conversation_id: int,
    db: Annotated[Session, Depends(get_db)],
) -> dict[str, Any]:
    """按 id 获取 Agent 会话详情。

    Args:
        conversation_id: 会话 id。
        db: 数据库会话（依赖注入）。

    Returns:
        dict[str, Any]: 统一响应体，data 为会话对象；不存在时
        返回 HTTP 404 + code=1005。
    """
    return success(
        data=get_by_id_or_404(
            db, AgentConversation, conversation_id, ConversationOut
        )
    )