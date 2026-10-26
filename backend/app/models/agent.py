"""Agent 会话与消息模型（agent_conversations / agent_messages）。

会话与消息强从属（CASCADE），同文件声明。``tool_calls`` 存 OpenAI
格式的工具调用 JSON（含调用参数），``tool_call_id`` 关联 assistant
消息 tool_calls 中的 id —— 仅存 tool_name 还原不出调用过程。
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, CreatedAtMixin, TimestampMixin, sa_enum
from app.models.enums import MessageRole
from app.models.types import JSONType


class AgentConversation(TimestampMixin, Base):
    """Agent 会话（agent_conversations）。

    Attributes:
        id: 主键。
        user_id: 外键 users.id。
        title: 会话标题（可由首条消息生成）。
    """

    __tablename__ = "agent_conversations"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
        comment="外键 users.id",
    )
    title: Mapped[str | None] = mapped_column(
        String(200), nullable=True, comment="会话标题"
    )

    user: Mapped["User"] = relationship(  # noqa: F821
        back_populates="conversations"
    )
    messages: Mapped[list["AgentMessage"]] = relationship(
        back_populates="conversation",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class AgentMessage(CreatedAtMixin, Base):
    """Agent 消息（agent_messages）。

    Attributes:
        id: 主键。
        conversation_id: 外键 agent_conversations.id（CASCADE）。
        role: user / assistant / tool / system。
        content: 消息内容。
        tool_name: role=tool 时记录的工具名。
        tool_calls: assistant 触发工具调用时的 OpenAI 格式 tool_calls JSON。
        tool_call_id: role=tool 时对应的调用 id。
    """

    __tablename__ = "agent_messages"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    conversation_id: Mapped[int] = mapped_column(
        ForeignKey("agent_conversations.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
        comment="外键 agent_conversations.id",
    )
    role: Mapped[MessageRole] = mapped_column(
        sa_enum(MessageRole), nullable=False, comment="user/assistant/tool/system"
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)
    tool_name: Mapped[str | None] = mapped_column(
        String(50), nullable=True, comment="role=tool 时的工具名"
    )
    tool_calls: Mapped[list[dict[str, Any]] | None] = mapped_column(
        JSONType, nullable=True, comment="OpenAI 格式 tool_calls JSON"
    )
    tool_call_id: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
        comment="role=tool 时对应的调用 id",
    )

    conversation: Mapped[AgentConversation] = relationship(
        back_populates="messages"
    )