"""向量化模块：在线批量向量化 + 本地兜底向量化（双模式）。

模块职责（design.md 2.4.1/2.4.2/2.4.3）：
- 在线路径：复用 ``services/llm.py`` 的 ``get_embedding_client()`` 唯一
  客户端（spec 4.5 规则 1 + 提示词双重锁定：**禁止另建客户端或读取
  其他环境变量**——本模块是「rag 不 import services」分层约束的
  唯一显式豁免点，豁免依据即该锁定条款本身，design.md 2.1.2 架构
  图中 rag_embed --> svc_llm 单线）；
- 批量约束：``EMBED_BATCH_SIZE = 16`` 分批调用；重试语义分层沿用
  ``services/llm.py`` docstring 既有口径——SDK 级 ``max_retries=1``
  只处理瞬态网络错误（客户端构造已含）+ 业务级整体重试 1 次，
  仍失败抛 :class:`EmbeddingUnavailableError`（含
  ``get_embedding_client`` 配置缺失抛 3000 的场景，同样视为在线
  不可用而非中断）；
- 本地兜底：带符号哈希 TF 特征降维（中文 2-gram + 英文/数字 token），
  纯标准库、无网络、无模型下载、确定性（同文本必得同向量）；
- 文档级模式锁定（design.md 2.4.1 规则 3）：在线任一批失败 → 整篇
  放弃在线向量（已成功批次一并丢弃），全篇统一走兜底，杜绝同一
  文档的在线库向量来自混合模式。

维度约定（design.md 2.9 决策 #16）：**在线向量维度不硬编码 1024**
（以 API 返回为准，Chroma 在线 collection 首批写入时自动锁定）；
``LOCAL_EMBED_DIM = 1024`` 仅是本地兜底向量的实现常量。

本地兜底算法口径（固定，避免口径漂移）：
- 分词：中文按 2 字符滑窗 bigram（「注意力机制」→ 注意/意力/力机/
  机制）；连续 ASCII 字母/数字/下划线段作单 token 并 lower
  （Transformer / QKV / d_k）；孤立单汉字（前后均为非中文字符）
  降级为单字 token；
- 特征映射：token → ``int(sha1(token).hexdigest[:8], 16)`` 的
  32 位哈希 → 低 10 位（``% 1024``）定桶；
- 带符号哈希：取 32 位哈希的次高位（bit 30）决定 ±1 方向（与低
  10 位桶索引位完全独立；hashing trick 标准做法，抵消桶碰撞的
  正向偏置）；
- 权重：桶内累加 ``sign × (1 + ln(tf))``（**TF 子线性压缩**，
  1+log 口径固定）；
- 归一化：L2 归一化（范数为 0 的空文本返回全零向量，防御性）。
"""

from __future__ import annotations

import hashlib
import logging
import math
import re
from collections import Counter
from typing import Literal

from app.core.config import settings
from app.core.response import BizException
from app.services.llm import get_embedding_client

logger = logging.getLogger(__name__)

# 在线向量化单批最大条数（design.md 2.4.3）。
EMBED_BATCH_SIZE: int = 16

# 本地兜底向量维度（仅兜底常量；在线维度以 API 返回为准）。
LOCAL_EMBED_DIM: int = 1024

# 检索/向量化模式标识（design.md 2.2.2-5：mode 收敛为 Literal 而非裸 str）。
EmbedMode = Literal["online", "offline"]

# 分词正则：连续 ASCII 字母/数字/下划线段（英文 token）或连续中文字符段。
# 中文字符限定基本区 U+4E00..U+9FFF（覆盖简体中文学习资料）。
_TOKEN_SEGMENT_RE: re.Pattern[str] = re.compile(r"[A-Za-z0-9_]+|[\u4e00-\u9fff]+")


class EmbeddingUnavailableError(Exception):
    """在线向量化不可用信号（触发本地兜底降级）。

    触发情形（design.md 2.4.3）：
    - Embedding 配置缺失（``get_embedding_client`` 抛 3000）；
    - 批量调用经 SDK 重试 + 业务级整体重试后仍失败
      （网络不可达 / 超时 / 鉴权失败 / 上游 5xx 等）。

    Attributes:
        reason: 不可用原因摘要（供日志，不外透给用户）。
    """

    def __init__(self, reason: str) -> None:
        """初始化在线不可用信号。

        Args:
            reason: 原因摘要（异常类型与消息前 200 字符）。
        """
        super().__init__(reason)
        self.reason = reason


# ---------------------------------------------------------------------------
# 在线批量向量化
# ---------------------------------------------------------------------------


async def embed_texts_online(texts: list[str]) -> list[list[float]]:
    """在线批量向量化（batch ≤ 16 + 两层重试）。

    按 ``EMBED_BATCH_SIZE`` 分批调用
    ``get_embedding_client().embeddings.create(model=
    settings.embedding_model_effective, input=[...])``；任一批失败
    （含配置缺失）→ 整体重试 1 次（SDK 层瞬态重试已由客户端
    ``max_retries=1`` 覆盖）→ 仍失败抛
    :class:`EmbeddingUnavailableError`。向量维度以 API 返回为准，
    本函数不做任何维度断言（design.md 2.9 决策 #16）。

    Args:
        texts: 文本列表（分块正文或单条查询）。

    Returns:
        list[list[float]]: 与 ``texts`` 逐条对齐的向量列表。

    Raises:
        EmbeddingUnavailableError: 配置缺失或两层重试后仍失败。
    """
    if not texts:
        return []
    batches = [
        texts[i : i + EMBED_BATCH_SIZE]
        for i in range(0, len(texts), EMBED_BATCH_SIZE)
    ]
    last_reason = "unknown"
    # 首次尝试 + 业务级整体重试 1 次（design.md 2.4.3 口径）。
    for attempt in range(2):
        try:
            client = get_embedding_client()
            vectors: list[list[float]] = []
            for batch in batches:
                response = await client.embeddings.create(
                    model=settings.embedding_model_effective,
                    input=batch,
                )
                if len(response.data) != len(batch):
                    raise RuntimeError(
                        f"返回向量数与输入不一致: {len(response.data)} != {len(batch)}"
                    )
                # 按返回 index 排序，保证与输入顺序严格对齐。
                ordered = sorted(response.data, key=lambda d: d.index)
                vectors.extend([list(d.embedding) for d in ordered])
            return vectors
        except (BizException, Exception) as exc:  # noqa: BLE001
            # BizException(3000)=配置缺失；其余为 SDK/网络/上游异常，
            # 一律视为在线不可用信号（不外透原始异常）。
            last_reason = f"{type(exc).__name__}: {str(exc)[:200]}"
            logger.warning(
                "在线向量化失败(第 %d 次): %s", attempt + 1, last_reason
            )
    raise EmbeddingUnavailableError(last_reason)


# ---------------------------------------------------------------------------
# 本地兜底向量化（纯标准库、确定性）
# ---------------------------------------------------------------------------


def _tokenize(text: str) -> list[str]:
    """按兜底口径分词：中文 bigram + 英文/数字 token。

    Args:
        text: 待分词文本。

    Returns:
        list[str]: token 列表（英文 token 已 lower）。
    """
    tokens: list[str] = []
    for match in _TOKEN_SEGMENT_RE.finditer(text):
        segment = match.group(0)
        if segment.isascii():
            tokens.append(segment.lower())
            continue
        # 中文字符段：2 字符滑窗 bigram；孤立单汉字降级为单字 token。
        if len(segment) == 1:
            tokens.append(segment)
            continue
        for i in range(len(segment) - 1):
            tokens.append(segment[i : i + 2])
    return tokens


def _bucket_and_sign(token: str) -> tuple[int, float]:
    """计算 token 的哈希桶索引与带符号方向。

    Args:
        token: 已分词的 token。

    Returns:
        tuple[int, float]: (桶索引 ∈ [0, 1024)，方向 ±1.0)。
        口径固定：32 位 sha1 哈希低 10 位定桶、次高位（bit 30）定
        符号（两区域位级独立）。
    """
    digest = hashlib.sha1(token.encode("utf-8")).hexdigest()[:8]
    hashed = int(digest, 16)
    bucket = hashed % LOCAL_EMBED_DIM
    sign = 1.0 if ((hashed >> 30) & 1) == 0 else -1.0
    return bucket, sign


def _embed_text_local(text: str) -> list[float]:
    """单文本本地兜底向量化（哈希 TF + L2 归一化）。

    Args:
        text: 文本。

    Returns:
        list[float]: 1024 维确定性向量；无有效 token 时返回全零
        向量（L2 范数为 0，防御性保留，Chroma 下 cosine 分数为 0）。
    """
    vector = [0.0] * LOCAL_EMBED_DIM
    term_freq = Counter(_tokenize(text))
    for token, count in term_freq.items():
        bucket, sign = _bucket_and_sign(token)
        # TF 子线性压缩口径固定：1 + ln(tf)。
        vector[bucket] += sign * (1.0 + math.log(count))
    norm = math.sqrt(sum(value * value for value in vector))
    if norm > 0.0:
        return [value / norm for value in vector]
    return vector


def embed_texts_local(texts: list[str]) -> list[list[float]]:
    """本地兜底批量向量化（确定性，无网络无模型）。

    Args:
        texts: 文本列表。

    Returns:
        list[list[float]]: 与 ``texts`` 逐条对齐的 1024 维向量列表。
    """
    return [_embed_text_local(text) for text in texts]


# ---------------------------------------------------------------------------
# 双模式编排（文档级模式锁定）
# ---------------------------------------------------------------------------


async def embed_texts_with_fallback(
    texts: list[str],
) -> tuple[list[list[float]], EmbedMode]:
    """批量向量化双模式编排（文档级模式锁定）。

    在线成功 → 返回在线向量与 ``mode="online"``；在线不可用
    （配置缺失/网络失败等）→ **整篇**转本地兜底并返回
    ``mode="offline"``——已成功的批次一并丢弃，杜绝同一文档的
    在线库向量来自混合模式（design.md 2.4.1 规则 3）。

    Args:
        texts: 分块正文列表。

    Returns:
        tuple[list[list[float]], EmbedMode]: (向量列表, 模式标识)。
        ``texts`` 为空时返回空列表与 ``"offline"``（无向量可产，
        不触发在线调用）。
    """
    if not texts:
        return [], "offline"
    try:
        vectors = await embed_texts_online(texts)
        return vectors, "online"
    except EmbeddingUnavailableError as exc:
        logger.warning("整篇转本地兜底向量化: %s", exc.reason)
        return embed_texts_local(texts), "offline"


async def embed_query_with_fallback(
    query: str,
) -> tuple[list[float], EmbedMode]:
    """查询向量化双模式编排（检索路径专用）。

    单条查询在线向量化，失败（两层重试后）降级本地兜底；查询向量
    与被查 collection 必然同空间（按返回 mode 选库，design.md
    2.4.1 规则 2）。

    Args:
        query: 检索查询文本。

    Returns:
        tuple[list[float], EmbedMode]: (查询向量, 模式标识)。
    """
    try:
        vectors = await embed_texts_online([query])
        return vectors[0], "online"
    except EmbeddingUnavailableError as exc:
        logger.warning("查询向量转本地兜底: %s", exc.reason)
        return embed_texts_local([query])[0], "offline"