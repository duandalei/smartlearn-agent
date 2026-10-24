"""AI 学习问答出入参模型（design.md 2.2.2-(1)(2)）。

- ``ChatQAIn``：SSE 问答入参（question；公共库已移除，无 scope）；
- ``QaSourceItem``：sources 事件条目 / qa_history.sources 快照条目；
- ``ChatHistoryOut``：历史出参（含 intent——历史回放双信号样式判定
  的前置信号，裁定①）。
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, StringConstraints


class ChatQAIn(BaseModel):
    """SSE 流式问答入参（design.md 2.2.2-(1)）。

    越界输入（空 question / 501 字符）经全局处理器自动 422 + 1001
    中文提示（spec 5.1.1 规则 6），schema 层零额外代码。

    Attributes:
        question: 问题文本，去首尾空白后非空，≤500 字符（与检索
            入参上限一致，spec 6.1）。
    """

    model_config = ConfigDict(extra="forbid")

    question: Annotated[
        str,
        StringConstraints(strip_whitespace=True, min_length=1, max_length=500),
    ]


class QaSourceItem(BaseModel):
    """来源条目（sources 事件 data 元素 / 历史快照元素，spec 6.2）。

    ``item_id`` / ``chunk_index`` 声明为可空是防御性设计
    （design.md 2.3.2）：极端脏 metadata 下历史接口不 500，前端
    跳转判空降级为纯展示。

    Attributes:
        item_id: 来源文档 id（跳转 /knowledge-base 定位依据）。
        chunk_index: 来源分块序号（高亮定位依据）。
        content: 命中片段正文（原文，不截断改写）。
        source_title: 来源展示名（「文档标题 » 标题路径」）。
        score: 相似度分数（1 − cosine 距离，保留 4 位小数）。
        scope: 归属（当前恒为 personal）。
    """

    item_id: int | None = None
    chunk_index: int | None = None
    content: str
    source_title: str
    score: float
    scope: str


class ChatHistoryOut(BaseModel):
    """历史问答出参（design.md 2.2.2-(2)，spec 6.3）。

    Attributes:
        id: 记录 id。
        question: 用户问题。
        answer: 完整回答。
        sources: 来源快照（数组原样，spec 5.4.3 场景 2）。
        mode: 该次问答的检索模式快照（online / offline）。
        is_grounded: 是否基于知识库检索回答。
        intent: 问题意图（knowledge / chat，回放双信号样式判定的
            前置信号，裁定① / 决策 D9）。
        created_at: 创建时间（UTC）。
    """

    model_config = ConfigDict(from_attributes=True)

    id: int
    question: str
    answer: str
    sources: list[QaSourceItem]
    mode: str
    is_grounded: bool
    intent: str
    created_at: datetime