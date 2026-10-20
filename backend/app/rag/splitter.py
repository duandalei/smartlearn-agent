"""文档切分模块：中文友好的标题/段落切分 + 滑窗二次切分。

切分规则（spec 5.2.1 规则 3/4/5，design.md 2.1.2 模块职责表）：
- 先按标题边界分组（loader 已产出 Section，标题路径随组透传）；
- 组内按段落聚合：空行分隔的段落逐个并入当前块，并入后超过
  ``MAX_CHUNK_LEN`` 字符则闭合当前块、以该段落开启新块；
- 段落自身超过 500 字符时滑窗二次切分：步长 = 500−80 = 420 字符、
  相邻块重叠 ``CHUNK_OVERLAP = 80`` 字符（保证跨块语义不丢失）；
- ``chunk_index`` 从 0 起在同一文档内连续递增（0..N-1 无跳号）；
- 每块保留所属标题层级路径（heading_path）；
- 空 sections 产出空列表（不产生分块）。

字符数一律按 Python ``len``（Unicode 码点）计，中文英文同口径。
本模块纯同步、零外部依赖，不 import api / services（契约 §4）。
"""

from __future__ import annotations

import re
from typing import TypedDict

from app.rag.loader import ParsedDocument

# 单块最大字符数（spec 5.2.1 规则 3）。
MAX_CHUNK_LEN: int = 500

# 相邻块重叠字符数（spec 5.2.1 规则 3）。
CHUNK_OVERLAP: int = 80

# 滑窗步长 = 最大块长 − 重叠（500 − 80 = 420）。
_SLIDE_STEP: int = MAX_CHUNK_LEN - CHUNK_OVERLAP

# 段落分隔正则：仅含空白字符的行视为段落边界（md/txt 源文件
# 以空行分段；loader 的 Section.text 保留了空行结构）。
_PARAGRAPH_SPLIT_RE: re.Pattern[str] = re.compile(r"\n[ \t]*\n")


class Chunk(TypedDict):
    """切分产物：一个可独立向量化的分块。

    Attributes:
        content: 分块正文（≤ ``MAX_CHUNK_LEN`` 字符，聚合块内段落以
            换行连接；滑窗块为原文连续子串）。
        heading_path: 所属标题层级路径（空串表示无标题结构）。
        chunk_index: 文档内全局序号（0..N-1 连续无跳号）。
    """

    content: str
    heading_path: str
    chunk_index: int


def _split_paragraphs(text: str) -> list[str]:
    """按空行把区间正文切成段落列表（丢弃纯空白段落）。

    Args:
        text: Section 正文（含空行结构）。

    Returns:
        list[str]: 非空段落列表（首尾空白已去除，顺序保持原文）。
    """
    parts = _PARAGRAPH_SPLIT_RE.split(text)
    return [part.strip() for part in parts if part.strip()]


def _sliding_window(paragraph: str) -> list[str]:
    """对超长段落做滑窗二次切分。

    窗口宽 ``MAX_CHUNK_LEN``、步长 ``_SLIDE_STEP``（420），相邻窗口
    的重叠恒为 ``CHUNK_OVERLAP``（80）字符——前一块结尾 80 字符与
    后一块开头 80 字符为原文同一段连续子串；最后一块取到段落末尾
    （长度可不足 500，不产生越界或丢字）。

    Args:
        paragraph: 超过 ``MAX_CHUNK_LEN`` 字符的段落原文。

    Returns:
        list[str]: 连续子串列表（按原文顺序拼接可还原整段，且相邻
            块恰重叠 80 字符）。
    """
    pieces: list[str] = []
    total = len(paragraph)
    start = 0
    while start < total:
        end = min(start + MAX_CHUNK_LEN, total)
        pieces.append(paragraph[start:end])
        if end >= total:
            break
        start += _SLIDE_STEP
    return pieces


def split_document(doc: ParsedDocument) -> list[Chunk]:
    """把解析结果切分为分块列表。

    流程（design.md 2.1.2）：逐 Section（标题区间）→ 按空行切段落 →
    组内段落聚合（并入后超 500 字符则闭合开新块）→ 超长段落滑窗
    二次切分（子块直接成块，不再与其他段落聚合）→ 全文档统一编号。

    Args:
        doc: loader 产出的解析中间表示。

    Returns:
        list[Chunk]: 分块列表（chunk_index 为 0..N-1）；doc 无有效
            sections 时返回空列表（不产生分块）。
    """
    chunks: list[Chunk] = []

    def _emit(content: str, heading_path: str) -> None:
        """追加一个分块并自动编号。"""
        chunks.append(
            Chunk(
                content=content,
                heading_path=heading_path,
                chunk_index=len(chunks),
            )
        )

    for section in doc["sections"]:
        heading_path = section["heading_path"]
        buffer: list[str] = []
        buffer_len = 0

        def _flush() -> None:
            """闭合当前聚合缓冲（非空才成块）。"""
            nonlocal buffer, buffer_len
            if buffer:
                _emit("\n".join(buffer), heading_path)
            buffer = []
            buffer_len = 0

        for paragraph in _split_paragraphs(section["text"]):
            if len(paragraph) > MAX_CHUNK_LEN:
                # 超长段落：先闭合缓冲，再滑窗切分（子块直接成块）。
                _flush()
                for piece in _sliding_window(paragraph):
                    _emit(piece, heading_path)
                continue
            if buffer_len == 0:
                buffer = [paragraph]
                buffer_len = len(paragraph)
            elif buffer_len + 1 + len(paragraph) <= MAX_CHUNK_LEN:
                # 段落间以单个换行连接（+1 为换行符字符数）。
                buffer.append(paragraph)
                buffer_len += 1 + len(paragraph)
            else:
                _flush()
                buffer = [paragraph]
                buffer_len = len(paragraph)
        _flush()
    return chunks