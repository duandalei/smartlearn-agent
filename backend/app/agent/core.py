"""Agent 对话主循环（ReAct + Function Calling，SSE 事件编排核心）。

职责（design 2.4.1）：组装 System Prompt（含用户档案 / 当前目标 /
最近学习概况预取）→ 携带 TOOLS_SCHEMA 调用 LLM → 若返回 tool_calls
则经 TOOL_MAP 执行、完整结果回灌、继续循环 → 最多 6 轮（超出优雅
收尾）→ 全程以 SSE 事件流推送（thinking / tool_call / tool_result /
delta / done / error）。

边界红线：本模块**不直接访问学习业务数据**（只经 ``TOOL_MAP``
派发——PROJECT_CONTEXT §4 铁律）；会话/消息持久化经 ``memory``
（组件自有元数据，裁决 #5）。SSE 事件 dict 由本模块产出，文本格式
化在 api 层（决策 A1，契约 §4「services/agent 禁拼接 HTTP 响应」）。

O8 常量引用铁律（design 2.4.1-C）：预算 / 轮次常量全部模块级定义、
函数体内以模块常量名直接引用（禁默认参数捕获、禁模块加载期求值）
——``monkeypatch.setattr("app.agent.core.TOTAL_BUDGET_S", ...)`` 才能
生效（D7 测试正确性的静态前提）。

回链：design 2.1.2（常量表）/ 2.1.3（状态机 / O5 收尾 / CP 检查点 /
OB-1 观测）/ 2.4.1（主循环七步）；spec §5.1 / §5.3 / §6.2。
"""

from __future__ import annotations

import json
import logging
import time
from collections.abc import AsyncIterator
from typing import Any

from sqlalchemy.orm import Session

from app.agent import memory
from app.agent.prompts import build_system_prompt
from app.agent.registry import TOOLS_SCHEMA, TOOL_MAP
from app.core.response import CODE_LLM_FAILED, BizException
from app.models.agent import AgentConversation
from app.services import llm

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 常量表（design 2.1.2——全部锁定值 + 注释实测依据，禁止环境变量化，
# 对齐 P10 SLOW_TOOL_MS 锁定惯例）
# ---------------------------------------------------------------------------
#: 轮次上限。P10 实测：deepseek-flash 有「过度调用」倾向（建完任务
#: 后仍继续查两次确认）；spec §4.1 规则 3 锁定 6 轮。
MAX_ROUNDS: int = 6

#: 循环总预算（秒）。裁决 #8：一次 /agent/chat 从受理到终结事件 ≤ 60s
#: （含全部轮次 LLM 调用与工具执行；单轮 60s 最坏 6 轮 ≥360s 与
#: 「不空转」意图相悖）。O8：模块常量，仅测试可 monkeypatch。
TOTAL_BUDGET_S: float = 60.0

#: O5 保护条件：进入收尾时剩余预算 < 15 秒则跳过总结 LLM 调用走模板
#: 拼接——第 6 轮结束后的总结调用很可能直接撞上 60s 上限，用户看到的
#: 将是超时错误而非收尾。
GRACEFUL_MIN_BUDGET_S: float = 15.0

#: 单次 LLM 调用 max_tokens。裁决 #9：≥1024 红线 + 为最终长总结留
#: 余量（P10 实测 300 时 finish=length 截断、工具调用参数不完整）。
MAX_TOKENS: int = 2048

#: tool_result 摘要截断长度（字符，序列化后计；任务书 SSE 契约）。
SUMMARY_TRUNCATE: int = 500

#: 多轮上下文窗口条数。O7 裁定：最近 20 条，成对边界截断禁孤儿
#: tool 消息。
CONTEXT_WINDOW: int = 20

#: 用户消息长度上限。O6 裁定：**独立于 P9 /chat/qa 的 500（两处各自
#: 定义、刻意不共用常量——问答是一句话，Agent 指令常带上下文）**；
#: schema 层 ``AGENT_MESSAGE_MAX_LEN`` 同值锁定（行内注释互相指认）。
MESSAGE_MAX_LEN: int = 2000

#: agent_messages.tool_name 列宽；非法工具名照存须截断。
TOOL_NAME_MAX_LEN: int = 50

#: agent_messages.tool_call_id 列宽；防御截断。
TOOL_CALL_ID_MAX_LEN: int = 64

#: 上下文体积观测阈值（R3 补充约束 3）：每轮 LLM 调用前统计本轮
#: messages 总字符数写 debug 日志，超过该值升 warning；**只观测不
#: 截断**——get_learning_records 单次 ≤100 条完整 JSON × 6 轮累积
#: 可能不知不觉膨胀，无此统计则「响应越来越慢」无法归因。
CONTEXT_LOG_WARN_CHARS: int = 30000

# SSE 事件类型字面量（spec §4.4 规则 3：前后端共用同一套字面量，
# core.py 单一来源）。
EVENT_THINKING: str = "thinking"
EVENT_TOOL_CALL: str = "tool_call"
EVENT_TOOL_RESULT: str = "tool_result"
EVENT_DELTA: str = "delta"
EVENT_DONE: str = "done"
EVENT_ERROR: str = "error"

# finish_reason 字面量（R2 补充约束 1：三值必须真实反映结束原因，
# 禁止一律报 normal——前端据此渲染差异化收尾样式）。
FINISH_NORMAL: str = "normal"
FINISH_MAX_ROUNDS: str = "max_rounds"
FINISH_TIMEOUT: str = "timeout"

#: O5 收尾指令（总结调用附加的 user 消息；tools 不传禁工具）。
_SUMMARIZE_INSTRUCTION: str = (
    "基于以上工具调用过程与结果，不要再调用任何工具，直接用中文"
    "分点生成最终总结回答，必须引用结果中的具体数字。"
)

#: 非法工具名兜底信封（spec §5.1.1 规则 8：不崩溃、回灌自纠）。
_TOOL_UNAVAILABLE: dict[str, str] = {"error": "该工具不可用"}

#: 工具执行未预期异常的第二道兜底信封（spec 5.3.3 场景 2）。
_TOOL_EXECUTION_FAILED: dict[str, str] = {"error": "工具执行失败，请稍后重试"}


# ---------------------------------------------------------------------------
# SSE 事件构造辅助（单一来源防散落拼 dict，design 2.4.1-A）
# ---------------------------------------------------------------------------
def _thinking_event(round_no: int) -> dict[str, Any]:
    """构造 thinking 轮次信号事件（每轮恰 1 条；决策 A6 两形态之一）。"""
    return {"type": EVENT_THINKING, "data": {"round": round_no}}


def _thinking_content_event(content: str) -> dict[str, Any]:
    """构造 thinking 推理增量事件（仅推理模型 reasoning_content 通道）。"""
    return {"type": EVENT_THINKING, "data": {"content": content}}


def _tool_call_event(
    call_id: str, name: str, arguments: dict[str, Any]
) -> dict[str, Any]:
    """构造 tool_call 事件（R2 补充约束 2：arguments 为解析后参数对象）。"""
    return {
        "type": EVENT_TOOL_CALL,
        "data": {"call_id": call_id, "name": name, "arguments": arguments},
    }


def _tool_result_event(
    call_id: str,
    name: str,
    ok: bool,
    elapsed_ms: int,
    summary: str,
    truncated: bool,
) -> dict[str, Any]:
    """构造 tool_result 事件（六字段：耗时与 ≤500 字摘要，SSE 契约）。"""
    return {
        "type": EVENT_TOOL_RESULT,
        "data": {
            "call_id": call_id,
            "name": name,
            "ok": ok,
            "elapsed_ms": elapsed_ms,
            "summary": summary,
            "truncated": truncated,
        },
    }


def _delta_event(text: str) -> dict[str, Any]:
    """构造 delta 事件（data 为字符串分片，任意轮文本增量实时转发）。"""
    return {"type": EVENT_DELTA, "data": text}


def _done_event(
    conversation_id: int,
    message_id: int | None,
    rounds: int,
    tool_call_count: int,
    finish_reason: str,
) -> dict[str, Any]:
    """构造 done 终结事件（五字段；finish_reason 三值真实反映）。"""
    return {
        "type": EVENT_DONE,
        "data": {
            "conversation_id": conversation_id,
            "message_id": message_id,
            "rounds": rounds,
            "tool_call_count": tool_call_count,
            "finish_reason": finish_reason,
        },
    }


def _error_event(code: int, message: str) -> dict[str, Any]:
    """构造 error 终结事件（与 done 互斥恰 1 次；受理后流内失败）。"""
    return {"type": EVENT_ERROR, "data": {"code": code, "message": message}}


# ---------------------------------------------------------------------------
# 内部辅助（观测 / 摘要 / 模板拼接）
# ---------------------------------------------------------------------------
def _log_context_size(
    messages: list[dict[str, Any]], conversation_id: int, round_no: int
) -> None:
    """OB-1 上下文体积观测（只观测不截断，design 2.1.3-F / 决策 A11）。

    位置：每轮 LLM 调用发起前（CP-1 通过后、thinking 之前）——OB 与
    CP 系列刻意区分：**CP 拦截调用，OB 只记录**，观测点对控制流零
    影响。口径：一次性序列化总长（含 role 等结构开销，量级观测足够，
    30k 字符级序列化毫秒以内）。观测信息不进 SSE 事件流（服务端运维
    信号）；**不得因此截断/修改回灌内容**（R3 明示，Agent 完整性优先）。
    """
    total_chars = len(json.dumps(messages, ensure_ascii=False))
    if total_chars > CONTEXT_LOG_WARN_CHARS:
        logger.warning(
            "agent_context_size conversation_id=%s round=%s chars=%s",
            conversation_id,
            round_no,
            total_chars,
        )
    else:
        logger.debug(
            "agent_context_size conversation_id=%s round=%s chars=%s",
            conversation_id,
            round_no,
            total_chars,
        )


def _summarize_result(result: dict[str, Any]) -> tuple[str, bool]:
    """生成 tool_result 摘要（≤500 字符截断，SSE 契约）。

    成功路径：完整结果序列化，超 ``SUMMARY_TRUNCATE`` 截断至 500 并
    置 truncated=True（**禁止把原始大 JSON 全量推给前端**）；失败路径
    （error 信封 / 非法工具名）：中文文案原样、truncated=False。完整
    结果仅回灌 LLM 与落库，不进 SSE。
    """
    if "error" in result:
        return str(result["error"]), False
    text = json.dumps(result, ensure_ascii=False)
    if len(text) > SUMMARY_TRUNCATE:
        return text[:SUMMARY_TRUNCATE], True
    return text, False


def _build_template_summary(collected: list[dict[str, str]]) -> str:
    """O5 模板拼接文案（分支②③共用，design 2.4.1-B-6）。

    Args:
        collected: 已获工具结果列表，每条 ``{"name": str, "summary": str}``。
    """
    if not collected:
        return "处理时间较长，暂未获取到足够信息，请稍后重试或换个问法。"
    lines = ["已为你查询到以下信息："]
    for item in collected:
        brief = item["summary"][:200]
        lines.append(f"- {item['name']}：{brief}")
    return "\n".join(lines)


def _log_completion(
    user_id: int,
    conversation_id: int,
    rounds: int,
    tool_call_count: int,
    finish_reason: str,
    elapsed_s: float,
) -> None:
    """收尾元数据日志（禁打印消息原文与回答全文——spec 4.3 规则 4）。"""
    logger.info(
        "agent_chat 完成: user_id=%s conversation_id=%s rounds=%s "
        "tool_call_count=%s finish_reason=%s 耗时=%.2fs",
        user_id,
        conversation_id,
        rounds,
        tool_call_count,
        finish_reason,
        elapsed_s,
    )


# ---------------------------------------------------------------------------
# O5 三分支优雅收尾（design 2.1.3-B 决策树逐弧）
# ---------------------------------------------------------------------------
async def _graceful_finish(
    messages: list[dict[str, Any]],
    collected: list[dict[str, str]],
    finish_reason: str,
    remaining: float,
    user_id: int,
) -> AsyncIterator[str]:
    """O5 收尾文本流（yield 文本分片；主循环包装为 delta 事件）。

    三分支降级链（design 2.1.3-B）：
    - 分支③ 模板拼接（零 LLM 调用）：``remaining < GRACEFUL_MIN_BUDGET_S``
      （O5 保护条件：剩余预算不足时总结调用很可能撞上 60s 上限）**或**
      触发源为 timeout（超时时剩余必为 0，必走模板——spec §5.1.1
      规则 6 后半句）；
    - 分支① 总结调用（预算充足）：tools 不传（协议禁工具）、不计轮次、
      不推 thinking；**防御：总结轮收到 tool_calls 非空时忽略取文本**
      （决策 A7）；
    - 分支② 降级模板拼接（总结调用失败）：无任何产出时以模板收尾
      （design「失败降级固定模板句」）；已有部分产出后中断时以已有
      文本收尾（追加模板会造成语义重复）。
    """
    if remaining < GRACEFUL_MIN_BUDGET_S or finish_reason == FINISH_TIMEOUT:
        yield _build_template_summary(collected)
        return

    summary_messages = messages + [
        {"role": "user", "content": _SUMMARIZE_INSTRUCTION}
    ]
    parts: list[str] = []
    try:
        async for part in llm.agent_chat_stream(
            summary_messages, tools=None, max_tokens=MAX_TOKENS
        ):
            if "content" in part:
                parts.append(part["content"])
                yield part["content"]
            # 推理增量与总结轮 tool_calls 均忽略（决策 A7 防御）。
    except BizException as exc:
        logger.warning(
            "O5 总结调用业务失败(降级模板): user_id=%s code=%s",
            user_id,
            exc.code,
        )
    except Exception as exc:  # noqa: BLE001 - 原始异常降级模板
        logger.warning(
            "O5 总结调用异常(降级): user_id=%s type=%s",
            user_id,
            type(exc).__name__,
        )
    if not parts:
        yield _build_template_summary(collected)


# ---------------------------------------------------------------------------
# 主循环生成器（design 2.4.1-B 七步 / 2.1.3-A 状态机的唯一实现）
# ---------------------------------------------------------------------------
async def agent_chat_stream(
    db: Session,
    user_id: int,
    conversation: AgentConversation,
    message: str,
) -> AsyncIterator[dict[str, Any]]:
    """Agent 对话主循环生成器：产出 SSE 事件 dict 流（非 SSE 文本）。

    主链路（design 2.4.1-B）：准备段（user 消息落库 + 窗口加载 +
    System Prompt 组装）→ 轮循环（CP-1 预算 → OB-1 观测 → thinking →
    LLM 流式消费 delta/推理增量/轮终聚合块）→ tool_calls 空则 normal
    自然结束（不经 O5——最后一轮文本本身就是回答，finish_reason
    判定表）；非空则工具执行段（CP-2 → tool_call 事件 → 派发 →
    tool_result 事件 → 完整结果回灌）→ 轮收口（成组落库 + messages
    追加）→ 第 7 轮或预算耗尽时 O5 优雅收尾（max_rounds / timeout）。

    LLM 调用经 ``llm.agent_chat_stream`` 模块属性访问（测试注入形态：
    monkeypatch ``app.services.llm.agent_chat_stream``，P9 同款）；
    工具一律经 ``TOOL_MAP`` 派发 ``(db, user_id, arguments)``（user_id
    取认证结果注入，spec §4.3 规则 2）。

    Args:
        db: 请求级数据库会话（生成器持有；P9 qa_stream 同款模式）。
        user_id: 当前认证用户 id（工具调用隔离边界）。
        conversation: 目标会话（ORM 对象；受理阶段已定位/新建并 commit）。
        message: 用户消息原文（入参已校验非空 ≤2000 字符）。

    Yields:
        dict[str, Any]: SSE 事件 dict（六事件契约，spec §5.6.2）；每个
        连接恰以 done 或 error 之一收尾。
    """
    started_at = time.monotonic()
    conversation_id = conversation.id

    # ① 准备段（design 2.4.1-B-1；决策 A2：user 消息落库在生成器
    # 首条语句——受理后立即，此后 error 终结也不回滚，裁决 #12）。
    try:
        memory.save_user_message(db, conversation, message)
    except Exception as exc:  # noqa: BLE001 - 双保险（memory 内部已消化，防 monkeypatch 注入异常抛穿）
        logger.warning(
            "user 消息落库异常(兜底): user_id=%s conversation_id=%s type=%s",
            user_id,
            conversation_id,
            type(exc).__name__,
        )
    history = memory.load_context_window(
        db, conversation, limit=CONTEXT_WINDOW
    )
    system_prompt = await build_system_prompt(db, user_id)
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": system_prompt}
    ] + history

    round_no = 1
    completed_rounds = 0
    tool_call_count = 0
    collected: list[dict[str, str]] = []
    has_delta = False

    def _remaining_budget() -> float:
        # O8：函数体直接引用模块常量（monkeypatch 生效前提）。
        return TOTAL_BUDGET_S - (time.monotonic() - started_at)

    while True:
        # CP-1 轮前检查（design 2.1.3-C）：轮次上限先于预算判定——
        # 第 7 轮永不存在（P10 过度调用防护）。
        if round_no > MAX_ROUNDS:
            finish_reason = FINISH_MAX_ROUNDS
            break
        if _remaining_budget() <= 0:
            finish_reason = FINISH_TIMEOUT
            break

        # OB-1 上下文体积观测（只观测不截断；CP-1 之后、thinking 之前）。
        _log_context_size(messages, conversation_id, round_no)

        yield _thinking_event(round_no)

        # ② 轮体：消费 LLM 流式响应（文本 / 推理增量实时转发；轮终
        # 聚合块在流末产出——design 2.4.2 聚合算法）。
        round_text_parts: list[str] = []
        round_tool_calls: list[dict[str, Any]] = []
        try:
            async for part in llm.agent_chat_stream(
                messages, tools=TOOLS_SCHEMA, max_tokens=MAX_TOKENS
            ):
                if "content" in part:
                    round_text_parts.append(part["content"])
                    has_delta = True
                    yield _delta_event(part["content"])
                elif "reasoning" in part:
                    yield _thinking_content_event(part["reasoning"])
                else:
                    round_tool_calls = part["tool_calls"]
        except BizException as exc:
            logger.warning(
                "agent_chat LLM 失败: user_id=%s conversation_id=%s "
                "round=%s code=%s",
                user_id,
                conversation_id,
                round_no,
                exc.code,
            )
            yield _error_event(exc.code, exc.message)
            return
        except Exception as exc:  # noqa: BLE001 - 迭代段原始异常（双兜）
            # 按「是否已推送 delta」区分场景文案（P9 同款口径）。
            error_text = (
                "回答生成中断，请重试"
                if has_delta
                else "AI 服务暂时不可用，请稍后重试"
            )
            logger.warning(
                "agent_chat LLM 流中断: user_id=%s conversation_id=%s "
                "round=%s type=%s has_delta=%s",
                user_id,
                conversation_id,
                round_no,
                type(exc).__name__,
                has_delta,
            )
            yield _error_event(CODE_LLM_FAILED, error_text)
            return

        # ③ 自然结束分支（normal）：不经 O5 收尾——最后一轮文本本身
        # 就是回答（finish_reason 判定表，R2 补充约束 1）。
        if not round_tool_calls:
            completed_rounds = round_no
            final_text = "".join(round_text_parts)
            try:
                message_id = memory.save_final_message(
                    db, conversation, final_text
                )
            except Exception as exc:  # noqa: BLE001 - 双保险（防注入异常抛穿）
                logger.warning(
                    "最终消息落库异常(兜底): user_id=%s conversation_id=%s type=%s",
                    user_id,
                    conversation_id,
                    type(exc).__name__,
                )
                message_id = None
            yield _done_event(
                conversation_id,
                message_id,
                completed_rounds,
                tool_call_count,
                FINISH_NORMAL,
            )
            _log_completion(
                user_id,
                conversation_id,
                completed_rounds,
                tool_call_count,
                FINISH_NORMAL,
                time.monotonic() - started_at,
            )
            return

        # ④ 工具执行段（design 2.4.1-B-4；契约偏序 tool_call* →
        # tool_result*，spec 5.3.1 规则 2 / 契约细则 2）：两遍式——
        # 第一遍逐条「CP-2 检查 → tool_call 事件」（arguments 已随轮终
        # 聚合完整，前端先见全部「正在调用」卡片）；第二遍逐个派发并推
        # tool_result（完成后显示摘要）。CP-2 触发时剩余（含当前）不
        # 推事件、不派发——超时截断以 done(timeout) 明示，正常路径
        # 「每个 tool_call 必有对应 tool_result」不变量不受影响。
        executed_calls: list[dict[str, Any]] = []
        round_results: list[dict[str, Any]] = []
        timeout_hit = False
        announced: list[tuple[str, str, dict[str, Any]]] = []
        for tc in round_tool_calls:
            if _remaining_budget() <= 0:
                timeout_hit = True
                break
            call_id = str(tc.get("id") or "")
            name = str(
                (tc.get("function") or {}).get("name") or ""
            )
            raw_args = str((tc.get("function") or {}).get("arguments") or "")
            # arguments 解析（决策 A5）：失败置 {} 照常派发——空 dict
            # 交给 P10 校验（必填参数工具返回 missing 信封供 LLM 自纠，
            # 无参工具照常执行，spec §6.2 规则 6）。
            try:
                parsed_args = json.loads(raw_args) if raw_args else {}
            except (json.JSONDecodeError, TypeError):
                parsed_args = {}
            if not isinstance(parsed_args, dict):
                parsed_args = {}

            yield _tool_call_event(call_id, name, parsed_args)
            announced.append((call_id, name, parsed_args))

        for tc, (call_id, name, parsed_args) in zip(round_tool_calls, announced):
            start = time.perf_counter()
            if name in TOOL_MAP:
                try:
                    result = await TOOL_MAP[name](db, user_id, parsed_args)
                except Exception:  # noqa: BLE001 - 第二道兜底（spec 5.3.3 场景 2）
                    result = _TOOL_EXECUTION_FAILED
            else:
                # 非法工具名（D5）：不派发，信封回灌供 LLM 自纠。
                result = _TOOL_UNAVAILABLE
            elapsed_ms = int((time.perf_counter() - start) * 1000)

            ok = isinstance(result, dict) and "error" not in result
            summary, truncated = _summarize_result(result)
            yield _tool_result_event(
                call_id, name, ok, elapsed_ms, summary, truncated
            )
            executed_calls.append(tc)
            round_results.append(
                {"call_id": call_id, "name": name, "result": result}
            )
            collected.append({"name": name, "summary": summary})
            tool_call_count += 1

        # ⑤ 轮收口（design 2.4.1-B-5）：成组落库 + messages 追加
        # （executed 子集保证每个 tool_call_id 均有对应 tool 消息，
        # 回灌协议合法）。
        if executed_calls:
            round_assistant_text = "".join(round_text_parts)
            try:
                memory.save_round_messages(
                    db,
                    conversation,
                    round_assistant_text,
                    executed_calls,
                    round_results,
                )
            except Exception as exc:  # noqa: BLE001 - 双保险（防注入异常抛穿）
                logger.warning(
                    "轮消息落库异常(兜底): user_id=%s conversation_id=%s type=%s",
                    user_id,
                    conversation_id,
                    type(exc).__name__,
                )
            messages.append(
                {
                    "role": "assistant",
                    "content": round_assistant_text,
                    "tool_calls": executed_calls,
                }
            )
            for item in round_results:
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": item["call_id"],
                        "content": json.dumps(
                            item["result"], ensure_ascii=False
                        ),
                    }
                )
        completed_rounds = round_no
        if timeout_hit:
            finish_reason = FINISH_TIMEOUT
            break
        round_no += 1

    # ⑥ 优雅收尾（O5 三分支，design 2.1.3-B）。触发源映射：
    # max_rounds（第 6 轮仍含 tool_calls）/ timeout（任一预算检查点
    # 剩余 ≤ 0——超时时剩余必 < 15s 保护线，必走模板拼接）。
    remaining = _remaining_budget()
    final_parts: list[str] = []
    async for text_chunk in _graceful_finish(
        messages, collected, finish_reason, remaining, user_id
    ):
        final_parts.append(text_chunk)
        yield _delta_event(text_chunk)
    final_text = "".join(final_parts)

    # ⑦ 收尾落库与终结（五字段 done；finish_reason 真实反映触发源）。
    try:
        message_id = memory.save_final_message(db, conversation, final_text)
    except Exception as exc:  # noqa: BLE001 - 双保险（防注入异常抛穿）
        logger.warning(
            "收尾消息落库异常(兜底): user_id=%s conversation_id=%s type=%s",
            user_id,
            conversation_id,
            type(exc).__name__,
        )
        message_id = None
    yield _done_event(
        conversation_id,
        message_id,
        completed_rounds,
        tool_call_count,
        finish_reason,
    )
    _log_completion(
        user_id,
        conversation_id,
        completed_rounds,
        tool_call_count,
        finish_reason,
        time.monotonic() - started_at,
    )