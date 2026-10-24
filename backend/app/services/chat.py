"""AI 学习问答业务编排：SSE 事件流生成 / 历史落库 / 历史分页。

分层（design.md 2.4.4 / 决策 D1/D2）：业务编排在 services 层
（``rag/qa.py`` 为纯函数，``search_knowledge`` 是 services 同层）；
本模块产出**事件 dict** 而非 SSE 文本（SSE 格式化属 HTTP 关注点，
在 api 层——契约 §4「services 禁止拼接 HTTP 响应」）；不 import
api、不接收 Request/Response。

主链路（design.md 2.1.3-A 活动图）：意图判断 →（knowledge）单次
``search_knowledge``（仅个人库）→ 阈值过滤 → yield sources →
三模板组装 → ``llm.chat_stream`` 逐片 yield delta（**真实流式零
缓冲，禁先算后发**）→ 落库（失败不抛穿，裁定③）→ yield done
（四字段 data，裁决 #8 + 裁定①）。

error 事件仅两源（裁定③收窄）：检索段 / LLM 段失败；**落库失败
不是 error 来源**——正常 done 收尾（``history_id=null``），
原则：主链路（回答）成功，不被辅链路（历史保存）的失败拖垮。

日志隐私红线（spec 4.3 规则 4）：全程禁打印问题原文与回答全文；
落库失败 warning 含 user_id 与异常类型，不含 question。
"""

from __future__ import annotations

import logging
import time
from collections.abc import AsyncIterator
from typing import Any

from sqlalchemy import desc
from sqlalchemy.orm import Session

from app.core.response import (
    CODE_INTERNAL_ERROR,
    CODE_LLM_FAILED,
    BizException,
)
from app.models.enums import EmbedMode
from app.models.qa import QAHistory
from app.rag.qa import QaIntent, build_qa_messages, classify_intent, filter_sources_by_threshold
from app.schemas.chat import ChatHistoryOut
from app.services import llm
from app.services.knowledge import search_knowledge
from app.services.readonly import paginate

logger = logging.getLogger(__name__)

# 检索条数（决策 D7）：与 P7 检索默认一致；5 片 × ~500 字符 ≈ 2.5K
# 字符 Prompt 上下文，量级安全；不暴露给前端（防参数面膨胀）。
QA_TOP_K: int = 5


# ---------------------------------------------------------------------------
# 事件构造辅助（事件结构单一来源，防散落拼 dict——design.md 2.4.4-1）
# ---------------------------------------------------------------------------
def _sources_event(data: list[dict[str, Any]]) -> dict[str, Any]:
    """构造 sources 事件（第 1 条，恰 1 次必推）。"""
    return {"type": "sources", "data": data}


def _delta_event(text: str) -> dict[str, Any]:
    """构造 delta 事件（sources 后 0..n 次，与 LLM 产出顺序一致）。"""
    return {"type": "delta", "data": text}


def _done_event(
    is_grounded: bool,
    mode: str,
    intent: QaIntent,
    history_id: int | None,
) -> dict[str, Any]:
    """构造 done 事件（终结，恰 1 次；data 四字段必推，R3 裁定①）。"""
    return {
        "type": "done",
        "data": {
            "is_grounded": is_grounded,
            "mode": mode,
            "intent": intent,
            "history_id": history_id,
        },
    }


def _error_event(code: int, message: str) -> dict[str, Any]:
    """构造 error 事件（终结，恰 1 次；仅检索 / LLM 失败路径）。"""
    return {"type": "error", "data": {"code": code, "message": message}}


# ---------------------------------------------------------------------------
# SSE 问答编排生成器（design.md 2.4.4）
# ---------------------------------------------------------------------------
async def qa_stream(
    db: Session,
    user_id: int,
    question: str,
) -> AsyncIterator[dict[str, Any]]:
    """SSE 问答编排生成器：产出事件 dict 流（非 SSE 文本）。

    编排顺序（design.md 2.1.3-A）：意图判断（异常退化为 knowledge）
    → chat 路径跳过检索 / knowledge 路径单次 ``search_knowledge``
    （检索边界恒为当前认证 user_id，仅个人库）→ 阈值过滤 →
    yield sources（恰 1 次）→ 三模板组装 → ``llm.chat_stream``
    逐片即时 yield delta → 落库（done 前一步，失败不抛穿）→
    yield done（四字段）。

    LLM 调用经 ``llm.chat_stream`` 模块属性访问（测试注入形态：
    monkeypatch ``app.services.llm.chat_stream``）；``search_knowledge``
    直接导入绑定（测试以真实检索驱动，跳检用例 patch
    ``app.services.chat.search_knowledge``）。

    Args:
        db: 请求级数据库会话（生成器持有；落库是唯一写事务且发生
            在流末——FastAPI 依赖 teardown 在响应发送完成后执行，
            流式期间会话有效）。
        user_id: 当前认证用户 id（检索与落库的隔离边界）。
        question: 用户问题（入参已校验非空 ≤500 字符）。

    Yields:
        dict[str, Any]: SSE 事件 dict（sources / delta / done / error）。
    """
    started_at = time.monotonic()

    # ① 意图判断（裁决 #9 可关停兜底：任何异常退化为始终检索）。
    intent: QaIntent = "knowledge"
    try:
        intent = classify_intent(question)
    except Exception:  # noqa: BLE001 - 纯字符串操作理论不抛，防御兜底
        intent = "knowledge"

    sources: list[dict[str, Any]] = []
    is_grounded = False
    mode = "online"

    # ② 检索段（仅 knowledge 路径；chat 跳过——mode 取约定值
    # "online"（决策 D3：无检索发生，无离线警示语义负担））。
    if intent == "knowledge":
        try:
            result = await search_knowledge(
                db, user_id, question, QA_TOP_K
            )
        except BizException as exc:
            logger.warning(
                "qa_stream 检索失败: user_id=%s code=%s",
                user_id,
                exc.code,
            )
            yield _error_event(exc.code, exc.message)
            return
        except Exception as exc:  # noqa: BLE001 - 未预期异常兜底
            logger.warning(
                "qa_stream 检索未预期异常: user_id=%s type=%s",
                user_id,
                type(exc).__name__,
            )
            yield _error_event(CODE_INTERNAL_ERROR, "服务器内部错误")
            return
        sources, is_grounded = filter_sources_by_threshold(result["results"])
        mode = result["mode"]

    # ③ sources 事件（恰 1 次必推；无据 / chat 时 data=[]）。
    yield _sources_event(sources)

    # ④ Prompt 组装（三模板分流：有据 / knowledge 无据 / chat）。
    messages = build_qa_messages(question, sources, intent)
    answer_parts: list[str] = []
    has_delta = False

    # ⑤ LLM 流式段：逐片即时转发（真实流式零缓冲，spec 4.1 规则 2）。
    try:
        async for chunk in llm.chat_stream(messages):
            answer_parts.append(chunk)
            has_delta = True
            yield _delta_event(chunk)
    except BizException as exc:
        logger.warning(
            "qa_stream LLM 失败: user_id=%s code=%s",
            user_id,
            exc.code,
        )
        yield _error_event(exc.code, exc.message)
        return
    except Exception as exc:  # noqa: BLE001 - 迭代段未包装的原始异常
        # 按「是否已推送 delta」区分场景 1 / 3 文案（spec 5.1.3）。
        message = (
            "回答生成中断，请重试"
            if has_delta
            else "AI 服务暂时不可用，请稍后重试"
        )
        logger.warning(
            "qa_stream LLM 流中断: user_id=%s type=%s has_delta=%s",
            user_id,
            type(exc).__name__,
            has_delta,
        )
        yield _error_event(CODE_LLM_FAILED, message)
        return

    # ⑥ 落库（done 前一步取 history_id；失败不抛穿——裁定③）。
    answer = "".join(answer_parts)
    history_id: int | None = None
    try:
        history_id = save_qa_history(
            db, user_id, question, answer, sources, mode, is_grounded, intent
        )
    except Exception as exc:  # noqa: BLE001 - 第二道防线（双保险）
        # save_qa_history 内部已消化异常；此处再兜一层，保证落库
        # 路径任何意外都不拖垮主链路（裁定③）。
        logger.warning(
            "qa_history 落库异常(兜底): user_id=%s type=%s",
            user_id,
            type(exc).__name__,
        )
        history_id = None

    # ⑦ done 事件（四字段必推；落库失败时 history_id=null 照常收尾）。
    yield _done_event(is_grounded, mode, intent, history_id)

    elapsed = time.monotonic() - started_at
    logger.info(
        "qa_stream 完成: user_id=%s intent=%s is_grounded=%s "
        "mode=%s delta片数=%s 耗时=%.2fs history_id=%s",
        user_id,
        intent,
        is_grounded,
        mode,
        len(answer_parts),
        elapsed,
        history_id,
    )


# ---------------------------------------------------------------------------
# 历史落库与分页查询（design.md 2.4.4-3 / 裁定③）
# ---------------------------------------------------------------------------
def save_qa_history(
    db: Session,
    user_id: int,
    question: str,
    answer: str,
    sources: list[dict[str, Any]],
    mode: str,
    is_grounded: bool,
    intent: QaIntent,
) -> int | None:
    """写入一条问答历史（唯一写入口，qa_stream 的 done 前一步调用）。

    ``sources`` 快照语义：sources 事件 ``data`` 的 JSON 数组**原样**
    落库（``JSONType`` 写入，无据与 chat 落 ``[]``）；快照不随后续
    库变化更新（spec 5.4.3 场景 2）。``intent`` 一并落库（决策 D9：
    chat 与 knowledge 无据两种记录既有字段完全同构，不落库则历史
    回放无法区分两种渲染）。

    **落库失败不抛穿**（裁定③）：捕获自身异常、``db.rollback()``
    释放 SQLite 写锁、记 ``logger.warning``（含 user_id 与异常类型，
    **禁止记录 question 原文与 answer 全文**——日志泄露用户内容
    红线，spec 4.3 规则 4）、返回 ``None``；调用方以
    ``history_id=None`` 照常构造 done 收尾——主链路（回答）成功，
    不被辅链路（历史保存）的失败拖垮。

    Args:
        db: 请求级数据库会话。
        user_id: 归属用户 id。
        question: 用户问题原文。
        answer: 完整回答（全部 delta 拼接）。
        sources: 来源快照（sources 事件 data 原样）。
        mode: 该次问答的检索模式快照（online / offline）。
        is_grounded: 是否基于知识库检索回答。
        intent: 问题意图（knowledge / chat）。

    Returns:
        int | None: 新记录 id；落库失败返回 ``None``。
    """
    try:
        record = QAHistory(
            user_id=user_id,
            question=question,
            answer=answer,
            sources=sources,
            mode=EmbedMode(mode),
            is_grounded=is_grounded,
            intent=intent,
        )
        db.add(record)
        db.commit()
        return record.id
    except Exception as exc:  # noqa: BLE001 - 裁定③：内部消化不抛穿
        db.rollback()
        logger.warning(
            "qa_history 落库失败: user_id=%s type=%s",
            user_id,
            type(exc).__name__,
        )
        return None


def list_qa_history(
    db: Session,
    user_id: int,
    page: int,
    page_size: int,
) -> dict[str, Any]:
    """分页查询当前用户的历史问答（created_at 倒序，仅本人可见）。

    恒带 ``QAHistory.user_id == user_id`` 过滤（「不可见即不存在」，
    spec 4.3 规则 3）；``created_at`` 倒序（同秒并列时按 id 倒序
    tie-break，保证分页稳定），第 1 页首条即最近一次问答
    （spec 5.5.1 规则 4）；复用 ``paginate`` 泛型助手 +
    ``ChatHistoryOut`` 序列化（禁止裸 ORM 对象出 services 边界）。

    Args:
        db: 数据库会话。
        user_id: 当前用户 id（隔离过滤依据）。
        page: 页码（从 1 开始，入参已校验）。
        page_size: 每页条数（1~100，入参已校验）。

    Returns:
        dict[str, Any]: ``{items, total, page, page_size}``。
    """
    return paginate(
        db,
        QAHistory,
        ChatHistoryOut,
        page=page,
        page_size=page_size,
        order_by=[desc(QAHistory.created_at), desc(QAHistory.id)],
        filters=[QAHistory.user_id == user_id],
    )