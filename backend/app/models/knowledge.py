"""知识库模型（knowledge_items / knowledge_chunks）。

文档与分块强从属（CASCADE）。双层知识库可见性：
``scope=public`` 系统预置只读（``user_id`` 为 NULL，全用户可见）；
``scope=personal`` 学生上传（仅本人可见）。
"""

from __future__ import annotations

from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, CreatedAtMixin, TimestampMixin, sa_enum
from app.models.enums import KnowledgeItemStatus, KnowledgeScope, KnowledgeSourceType


class KnowledgeItem(TimestampMixin, Base):
    """知识库文档（knowledge_items）。

    Attributes:
        id: 主键。
        user_id: 外键 users.id；personal 必填，public 为 NULL。
        title: 文档标题。
        source_type: pdf / md / txt / docx / pptx / note。
        file_path: 原始文件路径（note 类型可空）。
        scope: personal / public。
        status: pending / parsing / indexed / failed。
        error_msg: 解析或向量化失败原因（failed 时必填）。
        chunk_count: 切分后的分块数。
        file_size: 原件字节数，上传受理写入，存量公共文档由启动迁移回填
            （字段定义见 design.md 2.3.2-A 与契约 PROJECT_CONTEXT §6.9）。
    """

    __tablename__ = "knowledge_items"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
        nullable=True,
        comment="personal 必填；public 为 NULL",
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    source_type: Mapped[KnowledgeSourceType] = mapped_column(
        sa_enum(KnowledgeSourceType, length=10),
        nullable=False,
        comment="pdf/md/txt/docx/pptx/note",
    )
    file_path: Mapped[str | None] = mapped_column(
        String(500), nullable=True, comment="原始文件路径"
    )
    scope: Mapped[KnowledgeScope] = mapped_column(
        sa_enum(KnowledgeScope, length=10),
        default=KnowledgeScope.PERSONAL,
        index=True,
        nullable=False,
        comment="personal/public",
    )
    status: Mapped[KnowledgeItemStatus] = mapped_column(
        sa_enum(KnowledgeItemStatus),
        default=KnowledgeItemStatus.PENDING,
        nullable=False,
        comment="pending/parsing/indexed/failed",
    )
    error_msg: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="解析/向量化失败原因"
    )
    chunk_count: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False, comment="分块数"
    )
    file_size: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
        comment="原件字节数，上传受理写入，存量公共文档由启动迁移回填",
    )

    user: Mapped["User | None"] = relationship(  # noqa: F821
        back_populates="knowledge_items", passive_deletes=True
    )
    chunks: Mapped[list["KnowledgeChunk"]] = relationship(
        back_populates="item", cascade="all, delete-orphan", passive_deletes=True
    )


class KnowledgeChunk(CreatedAtMixin, Base):
    """知识分块（knowledge_chunks）。

    Attributes:
        id: 主键。
        item_id: 外键 knowledge_items.id（CASCADE）。
        user_id: 冗余外键 users.id（public 为 NULL，便于按用户过滤）。
        chunk_index: 分块序号，从 0 开始。
        content: 分块文本内容。
        heading_path: 标题层级路径（如「机器学习基础 > Transformer > 多头注意力」），
            用于检索结果定位原文章节（字段定义见 design.md 2.3.2-A 与契约
            PROJECT_CONTEXT §6.10；SQLite 动态类型下与 TEXT 存储等价）。
        embedding_id: Chroma 向量记录 id（RAG 阶段回填，P2 恒为 NULL）。
    """

    __tablename__ = "knowledge_chunks"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    item_id: Mapped[int] = mapped_column(
        ForeignKey("knowledge_items.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
        comment="外键 knowledge_items.id",
    )
    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        index=True,
        nullable=True,
        comment="冗余列：personal 归属用户；public 为 NULL",
    )
    chunk_index: Mapped[int] = mapped_column(
        Integer, nullable=False, comment="分块序号，从 0 开始"
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)
    heading_path: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
        comment="标题层级路径，用于检索结果定位原文章节",
    )
    embedding_id: Mapped[str | None] = mapped_column(
        String(100), nullable=True, comment="Chroma 向量 id（RAG 阶段回填）"
    )

    item: Mapped[KnowledgeItem] = relationship(back_populates="chunks")