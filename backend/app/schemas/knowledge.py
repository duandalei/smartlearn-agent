"""知识库出入参模型。

出参：``KnowledgeItemOut`` / ``KnowledgeChunkOut``（P2 存量，P8 各
增补一个可空字段，向前兼容）；入参与检索模型为 P8 新增（字段签名
以 design.md 2.2.2-(5) 为准）。
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


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
    file_size: int | None = None
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
    heading_path: str | None = None
    embedding_id: str | None
    created_at: datetime


class KnowledgeSearchIn(BaseModel):
    """语义检索入参（design.md 2.2.2-(5)）。

    Attributes:
        query: 检索问题文本，非空且 ≤500 字符。
        top_k: 返回条数，默认 5，范围 1~20。
    """

    query: str = Field(min_length=1, max_length=500)
    top_k: int = Field(default=5, ge=1, le=20)


class KnowledgeSearchHit(BaseModel):
    """单条检索命中（design.md 2.2.2-(5)；P9 裁决 #3 扩展三字段）。

    ``item_id`` / ``chunk_index`` / ``scope`` 为 P9 新增可选字段
    （底层 ``query_visible`` 命中已含、P7 组装时被丢弃，P9 恢复
    透出，供问答来源跳转与归属徽章使用）；可选语义（默认 None，
    实际总有值），既有消费方按原三字段读取不受影响。

    Attributes:
        content: 命中片段正文。
        source_title: 来源展示名，「文档标题 » 标题路径」。
        score: 相似度分数（1 - cosine 距离，降序，保留 4 位小数）。
        item_id: 来源文档 id（P9，跳转定位依据）。
        chunk_index: 来源分块序号（P9，高亮定位依据）。
        scope: 归属作用域（P9，personal / public）。
    """

    content: str
    source_title: str
    score: float
    item_id: int | None = None
    chunk_index: int | None = None
    scope: str | None = None


class KnowledgeSearchOut(BaseModel):
    """语义检索响应（design.md 2.2.2-(5)）。

    Attributes:
        mode: 检索模式标识（online / offline）。offline → 前端常驻
            离线警示条（design.md 2.6.2-D 硬性要求）；mode 为前端
            渲染的唯一权威信号（可用性是瞬时状态，不落库）。
        results: 命中列表，按 score 降序，条数 ≤ top_k。
    """

    mode: Literal["online", "offline"]
    results: list[KnowledgeSearchHit]


class KnowledgeUploadOut(BaseModel):
    """上传受理响应（异步受理，立即返回；design.md 2.2.2-(1)）。

    Attributes:
        item_id: 新建文档 id（前端据此轮询状态）。
        status: 受理时刻状态（恒为 pending；后续流转由后台流水线驱动）。
    """

    item_id: int
    status: str