"""RAG 问答历史 ORM 模型（qa_history，第 16 张表）。

字段口径唯一来源：PROJECT_CONTEXT §6.16（R3 九字段）与
design.md 2.3.2。

独立建表理由（裁决 #5）：复用 agent_messages 会造成 AI Agent 页
会话历史与 RAG 问答历史混杂，是用户可见的错误；qa_history 是独立
功能实体、有用户可见的历史列表，值得一张表。

mode 落库与 P8「mode 不落库」惯例的关系（design.md 2.3.1-4）：
P8 惯例针对**文档状态**（可用性是瞬时状态，落在文档上会过期误导）；
本表 mode 落的是**某次问答发生时刻的检索模式快照**（历史事实，
不会过期），两者对象不同、不冲突。

intent 列（裁定① / 决策 D9）：``rag/qa.py`` 意图判断结果原样落库。
chat 与 knowledge 无据两种记录的既有字段完全同构
（``sources=[] + is_grounded=false``），不落库则历史回放无法区分
「正常聊天」与「无据警示」两种渲染。取值 knowledge | chat，普通
VARCHAR 不设 CHECK（与 ``learning_reports.report_type`` 等既有
轻量枚举列惯例对齐，值为代码唯一写入点控制）。

检索范围不落库（裁决 #5 字段清单不含；公共库移除后检索恒为个人库）。
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import Boolean, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, CreatedAtMixin, sa_enum
from app.models.enums import EmbedMode
from app.models.types import JSONType


class QAHistory(Base, CreatedAtMixin):
    """RAG 问答历史（成功 done 的问答快照，spec 5.5）。

    Attributes:
        id: 主键，自增。
        user_id: 归属用户 id（FK users.id，CASCADE；仅本人可见）。
        question: 用户问题原文。
        answer: 完整回答（全部 delta 拼接）。
        sources: 来源快照（sources 事件 data 的 JSON 数组原样；
            无据与 chat 落 ``[]`` 而非 NULL——JSONType 写入）。
        mode: 该次问答的检索模式快照（online/offline）。
        is_grounded: 是否基于知识库检索回答。
        intent: 问题意图（knowledge/chat，历史回放双信号样式判定的
            前置信号，裁定①）。
        created_at: 创建时间（UTC，CreatedAtMixin）。

    生命周期（design.md 2.3.2）：创建于 qa_stream 的 done 前一步
    （唯一写入口 ``services/chat.save_qa_history``）；本阶段无更新、
    无删除（spec 5.5.1 规则 6 只读）；用户删除时经 FK CASCADE 级联
    清理（与全库惯例一致）。
    """

    __tablename__ = "qa_history"
    __table_args__ = (
        # 复合索引精确覆盖历史查询「过滤 + 倒序 + 分页」三要素
        # （等值 user_id 前缀 + created_at 有序后缀），不另设单列
        # user_id 索引（design.md 2.3.2 索引论证）。
        Index("ix_qa_history_user_created", "user_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        comment="归属用户 id（仅本人可见）",
    )
    question: Mapped[str] = mapped_column(
        Text, nullable=False, comment="用户问题原文"
    )
    answer: Mapped[str] = mapped_column(
        Text, nullable=False, comment="完整回答（全部 delta 拼接）"
    )
    sources: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONType,
        nullable=False,
        comment="来源快照（sources 事件 data 的 JSON 数组原样）",
    )
    mode: Mapped[EmbedMode] = mapped_column(
        sa_enum(EmbedMode),
        nullable=False,
        comment="检索模式快照（online/offline）",
    )
    is_grounded: Mapped[bool] = mapped_column(
        Boolean, nullable=False, comment="是否基于知识库检索回答"
    )
    intent: Mapped[str] = mapped_column(
        String(20), nullable=False, comment="问题意图（knowledge/chat）"
    )