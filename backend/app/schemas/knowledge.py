"""知识库出参模型（KnowledgeItemOut / KnowledgeChunkOut）。"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class KnowledgeItemOut(BaseModel):
    """知识库文档出参。"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int | None
    title: str
    source_type: str
    file_path: str | None
    scope: str
    status: str
    error_msg: str | None
    chunk_count: int
    created_at: datetime
    updated_at: datetime


class KnowledgeChunkOut(BaseModel):
    """知识分块出参。"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    item_id: int
    user_id: int | None
    chunk_index: int
    content: str
    embedding_id: str | None
    created_at: datetime