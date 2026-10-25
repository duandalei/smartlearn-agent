"""计划生成测试（tasks.md 组 8：scheduler 引擎单测 E 组 + G1–G10 服务级）。

覆盖验收：D1（结构容量）/ D2（落库 OP1）/ D7（多周并存）/ D8（重生成
+ 幽灵清理）/ D9（计划侧降级）/ D14（事务原子性）。

- 引擎单测（E 组）：构造 dataclass 直测，不依赖 LLM 与 DB；
- 服务级（G 组）：mock 规划 LLM（``app.services.plan.llm.chat`` 三态）
  + 真实 SQLite + ASGI 直调；日期断言全部动态计算（北京时区口径）。
"""

from __future__ import annotations

import json
from datetime import date, datetime, time, timedelta, timezone
from typing import Any

import pytest

from app.analytics.scheduler import (
    CANDIDATE_MAX_MINUTES,
    DAY_SLOT_ANCHORS,
    REST_WEEKDAY,
    ScheduleCandidate,
    ScheduleInput,
    build_rule_candidates,
    build_week_schedule,
    current_week_window,
    next_week_window,
)

TZ = timezone(timedelta(hours=8))


def _next_monday() -> date:
    """北京今天 → 下周一（与被测代码同口径动态计算）。"""
    today = datetime.now(TZ).date()
    return today + timedelta(days=7 - today.weekday())


def _week_of(monday: date) -> list[date]:
    return [monday + timedelta(days=i) for i in range(7)]


def _this_monday() -> date:
    """北京今天 → 本周一。"""
    today = datetime.now(TZ).date()
    return today - timedelta(days=today.weekday())


# ---------------------------------------------------------------------------
# E 组：scheduler 引擎单测（纯函数直测）
# ---------------------------------------------------------------------------


def test_engine_next_week_window() -> None:
    """周期推导：今天周四 → 下周一~下周日；今天周一 → 恰 +7。"""
    thursday = date(2026, 10, 29)
    start, end = next_week_window(thursday)
    assert (start, end) == (date(2026, 11, 2), date(2026, 11, 8))
    monday = date(2026, 11, 2)
    start2, end2 = next_week_window(monday)
    assert (start2, end2) == (date(2026, 11, 9), date(2026, 11, 15))


def test_engine_current_week_window() -> None:
    """本周周期推导：周一 → 当天~周日；周四 → 本周一~周日；周日 → 本周一~周日。"""
    monday = date(2026, 10, 26)
    assert current_week_window(monday) == (monday, monday + timedelta(days=6))
    thursday = date(2026, 10, 29)
    assert current_week_window(thursday) == (monday, monday + timedelta(days=6))
    sunday = date(2026, 11, 1)
    assert current_week_window(sunday) == (monday, sunday)


def test_engine_capacity_and_no_conflict() -> None:
    """硬约束构造性：每日合计 ≤ 容量、start_time 无重复、时长恒等。"""
    monday = date(2026, 10, 26)
    week = _week_of(monday)
    candidates = [
        ScheduleCandidate(topic=f"主题{i}", estimated_minutes=50, priority="medium")
        for i in range(10)
    ]
    out = build_week_schedule(
        ScheduleInput(candidates=candidates, daily_capacity_minutes=60, week_days=week)
    )
    per_day: dict[date, int] = {}
    slots: set[tuple[date, time]] = set()
    for item in out.placed:
        per_day[item.plan_date] = per_day.get(item.plan_date, 0) + item.estimated_minutes
        assert (item.end_time.hour * 60 + item.end_time.minute) - (
            item.start_time.hour * 60 + item.start_time.minute
        ) == item.estimated_minutes
        key = (item.plan_date, item.start_time)
        assert key not in slots, f"时段冲突：{key}"
        slots.add(key)
    assert all(v <= 60 for v in per_day.values()), per_day
    assert REST_WEEKDAY not in per_day  # 周五跳过


def test_engine_three_slot_anchors_op2() -> None:
    """OP2 三窗口 + 首选锚点按星期（用户 2026-10-24 裁定）。

    周一（工作日）首选 19:00：连排满晚间窗口后推进 14:00、再 09:00；
    周六首选 14:00（需求文档第 13 章「周六 14:00-17:00」作息语义）。
    """
    monday = date(2026, 10, 26)
    week = _week_of(monday)
    out = build_week_schedule(
        ScheduleInput(
            candidates=[
                ScheduleCandidate(topic=f"X{i}", estimated_minutes=90)
                for i in range(7)
            ],
            daily_capacity_minutes=840,
            week_days=week,
        )
    )
    same_day = [i for i in out.placed if i.plan_date == monday]
    starts = [str(i.start_time)[:5] for i in same_day]
    assert starts == ["19:00", "20:30", "14:00", "15:30", "17:00", "09:00", "10:30"], starts
    assert DAY_SLOT_ANCHORS == [time(9, 0), time(14, 0), time(19, 0)]

    # 周六首选下午：容量 60/天时逐日一条，周六那条锚点必须是 14:00
    saturday = monday + timedelta(days=5)
    out_sat = build_week_schedule(
        ScheduleInput(
            candidates=[
                ScheduleCandidate(topic=f"S{i}", estimated_minutes=60)
                for i in range(6)
            ],
            daily_capacity_minutes=60,
            week_days=week,
        )
    )
    sat_items = [i for i in out_sat.placed if i.plan_date == saturday]
    assert [str(i.start_time)[:5] for i in sat_items] == ["14:00"]

    # 工作日容量 ≤ 300 时锚点是 19:00（原「七天全 09:00」缺陷的回归断言）
    out_weekday = build_week_schedule(
        ScheduleInput(
            candidates=[ScheduleCandidate(topic="W", estimated_minutes=120)],
            daily_capacity_minutes=120,
            week_days=week,
        )
    )
    assert str(out_weekday.placed[0].start_time)[:5] == "19:00"


def test_engine_unplaced_oversize_candidate() -> None:
    """单条目 > CANDIDATE_MAX_MINUTES 直接进 unplaced（中文原因）。"""
    monday = date(2026, 10, 26)
    out = build_week_schedule(
        ScheduleInput(
            candidates=[ScheduleCandidate(topic="超长专题", estimated_minutes=300)],
            daily_capacity_minutes=600,
            week_days=_week_of(monday),
        )
    )
    assert out.placed == []
    assert len(out.unplaced) == 1
    assert "超出" in out.unplaced[0].reason
    assert CANDIDATE_MAX_MINUTES == 240


def test_engine_overdue_candidates_first() -> None:
    """逾期/临期候选（deadline 非空升序）排在周期前段。"""
    monday = date(2026, 10, 26)
    now = datetime(2026, 10, 26, 8, 0, tzinfo=timezone.utc)
    out = build_week_schedule(
        ScheduleInput(
            candidates=[
                ScheduleCandidate(topic="无截止A", estimated_minutes=60),
                ScheduleCandidate(
                    topic="截止早", estimated_minutes=60, deadline=now + timedelta(hours=10)
                ),
                ScheduleCandidate(
                    topic="截止晚", estimated_minutes=60, deadline=now + timedelta(hours=40)
                ),
            ],
            daily_capacity_minutes=300,
            week_days=_week_of(monday),
            now=now,
        )
    )
    topics = [i.topic for i in out.placed]
    assert topics.index("截止早") < topics.index("截止晚") < topics.index("无截止A")


def test_engine_rule_candidates_order_and_ids() -> None:
    """降级候选：逾期 → 临期 → roadmap/薄弱点；逾期候选携带 related_task_id。"""
    now = datetime(2026, 10, 26, 8, 0, tzinfo=timezone.utc)
    overdue = [
        {
            "id": 11,
            "title": "逾期任务",
            "estimated_minutes": 60,
            "priority": "high",
            "knowledge_points": ["CNN"],
            "deadline": now - timedelta(hours=2),
        }
    ]
    due_soon = [
        {
            "id": 12,
            "title": "临期任务",
            "estimated_minutes": 45,
            "priority": "medium",
            "knowledge_points": ["RNN"],
            "deadline": now + timedelta(hours=30),
        }
    ]
    candidates = build_rule_candidates(
        overdue, due_soon, ["线性代数", "概率论"], [{"knowledge_point": "注意力", "mastery_score": 30.0}]
    )
    topics = [c.topic for c in candidates]
    assert topics[0] == "逾期任务" and topics[1] == "临期任务"
    assert candidates[0].related_task_id == 11 and candidates[0].deadline is not None
    assert any("线性代数" in t for t in topics)
    assert any("注意力" in t for t in topics)
    assert all(c.estimated_minutes >= 15 for c in candidates)


# ---------------------------------------------------------------------------
# 测试辅助（mock 规划 LLM 三态 + 数据构造）
# ---------------------------------------------------------------------------


def _install_plan_llm(
    monkeypatch: pytest.MonkeyPatch, responder: Any
) -> list[list[dict[str, Any]]]:
    """注入规划 LLM fake 并捕获每次调用入参。"""
    captured: list[list[dict[str, Any]]] = []

    async def fake(messages: list[dict[str, Any]]) -> str:
        captured.append([dict(m) for m in messages])
        result = responder(messages)
        if isinstance(result, Exception):
            raise result
        return result

    monkeypatch.setattr("app.services.plan.llm.chat", fake)
    return captured


def _candidates_json(candidates: list[dict[str, Any]]) -> str:
    """构造 LLM 候选 JSON（含 ```json 围栏——解析流水线覆盖两种形态）。"""
    return f"```json\n{json.dumps({'candidates': candidates}, ensure_ascii=False)}\n```"


def _five_candidates(related_task_id: int | None = None, count: int = 5) -> list[dict[str, Any]]:
    """固定候选（G1/G3 确定性基础；count 可扩到 12 条覆盖 7 天）。"""
    pool = [
        {"topic": "Transformer 注意力机制", "knowledge_points": ["Transformer"], "estimated_minutes": 45, "priority": "high"},
        {"topic": "线性代数特征值", "knowledge_points": ["线性代数"], "estimated_minutes": 30, "priority": "medium"},
        {"topic": "概率论基础", "knowledge_points": ["概率论"], "estimated_minutes": 45, "priority": "medium"},
        {"topic": "Python 数据处理", "knowledge_points": ["Python"], "estimated_minutes": 30, "priority": "low"},
        {"topic": "模型评估方法", "knowledge_points": ["评估"], "estimated_minutes": 45, "priority": "medium"},
        {"topic": "卷积神经网络", "knowledge_points": ["CNN"], "estimated_minutes": 45, "priority": "medium"},
        {"topic": "循环神经网络", "knowledge_points": ["RNN"], "estimated_minutes": 45, "priority": "low"},
        {"topic": "过拟合与正则化", "knowledge_points": ["正则化"], "estimated_minutes": 45, "priority": "medium"},
        {"topic": "梯度下降优化", "knowledge_points": ["优化"], "estimated_minutes": 45, "priority": "medium"},
        {"topic": "数据预处理", "knowledge_points": ["数据"], "estimated_minutes": 45, "priority": "low"},
        {"topic": "聚类算法", "knowledge_points": ["聚类"], "estimated_minutes": 45, "priority": "medium"},
        {"topic": "决策树模型", "knowledge_points": ["决策树"], "estimated_minutes": 45, "priority": "low"},
    ]
    base = pool[:count]
    if related_task_id is not None:
        base[0]["related_task_id"] = related_task_id
    return base


def _set_profile(app_client: Any, user: dict[str, Any], minutes: int) -> None:
    """设置档案每日可学习时长。"""
    resp = app_client.put(
        "/api/v1/profile",
        headers=user["headers"],
        json={"daily_study_minutes": minutes},
    )
    assert resp.status_code == 200, resp.text


def _create_task(
    app_client: Any,
    user: dict[str, Any],
    title: str,
    deadline: datetime | None = None,
    priority: str = "medium",
) -> int:
    """创建任务并返回 id。"""
    payload: dict[str, Any] = {"title": title, "priority": priority}
    if deadline is not None:
        payload["deadline"] = deadline.isoformat()
    resp = app_client.post("/api/v1/tasks", headers=user["headers"], json=payload)
    assert resp.status_code == 200, resp.text
    return resp.json()["data"]["id"]


def _get_user_id(app_client: Any, user: dict[str, Any]) -> int:
    resp = app_client.get("/api/v1/auth/me", headers=user["headers"])
    return resp.json()["data"]["id"]


def _db():
    """惰性导入 SessionLocal（conftest 已切换测试库）。"""
    from app.db.session import SessionLocal

    return SessionLocal()


# ---------------------------------------------------------------------------
# G 组：服务级用例（mock LLM + 真实 SQLite）
# ---------------------------------------------------------------------------


@pytest.fixture
def demo_env(app_client: Any, user_a: dict[str, Any]) -> dict[str, Any]:
    """G1 情境：档案 90 分钟/天 + 1 逾期 + 1 临期任务。"""
    _set_profile(app_client, user_a, 90)
    now = datetime.now(TZ)
    overdue_id = _create_task(app_client, user_a, "逾期任务-Transformer 作业", now - timedelta(hours=3), "high")
    due_soon_id = _create_task(app_client, user_a, "临期任务-线性代数测验", now + timedelta(hours=24), "medium")
    return {"overdue_id": overdue_id, "due_soon_id": due_soon_id}


def test_g1_plan_structure_and_capacity(
    app_client: Any, user_a: dict[str, Any], demo_env: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    """D1：7 天条目、每日合计 ≤ 容量、时段无重复、周五休息、逾期临期前段。"""
    _install_plan_llm(
        monkeypatch, lambda _m: _candidates_json(_five_candidates(demo_env["overdue_id"], count=12))
    )
    resp = app_client.post("/api/v1/plans/generate", headers=user_a["headers"], json={})
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data["generated_by"] == "llm"

    next_monday = _next_monday()
    next_sunday = next_monday + timedelta(days=6)
    assert data["plan"]["start_date"] == next_monday.isoformat()
    assert data["plan"]["end_date"] == next_sunday.isoformat()
    assert data["plan"]["status"] == "active"
    assert data["plan"]["parent_plan_id"] is None
    assert data["plan"]["adjust_reason"] is None

    items = data["items"]
    dates = {item["plan_date"] for item in items}
    assert dates == {
        (next_monday + timedelta(days=i)).isoformat() for i in range(7)
    }  # 7 天全覆盖（含周五休息条目）

    per_day: dict[str, int] = {}
    slots: set[tuple[str, Any]] = set()
    for item in items:
        if item["estimated_minutes"] is not None:
            per_day[item["plan_date"]] = per_day.get(item["plan_date"], 0) + item["estimated_minutes"]
        key = (item["plan_date"], item["start_time"])
        assert key not in slots
        slots.add(key)
    assert all(v <= 90 for v in per_day.values()), per_day

    friday = (next_monday + timedelta(days=4)).isoformat()
    friday_items = [i for i in items if i["plan_date"] == friday]
    assert len(friday_items) == 1 and friday_items[0]["topic"] == "休息 / 复习"
    assert friday_items[0]["task_id"] is None and friday_items[0]["start_time"] is None

    task_items = [i for i in items if i["task_id"] is not None]
    first_task = task_items[0]
    assert first_task["topic"] == "Transformer 注意力机制"  # 逾期关联候选排最前
    assert first_task["plan_date"] == next_monday.isoformat()


def test_g2_task_persistence_op1(
    app_client: Any, user_a: dict[str, Any], demo_env: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    """D2 + OP1：任务落库四断言 + 复用既有任务 + 同 plan 内 task_id 无重复。"""
    _install_plan_llm(
        monkeypatch, lambda _m: _candidates_json(_five_candidates(demo_env["overdue_id"]))
    )
    resp = app_client.post("/api/v1/plans/generate", headers=user_a["headers"], json={})
    data = resp.json()["data"]
    plan_id = data["plan"]["id"]

    with _db() as db:
        from sqlalchemy import select

        from app.models.plan import LearningPlanItem
        from app.models.task import Task

        items = db.execute(
            select(LearningPlanItem).where(LearningPlanItem.plan_id == plan_id)
        ).scalars().all()
        task_ids = [i.task_id for i in items if i.task_id is not None]
        # 唯一性铁律断言：一个任务在整个计划里只出现一次
        assert len(task_ids) == len(set(task_ids)), task_ids

        tasks = db.execute(select(Task).where(Task.id.in_(task_ids))).scalars().all()
        reused = next((t for t in tasks if t.id == demo_env["overdue_id"]), None)
        assert reused is not None  # OP1：候选带 related_task_id → 复用既有任务
        reused_item = next(i for i in items if i.task_id == reused.id)
        assert reused.scheduled_date == reused_item.plan_date  # scheduled_date 同步
        assert reused.source == "manual"  # 复用不改来源（那是用户数据）

        created = [t for t in tasks if t.id != demo_env["overdue_id"]]
        assert created, "应有新建 agent 任务"
        assert all(t.source == "agent" and t.status == "todo" for t in created)
        for t in created:
            item = next(i for i in items if i.task_id == t.id)
            assert t.scheduled_date == item.plan_date
            assert t.estimated_minutes == item.estimated_minutes

        rest = [i for i in items if i.task_id is None]
        assert len(rest) == 1 and rest[0].topic == "休息 / 复习"


def test_g3_llm_candidates_consistency(
    app_client: Any, user_a: dict[str, Any], demo_env: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    """G3：mock 固定候选 → 条目 topic 与候选一致且硬约束成立。"""
    candidates = _five_candidates(demo_env["overdue_id"])
    _install_plan_llm(monkeypatch, lambda _m: _candidates_json(candidates))
    resp = app_client.post("/api/v1/plans/generate", headers=user_a["headers"], json={})
    data = resp.json()["data"]
    topics = {i["topic"] for i in data["items"] if i["task_id"] is not None}
    assert topics == {c["topic"] for c in candidates}
    # 硬约束仍由引擎保证（LLM 只选内容不排时）
    per_day: dict[str, int] = {}
    for item in data["items"]:
        if item["estimated_minutes"] is not None:
            per_day[item["plan_date"]] = per_day.get(item["plan_date"], 0) + item["estimated_minutes"]
    assert all(v <= 90 for v in per_day.values())


def test_g4_fallback_rules_structure_isomorphic(
    app_client: Any, user_a: dict[str, Any], demo_env: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    """D9 + 用户指令②：降级路径与 LLM 路径产出**完全相同的结构**（key 集合显式对比）。"""
    from app.core.response import BizException

    llm_data: dict[str, Any] | None = None
    rules_data: dict[str, Any] | None = None

    responder_calls = {"n": 0}

    def ok_then_fail(_messages: list[dict[str, Any]]) -> Any:
        responder_calls["n"] += 1
        if responder_calls["n"] == 1:
            return _candidates_json(_five_candidates(demo_env["overdue_id"]))
        return BizException(3000, "AI 服务暂时不可用", 502)

    _install_plan_llm(monkeypatch, ok_then_fail)
    resp = app_client.post("/api/v1/plans/generate", headers=user_a["headers"], json={})
    assert resp.status_code == 200, resp.text
    llm_data = resp.json()["data"]
    assert llm_data["generated_by"] == "llm"

    # 降级：服务类失败直接降级（不重试）
    _install_plan_llm(
        monkeypatch, lambda _m: BizException(3000, "AI 服务暂时不可用", 502)
    )
    resp2 = app_client.post("/api/v1/plans/generate", headers=user_a["headers"], json={})
    assert resp2.status_code == 200, resp2.text
    rules_data = resp2.json()["data"]
    assert rules_data["generated_by"] == "rules"

    # 用户指令②：两次生成的顶层 key 集合完全相同；items 元素 key 集合相同
    assert set(llm_data.keys()) == set(rules_data.keys())
    assert {frozenset(i.keys()) for i in llm_data["items"]} == {
        frozenset(i.keys()) for i in rules_data["items"]
    }
    assert set(llm_data["plan"].keys()) == set(rules_data["plan"].keys())
    if llm_data["unplaced_tasks"] and rules_data["unplaced_tasks"]:
        assert {frozenset(u.keys()) for u in llm_data["unplaced_tasks"]} == {
            frozenset(u.keys()) for u in rules_data["unplaced_tasks"]
        }
    # 降级产物仍满足硬约束（每日 ≤ 容量）
    per_day: dict[str, int] = {}
    for item in rules_data["items"]:
        if item["estimated_minutes"] is not None:
            per_day[item["plan_date"]] = per_day.get(item["plan_date"], 0) + item["estimated_minutes"]
    assert all(v <= 90 for v in per_day.values())
    # 降级候选来自任务池（逾期任务复用）
    assert any(
        i["task_id"] == demo_env["overdue_id"] for i in rules_data["items"]
    )


def test_g4b_fallback_on_timeout(
    app_client: Any, user_a: dict[str, Any], demo_env: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    """D9：LLM 挂起 + 超时加速 → 降级 rules（真实超时链路）。"""
    import asyncio

    async def hang(_messages: list[dict[str, Any]]) -> str:
        await asyncio.sleep(60)
        return ""

    monkeypatch.setattr("app.services.plan.llm.chat", hang)
    monkeypatch.setattr("app.services.plan.PLAN_LLM_TIMEOUT_S", 0.05)
    resp = app_client.post("/api/v1/plans/generate", headers=user_a["headers"], json={})
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data["generated_by"] == "rules"
    assert data["items"]


def test_g4c_retry_on_parse_failure(
    app_client: Any, user_a: dict[str, Any], demo_env: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    """A7：首次返回破损 JSON → 重试成功（附纠错提示）。"""
    calls = {"n": 0}

    def broken_then_ok(_messages: list[dict[str, Any]]) -> str:
        calls["n"] += 1
        if calls["n"] == 1:
            return "这不是 JSON"
        return _candidates_json(_five_candidates(demo_env["overdue_id"]))

    captured = _install_plan_llm(monkeypatch, broken_then_ok)
    resp = app_client.post("/api/v1/plans/generate", headers=user_a["headers"], json={})
    assert resp.status_code == 200, resp.text
    assert resp.json()["data"]["generated_by"] == "llm"
    assert calls["n"] == 2
    assert any("重新输出" in str(m[-1].get("content", "")) for m in captured if m)


def test_g5_multi_week_coexist(
    app_client: Any, user_a: dict[str, Any], demo_env: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    """D7：本周 active 存在时生成下周 → 两版同时 active、区间不重叠。"""
    today = datetime.now(TZ).date()
    this_monday = today - timedelta(days=today.weekday())
    with _db() as db:
        from app.models.plan import LearningPlan

        db.add(
            LearningPlan(
                user_id=_get_user_id(app_client, user_a),
                goal_id=None,
                title="本周计划",
                version=1,
                status="active",
                source="agent",
                start_date=this_monday,
                end_date=this_monday + timedelta(days=6),
            )
        )
        db.commit()

    _install_plan_llm(
        monkeypatch, lambda _m: _candidates_json(_five_candidates(demo_env["overdue_id"]))
    )
    resp = app_client.post("/api/v1/plans/generate", headers=user_a["headers"], json={})
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]

    with _db() as db:
        from sqlalchemy import select

        from app.models.plan import LearningPlan

        actives = db.execute(
            select(LearningPlan).where(
                LearningPlan.user_id == _get_user_id(app_client, user_a),
                LearningPlan.status == "active",
            )
        ).scalars().all()
        assert len(actives) == 2
        intervals = sorted((p.start_date, p.end_date) for p in actives)
        assert intervals[0][1] < intervals[1][0]  # 区间不重叠
        assert intervals[1] == (
            date.fromisoformat(data["plan"]["start_date"]),
            date.fromisoformat(data["plan"]["end_date"]),
        )


def test_g6_same_period_regenerate_ghost_cleanup(
    app_client: Any, user_a: dict[str, Any], demo_env: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    """D8：同周期重生成归档旧版；幽灵清理只删 agent-todo、done 保留。"""
    _install_plan_llm(
        monkeypatch, lambda _m: _candidates_json(_five_candidates(demo_env["overdue_id"]))
    )
    resp = app_client.post("/api/v1/plans/generate", headers=user_a["headers"], json={})
    first = resp.json()["data"]
    uid = _get_user_id(app_client, user_a)

    # 手动把两个 agent 新建任务之一置 done（用户事实，不应被幽灵清理删除）
    with _db() as db:
        from sqlalchemy import select

        from app.models.plan import LearningPlanItem
        from app.models.task import Task

        plan_id = first["plan"]["id"]
        agent_tasks = db.execute(
            select(Task).where(
                Task.user_id == uid,
                Task.source == "agent",
                Task.id.in_(
                    [
                        i.task_id
                        for i in db.execute(
                            select(LearningPlanItem).where(
                                LearningPlanItem.plan_id == plan_id
                            )
                        ).scalars()
                        if i.task_id is not None
                    ]
                ),
            )
        ).scalars().all()
        assert len(agent_tasks) >= 2
        agent_tasks[0].status = "done"
        agent_tasks[0].completed_at = datetime.now(timezone.utc)
        done_id, todo_id = agent_tasks[0].id, agent_tasks[1].id
        db.commit()

    # 对同一周期重新生成
    resp2 = app_client.post("/api/v1/plans/generate", headers=user_a["headers"], json={})
    assert resp2.status_code == 200, resp2.text
    second = resp2.json()["data"]

    with _db() as db:
        from sqlalchemy import select

        from app.models.plan import LearningPlan
        from app.models.task import Task

        old = db.get(LearningPlan, first["plan"]["id"])
        new = db.get(LearningPlan, second["plan"]["id"])
        assert old.status == "archived" and new.status == "active"
        assert new.version == old.version + 1  # 裁决 #4 per-user 单调
        assert db.get(Task, done_id) is not None  # done 保留
        assert db.get(Task, todo_id) is None  # agent-todo 幽灵清理
        assert db.get(Task, demo_env["overdue_id"]) is not None  # manual 保留


def test_g7_capacity_insufficiency_unplaced(
    app_client: Any, user_a: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    """G7：容量不足可解释——unplaced 非空且任务仍在 tasks 表（scheduled_date=null）。"""
    _set_profile(app_client, user_a, 15)  # 15 分钟/天 → 全周 6×15=90 分钟
    candidates = [
        {"topic": f"专题{i}", "knowledge_points": [], "estimated_minutes": 60, "priority": "medium"}
        for i in range(5)
    ]
    _install_plan_llm(monkeypatch, lambda _m: _candidates_json(candidates))
    resp = app_client.post("/api/v1/plans/generate", headers=user_a["headers"], json={})
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data["generated_by"] == "llm"
    assert len(data["unplaced_tasks"]) >= 4  # 300 分钟 vs 90 分钟容量

    uid = _get_user_id(app_client, user_a)
    with _db() as db:
        from sqlalchemy import select

        from app.models.task import Task

        for entry in data["unplaced_tasks"]:
            task = db.get(Task, entry["task_id"])
            assert task is not None  # 任务不丢失
            assert task.scheduled_date is None
            assert task.source == "agent"
        placed_task_ids = {i["task_id"] for i in data["items"] if i["task_id"]}
        all_ids = placed_task_ids | {u["task_id"] for u in data["unplaced_tasks"]}
        assert len(all_ids) == len(
            db.execute(select(Task.id).where(Task.user_id == uid, Task.source == "agent")).scalars().all()
        )


def test_g8_no_profile_default_and_no_goal(
    app_client: Any, user_a: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    """G8：无档案按默认 60 分钟约束；无目标 goal_id=null 容错。"""
    candidates = [
        {"topic": f"学习{i}", "knowledge_points": [], "estimated_minutes": 60, "priority": "medium"}
        for i in range(5)
    ]
    _install_plan_llm(monkeypatch, lambda _m: json.dumps({"candidates": candidates}))
    resp = app_client.post("/api/v1/plans/generate", headers=user_a["headers"], json={})
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    per_day: dict[str, int] = {}
    for item in data["items"]:
        if item["estimated_minutes"] is not None:
            per_day[item["plan_date"]] = per_day.get(item["plan_date"], 0) + item["estimated_minutes"]
    assert all(v <= 60 for v in per_day.values())  # 默认 60
    assert data["plan"]["goal_id"] is None  # 无目标容错


def test_g9_partial_overlap_1007(
    app_client: Any, user_a: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    """G9：目标周期与既有 active 部分重叠 → 400 + 1007，不自动归档。"""
    today = datetime.now(TZ).date()
    next_monday = _next_monday()
    with _db() as db:
        from app.models.plan import LearningPlan

        db.add(
            LearningPlan(
                user_id=_get_user_id(app_client, user_a),
                goal_id=None,
                title="部分重叠计划",
                version=1,
                status="active",
                source="agent",
                start_date=next_monday - timedelta(days=1),
                end_date=next_monday + timedelta(days=3),
            )
        )
        db.commit()

    _install_plan_llm(monkeypatch, lambda _m: _candidates_json(_five_candidates()))
    resp = app_client.post("/api/v1/plans/generate", headers=user_a["headers"], json={})
    assert resp.status_code == 400, resp.text
    body = resp.json()
    assert body["code"] == 1007

    with _db() as db:
        from sqlalchemy import select

        from app.models.plan import LearningPlan

        actives = db.execute(
            select(LearningPlan).where(
                LearningPlan.user_id == _get_user_id(app_client, user_a),
                LearningPlan.status == "active",
            )
        ).scalars().all()
        assert len(actives) == 1  # 既有 active 未被动


def test_g10_transaction_atomicity(
    app_client: Any, user_a: dict[str, Any], demo_env: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    """D14：落库中途异常 → 库中零新增（计划/条目/任务）。

    直调 service 层（TestClient 默认 re-raise 服务端异常，不适合注入
    场景）；异常由 pytest.raises 捕获，get_db teardown 语义由
    SessionLocal 上下文关闭回滚承接。
    """
    import asyncio

    from app.services.plan import generate_plan

    _install_plan_llm(
        monkeypatch, lambda _m: _candidates_json(_five_candidates(demo_env["overdue_id"]))
    )
    uid = _get_user_id(app_client, user_a)

    def boom_factory(**_kwargs: Any) -> Any:
        raise RuntimeError("注入的落库失败")

    monkeypatch.setattr("app.services.plan.LearningPlanItem", boom_factory)
    with _db() as db:
        with pytest.raises(RuntimeError):
            asyncio.run(generate_plan(db, uid))

    monkeypatch.undo()
    with _db() as db:
        from sqlalchemy import select

        from app.models.plan import LearningPlan, LearningPlanItem
        from app.models.task import Task

        plans = db.execute(
            select(LearningPlan).where(LearningPlan.user_id == uid)
        ).scalars().all()
        assert plans == []  # 无半截计划
        agent_tasks = db.execute(
            select(Task).where(Task.user_id == uid, Task.source == "agent")
        ).scalars().all()
        assert agent_tasks == []  # 无半截任务
        items = db.execute(select(LearningPlanItem)).scalars().all()
        assert items == []


def test_g11_generate_current_week_remaining_days(
    app_client: Any, user_a: dict[str, Any], demo_env: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    """本周兜底：周期为本周一~本周日，只排今天及以后；周五已过不注入休息条目。"""
    _install_plan_llm(
        monkeypatch,
        lambda _m: _candidates_json(_five_candidates(demo_env["overdue_id"], count=12)),
    )
    resp = app_client.post(
        "/api/v1/plans/generate",
        headers=user_a["headers"],
        json={"target": "current_week"},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]

    today = datetime.now(TZ).date()
    this_monday = _this_monday()
    this_sunday = this_monday + timedelta(days=6)
    friday = this_monday + timedelta(days=4)

    assert data["plan"]["start_date"] == this_monday.isoformat()
    assert data["plan"]["end_date"] == this_sunday.isoformat()
    assert data["items"]
    assert all(item["plan_date"] >= today.isoformat() for item in data["items"])

    friday_items = [i for i in data["items"] if i["plan_date"] == friday.isoformat()]
    if friday >= today:
        assert len(friday_items) == 1
        assert friday_items[0]["topic"] == "休息 / 复习"
        assert friday_items[0]["start_time"] is None
    else:
        assert friday_items == []

    per_day: dict[str, int] = {}
    for item in data["items"]:
        if item["estimated_minutes"] is not None:
            per_day[item["plan_date"]] = per_day.get(item["plan_date"], 0) + item[
                "estimated_minutes"
            ]
    assert all(v <= 90 for v in per_day.values()), per_day