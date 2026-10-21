"""RAG 问答纯函数单测（tasks.md 9.1，design.md 2.7.1-A）。

覆盖：意图判断矩阵 / 阈值过滤（含 monkeypatch 阈值）/ RAG_MIN_SCORE
配置（空串回退 + 非法值拒绝）/ Prompt 三模板组装（有据含第二道
防线逐字指令、无据含固定句式、chat 模板禁句式）——全部无 IO。
"""

from __future__ import annotations

from typing import Any

import pytest
from pydantic import ValidationError

from app.core.config import Settings, settings
from app.rag.qa import (
    build_qa_messages,
    classify_intent,
    filter_sources_by_threshold,
)

# 第二道防线逐字指令（裁决 #12，模板一规则 3）。
_DEFENSE_LINE = "如果检索片段与问题无关，直接说明知识库中没有相关内容，不要强行拼接"

# 无据固定句式（spec 5.3.1 规则 2，模板二规则 1 逐字锁定）。
_UNGROUNDED_SENTENCE = "你的知识库中没有找到相关内容，以下为基于通用知识的回答"


# ---------------------------------------------------------------------------
# 意图判断（spec 5.1.1 规则 7 R3 口径）
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "question",
    [
        "你好",
        "您好",
        "谢谢",
        "你是谁",
        "这个系统是干嘛的",
        "hello",
        "HELLO",
        "嗨",
        "拜拜",
        "辛苦了",
        "谢谢！",
        "早上好。",
        "这个平台是做什么的",
    ],
)
def test_classify_intent_chat(question: str) -> None:
    """问候 / 感谢告别 / 元问题 → intent=chat。"""
    assert classify_intent(question) == "chat"


@pytest.mark.parametrize(
    "question",
    [
        "什么是 Transformer",
        "Dijkstra 算法是什么",
        "你好，请问什么是 SVM",
        "贝叶斯公式怎么用",
        "过拟合怎么解决",
    ],
)
def test_classify_intent_knowledge(question: str) -> None:
    """知识型问题（含混入问候词的复合句）→ intent=knowledge。"""
    assert classify_intent(question) == "knowledge"


# ---------------------------------------------------------------------------
# 阈值过滤（spec 5.3.1 规则 1/3；验收 D9 第一段）
# ---------------------------------------------------------------------------
def _hit(score: float) -> dict[str, Any]:
    return {"content": "片段", "source_title": "标题", "score": score}


def test_threshold_filter_default_keeps_above() -> None:
    """默认 0.55：高于阈值保留、低于阈值丢弃，is_grounded=True。"""
    filtered, is_grounded = filter_sources_by_threshold(
        [_hit(0.733), _hit(0.572), _hit(0.533)]
    )
    assert [h["score"] for h in filtered] == [0.733, 0.572]
    assert is_grounded is True


def test_threshold_filter_default_all_below() -> None:
    """默认 0.55：最高分低于阈值 → ([], False)（无据）。"""
    filtered, is_grounded = filter_sources_by_threshold([_hit(0.533), _hit(0.484)])
    assert filtered == []
    assert is_grounded is False


def test_threshold_filter_empty_input() -> None:
    """空输入 → ([], False)。"""
    assert filter_sources_by_threshold([]) == ([], False)


def test_threshold_filter_boundary_equal_kept() -> None:
    """score 恰等于阈值（>= 语义）保留。"""
    filtered, is_grounded = filter_sources_by_threshold([_hit(0.55)])
    assert len(filtered) == 1
    assert is_grounded is True


def test_threshold_filter_lowered_threshold(monkeypatch: pytest.MonkeyPatch) -> None:
    """monkeypatch RAG_MIN_SCORE=0.30 后 0.484 保留（D9 第一段）。"""
    monkeypatch.setattr(settings, "RAG_MIN_SCORE", 0.30)
    filtered, is_grounded = filter_sources_by_threshold([_hit(0.484)])
    assert [h["score"] for h in filtered] == [0.484]
    assert is_grounded is True


# ---------------------------------------------------------------------------
# RAG_MIN_SCORE 配置（spec 4.4 规则 2；tasks.md 1.1）
# ---------------------------------------------------------------------------
_TEST_SECRET = "unit-test-secret-0123456789abcdef0123456789abcdef"


def test_config_rag_min_score_default() -> None:
    """未配置时默认 0.55。"""
    s = Settings(JWT_SECRET=_TEST_SECRET)
    assert s.RAG_MIN_SCORE == 0.55


def test_config_rag_min_score_empty_fallback() -> None:
    """留空（init 空串 / None）回退 0.55，不为 0 或 None。"""
    assert Settings(JWT_SECRET=_TEST_SECRET, RAG_MIN_SCORE="").RAG_MIN_SCORE == 0.55
    assert Settings(JWT_SECRET=_TEST_SECRET, RAG_MIN_SCORE=None).RAG_MIN_SCORE == 0.55
    assert Settings(JWT_SECRET=_TEST_SECRET, RAG_MIN_SCORE="  ").RAG_MIN_SCORE == 0.55


def test_config_rag_min_score_env_empty_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """环境变量为空串时回退 0.55（契约 §2「留空回退默认」）。"""
    monkeypatch.setenv("RAG_MIN_SCORE", "")
    assert Settings().RAG_MIN_SCORE == 0.55


def test_config_rag_min_score_env_override(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """环境变量合法值（0.30）生效。"""
    monkeypatch.setenv("RAG_MIN_SCORE", "0.30")
    assert Settings().RAG_MIN_SCORE == 0.30


@pytest.mark.parametrize("bad", ["1.5", "-0.1", "2", "-1"])
def test_config_rag_min_score_invalid_rejected(bad: str) -> None:
    """非法值（>1 / 负数）→ 配置加载失败。"""
    with pytest.raises(ValidationError):
        Settings(JWT_SECRET=_TEST_SECRET, RAG_MIN_SCORE=bad)


# ---------------------------------------------------------------------------
# Prompt 三模板组装（spec 5.1.1 规则 4/5、5.3.1 规则 1/2/7；决策 D10）
# ---------------------------------------------------------------------------
_SOURCES = [
    {
        "content": "Transformer 的自注意力机制让每个位置直接关注所有位置。",
        "source_title": "机器学习基础 » Transformer",
        "score": 0.7331,
        "item_id": 5,
        "chunk_index": 2,
        "scope": "public",
    },
    {
        "content": "多头注意力将 QKV 投影到多个子空间并行计算。",
        "source_title": "机器学习基础 » 多头注意力",
        "score": 0.664,
        "item_id": 5,
        "chunk_index": 3,
        "scope": "public",
    },
]


def test_build_messages_grounded_template() -> None:
    """有据模板：含防线指令逐字、[n] 来源块、片段原文；不含固定句式。"""
    messages = build_qa_messages("什么是 Transformer", _SOURCES, "knowledge")
    assert [m["role"] for m in messages] == ["system", "user"]
    system = messages[0]["content"]
    assert messages[1]["content"] == "什么是 Transformer"
    # 第二道防线逐字指令（裁决 #12）。
    assert _DEFENSE_LINE in system
    # 引用编号与来源块（第 i 条格式）。
    assert "[1]（来源：机器学习基础 » Transformer，相似度 0.7331）" in system
    assert "[2]（来源：机器学习基础 » 多头注意力，相似度 0.664）" in system
    # 片段正文原文（不截断改写）。
    assert "Transformer 的自注意力机制让每个位置直接关注所有位置。" in system
    assert "多头注意力将 QKV 投影到多个子空间并行计算。" in system
    # 无据固定句式不出现在有据模板（R3 收窄）。
    assert _UNGROUNDED_SENTENCE not in system


def test_build_messages_ungrounded_template() -> None:
    """knowledge 无据模板：固定句式逐字且要求首句；不含片段块与防线指令。"""
    messages = build_qa_messages("法国大革命的历史背景", [], "knowledge")
    system = messages[0]["content"]
    assert _UNGROUNDED_SENTENCE in system
    assert "不得改写、不得省略、不得在该句之前添加任何内容" in system
    assert "禁止声称回答内容来自用户的知识库、笔记或文档" in system
    # 无片段可引用：不含知识库片段块与防线指令。
    assert "知识库片段" not in system
    assert _DEFENSE_LINE not in system
    assert messages[1]["content"] == "法国大革命的历史背景"


def test_build_messages_chat_template() -> None:
    """chat 模板（决策 D10）：模板三全文；不含固定句式、不含片段块。"""
    messages = build_qa_messages("你好", _SOURCES, "chat")
    system = messages[0]["content"]
    assert "用户正在进行日常问候或闲聊" in system
    assert "不要使用任何「知识库中没有找到相关内容」类的表述" in system
    # chat 类禁谈知识库检索结果。
    assert _UNGROUNDED_SENTENCE not in system
    assert "知识库片段" not in system
    assert messages[1]["content"] == "你好"


def test_build_messages_chat_ignores_sources() -> None:
    """chat 分流忽略 sources（传了 sources 也不进 Prompt）。"""
    messages = build_qa_messages("谢谢", _SOURCES, "chat")
    assert "自注意力" not in messages[0]["content"]


def test_build_messages_default_intent_is_knowledge() -> None:
    """intent 缺省值为 knowledge（兼容旧调用形态）。"""
    messages = build_qa_messages("什么是过拟合", [])
    assert _UNGROUNDED_SENTENCE in messages[0]["content"]