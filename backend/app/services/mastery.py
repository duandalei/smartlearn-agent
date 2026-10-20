"""知识点掌握度重放引擎（P6 核心，唯一公式实现）。

【P7 消费口径标注】``source='goal_breakdown'`` 且 ``mastery_score=0``
的知识点是目标拆解的正常产物（已规划、尚未真正学习）；本模块产出的
掌握度数据**本身不过滤**这批行，但 P7 Dashboard 薄弱点分析消费时
**必须排除**「source='goal_breakdown' 且 mastery_score=0」的知识点
（PROJECT_CONTEXT §6.12）；一旦某知识点经学习记录重放过（source
变为 'record'），即恢复正常参与排序。

事务契约：本模块全程**纯操作不 commit**——事务边界单点收敛在
``services/record.py`` 的三个编排函数（create / update / delete），
构造上保证「学习记录写入 / 掌握度重放 / 任务时长回填」三部分原子
（spec 4.2.1）。``recalculate_all`` 为独立入口，自带单次 commit。

时区口径：衰减间隔按北京时间「今天」计算，``TZ_BEIJING`` 复用
``services/task.py`` 的定义（单向依赖，无环；spec 6.3.4 / 裁定㉒）。
"""

from __future__ import annotations

import json
import logging
from datetime import date, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.base import utc_now
from app.models.enums import MasterySource
from app.models.mastery import KnowledgeMastery
from app.models.mistake import Mistake
from app.models.record import LearningRecord
from app.services.task import TZ_BEIJING

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 公式参数（唯一数据源，禁止散落硬编码）
# ---------------------------------------------------------------------------
#: EMA 聚合的旧分权重（PROJECT_CONTEXT §6.12 定稿公式）。
EMA_OLD_WEIGHT: float = 0.7
#: EMA 聚合的本次自评权重。
EMA_NEW_WEIGHT: float = 0.3
#: 每道错题的扣分数。
MISTAKE_DEDUCTION: int = 3
#: 时间衰减的免扣门槛（天）：距最后一次学习记录超过该天数才开始衰减。
DECAY_GRACE_DAYS: int = 30
#: 衰减步长（天）：每满该天数扣一次。
DECAY_STEP_DAYS: int = 7
#: 每个衰减步长的扣分数。
DECAY_STEP_PENALTY: int = 2

#: 每日衰减检查的进程内判重标记（user_id → 最近已检查的北京日期）。
#: 生命周期 = 进程生命周期；仅成功后写入，失败不标记（同日可重试）。
_daily_decay_checked: dict[int, date] = {}


def _replay_one_kp(
    db: Session, user_id: int, kp: str, now: datetime
) -> None:
    """单知识点三步重放（**全项目唯一**的掌握度公式实现）。

    掌握度计算（按知识点重放，三步顺序固定，禁止调序/跳步）：

    第一步 · EMA 聚合（按知识点重放，禁止增量更新）：
        取该用户该知识点全部 mastery_level 非空的学习记录，
        按 (study_date, id) 升序排列，从 0 分开始逐条应用：
            新分数 = 旧分数 × 0.7 + 该条自评 × 0.3
        每步结果为凸组合，天然落在 0–100（首条：0×0.7 + 自评×0.3）。
        禁止以「库中旧值 × 0.7 + 本次自评 × 0.3」增量更新——
        EMA 顺序敏感，允许补记历史日期时增量结果必然与全量重放漂移
        （例：先记 10-10 自评 80 得 24，再补记 09-01 自评 100，
        正确重放 = 0×0.7+100×0.3=30 → 30×0.7+80×0.3=45；
        错误增量 = 24×0.7+100×0.3=46.8）。

    第二步 · 错题扣分：
        score = max(第一步结果 − 该知识点错题数 × 3, 0)

    第三步 · 时间衰减（衰减基准 = 该知识点最后一次学习记录的 study_date；
        禁止用 updated_at 作基准——重放会刷新 updated_at，把衰减输入清零，
        导致 recalculate_all 两次结果不一致）：
        last_study = 该用户该知识点全部学习记录（含未自评记录）的 max(study_date)
        ——衡量「多久没学」，而非「多久没写库」
        间隔天数 interval = (北京今天 − last_study).days   （timedelta.days）
        若 interval > 30：衰减 = ((interval − 30) // 7) × 2
        score = max(第二步结果 − 衰减, 0)
        没有任何学习记录的知识点（零分待学点、记录被删空的知识点）不做衰减。
        （反例：若误用 updated_at 作基准——上次学习 40 天后第一次重算扣
        ((40−30)//7)×2=2 分并刷新 updated_at=now，第二次重算 interval≈0
        不扣 → 两次差 2 分，违反幂等；故衰减禁用 updated_at。）

    写回：最终值 round(score, 2)；知识点不存在则 INSERT（source='record'），
          存在则 UPDATE mastery_score / source='record' / updated_at=now
          （updated_at 仅表示最近更新时间，不参与任何计算）。

    Example（验收数值推演，spec 5.6.1 / design 2.1.3-A）:
        - 验收①：Transformer 无行，首条自评 60 → 0×0.7 + 60×0.3 = 18，
          INSERT source='record'。
        - 验收②：再提交自评 80（study_date 在后）→ 18×0.7 + 80×0.3
          = 36.6，上升且 ≤100。
        - 上限：重放至 90 后追加自评 100 → 90×0.7 + 100×0.3 = 93。
        - 乱序补记：已有 R2（10-10，自评 80，当前 24），补记 R1
          （09-01，自评 100）→ 按 (study_date, id) 升序 R1 在前：
          0×0.7+100×0.3=30 → 30×0.7+80×0.3=45（≠ 46.8）。
        - 衰减边界（interval = 北京今天 − last_study）：35 天 →
          (35−30)//7=0 不扣；37 天 → 扣 2；44 天 → 扣 4；衰减前 3
          分间隔 100 天 → max(3−((100−30)//7)×2, 0)=0。
        - 幂等（40 天场景）：last_study 距今 40 天 → 第一次重算衰减
          ((40−30)//7)×2=2 分；第二次重算 last_study 未变（重放只写
          knowledge_mastery、不改学习记录）→ interval 仍 40 天 → 仍
          衰减 2 分，两次分数完全一致（若误用 updated_at 作基准：第一
          次衰减 2 分后 updated_at=now，第二次 interval≈0 不衰减 →
          分数高 2 分，违反幂等）。
        - 精度：全程仅最终写回值 round(score, 2)，中间步骤不取整
          （保持数学语义；30×0.7+80×0.3 的浮点尾差由最终 round 消除，
          45.0000000000001 → 45.0）。

    Args:
        db: 数据库会话（纯操作，不 commit——事务归调用方）。
        user_id: 当前用户 id。
        kp: 知识点名称（单数，来自 learning_records.knowledge_points
            的数组元素）。
        now: 本次重放的统一时间基准（aware UTC，由调用方取一次复用）。

    Returns:
        None: 结果直接写回 ``knowledge_mastery``（经调用方 commit 生效）。
    """
    # JSON 引号边界匹配（平移 services/task.py 裁定⑩）：json.dumps 仅为
    # 构造带引号边界的匹配串（'"Transformer"'），非字段序列化；在
    # ["Multi-Head Attention"] 中 instr 找不到 '"Transformer"'
    #（Attention 前是空格非引号）→ 不误命中。
    kp_json = json.dumps(kp, ensure_ascii=False)

    # 该知识点全部学习记录（含未自评），按 (study_date, id) 升序。
    # （必须显式 ORDER BY：不排序时 SQLite 按 rowid≈插入序返回，补记
    # 历史日期的记录会排到其真实时间线之后，EMA 顺序敏感即出错——
    # spec 5.6.1 乱序补记用例 45 ≠ 46.8 正是此坑。）
    records = db.execute(
        select(
            LearningRecord.study_date, LearningRecord.mastery_level
        )
        .where(
            LearningRecord.user_id == user_id,
            func.instr(LearningRecord.knowledge_points, kp_json) > 0,
        )
        .order_by(LearningRecord.study_date, LearningRecord.id)
    ).all()

    # 第一步：EMA 聚合——仅 mastery_level 非空的记录参与，从 0 重放。
    score = 0.0
    for _, mastery_level in records:
        if mastery_level is None:
            continue
        score = score * EMA_OLD_WEIGHT + mastery_level * EMA_NEW_WEIGHT

    # 第二步：错题扣分（每道 -3，下限 0）。
    mistake_count = (
        db.scalar(
            select(func.count())
            .select_from(Mistake)
            .where(
                Mistake.user_id == user_id,
                Mistake.knowledge_point == kp,
            )
        )
        or 0
    )
    score = max(score - int(mistake_count) * MISTAKE_DEDUCTION, 0.0)

    # 第三步：时间衰减——基准 = 全部学习记录（含未自评）的 max(study_date)，
    # 禁用 updated_at（本函数写回时刷新 updated_at，作基准会破坏幂等）。
    last_study: date | None = None
    for study_date, _ in records:
        if last_study is None or study_date > last_study:
            last_study = study_date
    if last_study is not None:
        interval = (now.astimezone(TZ_BEIJING).date() - last_study).days
        if interval > DECAY_GRACE_DAYS:
            decay = (
                (interval - DECAY_GRACE_DAYS) // DECAY_STEP_DAYS
            ) * DECAY_STEP_PENALTY
            score = max(score - decay, 0.0)

    # 写回：不存在则 INSERT（禁止只 UPDATE，spec 5.6.1 规则 5），
    # 存在则 UPDATE 三字段；updated_at 仅表示最近更新时间。
    final_score = round(score, 2)
    row = db.scalar(
        select(KnowledgeMastery).where(
            KnowledgeMastery.user_id == user_id,
            KnowledgeMastery.knowledge_point == kp,
        )
    )
    if row is None:
        db.add(
            KnowledgeMastery(
                user_id=user_id,
                knowledge_point=kp,
                mastery_score=final_score,
                source=MasterySource.RECORD,
                updated_at=now,
            )
        )
    else:
        row.mastery_score = final_score
        row.source = MasterySource.RECORD
        row.updated_at = now


def replay_knowledge_points(
    db: Session, user_id: int, knowledge_points: set[str] | list[str]
) -> None:
    """批量重放知识点集合（记录写入事务内的调用入口）。

    遍历知识点集合逐个调 :func:`_replay_one_kp`；空集合直接返回。
    **不 commit**——事务边界归调用方（record service 的三个编排
    函数），保证记录 / 掌握度 / 任务回填三部分原子。

    Args:
        db: 数据库会话（纯操作，不 commit）。
        user_id: 当前用户 id。
        knowledge_points: 受影响知识点集合（重复元素天然去重）。

    Returns:
        None: 结果经调用方 commit 生效。
    """
    if not knowledge_points:
        return
    now = utc_now()
    for kp in sorted(set(knowledge_points)):
        _replay_one_kp(db, user_id, kp, now)


def recalculate_all(db: Session, user_id: int) -> dict:
    """全量重算当前用户的掌握度（数据修复 / 答辩演示入口）。

    **重放范围口径（关键决策，design 2.1.3-A）**：重放范围 = 该用户
    全部 ``mastery_level`` 非空的学习记录的 knowledge_points 元素去重
    集合 R；``knowledge_mastery`` 中不属于 R 的行**一律跳过、保持
    原值**。理由：
    1. 保护零分待学点——``source='goal_breakdown'`` 且 0 分的行若被
       全表重放，EMA 无记录得 0、source 被改写为 'record'，零分待学
       点语义被破坏，P7 薄弱点排除条件失效；
    2. 保护种子演示底座——self_report（Python 90 等）与种子 record
       行无学习记录，全表重放会把它们抹为 0 分；且按 study_date 衰减
       基准，无学习记录（无 last_study）的知识点不做衰减。
    3. 删除删空场景一致性——某点记录被删空时，单点路径写 0 分；此后
       recalculate_all 因该点 ∉ R 跳过，保持 0 分，两入口一致。

    **幂等保证**：衰减基准为该知识点最后一条学习记录的 study_date，
    重放只写 knowledge_mastery、不改变学习记录 → 衰减输入在两次重算
    间保持不变（同一天内两次执行 interval 相同）、EMA 输入亦未变 →
    连续执行两次结果完全一致。

    Args:
        db: 数据库会话（本函数自带事务：逐点重放后单次 commit）。
        user_id: 目标用户 id。

    Returns:
        dict: ``{"user_id": int, "replayed": int}``——重放的知识点数。
    """
    rows = db.scalars(
        select(LearningRecord.knowledge_points).where(
            LearningRecord.user_id == user_id,
            LearningRecord.mastery_level.is_not(None),
        )
    )
    kp_set: set[str] = {kp for kps in rows for kp in (kps or [])}

    now = utc_now()
    for kp in sorted(kp_set):
        _replay_one_kp(db, user_id, kp, now)
    db.commit()
    return {"user_id": user_id, "replayed": len(kp_set)}

def run_daily_decay_check(db: Session, user_id: int) -> bool:
    """每日掌握度衰减检查（Dashboard overview 请求前触发，每用户每天最多一次）。

    取舍一 · 重算范围：种子掌握度值（10 条）是初始化脚本直接写入的，
    未经过公式重放；若每日访问都做全量重算，会把这些值整体改写
    （如概率论 40 → 约 32、动态规划 45 → 19.5），推翻演示基线。
    因此衰减检查只作用于「衰减值 > 0」的知识点（last_study 距今
    > 30 天）。这是演示种子数据与公式计算值并存的已知差异，P13 的
    演示数据重置脚本会统一处理。

    取舍二 · 判重方式：判重使用进程内模块级字典（user_id → 日期），
    不建持久化表——为「今天检查过没有」的幂等标记新增一张表，代价
    与收益不成比例（契约 §6 表清单、init_db 建表、models 导出、
    库版本排查点全部受牵连）。多 worker 部署时各进程独立判断
    （每 worker 各执行一次，重算幂等无正确性风险）；本项目为单进程
    uvicorn 不受影响；未来若上多 worker，再升级为持久化标记。

    Args:
        db: 数据库会话（自带事务：候选重放后单次 commit）。
        user_id: 当前用户 id。

    Returns:
        bool: 本次是否实际执行了重算（今日已检查或失败均返回 False）。
    """
    today = utc_now().astimezone(TZ_BEIJING).date()
    if _daily_decay_checked.get(user_id) == today:
        return False
    try:
        rows = db.execute(
            select(
                LearningRecord.study_date, LearningRecord.knowledge_points
            ).where(LearningRecord.user_id == user_id)
        ).all()
        last_study: dict[str, date] = {}
        for study_date, kps in rows:
            for kp in kps or []:
                prev = last_study.get(kp)
                if prev is None or study_date > prev:
                    last_study[kp] = study_date
        candidates = {
            kp
            for kp, d in last_study.items()
            if (today - d).days > DECAY_GRACE_DAYS
        }
        if candidates:
            replay_knowledge_points(db, user_id, candidates)
        db.commit()
        _daily_decay_checked[user_id] = today
        return True
    except Exception:
        db.rollback()
        logger.warning(
            "每日衰减检查失败 user_id=%s", user_id, exc_info=True
        )
        return False