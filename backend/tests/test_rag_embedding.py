"""embedding 向量化单元测试（tasks.md 5.4）。

覆盖：本地兜底确定性/维度/分词口径（白盒锁定）/ 桶与符号口径 /
空文本防御 / 在线降级链路（BizException 3000 与网络异常两类）/
业务级重试次数 / 批量约束（105 条 → 7 批、单批 ≤16）/
响应 index 乱序对齐 / 文档级模式锁定（部分批失败整篇转兜底）。
在线路径全部使用假 client（本地兜底与降级链路为真实执行）。
"""

from __future__ import annotations

import asyncio
import hashlib
import math
from typing import Any, Callable

import pytest

import app.rag.embedding as embedding_module
from app.core.response import BizException
from app.rag.embedding import (
    EMBED_BATCH_SIZE,
    LOCAL_EMBED_DIM,
    EmbeddingUnavailableError,
    _bucket_and_sign,
    _tokenize,
    embed_texts_local,
)


# ---------------------------------------------------------------------------
# 假在线 client（记录调用、可注入失败）
# ---------------------------------------------------------------------------


class _FakeEmbeddingObj:
    """假 embedding 数据对象（index + 向量）。"""

    def __init__(self, index: int, vector: list[float]) -> None:
        self.index = index
        self.embedding = vector


class _FakeResponse:
    """假 embeddings.create 响应。"""

    def __init__(self, data: list[_FakeEmbeddingObj]) -> None:
        self.data = data


class _FakeEmbeddings:
    """假 embeddings 子对象：记录每批 input，按 handler 产出或抛错。"""

    def __init__(self, handler: Callable[[list[str]], _FakeResponse]) -> None:
        self.handler = handler
        self.calls: list[list[str]] = []

    async def create(self, *, model: str, input: list[str]) -> _FakeResponse:
        self.calls.append(list(input))
        return self.handler(input)


class _FakeClient:
    """假在线 embedding client。"""

    def __init__(self, embeddings: _FakeEmbeddings) -> None:
        self.embeddings = embeddings


def _install_fake_client(
    monkeypatch: pytest.MonkeyPatch,
    handler: Callable[[list[str]], _FakeResponse],
) -> _FakeEmbeddings:
    """把 embedding 模块的 get_embedding_client 替换为假工厂。"""
    fake = _FakeEmbeddings(handler)
    monkeypatch.setattr(
        embedding_module, "get_embedding_client", lambda: _FakeClient(fake)
    )
    return fake


def _ok_handler(texts: list[str]) -> _FakeResponse:
    """默认成功 handler：index 顺序一致，向量 [i]。"""
    return _FakeResponse([_FakeEmbeddingObj(i, [float(i)]) for i in range(len(texts))])


# ---------------------------------------------------------------------------
# 本地兜底
# ---------------------------------------------------------------------------


def test_local_embedding_deterministic_and_dim() -> None:
    """同文本必得同向量（逐位相等）、维度 1024、L2 范数 1。"""
    texts = ["注意力机制是 Transformer 的核心组件", "线性回归是最简单的监督学习算法"]
    first = embed_texts_local(texts)
    second = embed_texts_local(texts)
    assert first == second
    assert all(len(v) == LOCAL_EMBED_DIM == 1024 for v in first)
    assert first[0] != first[1]
    for vector in first:
        norm = math.sqrt(sum(x * x for x in vector))
        assert abs(norm - 1.0) < 1e-9


def test_local_tokenization_rules() -> None:
    """分词口径：中文 bigram / 英文数字 token lower / 孤立单字。"""
    assert _tokenize("注意力机制") == ["注意", "意力", "力机", "机制"]
    assert _tokenize("Transformer is Great 42") == ["transformer", "is", "great", "42"]
    assert _tokenize("学 a") == ["学", "a"]
    assert _tokenize("，。！") == []


def test_local_bucket_sign_oral_locked() -> None:
    """桶与符号口径白盒锁定：sha1 低 10 位定桶、bit 30 定符号。"""
    for token in ("注意", "transformer", "机制"):
        hashed = int(hashlib.sha1(token.encode("utf-8")).hexdigest()[:8], 16)
        expected_bucket = hashed % LOCAL_EMBED_DIM
        expected_sign = 1.0 if ((hashed >> 30) & 1) == 0 else -1.0
        assert _bucket_and_sign(token) == (expected_bucket, expected_sign)


def test_local_single_token_bucket_value() -> None:
    """单 token 文本：唯一非零桶位置正确、值为 ±1.0（TF=1 → 1+ln1）。"""
    token = "机制"
    bucket, sign = _bucket_and_sign(token)
    vector = embed_texts_local([token])[0]
    assert _tokenize(token) == [token], "前提：整体为单一 token"
    nonzero = [(i, value) for i, value in enumerate(vector) if value != 0.0]
    assert nonzero == [(bucket, pytest.approx(sign))]


def test_local_empty_text_zero_vector() -> None:
    """空文本/纯标点：全零向量（范数 0，防御性保留）。"""
    for text in ("", "   ", "，。！……"):
        vector = embed_texts_local([text])[0]
        assert len(vector) == LOCAL_EMBED_DIM
        assert all(value == 0.0 for value in vector)


# ---------------------------------------------------------------------------
# 降级链路与重试
# ---------------------------------------------------------------------------


def test_online_config_missing_falls_back(offline_embedding: None) -> None:
    """配置缺失（BizException 3000）→ 整体转本地兜底（offline 模式）。"""
    texts = ["监督学习需要标注数据", "无监督学习从数据结构中发现模式"]
    vectors, mode = asyncio.run(embedding_module.embed_texts_with_fallback(texts))
    assert mode == "offline"
    assert vectors == embed_texts_local(texts)
    with pytest.raises(EmbeddingUnavailableError):
        asyncio.run(embedding_module.embed_texts_online(texts))


def test_online_network_error_falls_back(monkeypatch: pytest.MonkeyPatch) -> None:
    """网络/上游异常 → 两层重试后抛不可用信号，fallback 转本地。"""
    def _boom(texts: list[str]) -> _FakeResponse:
        raise RuntimeError("connection timed out")

    fake = _install_fake_client(monkeypatch, _boom)
    texts = ["梯度下降是基础优化算法"]
    vectors, mode = asyncio.run(embedding_module.embed_texts_with_fallback(texts))
    assert mode == "offline"
    assert vectors == embed_texts_local(texts)
    # 单批 × （首次 + 业务级整体重试 1 次）= 2 次调用。
    assert len(fake.calls) == 2


def test_online_retry_only_once_per_attempt(monkeypatch: pytest.MonkeyPatch) -> None:
    """在线失败重试口径：整体重试恰 1 次（共 2 次尝试）后抛信号。"""
    def _boom(texts: list[str]) -> _FakeResponse:
        raise ValueError("upstream 5xx")

    fake = _install_fake_client(monkeypatch, _boom)
    with pytest.raises(EmbeddingUnavailableError) as exc_info:
        asyncio.run(embedding_module.embed_texts_online(["单条文本"]))
    assert exc_info.value.reason.startswith("ValueError")
    assert len(fake.calls) == 2


# ---------------------------------------------------------------------------
# 批量约束与顺序对齐
# ---------------------------------------------------------------------------


def test_online_batch_splitting_105_texts(monkeypatch: pytest.MonkeyPatch) -> None:
    """批量约束：105 条 → 7 批（≥7 次调用）、单批 ≤16、逐条对齐。"""
    fake = _install_fake_client(monkeypatch, _ok_handler)
    texts = [f"第{i}条测试文本内容" for i in range(105)]
    vectors, mode = asyncio.run(embedding_module.embed_texts_with_fallback(texts))
    assert mode == "online"
    assert len(fake.calls) == 7
    assert all(len(batch) <= EMBED_BATCH_SIZE for batch in fake.calls)
    assert [len(batch) for batch in fake.calls] == [16, 16, 16, 16, 16, 16, 9]
    assert len(vectors) == 105
    # 假 handler 向量为批内 index：顺序对齐断言按批内口径拼接校验。
    assert all(vectors[i] == [float(i % 16)] for i in range(105))


def test_online_response_index_reordered(monkeypatch: pytest.MonkeyPatch) -> None:
    """响应 data index 乱序时按 index 排序，输出仍与输入对齐。"""
    def _shuffled(texts: list[str]) -> _FakeResponse:
        n = len(texts)
        data = [_FakeEmbeddingObj(n - 1 - i, [float(n - 1 - i)]) for i in range(n)]
        return _FakeResponse(data)

    _install_fake_client(monkeypatch, _shuffled)
    texts = ["甲内容", "乙内容", "丙内容"]
    vectors, mode = asyncio.run(embedding_module.embed_texts_with_fallback(texts))
    assert mode == "online"
    assert vectors == [[0.0], [1.0], [2.0]]


# ---------------------------------------------------------------------------
# 文档级模式锁定
# ---------------------------------------------------------------------------


def test_document_level_mode_locking(monkeypatch: pytest.MonkeyPatch) -> None:
    """任一批失败 → 整篇转兜底（已成功批次一并丢弃，不混合模式）。"""
    state = {"fail_on": {2, 4}}

    def _partial(texts: list[str]) -> Any:
        return _FakeResponse([_FakeEmbeddingObj(i, [float(i)]) for i in range(len(texts))])

    fake = _FakeEmbeddings(_partial)

    async def _create(*, model: str, input: list[str]) -> Any:
        fake.calls.append(list(input))
        if len(fake.calls) in state["fail_on"]:
            raise RuntimeError("second batch failed")
        return fake.handler(input)

    fake.create = _create  # type: ignore[method-assign]
    monkeypatch.setattr(
        embedding_module, "get_embedding_client", lambda: _FakeClient(fake)
    )
    texts = [f"模式锁定测试文本第{i}段" for i in range(33)]
    vectors, mode = asyncio.run(embedding_module.embed_texts_with_fallback(texts))
    assert mode == "offline"
    assert len(vectors) == 33
    assert vectors == embed_texts_local(texts)
    # 33 条 → 3 批；两次尝试都在第 2 批失败（调用序 2、4）。
    assert len(fake.calls) == 4


# ---------------------------------------------------------------------------
# 查询路径与空输入
# ---------------------------------------------------------------------------


def test_embed_query_with_fallback_both_modes(
    monkeypatch: pytest.MonkeyPatch, offline_embedding: None
) -> None:
    """查询路径：在线成功返回在线向量；不可用降级本地。"""
    _install_fake_client(monkeypatch, _ok_handler)
    vector, mode = asyncio.run(embedding_module.embed_query_with_fallback("什么是过拟合"))
    assert mode == "online"
    assert vector == [0.0]

    monkeypatch.setattr(
        embedding_module,
        "get_embedding_client",
        _raise_bizexception,
    )
    vector, mode = asyncio.run(embedding_module.embed_query_with_fallback("什么是过拟合"))
    assert mode == "offline"
    assert vector == embed_texts_local(["什么是过拟合"])[0]


def _raise_bizexception() -> Any:
    """抛配置缺失异常的假工厂。"""
    raise BizException(3000, "AI 服务未配置", http_status=502)


def test_empty_texts_short_circuit(monkeypatch: pytest.MonkeyPatch) -> None:
    """空文本列表：直接返回 ([], offline)，不触发在线调用。"""
    fake = _install_fake_client(monkeypatch, _ok_handler)
    vectors, mode = asyncio.run(embedding_module.embed_texts_with_fallback([]))
    assert vectors == []
    assert mode == "offline"
    assert fake.calls == []