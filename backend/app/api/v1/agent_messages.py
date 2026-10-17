"""Agent 消息只读路由（需登录；间接归属：经所属会话按当前用户过滤）。

消息本身无 ``user_id``，归属链为
``agent_messages.conversation_id -> agent_conversations.user_id``。
业务入口为 ``GET /api/v1/agent/conversations/{id}/messages``
（P3+ 在 agent.py 扩展）；本端点供全表验证。
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.core.response import success
from app.models.agent import AgentConversation, AgentMessage
from app.models.user import User
from app.schemas.agent import MessageOut
from app.schemas.common import PaginationParams
from app.services.readonly import get_by_id_or_404, paginate

router: APIRouter = APIRouter(prefix="/agent-messages", tags=["Agent 消息"])


def _ownership_filters(current_user: User) -> list[Any]:
    """构造消息归属过滤条件：所属会话属于当前用户。"""
    return [
        AgentMessage.conversation_id.in_(
            select(AgentConversation.id).where(
                AgentConversation.user_id == current_user.id
            )
        )
    ]


@router.get("", summary="Agent 消息列表（分页，仅当前用户的会话）")
def list_agent_messages(
    page_params: Annotated[PaginationParams, Query()],
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> dict[str, Any]:
    """分页查询**当前用户**的 Agent 消息列表（按 id 升序）。

    Args:
        page_params: 分页参数。
        db: 数据库会话（依赖注入）。
        current_user: 当前登录用户（依赖注入）。

    Returns:
        dict[str, Any]: 统一响应体，data 为 {items, total, page, page_size}；
        未登录返回 HTTP 401 + code=1003。
    """
    return success(
        data=paginate(
            db,
            AgentMessage,
            MessageOut,
            page=page_params.page,
            page_size=page_params.page_size,
            filters=_ownership_filters(current_user),
        )
    )


@router.get("/{message_id}", summary="Agent 消息详情")
def get_agent_message(
    message_id: int,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> dict[str, Any]:
    """按 id 获取 Agent 消息详情（仅限本人会话内的消息）。

    越权访问他人会话的消息与不存在统一返回 HTTP 404 + code=1005。

    Args:
        message_id: 消息 id。
        db: 数据库会话（依赖注入）。
        current_user: 当前登录用户（依赖注入）。

    Returns:
        dict[str, Any]: 统一响应体，data 为消息对象。
    """
    return success(
        data=get_by_id_or_404(
            db,
            AgentMessage,
            message_id,
            MessageOut,
            filters=_ownership_filters(current_user),
        )
    )