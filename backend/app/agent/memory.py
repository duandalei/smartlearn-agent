"""Agent 会话与消息持久化（agent_conversations / agent_messages 读写）。

分层边界（裁决 #5）：本模块直接操作 AgentConversation / AgentMessage
ORM 模型——会话日志是 Agent 组件**自有元数据**（PROJECT_CONTEXT §4
「db 为全局基础设施，可被任意层引用」；P3 的 api/v1/agent.py 直查
ORM 先例）。「Agent 绝不直接访问数据库」铁律收窄为「**LLM 工具决策
通道**访问**学习业务数据**必须经 tools.py / services」——本模块仍
禁触碰 tasks / learning_records 等业务表。

事务设计（design 2.1.3-D，决策 A3）：落库按「组」划分，每组一次
commit——① user 消息组（受理后立即落库，裁决 #12：此后即使循环
error 终结也不回滚）；② 每轮工具组（assistant(tool_calls) + 全部
tool 消息**一次事务成组落库**，成对语义最强实现：中断/失败时整组
不出现，孤儿 tool 消息在数据层不可能）；③ 最终回答组。每组成功后
显式触碰 ``conversation.updated_at``（O2 倒序正确性前提——实测
``onupdate`` 只在该行自身 UPDATE 时触发、insert 子消息不触碰父行，
故必须显式赋值）。落库失败统一 ``db.rollback()`` + ``logger.warning``
（仅 user_id / conversation_id / 异常类型，**禁记消息原文与结果全文**
——spec 4.3 规则 4 隐私红线）+ 不抛穿主链路。

上下文窗口（O7，design 2.4.4-A，决策 A9/A10）：尾部对齐取最近
limit 条 + 头部连续孤儿 tool 剔除。正确性论证：截断只发生在头部
（尾部是最新消息）；tool 消息在协议上必须紧跟其 assistant(tool_calls)
消息之后（id 更大），故头部孤儿只可能是 tool 消息；连续剔除即合法
边界，O(n) 无回溯。system 消息不落库（裁决 #6）→ 窗口天然不含
system。

回链：design 2.2.2-(9) / 2.4.4；spec §5.4 / §6.3 / §6.4。
"""

from __future__ import annotations

import json
import logging
from typing import Any

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.core.response import CODE_NOT_FOUND, BizException
from app.models.agent import AgentConversation, AgentMessage
from app.models.base import utc_now
from app.models.enums import MessageRole
from app.schemas.agent import ConversationOut, MessageOut
from app.services.readonly import paginate

logger = logging.getLogger(__name__)

#: 上下文窗口默认条数（O7：与 app/agent/core.CONTEXT_WINDOW 同值；
#: core.py 调用时显式传参，此处默认值仅供独立调用兜底）。
_CONTEXT_WINDOW_DEFAULT: int = 20

#: 会话标题截断长度（O4 裁定：首条用户消息截断 20 字符）。
_TITLE_TRUNCATE: int = 20

#: tool_name 列宽（agent_messages.tool_name = String(50)；非法工具名
#: 照存须截断——与 core.TOOL_NAME_MAX_LEN 同值）。
_TOOL_NAME_MAX_LEN: int = 50

#: tool_call_id 列宽（agent_messages.tool_call_id = String(64)；防御
#: 截断——与 core.TOOL_CALL_ID_MAX_LEN 同值）。
_TOOL_CALL_ID_MAX_LEN: int = 64


# ---------------------------------------------------------------------------
# 会话 CRUD（design 2.2.2-(9) ①–④）
# ---------------------------------------------------------------------------
def create_conversation(
    db: Session, user_id: int, title: str | None
) -> AgentConversation:
    """新建 Agent 会话（chat 自动新建与显式新建共用入口）。

    Args:
        db: 数据库会话。
        user_id: 归属用户 id（服务端认证结果注入）。
        title: 会话标题；可为 None（首条 user 消息落库时按 O4 补
            截断标题）。显式新建传空串时视为 None 同样后补。

    Returns:
        AgentConversation: 已 commit 的会话 ORM 对象（调用方以
        ConversationOut 序列化出参或生成器持有）。
    """
    normalized_title = title.strip() if title else None
    conversation = AgentConversation(
        user_id=user_id,
        title=normalized_title if normalized_title else None,
    )
    db.add(conversation)
    db.commit()
    return conversation


def get_conversation_or_404(
    db: Session, conversation_id: int, user_id: int
) -> AgentConversation:
    """定位会话并校验归属；不存在或越权统一 404/1005。

    「不可见即不存在」（spec §5.4.1 规则 9）：主键 + user_id 双过滤。

    Args:
        db: 数据库会话。
        conversation_id: 会话 id（仅作定位，服务端校验归属）。
        user_id: 当前认证用户 id。

    Returns:
        AgentConversation: 本人会话 ORM 对象。

    Raises:
        BizException: code=1005 / HTTP 404，会话不存在或属他人时抛出。
    """
    conversation = db.scalar(
        select(AgentConversation).where(
            AgentConversation.id == conversation_id,
            AgentConversation.user_id == user_id,
        )
    )
    if conversation is None:
        raise BizException(
            CODE_NOT_FOUND,
            "资源不存在",
            http_status=404,
        )
    return conversation


def rename_conversation(
    db: Session, conversation_id: int, user_id: int, title: str
) -> dict[str, Any]:
    """重命名会话（1–200 字符已由 schema 校验；仅限本人）。

    Args:
        db: 数据库会话。
        conversation_id: 会话 id。
        user_id: 当前认证用户 id。
        title: 新标题（strip 后非空、≤200）。

    Returns:
        dict[str, Any]: 更新后的 ConversationOut 序列化（统一响应体
        data 直用）。

    Raises:
        BizException: code=1005 / HTTP 404，会话不存在或属他人时抛出。
    """
    conversation = get_conversation_or_404(db, conversation_id, user_id)
    conversation.title = title.strip()
    conversation.updated_at = utc_now()
    db.commit()
    return ConversationOut.model_validate(conversation).model_dump(mode="json")


def delete_conversation(
    db: Session, conversation_id: int, user_id: int
) -> None:
    """删除会话并级联删除其全部消息（硬删除，仅限本人）。

    ORM ``cascade="all, delete-orphan"`` 级联删子消息（SQLite 无 DB
    级 ON DELETE CASCADE，passive_deletes=True 下由 SQLAlchemy 发
    DELETE）；单会话消息量级（数十条）一次事务删除无性能风险。

    Args:
        db: 数据库会话。
        conversation_id: 会话 id。
        user_id: 当前认证用户 id。

    Raises:
        BizException: code=1005 / HTTP 404，会话不存在或属他人时抛出。
    """
    conversation = get_conversation_or_404(db, conversation_id, user_id)
    db.delete(conversation)
    db.commit()


# ---------------------------------------------------------------------------
# 会话列表倒序与消息全量查询（design 2.2.2-(9) ⑤–⑥）
# ---------------------------------------------------------------------------
def list_conversations(
    db: Session, user_id: int, page: int, page_size: int
) -> dict[str, Any]:
    """分页查询当前用户的会话列表（updated_at 倒序，O2 裁定）。

    同秒并列由 id 倒序 tie-break 兜底（保证分页稳定）；恒带
    user_id 过滤（「不可见即不存在」）。对 P3 的 id 升序是**有意
    行为变更**（R6 断言新行为）。

    Args:
        db: 数据库会话。
        user_id: 当前认证用户 id。
        page: 页码（从 1 开始，入参已校验）。
        page_size: 每页条数（1~100，入参已校验）。

    Returns:
        dict[str, Any]: ``{items, total, page, page_size}``。
    """
    return paginate(
        db,
        AgentConversation,
        ConversationOut,
        page=page,
        page_size=page_size,
        order_by=[
            desc(AgentConversation.updated_at),
            desc(AgentConversation.id),
        ],
        filters=[AgentConversation.user_id == user_id],
    )


def list_messages(
    db: Session, conversation_id: int, user_id: int
) -> list[dict[str, Any]]:
    """全量返回该会话全部消息（O3 裁定：不分页，id 升序）。

    404 定位**先于**空列表判定（会话不存在/越权 → 404/1005；会话
    存在无消息 → ``[]``，spec 5.4.3 场景 3）。出参零新增字段
    （P3 MessageOut 已含 role/content/tool_name/tool_calls/
    tool_call_id 全链，足以还原对话流与工具调用卡片）。

    Args:
        db: 数据库会话。
        conversation_id: 会话 id。
        user_id: 当前认证用户 id。

    Returns:
        list[dict[str, Any]]: MessageOut 序列化数组（id 升序）。

    Raises:
        BizException: code=1005 / HTTP 404，会话不存在或属他人时抛出。
    """
    conversation = get_conversation_or_404(db, conversation_id, user_id)
    rows = db.scalars(
        select(AgentMessage)
        .where(AgentMessage.conversation_id == conversation.id)
        .order_by(AgentMessage.id.asc())
    ).all()
    return [
        MessageOut.model_validate(row).model_dump(mode="json") for row in rows
    ]


# ---------------------------------------------------------------------------
# 消息三形态落库（design 2.2.2-(9) ⑦–⑨ / 2.4.4-D 落库映射表）
# ---------------------------------------------------------------------------
def save_user_message(
    db: Session, conversation: AgentConversation, content: str
) -> None:
    """落库 user 消息（独立事务；受理后立即，裁决 #12）。

    首条消息标题补全（O4）：conversation.title 为空时置
    ``content[:20]``；显式新建空 title 会话同样在此补全。失败不抛穿
    （rollback + warning，user 消息缺失不阻塞主链路——对话照常进行，
    仅历史缺失该条）。

    Args:
        db: 请求级数据库会话（生成器持有）。
        conversation: 目标会话（ORM 对象）。
        content: 用户消息原文（入参已校验 ≤2000 字符）。
    """
    user_id = conversation.user_id
    try:
        if not conversation.title:
            conversation.title = content[:_TITLE_TRUNCATE]
        db.add(
            AgentMessage(
                conversation_id=conversation.id,
                role=MessageRole.USER,
                content=content,
            )
        )
        conversation.updated_at = utc_now()
        db.commit()
    except Exception as exc:  # noqa: BLE001 - 落库失败不抛穿主链路
        db.rollback()
        logger.warning(
            "agent user 消息落库失败: user_id=%s conversation_id=%s type=%s",
            user_id,
            conversation.id,
            type(exc).__name__,
        )


def save_round_messages(
    db: Session,
    conversation: AgentConversation,
    assistant_content: str,
    tool_calls: list[dict[str, Any]],
    tool_results: list[dict[str, Any]],
) -> None:
    """轮内成组落库：assistant(tool_calls) + 全部 tool 消息一次事务（决策 A3）。

    成对语义的最强实现：中断/失败时整组不出现（rollback），孤儿 tool
    消息在数据层不可能。``tool_calls`` 以 JSONType 直存 list 结构
    （契约 §8.1 禁手动 json.dumps）；tool 消息 content 存**完整结果
    JSON 字符串**（含 error 信封原样——content 是协议文本列语义，
    裁决 #7：多轮上下文回灌与前端历史回放展开均需完整数据）。

    Args:
        db: 请求级数据库会话。
        conversation: 目标会话（ORM 对象）。
        assistant_content: 该轮 assistant 文本（可为空串——纯工具轮）。
        tool_calls: 已执行的 OpenAI 形态 tool_calls 列表（id/name/
            arguments，与 SSE tool_call 事件同源；CP-2 超时截断时为
            已执行子集，保证每个 id 均有对应 tool 消息）。
        tool_results: 每条 ``{"call_id": str, "name": str, "result": dict}``；
            result 为工具返回的业务 dict 或 ``{"error"}`` 信封原样。
    """
    user_id = conversation.user_id
    try:
        db.add(
            AgentMessage(
                conversation_id=conversation.id,
                role=MessageRole.ASSISTANT,
                content=assistant_content,
                tool_calls=tool_calls or None,
            )
        )
        for item in tool_results:
            db.add(
                AgentMessage(
                    conversation_id=conversation.id,
                    role=MessageRole.TOOL,
                    content=json_dumps(item["result"]),
                    tool_name=(item["name"] or "")[:_TOOL_NAME_MAX_LEN],
                    tool_call_id=(item["call_id"] or "")[:_TOOL_CALL_ID_MAX_LEN],
                )
            )
        conversation.updated_at = utc_now()
        db.commit()
    except Exception as exc:  # noqa: BLE001 - 组失败整体回滚不抛穿
        db.rollback()
        logger.warning(
            "agent 轮消息成组落库失败: user_id=%s conversation_id=%s type=%s",
            user_id,
            conversation.id,
            type(exc).__name__,
        )


def save_final_message(
    db: Session, conversation: AgentConversation, content: str
) -> int | None:
    """落库最终 assistant 纯文本消息（独立事务 + 触碰）。

    失败 rollback + warning + 返回 None（调用方以 ``message_id=None``
    照常构造 done 收尾——主链路不被辅链路拖垮，对齐 P9 裁定③）。

    Args:
        db: 请求级数据库会话。
        conversation: 目标会话（ORM 对象）。
        content: 最终回答文本（normal 路径或 O5 收尾产物）。

    Returns:
        int | None: 新消息 id；落库失败返回 None。
    """
    user_id = conversation.user_id
    try:
        message = AgentMessage(
            conversation_id=conversation.id,
            role=MessageRole.ASSISTANT,
            content=content,
        )
        db.add(message)
        conversation.updated_at = utc_now()
        db.commit()
        return message.id
    except Exception as exc:  # noqa: BLE001 - 落库失败不抛穿主链路
        db.rollback()
        logger.warning(
            "agent 最终消息落库失败: user_id=%s conversation_id=%s type=%s",
            user_id,
            conversation.id,
            type(exc).__name__,
        )
        return None


# ---------------------------------------------------------------------------
# 上下文窗口成对边界截断（O7，design 2.4.4-A）
# ---------------------------------------------------------------------------
def load_context_window(
    db: Session,
    conversation: AgentConversation,
    limit: int = _CONTEXT_WINDOW_DEFAULT,
) -> list[dict[str, Any]]:
    """加载会话最近历史并映射为 OpenAI 协议消息序列（禁孤儿 tool）。

    四步算法（design 2.4.4-A 逐字）：① 全量查询该会话全部消息
    （id 升序——单会话消息量受 6 轮上限结构性约束，全量取出毫秒级，
    决策 A10）；② ``rows[-limit:]`` 尾部对齐（含刚落库的本轮 user
    消息——调用顺序为先落库后加载，天然包含）；③ 头部连续孤儿 tool
    剔除；④ 行 → OpenAI 协议 dict 三形态映射。

    Args:
        db: 请求级数据库会话。
        conversation: 目标会话（ORM 对象）。
        limit: 窗口条数上限（core.py 显式传 CONTEXT_WINDOW=20）。

    Returns:
        list[dict[str, Any]]: 协议合法的消息序列（首条必非孤立 tool）；
        user/assistant 纯文本 → ``{role, content}``；assistant(工具轮)
        → ``{role, content, tool_calls}``；tool → ``{role, content,
        tool_call_id}``（content 为完整结果 JSON 字符串原样）。
    """
    rows = db.scalars(
        select(AgentMessage)
        .where(AgentMessage.conversation_id == conversation.id)
        .order_by(AgentMessage.id.asc())
    ).all()
    window = rows[-limit:] if limit > 0 else []
    while window and window[0].role == MessageRole.TOOL:
        # 头部孤儿 tool：其配对 assistant(tool_calls) 在窗口外（id 更小
        # 被截），保留即协议非法——连续剔除至合法边界（宁少勿非法）。
        window.pop(0)
    messages: list[dict[str, Any]] = []
    for row in window:
        if row.role == MessageRole.TOOL:
            messages.append(
                {
                    "role": "tool",
                    "content": row.content,
                    "tool_call_id": row.tool_call_id or "",
                }
            )
        elif row.tool_calls:
            messages.append(
                {
                    "role": "assistant",
                    "content": row.content,
                    "tool_calls": row.tool_calls,
                }
            )
        else:
            messages.append({"role": row.role.value, "content": row.content})
    return messages


def json_dumps(value: dict[str, Any]) -> str:
    """完整结果 JSON 序列化（中文原样；供 tool 消息 content 与回灌共用）。"""

    return json.dumps(value, ensure_ascii=False)