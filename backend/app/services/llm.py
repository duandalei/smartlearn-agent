"""LLM 基础服务（纯基础设施层）。

封装 OpenAI 兼容协议的异步客户端，提供对话（一次性 / 流式）能力。
**双配置组分客户端构造**（PROJECT_CONTEXT §2）：

- 对话组：``LLM_BASE_URL / LLM_API_KEY / LLM_MODEL``（如 DeepSeek）；
- 向量化组：``EMBEDDING_BASE_URL / EMBEDDING_API_KEY / EMBEDDING_MODEL``
  （如硅基流动），任一项为空时逐项回退对应 ``LLM_*`` 值；P4 仅交付
  构造能力、不发起调用（P8 由 ``rag/embedder`` 复用）。

约定：
- 所有调用**必须异步**，禁止阻塞事件循环；
- 密钥只从环境变量经 ``core/config.py`` 读取，禁止硬编码、禁止落日志；
- 服务类异常（超时 / 连接 / 鉴权 / 限流 / 上游 5xx）统一包装为
  ``BizException(3000, "AI 服务暂时不可用，请稍后重试", 502)``，
  原始异常与堆栈一律不外透（spec 5.4.1 规则 4）。

重试语义分层（design 2.2.3）：
- SDK 级 ``max_retries=1`` 只处理瞬态网络 / 连接错误（秒级快速重试）；
- 解析失败的业务级重试 1 次由 ``services/goal.py`` 拆解编排负责
  （附带纠错提示词）；服务类失败不做业务级重试，避免最坏情形
  90s × 2 的成倍等待。
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator, Sequence
from typing import TypedDict

import openai
from openai import AsyncOpenAI

from app.core.config import settings
from app.core.response import CODE_LLM_FAILED, BizException

logger = logging.getLogger(__name__)

# LLM 调用统一超时（秒）：与前端拆解请求 90s 超时对齐（spec 4.1 规则 5）。
_LLM_TIMEOUT_SECONDS: float = 90.0

# SDK 级瞬态错误快速重试次数（仅网络 / 连接类）。
_SDK_MAX_RETRIES: int = 1


class ChatMessage(TypedDict):
    """OpenAI chat 协议消息。

    Attributes:
        role: "system" | "user" | "assistant"。
        content: 消息文本。
    """

    role: str
    content: str


# ---------------------------------------------------------------------------
# 客户端构造（懒加载模块级单例，两组分开构造）
# ---------------------------------------------------------------------------
_chat_client: AsyncOpenAI | None = None
_embedding_client: AsyncOpenAI | None = None


def get_chat_client() -> AsyncOpenAI:
    """获取对话组客户端（懒加载单例）。

    只读 ``LLM_BASE_URL / LLM_API_KEY / LLM_MODEL`` 原始字段构造，
    **不使用**向量化组配置；三项任一为空（未配置）时抛业务异常。

    Returns:
        AsyncOpenAI: 对话组异步客户端（timeout=90s，max_retries=1）。

    Raises:
        BizException: code=3000 / HTTP 502，LLM 对话组配置缺失时抛出。
    """
    global _chat_client
    if _chat_client is None:
        base_url = settings.LLM_BASE_URL.strip()
        api_key = settings.LLM_API_KEY.strip()
        model = settings.LLM_MODEL.strip()
        if not base_url or not api_key or not model:
            raise BizException(
                CODE_LLM_FAILED,
                "AI 服务未配置，请联系管理员或检查环境变量",
                http_status=502,
            )
        _chat_client = AsyncOpenAI(
            base_url=base_url,
            api_key=api_key,
            timeout=_LLM_TIMEOUT_SECONDS,
            max_retries=_SDK_MAX_RETRIES,
        )
    return _chat_client


def get_embedding_client() -> AsyncOpenAI:
    """获取向量化组客户端（懒加载单例）。

    只读 ``embedding_*_effective`` 派生属性构造（EMBEDDING_* 为空时
    逐项回退 LLM_*）；发生回退时记 debug 日志（仅记录「某项发生回退
    与目标值」，禁止密钥明文）。**P4 仅构造不调用**，供 P8 rag/embedder
    复用（design 2.2.3）。

    Returns:
        AsyncOpenAI: 向量化组异步客户端（timeout=90s，max_retries=1）。

    Raises:
        BizException: code=3000 / HTTP 502，向量化生效配置三项任一
            为空时抛出（与对话组同口径，便于 P8 提前暴露配置问题）。
    """
    global _embedding_client
    if _embedding_client is None:
        base_url = settings.embedding_base_url_effective
        api_key = settings.embedding_api_key_effective
        model = settings.embedding_model_effective
        if not base_url or not api_key or not model:
            raise BizException(
                CODE_LLM_FAILED,
                "AI 服务未配置，请联系管理员或检查环境变量",
                http_status=502,
            )
        if not settings.EMBEDDING_BASE_URL.strip():
            logger.debug("Embedding base_url 未配置，回退使用 LLM_BASE_URL")
        if not settings.EMBEDDING_API_KEY.strip():
            logger.debug("Embedding api_key 未配置，回退使用 LLM_API_KEY")
        if not settings.EMBEDDING_MODEL.strip():
            logger.debug(
                "Embedding 模型未配置，回退使用 LLM_MODEL: %s", model
            )
        _embedding_client = AsyncOpenAI(
            base_url=base_url,
            api_key=api_key,
            timeout=_LLM_TIMEOUT_SECONDS,
            max_retries=_SDK_MAX_RETRIES,
        )
    return _embedding_client


def reset_clients() -> None:
    """清空缓存的客户端单例。

    仅供测试注入 mock 配置后重建使用，业务代码不得调用。
    """
    global _chat_client, _embedding_client
    _chat_client = None
    _embedding_client = None


# ---------------------------------------------------------------------------
# 对话能力
# ---------------------------------------------------------------------------
# 服务类异常统一捕获清单：超时 / 连接 / 鉴权 / 限流 / 上游 4xx-5xx。
# APIStatusError 为 AuthenticationError / RateLimitError / InternalServerError /
# BadRequestError 的共同基类，一并显式列出以便与 design 2.2.3 对齐。
_SERVICE_ERRORS: tuple[type[Exception], ...] = (
    openai.APITimeoutError,
    openai.APIConnectionError,
    openai.AuthenticationError,
    openai.RateLimitError,
    openai.InternalServerError,
    openai.APIStatusError,
    openai.BadRequestError,
)


async def chat(messages: Sequence[ChatMessage]) -> str:
    """一次性对话：返回首选项完整文本。

    Args:
        messages: 消息列表（system / user / assistant）。

    Returns:
        str: ``choices[0].message.content``；上游返回 None 时返回 ``""``。

    Raises:
        BizException: code=3000 / HTTP 502，服务类失败（超时、连接、
            鉴权、限流、上游 4xx/5xx）或对话组配置缺失时抛出；
            原始异常与堆栈不外透（日志仅记异常类型与摘要）。
    """
    try:
        response = await get_chat_client().chat.completions.create(
            model=settings.LLM_MODEL.strip(),
            messages=list(messages),
        )
    except BizException:
        raise
    except _SERVICE_ERRORS as exc:
        logger.warning(
            "LLM 服务类失败: 类型=%s 摘要=%s", type(exc).__name__, str(exc)[:200]
        )
        raise BizException(
            CODE_LLM_FAILED,
            "AI 服务暂时不可用，请稍后重试",
            http_status=502,
        ) from None
    content = response.choices[0].message.content
    return content if content is not None else ""


async def chat_stream(messages: Sequence[ChatMessage]) -> AsyncIterator[str]:
    """流式对话：逐片段 yield 文本增量。

    连接中断时 try/finally 安全结束迭代并释放资源，由上层决定提示；
    调用前异常包装同 :func:`chat`。P4 无调用方，作为独立基础能力
    交付，供后续 Agent 对话（SSE 流式）复用（spec 5.4.1 规则 3）。

    Args:
        messages: 消息列表（system / user / assistant）。

    Yields:
        str: 每个 chunk 的 ``delta.content``（跳过空片段）。

    Raises:
        BizException: code=3000 / HTTP 502，服务类失败或配置缺失时抛出。
    """
    try:
        stream = await get_chat_client().chat.completions.create(
            model=settings.LLM_MODEL.strip(),
            messages=list(messages),
            stream=True,
        )
    except BizException:
        raise
    except _SERVICE_ERRORS as exc:
        logger.warning(
            "LLM 服务类失败(stream): 类型=%s 摘要=%s",
            type(exc).__name__,
            str(exc)[:200],
        )
        raise BizException(
            CODE_LLM_FAILED,
            "AI 服务暂时不可用，请稍后重试",
            http_status=502,
        ) from None
    try:
        async for chunk in stream:
            delta = chunk.choices[0].delta.content if chunk.choices else None
            if delta:
                yield delta
    finally:
        # 连接中断（客户端断开等）时安全结束迭代并释放上游资源。
        await stream.close()

# ---------------------------------------------------------------------------
# Agent 专用流式 + function calling（P11 追加区，design 2.4.2 / 裁决 #4）
# ---------------------------------------------------------------------------
# 既有 ChatMessage / get_chat_client / chat / chat_stream / 客户端构造区
# 契约零改动（P9 问答与 P4 目标拆解依赖，spec §4.5 规则 1）；本区仅在
# 文件末尾追加。模块定位不变：纯传输层——收 OpenAI 协议 dict 消息，
# 发结构化分片（AgentStreamPart）；消息序列的结构合法性由
# app/agent/core.py 的构造逻辑单点保证，本模块不定义业务消息语义。
from typing import Any  # noqa: E402 - 追加区独立 import（纯追加铁律：不触碰文件头部既有 import 行）

AgentTextDelta = TypedDict("AgentTextDelta", {"content": str})
AgentReasoningDelta = TypedDict("AgentReasoningDelta", {"reasoning": str})
AgentRoundResult = TypedDict(
    "AgentRoundResult",
    {"tool_calls": list[dict[str, Any]], "finish_reason": str},
)
#: Agent 流式分片三形态可辨识联合（design 2.2.2-(8)）：core.py 以键
#: 存在性判别——``"content" in part`` → 文本增量；``"reasoning" in
#: part`` → 推理增量；其余为轮终聚合块 AgentRoundResult（每轮流恰产
#: 出一次，流末聚合）。
AgentStreamPart = AgentTextDelta | AgentReasoningDelta | AgentRoundResult


async def agent_chat_stream(
    messages: Sequence[dict[str, Any]],
    tools: Sequence[dict[str, Any]] | None = None,
    max_tokens: int = 2048,
) -> AsyncIterator[AgentStreamPart]:
    """Agent 专用流式对话：function calling + 文本 / 推理增量（design 2.4.2）。

    与既有 :func:`chat_stream` 的差异：携带 ``tools``（TOOLS_SCHEMA
    直传）与 ``max_tokens``（Agent 循环锁定 2048——P10 实测 300 时
    finish=length 截断、工具调用参数不完整，裁决 #9），并把流式
    tool_calls 分片聚合为轮终块。

    请求构造：``tools=None``（O5 总结调用路径）时**省略 tools /
    tool_choice 两键**——模型协议上无法发起 tool_call（决策 A7）。
    创建段异常沿用 ``_SERVICE_ERRORS`` 包装口径；**迭代段异常不包装**
    （与 chat_stream 一致，由 core.py 双兜：BizException 用其
    code/message、原始异常按已推 delta 区分文案）。

    Args:
        messages: OpenAI 协议消息序列（system / user / assistant /
            tool 各形态，结构由调用方 core.py 单点保证）。
        tools: function calling 工具描述（TOOLS_SCHEMA 直传）；
            None 时请求体不带 tools 键（禁工具总结调用）。
        max_tokens: 单次调用生成上限；Agent 循环固定传 2048。

    Yields:
        AgentStreamPart: 三形态分片——AgentTextDelta（文本增量，
            实时）、AgentReasoningDelta（推理增量，实时）、
            AgentRoundResult（流末聚合：tool_calls 非流式形态 +
            finish_reason，缺省 ``"stop"``）。

    Raises:
        BizException: code=3000 / HTTP 502，创建段服务类失败或
            对话组配置缺失时抛出；原始异常与堆栈不外透。
    """
    request_kwargs: dict[str, Any] = {
        "model": settings.LLM_MODEL.strip(),
        "messages": list(messages),
        "stream": True,
        "max_tokens": max_tokens,
    }
    if tools is not None:
        request_kwargs["tools"] = tools
        request_kwargs["tool_choice"] = "auto"
    try:
        stream = await get_chat_client().chat.completions.create(**request_kwargs)
    except BizException:
        raise
    except _SERVICE_ERRORS as exc:
        logger.warning(
            "LLM 服务类失败(agent_stream): 类型=%s 摘要=%s",
            type(exc).__name__,
            str(exc)[:200],
        )
        raise BizException(
            CODE_LLM_FAILED,
            "AI 服务暂时不可用，请稍后重试",
            http_status=502,
        ) from None

    # tool_calls 流式增量聚合状态（design 2.4.2-B）：
    # - pending：index → {id, name, args_parts} 分桶。**按 index 分桶
    #   是正确性核心**——一轮可含多个并行 tool_call，各调用的 name 与
    #   arguments 分片以 index 区分交错到达，同 index 累加、跨 index
    #   不串（真实 DeepSeek 流下 name 与 arguments 分散在多个 chunk）；
    # - last_index：兼容不回 index 的端点（缺失时沿用最近 index）。
    pending: dict[int, dict[str, Any]] = {}
    last_index: int = 0
    final_finish: str | None = None
    try:
        async for chunk in stream:
            if not chunk.choices:
                continue
            choice = chunk.choices[0]
            delta = choice.delta
            if delta is None:
                continue
            content = getattr(delta, "content", None)
            if content:
                yield {"content": content}
            reasoning = getattr(delta, "reasoning_content", None)
            if reasoning:
                yield {"reasoning": reasoning}
            tool_call_deltas = getattr(delta, "tool_calls", None)
            if tool_call_deltas:
                for tc in tool_call_deltas:
                    idx = getattr(tc, "index", None)
                    if idx is None:
                        idx = last_index
                    last_index = idx
                    bucket = pending.setdefault(
                        idx, {"id": None, "name": None, "args_parts": []}
                    )
                    tc_id = getattr(tc, "id", None)
                    if tc_id:
                        bucket["id"] = tc_id
                    function = getattr(tc, "function", None)
                    if function is not None:
                        fn_name = getattr(function, "name", None)
                        if fn_name:
                            bucket["name"] = fn_name
                        fn_args = getattr(function, "arguments", None)
                        if fn_args:
                            # arguments 是字符串增量累加（OpenAI 协议流式
                            # 形态），聚合完成才是完整 JSON 字符串——解析
                            # 职责在上层 core.py（算法要点②）。
                            bucket["args_parts"].append(fn_args)
            if choice.finish_reason:
                final_finish = choice.finish_reason
    finally:
        # 连接中断（客户端断开等）时安全结束迭代并释放上游资源。
        await stream.close()

    # 流末聚合：按 index 升序还原 LLM 的调用顺序（协议保证分片按调用
    # 序发送）。防御：finish_reason 缺失默认 "stop"（部分兼容端末包
    # 行为差异兜底）；id 缺失空串（DeepSeek 实际必回 id）。
    tool_calls: list[dict[str, Any]] = [
        {
            "id": bucket["id"] or "",
            "type": "function",
            "function": {
                "name": bucket["name"] or "",
                "arguments": "".join(bucket["args_parts"]),
            },
        }
        for _, bucket in sorted(pending.items())
    ]
    yield {
        "tool_calls": tool_calls,
        "finish_reason": final_finish or "stop",
    }