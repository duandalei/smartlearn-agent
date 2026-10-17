# TODO(P3): 认证阶段为全部业务端点补挂 get_current_user
"""Agent 消息只读路由（表名 kebab-case 路径，即最终正式路径）。

业务入口为 ``GET /api/v1/agent/conversations/{id}/messages``
（P3+ 在 agent.py 扩展）；本端点供 P2 阶段全表验证。
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.core.response import success
from app.models.agent import AgentMessage
from app.schemas.agent import MessageOut
from app.schemas.common import PaginationParams
from app.services.readonly import get_by_id_or_404, paginate

router: APIRouter = APIRouter(prefix="/agent-messages", tags=["Agent 消息"])


@router.get("", summary="Agent 消息列表（分页）")
def list_agent_messages(
    page_params: Annotated[PaginationParams, Query()],
    db: Annotated[Session, Depends(get_db)],
) -> dict[str, Any]:
    """分页查询 Agent 消息列表（按 id 升序）。

    Args:
        page_params: 分页参数。
        db: 数据库会话（依赖注入）。

    Returns:
        dict[str, Any]: 统一响应体，data 为 {items, total, page, page_size}。
    """
    return success(
        data=paginate(
            db,
            AgentMessage,
            MessageOut,
            page=page_params.page,
            page_size=page_params.page_size,
        )
    )


@router.get("/{message_id}", summary="Agent 消息详情")
def get_agent_message(
    message_id: int,
    db: Annotated[Session, Depends(get_db)],
) -> dict[str, Any]:
    """按 id 获取 Agent 消息详情。

    Args:
        message_id: 消息 id。
        db: 数据库会话（依赖注入）。

    Returns:
        dict[str, Any]: 统一响应体，data 为消息对象；不存在时
        返回 HTTP 404 + code=1005。
    """
    return success(
        data=get_by_id_or_404(db, AgentMessage, message_id, MessageOut)
    )