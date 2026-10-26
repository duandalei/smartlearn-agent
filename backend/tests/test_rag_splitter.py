"""splitter 切分逻辑单元测试（tasks.md 5.2）。

覆盖：标题路径保留 / 滑窗边界（重叠逐位比较）/ chunk_index 连续
性 / 短段落聚合与无内容丢失 / 真实样例 ml_basics.md。
"""

from __future__ import annotations

from pathlib import Path

from app.rag.loader import ParsedDocument, Section, load_document
from app.rag.splitter import (
    CHUNK_OVERLAP,
    MAX_CHUNK_LEN,
    _sliding_window,
    split_document,
)


def _doc(*sections: Section) -> ParsedDocument:
    """构造测试用 ParsedDocument。"""
    return ParsedDocument(sections=list(sections), full_text="x")


def test_heading_path_preserved_multilevel() -> None:
    """多级标题文档切分后每块携带正确层级链。"""
    doc = _doc(
        Section(heading_path="机器学习 > 监督学习", text="线性回归内容"),
        Section(heading_path="机器学习 > 无监督学习", text="聚类内容"),
    )
    chunks = split_document(doc)
    assert len(chunks) == 2
    assert chunks[0]["heading_path"] == "机器学习 > 监督学习"
    assert chunks[1]["heading_path"] == "机器学习 > 无监督学习"


def test_sliding_window_overlap_exact_chars() -> None:
    """超长段落滑窗：每块 ≤500、相邻块重叠恰 80（字符逐位比较）。"""
    paragraph = "".join(chr(0x4E00 + i % 300) for i in range(1200))
    pieces = _sliding_window(paragraph)
    # 步长 420：窗 [0,500) [420,920) [840,1200)，末窗为剩余 360。
    assert [len(p) for p in pieces] == [500, 500, 360]
    for prev, curr in zip(pieces, pieces[1:]):
        assert prev[-CHUNK_OVERLAP:] == curr[:CHUNK_OVERLAP], "重叠必须逐位一致"
    assert all(len(p) <= MAX_CHUNK_LEN for p in pieces)
    # 无内容丢失：逐块去重叠拼接可还原整段。
    assert pieces[0] + "".join(p[CHUNK_OVERLAP:] for p in pieces[1:]) == paragraph


def test_chunk_index_contiguous() -> None:
    """chunk_index 为 0..N-1 无跳号（含滑窗与聚合混合场景）。"""
    long_para = "深度学习模型训练" * 100  # 800 字符超长段落
    doc = _doc(
        Section(heading_path="A", text=long_para),
        Section(heading_path="B", text="短段落一\n\n短段落二"),
        Section(heading_path="C", text="尾段"),
    )
    chunks = split_document(doc)
    assert [c["chunk_index"] for c in chunks] == list(range(len(chunks)))
    assert len(chunks) >= 3


def test_short_paragraphs_aggregate_without_loss() -> None:
    """短段落聚合成块：不超上限、内容无丢失、段落以换行连接。"""
    paragraphs = "\n\n".join(f"第{i}段内容" for i in range(1, 11))
    doc = _doc(Section(heading_path="聚合", text=paragraphs))
    chunks = split_document(doc)
    assert len(chunks) >= 1
    assert all(len(c["content"]) <= MAX_CHUNK_LEN for c in chunks)
    joined = "\n".join(c["content"] for c in chunks)
    for i in range(1, 11):
        assert f"第{i}段内容" in joined, f"段落 {i} 内容丢失"


def test_aggregate_boundary_exactly_500() -> None:
    """聚合边界：并入后恰 500 字符成一块，501 字符分两块。"""
    doc = _doc(Section(heading_path="", text="a" * 230 + "\n\n" + "b" * 269))
    assert len(split_document(doc)) == 1
    doc2 = _doc(Section(heading_path="", text="a" * 230 + "\n\n" + "b" * 270))
    result = split_document(doc2)
    assert len(result) == 2
    assert result[0]["content"] == "a" * 230
    assert result[1]["content"] == "b" * 270


def test_empty_sections_yield_no_chunks() -> None:
    """空 sections 产出空列表（不产生分块）。"""
    assert split_document(_doc()) == []


def test_real_ml_basics_document() -> None:
    """真实样例：1_ml_basics.md 切分 8~12 块且含第六章路径节点。"""
    path = Path(__file__).resolve().parent / "fixtures" / "uploads" / "1_ml_basics.md"
    doc = load_document(Path(path), "md")
    chunks = split_document(doc)
    assert 8 <= len(chunks) <= 12, f"分块数超出预估区间: {len(chunks)}"
    assert all(len(c["content"]) <= MAX_CHUNK_LEN for c in chunks)
    assert [c["chunk_index"] for c in chunks] == list(range(len(chunks)))
    paths = {c["heading_path"] for c in chunks}
    assert any("六、Transformer 与注意力机制" in p for p in paths), paths
    assert all(p for p in paths), "该文档每块都应携带标题路径"