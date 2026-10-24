"""RAG 问答纯函数层：意图判断 / 阈值过滤 / Prompt 三模板组装。

设计定位（design.md 2.4.1–2.4.3 / 决策 D1/D5）：本模块为**纯函数**，
无 IO、无事务、不 import services / api（rag 包单向被依赖的静态
可验证性）；``ChatMessage`` 在本模块重复声明而非 import
``services.llm``（决策 D5：TypedDict 纯类型重复成本趋零，换取
rag 层零 services import）。

三模板分流（裁定①引申 / 决策 D10）：
- 模板一（有据）：含第二道防线逐字指令（裁决 #12）——阈值管
  「有没有召回」，Prompt 管「召回的能不能用」；
- 模板二（knowledge 无据）：固定句式逐字锁定（spec 5.3.1 规则 2，
  R3 收窄：句式**仅**出现在 knowledge 无据回答中）；
- 模板三（chat）：显式禁止任何「知识库中没有找到相关内容」类
  表述——本次未做知识库检索，若沿用无据句式会出现「文字说无
  相关内容、样式却正常聊天」的自相矛盾。

意图判断（裁决 #9，宁缺毋滥）：误判「知识型为闲聊」的代价是丢失
检索（有据变无据，伤演示），误判「闲聊为知识型」的代价只是一次
多余检索（无害），故规则集只收录高置信模式。
"""

from __future__ import annotations

import re
from typing import Any, Literal, TypedDict

from app.core.config import settings

# 问题意图：chat（非知识型，跳过检索）/ knowledge（知识型，走检索）。
QaIntent = Literal["chat", "knowledge"]

# ---------------------------------------------------------------------------
# 意图判断（design.md 2.4.1 规则集，预编译正则）
# ---------------------------------------------------------------------------
# 四类高置信小谈模式：纯问候 / 感谢告别 / 助手身份元问题 / 系统元问题。
# 前两类 ^...$ 锚定整句（仅问候词 + 语气符号构成）；后两类 search
# 包含即命中（问句中含该表述即视为元问题）。
_SMALL_TALK_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(
        r"^(你好|您好|嗨|哈喽|hi|hello|hey|早上好|上午好|中午好|下午好|晚上好|早安|晚安)[!！。.~～呀啊哦哈]*$"
    ),
    re.compile(
        r"^(谢谢|多谢|感谢|辛苦了|thanks|thank you|thx|再见|拜拜|bye|goodbye)[!！。.~～]*$"
    ),
    re.compile(
        r"你是谁|你叫什么|你是什么(模型|AI|机器人|东西)|介绍一下你自己|你能(做|帮)什么"
    ),
    re.compile(r"(这个|本)?(系统|网站|平台|软件|应用)是(什么|干嘛|做什么)(的)?"),
)


def classify_intent(question: str) -> QaIntent:
    """判断问题意图：明显非知识型返回 ``"chat"``，否则 ``"knowledge"``。

    纯字符串操作、无外部依赖、不抛异常；调用侧（qa_stream）仍以
    try/except 包裹，任何异常一律返回 ``"knowledge"``（退化为始终
    检索，裁决 #9 可关停兜底）。清空 ``_SMALL_TALK_PATTERNS`` 数组
    即恢复全量检索，无需改调用方。

    返回值三处消费（裁定①）：qa_stream 跳检依据 / done 事件
    ``data.intent`` 透出 / qa_history ``intent`` 落库。

    Args:
        question: 用户问题原文（入参已 strip 非空）。

    Returns:
        QaIntent: ``"chat"`` 或 ``"knowledge"``。
    """
    text = question.strip().lower()
    return (
        "chat" if any(pattern.search(text) for pattern in _SMALL_TALK_PATTERNS)
        else "knowledge"
    )


# ---------------------------------------------------------------------------
# ChatMessage 类型（决策 D5：本模块重复声明，不 import services.llm）
# ---------------------------------------------------------------------------
class ChatMessage(TypedDict):
    """LLM 对话消息（与 ``services/llm.ChatMessage`` 结构兼容）。"""

    role: str
    content: str


# ---------------------------------------------------------------------------
# 阈值过滤（design.md 2.4.2，无据判定的唯一实现）
# ---------------------------------------------------------------------------
def filter_sources_by_threshold(
    results: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], bool]:
    """按 ``RAG_MIN_SCORE`` 过滤检索命中，返回 (有效 sources, is_grounded)。

    与 spec 5.3.1 规则 1 的等价性：规则表述为「检索结果为空，或
    最高 score < T → 无据」；本实现「逐条过滤后为空 → 无据」。
    ``filtered`` 非空 ⇔ 存在某条 ``score ≥ T`` ⇔ ``max(score) ≥ T``，
    二者等价。逐条过滤（而非仅判最高分）的额外收益：**有据场景下
    低于阈值的噪声条目也被挡在 sources 之外**，使引用编号与「有效
    片段」严格一一对应，与第二道防线的分层语义一致。

    阈值读取点集中于本函数（``settings.RAG_MIN_SCORE`` 单一读取点），
    qa_stream 不重复读配置——保证 D9 验收「临时调低/复原」只经
    ``.env`` + 重启生效。只在 ``intent=knowledge`` 路径被调用
    （chat 路径跳过检索与过滤）；``is_grounded`` 表达「回答是否基于
    知识库检索」，与 ``intent``（「问题是否走了检索路径」）分工见
    design.md 2.4.2（裁定①核心）。

    Args:
        results: ``search_knowledge`` 返回的 results（每条含 score）。

    Returns:
        tuple[list[dict[str, Any]], bool]:
            (过滤后条目列表, 是否有据)；results 为空时返回
            ``([], False)``。
    """
    filtered = [r for r in results if r["score"] >= settings.RAG_MIN_SCORE]
    return filtered, len(filtered) > 0


# ---------------------------------------------------------------------------
# Prompt 三模板（design.md 2.4.3 全文，集中本模块单一位置——spec 4.4 规则 3）
# ---------------------------------------------------------------------------
_GROUNDED_SYSTEM_TEMPLATE: str = """你是「彭城智学」的 AI 学习助手，基于学生本人的个人知识库回答学习问题。

回答规则：
1. 仅依据下方提供的知识库片段回答问题；引用来源时使用 [1]、[2] 形式的编号标注，编号与片段的排列顺序一一对应。
2. 禁止编造用户笔记或知识库中不存在的内容；禁止在回答中使用「根据你的笔记」「你的文档里写道」等有据口吻来陈述片段中并不存在的内容。
3. 如果检索片段与问题无关，直接说明知识库中没有相关内容，不要强行拼接。
4. 回答使用简体中文，条理清晰、结构完整，适合高校学生学习阅读。

知识库片段（按相似度从高到低排列）：
{context_block}"""

_UNGROUNDED_SYSTEM_TEMPLATE: str = """你是「彭城智学」的 AI 学习助手。当前知识库中没有检索到与问题相关的内容，请基于通用知识回答。

回答规则：
1. 回答的第一句必须逐字为「你的知识库中没有找到相关内容，以下为基于通用知识的回答」，不得改写、不得省略、不得在该句之前添加任何内容。
2. 固定句式之后，基于你自己的通用知识完整回答问题。
3. 禁止声称回答内容来自用户的知识库、笔记或文档。
4. 回答使用简体中文，条理清晰、结构完整，适合高校学生学习阅读。"""

_CHAT_SYSTEM_TEMPLATE: str = """你是「彭城智学」的 AI 学习助手。用户正在进行日常问候或闲聊，请自然、友好地回应。

回答规则：
1. 直接回应问候或闲聊内容，保持简洁友好，可以顺带说明你能提供的学习帮助（如基于知识库的问答、检索来源展示等）。
2. 不要谈论知识库检索结果，不要使用任何「知识库中没有找到相关内容」类的表述——本次没有进行知识库检索，该表述不适用。
3. 回答使用简体中文，篇幅简短（问候类一般一两句话即可）。"""


def build_qa_messages(
    question: str,
    sources: list[dict[str, Any]],
    intent: QaIntent = "knowledge",
) -> list[ChatMessage]:
    """按意图与有据性分流三模板，组装单轮对话消息列表。

    分流规则（design.md 2.4.3）：
    - ``intent="chat"`` → 模板三（sources 恒为空，忽略该参数）；
    - ``intent="knowledge"`` 且 sources 非空 → 模板一（拼接
      context_block）；
    - ``intent="knowledge"`` 且 sources 为空 → 模板二（固定句式）。

    返回 ``[system, user]`` 两元素（单轮、无历史上下文，裁决 #6）；
    片段正文不截断改写（spec 6.2-3，content 原文进 Prompt，与
    sources 事件载荷同源）。

    Args:
        question: 用户问题原文。
        sources: 阈值过滤后的有效来源条目（每条含
            content / source_title / score）。
        intent: 问题意图（``classify_intent`` 的返回值）。

    Returns:
        list[ChatMessage]: 两元素消息列表（system + user）。
    """
    if intent == "chat":
        system_content = _CHAT_SYSTEM_TEMPLATE
    elif sources:
        context_block = "".join(
            f"[{i}]（来源：{source['source_title']}，相似度 {source['score']}）\n"
            f"{source['content']}\n\n"
            for i, source in enumerate(sources, start=1)
        )
        system_content = _GROUNDED_SYSTEM_TEMPLATE.format(
            context_block=context_block
        )
    else:
        system_content = _UNGROUNDED_SYSTEM_TEMPLATE
    return [
        {"role": "system", "content": system_content},
        {"role": "user", "content": question},
    ]