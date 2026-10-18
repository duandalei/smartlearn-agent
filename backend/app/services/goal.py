"""学习目标业务逻辑（CRUD + AI 目标拆解编排）。

分层契约（PROJECT_CONTEXT 第 4 章）：本模块承载全部业务规则与事务，
不接收 FastAPI 的 Request/Response、不拼接 HTTP 响应。

数据语义约定（spec 5.2.1 规则 10，P7 分析引擎消费）：
    目标拆解写入 ``knowledge_mastery`` 的记录为
    ``source='goal_breakdown'`` 且 ``mastery_score=0`` 的「零分待学」
    记录；薄弱点分析与 Dashboard 展示中**必须**排除这类知识点
    （尚未真正学习，不得列为薄弱）。一旦该点通过学习记录或自评被
    更新过，即恢复正常参与排序。

事务边界（design 2.1.3-B，本模块最重要的架构约束）：
    ``breakdown_goal`` 全程不持有请求级 Session，由 service 显式管理
    两段**短会话**（阶段①归属校验快照 / 阶段③单写事务），LLM 调用
    （可达 90s+）期间禁止开启任何数据库会话，避免耗尽 SQLite
    连接池阻塞全站。
"""

from __future__ import annotations

import json
import logging
import re
import time
from dataclasses import dataclass
from datetime import date, datetime

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.response import (
    CODE_BIZ_CONFLICT,
    CODE_INTERNAL_ERROR,
    CODE_LLM_FAILED,
    CODE_NOT_FOUND,
    BizException,
)
from app.db.session import SessionLocal
from app.models.base import utc_now
from app.models.enums import GoalStatus, MasterySource
from app.models.goal import LearningGoal
from app.models.mastery import KnowledgeMastery
from app.schemas.goal import (
    GoalCreate,
    GoalOut,
    GoalUpdate,
    RoadmapNode,
    RoadmapOut,
)
from app.services import llm

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 拆解提示词（design 2.4.1 全文，逐字使用，禁止散落拼接）
# ---------------------------------------------------------------------------
SYSTEM_PROMPT: str = """你是一名资深的学习规划专家，擅长把学生的学习目标拆解为结构化的知识体系。

你的任务是将给定的学习目标拆解为一棵知识树，并严格遵守以下规则：
1. 只输出一个 JSON 对象，不要输出任何其他文字、解释、前后缀或 Markdown 代码块标记。
2. 顶层必须是单个 JSON 对象（即根节点），禁止输出 JSON 数组或多个并列对象。JSON 结构固定为：{"name":"...","children":[{"name":"...","children":[]}]}，每个节点只有 name 和 children 两个字段。
3. 层级最多 4 层：根节点为第 1 层，最深到第 4 层；第 4 层节点必须使用空的 children 数组（"children":[]）。
4. 层级按「目标 → 领域 → 技能 → 具体知识点」组织：根节点的 name 应概括整个目标的核心主题（通常就是目标的学科或方向，如「机器学习」）；第 2 层是知识领域，第 3 层是技能模块，第 4 层是具体知识点。
5. 每个中间节点是一个知识领域或模块（如「数学基础」「监督学习」），相互之间尽量不重叠。
6. 叶子节点（children 为空数组的节点）必须是可独立学习、可检验的最小知识单元（如「逻辑回归」「特征值与特征向量」），不要用「了解」「掌握」等动词开头，直接用知识点名称。
7. 整棵树的根节点必须包含至少 1 个子节点，禁止输出空的 children 数组作为根。
8. 同一层级的孩子数量控制在 3~7 个，保证结构清晰、粒度均衡。
9. 输出必须是合法的 JSON：字符串用双引号，不要有尾逗号，不要有注释。"""

# NOTE: 本模板只含 5 个命名占位符、无字面 JSON 花括号，可安全 .format()。
USER_PROMPT_TEMPLATE: str = """请把下面的学习目标拆解为知识树。

【目标名称】{title}
【目标类型】{goal_type}
【目标描述】{description}
【开始日期】{start_date}
【截止日期】{end_date}

补充说明：
- 目标类型、描述、起止日期为空表示未填写，拆解时忽略对应信息。
- 若提供了起止日期，请据此评估学习容量：时间越充裕，知识树可越全面细致；时间紧张时优先保留核心必学的知识分支。
- 请根据目标名称与类型推断合理的学科知识体系（例如「考研」类目标应覆盖该学科考研大纲的核心考点）。

现在请直接输出 JSON。"""

# NOTE: 模板含字面 JSON 示例，其花括号已转义为 {{ }} 以支持 .format()。
RETRY_PROMPT: str = """你上一次的输出无法解析为要求的知识树 JSON（原因：{failure_reason}）。上一次的原始输出如下：

{first_output_truncated}

请重新输出。要求：只输出一个合法的 JSON 对象，不要包含任何其他文字或 Markdown 代码块标记；结构为 {{"name":"...","children":[{{"name":"...","children":[]}}]}}；层级最多 4 层；根节点 children 必须非空。"""

# 知识树最大深度（根为第 1 层）。
_MAX_DEPTH: int = 4

# 纠错重试时附带的首次输出最大字符数（防止上下文爆炸）。
_FIRST_OUTPUT_MAX_CHARS: int = 2000

# Markdown 代码块包裹剥离正则（```json ... ``` 或 ``` ... ```，DOTALL）。
_CODE_FENCE_RE = re.compile(r"^\s*```(?:json)?\s*(.*?)\s*```\s*$", re.DOTALL)


@dataclass(frozen=True)
class _GoalContext:
    """拆解用的目标上下文快照（阶段①短会话中读取）。"""

    title: str
    goal_type: str | None
    description: str | None
    start_date: date | None
    end_date: date | None
    has_roadmap: bool


class _ParseFailed(Exception):
    """LLM 输出解析失败（内部异常，仅用于拆解编排的重试控制）。"""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason: str = reason


# ---------------------------------------------------------------------------
# 并发拆解互斥（进程内标志位，design 2.1.3-C，spec 裁定⑦）
# ---------------------------------------------------------------------------
# 原子性论证：FastAPI async 路由全部运行在单线程事件循环上，
# 「if goal_id in set: raise」与「set.add(goal_id)」两条语句之间不存在
# await，不可能被其他协程插入 —— 检查与登记天然原子，无需 asyncio.Lock。
# 已知限制：进程内存态，uvicorn 单进程部署（MVP 运行形态）语义正确；
# 若未来多 worker 部署，互斥退化为「每 worker 各自互斥」，需升级为
# DB 乐观锁（P4 不实现，仅在此标注演进点）。
_breakdown_in_progress: set[int] = set()


# ---------------------------------------------------------------------------
# 私有助手
# ---------------------------------------------------------------------------
def _get_goal_or_404(db: Session, user_id: int, goal_id: int) -> LearningGoal:
    """按 id + 归属查询目标；不存在或越权统一抛 404（防 ID 枚举）。

    Args:
        db: 数据库会话。
        user_id: 当前用户 id。
        goal_id: 目标 id。

    Returns:
        LearningGoal: 目标 ORM 对象。

    Raises:
        BizException: code=1005 / HTTP 404。
    """
    goal = db.scalar(
        select(LearningGoal).where(
            LearningGoal.id == goal_id,
            LearningGoal.user_id == user_id,
        )
    )
    if goal is None:
        raise BizException(CODE_NOT_FOUND, "资源不存在", http_status=404)
    return goal


def _validate_date_order(start: date | None, end: date | None) -> None:
    """校验起止日期先后关系（两者齐且倒置时抛业务冲突）。

    Args:
        start: 开始日期（可空）。
        end: 截止日期（可空）。

    Raises:
        BizException: code=1007 / HTTP 400，截止早于开始时抛出。
    """
    if start is not None and end is not None and end < start:
        raise BizException(
            CODE_BIZ_CONFLICT, "截止时间不能早于开始时间", http_status=400
        )


def _serialize_goal(goal: LearningGoal) -> dict:
    """把目标 ORM 对象序列化为 GoalOut 结构的 JSON dict。"""

    return GoalOut.model_validate(goal).model_dump(mode="json")


def _build_breakdown_messages(ctx: _GoalContext) -> list[llm.ChatMessage]:
    """组装拆解提示词消息（system + user，未填写字段占位「无」）。

    Args:
        ctx: 目标上下文快照。

    Returns:
        list[llm.ChatMessage]: [system, user] 两条消息。
    """
    user_prompt = USER_PROMPT_TEMPLATE.format(
        title=ctx.title,
        goal_type=ctx.goal_type if ctx.goal_type else "无",
        description=ctx.description if ctx.description else "无",
        start_date=ctx.start_date.isoformat() if ctx.start_date else "无",
        end_date=ctx.end_date.isoformat() if ctx.end_date else "无",
    )
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt},
    ]


def _parse_roadmap(text: str) -> dict:
    """解析 LLM 输出为知识树（固定顺序容错，design 2.4.2）。

    固定顺序：① 剥离 Markdown 代码块包裹 → ② JSON 解析 →
    ③ RoadmapNode 结构校验（忽略多余字段、递归校验）→ ④ 空树判定。

    Args:
        text: LLM 原始输出文本。

    Returns:
        dict: 校验通过的知识树（仅 name / children，尚未截断）。

    Raises:
        _ParseFailed: 任一步失败（附原因摘要，供纠错重试提示词使用）。
    """
    stripped = text.strip()
    fence = _CODE_FENCE_RE.match(stripped)
    payload = fence.group(1) if fence else stripped

    try:
        data = json.loads(payload)
    except (json.JSONDecodeError, ValueError):
        raise _ParseFailed("无法解析为 JSON") from None

    try:
        root = RoadmapNode.model_validate(data)
    except ValidationError:
        raise _ParseFailed("节点结构不合法") from None

    if not root.children:
        # 空树判定（spec 裁定③）：根 children 缺失 / null（已在上一步
        # 拦截）/ 空数组 → 失败；children 非空（哪怕只有 1 个）→ 成功。
        raise _ParseFailed("根节点 children 为空")

    return root.model_dump()


def _truncate_tree(node: dict, depth: int = 1) -> dict:
    """层级截断（超过 4 层时保留第 4 层节点、丢弃其子节点）。

    截断属**正常处理路径**而非错误路径（spec 裁定②）；同时完成
    字段规范化——输出仅含 name / children（LLM 夹带的多余字段在
    重建时被自然丢弃）。

    Args:
        node: 知识树节点（dict，含 name / children）。
        depth: 当前层级（根为 1）。

    Returns:
        dict: 截断与规范化后的节点。
    """
    children = node.get("children") or []
    if depth >= _MAX_DEPTH or not children:
        return {"name": node["name"], "children": []}
    return {
        "name": node["name"],
        "children": [_truncate_tree(child, depth + 1) for child in children],
    }


def _collect_leaves(tree: dict) -> set[str]:
    """DFS 提取知识树全部叶子节点名称（树内去重，spec 规则 8）。

    Args:
        tree: 截断后的知识树。

    Returns:
        set[str]: 叶子节点 name 集合。
    """
    leaves: set[str] = set()
    stack: list[dict] = [tree]
    while stack:
        node = stack.pop()
        children = node.get("children") or []
        if not children:
            leaves.add(node["name"])
        else:
            stack.extend(children)
    return leaves


def _tree_depth(tree: dict) -> int:
    """计算知识树深度（根为 1），用于成功日志。"""
    children = tree.get("children") or []
    if not children:
        return 1
    return 1 + max(_tree_depth(child) for child in children)


async def _call_and_parse(goal_id: int, ctx: _GoalContext) -> dict:
    """LLM 调用与解析的两次尝试编排（解析失败自动重试 1 次）。

    服务类失败（超时 / 鉴权 / 限流等）已由 :func:`llm.chat` 包装为
    BizException 直接上抛，**不进入**解析重试（避免最坏情形 90s × 2）。

    Args:
        goal_id: 目标 id（日志用）。
        ctx: 目标上下文快照。

    Returns:
        dict: 截断与规范化后的知识树。

    Raises:
        BizException: code=3000 / HTTP 502，两次解析均失败时抛出。
    """
    messages = _build_breakdown_messages(ctx)
    first_output = ""
    for attempt in (1, 2):
        try:
            text = await llm.chat(messages)
            if attempt == 1:
                first_output = text
            return _truncate_tree(_parse_roadmap(text))
        except _ParseFailed as exc:
            if attempt == 1:
                truncated = first_output[:_FIRST_OUTPUT_MAX_CHARS]
                messages = messages + [
                    {"role": "assistant", "content": first_output},
                    {
                        "role": "user",
                        "content": RETRY_PROMPT.format(
                            failure_reason=exc.reason,
                            first_output_truncated=truncated,
                        ),
                    },
                ]
                continue
            logger.warning(
                "goal_id=%s 拆解解析失败(两次): 原因=%s", goal_id, exc.reason
            )
            raise BizException(
                CODE_LLM_FAILED, "AI 解析失败，请重试", http_status=502
            ) from None
    # 理论不可达（循环内必然 return 或 raise）。
    raise BizException(
        CODE_LLM_FAILED, "AI 解析失败，请重试", http_status=502
    )


# ---------------------------------------------------------------------------
# CRUD（请求级短事务，保持 get_db 注入模式）
# ---------------------------------------------------------------------------
def create_goal(db: Session, user_id: int, data: GoalCreate) -> dict:
    """创建学习目标（status 固定 active、roadmap 初始 None）。

    Args:
        db: 数据库会话（依赖注入）。
        user_id: 当前用户 id。
        data: 创建入参。

    Returns:
        dict: GoalOut 结构。

    Raises:
        BizException: code=1007 / HTTP 400，日期倒置时抛出。
    """
    _validate_date_order(data.start_date, data.end_date)
    goal = LearningGoal(
        user_id=user_id,
        title=data.title,
        goal_type=data.goal_type,
        description=data.description,
        start_date=data.start_date,
        end_date=data.end_date,
        status=GoalStatus.ACTIVE,
        roadmap=None,
        roadmap_updated_at=None,
    )
    db.add(goal)
    db.commit()
    db.refresh(goal)
    return _serialize_goal(goal)


def update_goal(db: Session, user_id: int, goal_id: int, data: GoalUpdate) -> dict:
    """编辑学习目标（字段级部分更新，仅写入已提交且非 None 的字段）。

    禁止触碰 roadmap / roadmap_updated_at / user_id（schema 未声明 +
    extra="forbid" 双保险）。日期先后校验与库中现值**合并后**判断
    （仅提交 start 时也要与库中 end 比较）。

    Args:
        db: 数据库会话（依赖注入）。
        user_id: 当前用户 id。
        goal_id: 目标 id。
        data: 更新入参。

    Returns:
        dict: 更新后的 GoalOut 结构。

    Raises:
        BizException: code=1005 / 404（不存在或越权）；
            code=1007 / 400（合并后日期倒置）。
    """
    goal = _get_goal_or_404(db, user_id, goal_id)
    updates: dict = {
        k: v for k, v in data.model_dump(exclude_unset=True).items() if v is not None
    }
    if updates:
        _validate_date_order(
            updates.get("start_date", goal.start_date),
            updates.get("end_date", goal.end_date),
        )
        for key, value in updates.items():
            setattr(goal, key, value)
        db.commit()
        db.refresh(goal)
    return _serialize_goal(goal)


def delete_goal(db: Session, user_id: int, goal_id: int) -> dict:
    """删除学习目标（返回被删对象；掌握度记录天然保留）。

    关联任务 / 计划的 ``goal_id`` 由数据库层 ``ondelete="SET NULL"`` +
    PRAGMA foreign_keys=ON 自动置空（service 零额外代码）；
    ``knowledge_mastery`` 无外键关联，拆解生成的掌握度记录保留
    （spec 裁定①：删目标不抹学习历史）。

    Args:
        db: 数据库会话（依赖注入）。
        user_id: 当前用户 id。
        goal_id: 目标 id。

    Returns:
        dict: 被删目标的 GoalOut 结构。

    Raises:
        BizException: code=1005 / HTTP 404。
    """
    goal = _get_goal_or_404(db, user_id, goal_id)
    snapshot = _serialize_goal(goal)
    db.delete(goal)
    db.commit()
    return snapshot


def get_roadmap(db: Session, user_id: int, goal_id: int) -> dict:
    """查询目标知识树（roadmap 为 None 时原样返回 null）。

    Args:
        db: 数据库会话（依赖注入）。
        user_id: 当前用户 id。
        goal_id: 目标 id。

    Returns:
        dict: RoadmapOut 结构（roadmap=None 表示从未拆解，
        禁止被替换成 {}，spec 6.1 规则 7）。

    Raises:
        BizException: code=1005 / HTTP 404。
    """
    goal = _get_goal_or_404(db, user_id, goal_id)
    return RoadmapOut.model_validate(
        {
            "goal_id": goal.id,
            "roadmap": goal.roadmap,
            "roadmap_updated_at": goal.roadmap_updated_at,
        }
    ).model_dump(mode="json")


# ---------------------------------------------------------------------------
# AI 拆解主流程（双段短会话事务边界，design 2.1.3-B）
# ---------------------------------------------------------------------------
async def breakdown_goal(user_id: int, goal_id: int) -> dict:
    """AI 拆解目标为知识树，落库并初始化叶子掌握度。

    全流程三阶段（阶段② LLM 调用期间**不持有任何数据库会话**）：
        ① 短会话：归属校验 + 快照目标上下文；
        ② LLM 调用 + 解析（互斥标志保护，两次尝试）+ 截断 + 叶子提取；
        ③ 短会话单写事务：重查归属 → 写树 / 时间戳 / 幂等插入叶子，
          **一个 commit 完成三件事**（要么同时生效、要么同时失败）。

    Args:
        user_id: 当前用户 id。
        goal_id: 目标 id。

    Returns:
        dict: RoadmapOut 结构（含新知识树与拆解时间）。

    Raises:
        BizException: code=1005 / 404（不存在、越权或拆解期间被并发删除）；
            code=1007 / 400（同一目标并发拆解互斥冲突）；
            code=3000 / 502（LLM 服务类失败 / 配置缺失 / 两次解析均失败）。
    """
    # 互斥检查与登记：两条语句之间无 await，事件循环单线程下天然原子。
    if goal_id in _breakdown_in_progress:
        raise BizException(
            CODE_BIZ_CONFLICT, "该目标正在拆解中，请稍候", http_status=400
        )
    _breakdown_in_progress.add(goal_id)
    try:
        started = time.monotonic()
        # 阶段①：短会话（毫秒级）——归属校验 + 读取目标上下文。
        with SessionLocal() as db:
            goal = _get_goal_or_404(db, user_id, goal_id)
            ctx = _GoalContext(
                title=goal.title,
                goal_type=goal.goal_type,
                description=goal.description,
                start_date=goal.start_date,
                end_date=goal.end_date,
                has_roadmap=goal.roadmap is not None,
            )
        # —— 此处无任何数据库会话，LLM 可安全占用任意时长（阶段②）——
        tree = await _call_and_parse(goal_id, ctx)
        leaves = _collect_leaves(tree)
        # 阶段③：短会话（毫秒级）——单写事务。
        roadmap_updated_at: datetime
        with SessionLocal() as db:
            goal = _get_goal_or_404(db, user_id, goal_id)
            roadmap_updated_at = utc_now()
            goal.roadmap = tree
            goal.roadmap_updated_at = roadmap_updated_at
            existing = set(
                db.scalars(
                    select(KnowledgeMastery.knowledge_point).where(
                        KnowledgeMastery.user_id == user_id,
                        KnowledgeMastery.knowledge_point.in_(leaves),
                    )
                )
            )
            # 幂等写入（spec 规则 7/8）：已存在的知识点（无论来源与分数）
            # 一律跳过，仅对差集插入 0 分待学记录。
            for kp in sorted(leaves - existing):
                db.add(
                    KnowledgeMastery(
                        user_id=user_id,
                        knowledge_point=kp,
                        mastery_score=0,
                        source=MasterySource.GOAL_BREAKDOWN,
                    )
                )
            try:
                db.commit()
            except Exception as exc:  # noqa: BLE001 —— 极端并发兜底
                # 唯一约束冲突极端兜底（design 2.1.3-E）：整体回滚后按
                # 「已存在」语义重放一次（该知识点已存在即幂等目标达成）。
                logger.warning(
                    "goal_id=%s 拆解落库冲突，按幂等语义重放: %s",
                    goal_id,
                    type(exc).__name__,
                )
                db.rollback()
                goal = _get_goal_or_404(db, user_id, goal_id)
                roadmap_updated_at = utc_now()
                goal.roadmap = tree
                goal.roadmap_updated_at = roadmap_updated_at
                existing = set(
                    db.scalars(
                        select(KnowledgeMastery.knowledge_point).where(
                            KnowledgeMastery.user_id == user_id,
                            KnowledgeMastery.knowledge_point.in_(leaves),
                        )
                    )
                )
                for kp in sorted(leaves - existing):
                    db.add(
                        KnowledgeMastery(
                            user_id=user_id,
                            knowledge_point=kp,
                            mastery_score=0,
                            source=MasterySource.GOAL_BREAKDOWN,
                        )
                    )
                try:
                    db.commit()
                except Exception:  # noqa: BLE001
                    db.rollback()
                    raise BizException(
                        CODE_INTERNAL_ERROR,
                        "拆解结果写入失败，请重试",
                        http_status=500,
                    ) from None
        elapsed_ms = int((time.monotonic() - started) * 1000)
        logger.info(
            "goal_id=%s 拆解成功: 叶子数=%s 深度=%s 耗时=%s(ms)",
            goal_id,
            len(leaves),
            _tree_depth(tree),
            elapsed_ms,
        )
        return RoadmapOut.model_validate(
            {
                "goal_id": goal_id,
                "roadmap": tree,
                "roadmap_updated_at": roadmap_updated_at,
            }
        ).model_dump(mode="json")
    finally:
        # 任何路径（含异常）必清除标志，杜绝死锁标志。
        _breakdown_in_progress.discard(goal_id)