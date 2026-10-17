"""Agent 会话与消息出参模型（ConversationOut / MessageOut）。"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class ConversationOut(BaseModel):
    """Agent 会话出参。"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    title: str | None
    created_at: datetime
    updated_at: datetime


class MessageOut(BaseModel):
    """Agent 消息出参。

    ``tool_calls`` 为 OpenAI 格式的调用列表（含参数）或 None；
    与 ``tool_call_id`` 配合可还原完整工具调用链。
    """

    model_config = ConfigDict(from_attributes=True)

    id: int
    conversation_id: int
    role: str
    content: str
    tool_name: str | None
    tool_calls: list[dict[str, Any]] | None
    tool_call_id: str | None
    created_at: datetime