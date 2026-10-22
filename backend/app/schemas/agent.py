"""Agent 会话与消息出入参模型（P3 出参 + P11 三入参）。

出参（ConversationOut / MessageOut）为 P3 既有交付零改动；入参三
模型为 P11 新增（design 2.2.2-(1)(3)(4)）。``AGENT_MESSAGE_MAX_LEN``
与 ``app/agent/core.MESSAGE_MAX_LEN`` **各自定义同值、刻意不共用
常量**（O6 裁定 / 决策 A8：与 P9 /chat/qa 的 500 上限语义独立演化
——问答是一句话，Agent 指令常带上下文；两处行内注释互相指认）。
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

#: 用户消息长度上限（O6 裁定：2000；独立于 P9 /chat/qa 的 500——
#: 同值锁定见 app/agent/core.MESSAGE_MAX_LEN，两处各自单一来源）。
AGENT_MESSAGE_MAX_LEN: int = 2000

#: 会话标题长度上限（agent_conversations.title 列宽）。
_TITLE_MAX_LEN: int = 200


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


class AgentChatIn(BaseModel):
    """Agent 对话入参（POST /agent/chat，spec §6.1）。

    ``message`` 去首尾空白后判定非空、≤2000 字符（O6）；
    ``conversation_id`` 可选正整数（未携带 → 自动新建会话；携带 →
    服务端校验存在且属本人，404/1005）。
    """

    model_config = ConfigDict(extra="forbid")

    message: Annotated[
        str,
        StringConstraints(
            strip_whitespace=True,
            min_length=1,
            max_length=AGENT_MESSAGE_MAX_LEN,
        ),
    ]
    conversation_id: int | None = Field(default=None, ge=1)


class ConversationCreateIn(BaseModel):
    """会话显式新建入参（POST /agent/conversations，O1 裁定纳入）。

    ``title`` 可选；strip 后为空（或缺省）时落 ``None``，首条 user
    消息落库时按 O4 补截断标题。
    """

    model_config = ConfigDict(extra="forbid")

    title: Annotated[
        str | None,
        StringConstraints(strip_whitespace=True, max_length=_TITLE_MAX_LEN),
    ] = None


class ConversationRenameIn(BaseModel):
    """会话重命名入参（PATCH /agent/conversations/{id}，O1 裁定纳入）。

    ``title`` 必填 1..200 字符（strip 后判定——空标题 422/1001）。
    """

    model_config = ConfigDict(extra="forbid")

    title: Annotated[
        str,
        StringConstraints(
            strip_whitespace=True, min_length=1, max_length=_TITLE_MAX_LEN
        ),
    ]