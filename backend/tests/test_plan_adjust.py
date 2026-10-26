"""计划调整测试（adjuster 引擎单测 + A1–A12 服务级）。

覆盖验收：D3（版本链）/ D4（diff 幂等）/ D14（事务原子性）/
AI 决策契约（失败报错、条目不合法拒绝）；OP1 调整路径同步义务（A8）。

- 引擎单测：reason 模板等纯函数，不依赖 LLM 与 DB；
- 服务级（A 组）：monkeypatch ``llm.chat`` 注入 AI 决策 JSON——
  判断「要不要调、调哪些」属于 LLM 职责，排程仍由确定性引擎完成；
  日期断言动态计算（北京口径）。
"""

from __future__ import annotations

import json
from datetime import date, datetime, time, timedelta, timezone
from typing import Any

import pytest

from app.analytics.adjuster import ReasonMaterial, render_adjust_reason

TZ = timezone(timedelta(hours=8))


def _this_monday() -> date:
    """北京今天 → 本周一。"""
    today = datetime.now(TZ).date()
    return today - timedelta(days=today.weekday())


def _next_monday() -> date:
    today = datetime.now(TZ).date()
    return today + timedelta(days=7 - today.weekday())


# ---------------------------------------------------------------------------
# adjuster 引擎单测（reason 模板等纯函数）
# ---------------------------------------------------------------------------


def test_adjuster_reason_single_move() -> None:
    """单任务移动：含任务名 + 从→到日期时段 + ≥20 字符（用户指令③红线）。"""
    material = ReasonMaterial(
        moved_topics=["Transformer 注意力机制"],
        moved_count=1,
        cause_desc="未完成且截止临近",
        first_from_desc="周三（10-28）晚上",
        first_to_desc="周六（10-31）下午",
    )
    reason = render_adjust_reason(material)
    assert reason == (
        "检测到你本周的Transformer 注意力机制学习任务未完成且截止临近，"
        "已从周三（10-28）晚上调整到周六（10-31）下午。"
    )
    assert "Transformer 注意力机制" in reason
    assert len(reason) >= 20
    assert "顺延" not in reason  # 无顺延不出现顺延话术
    assert "移出计划" not in reason


def test_adjuster_reason_multi_move() -> None:
    """多任务移动：数量表述 + 首 from→to + 等N处。"""
    material = ReasonMaterial(
        moved_topics=["任务A", "任务B"],
        moved_count=2,
        cause_desc="未完成且近期学习时长不足",
        first_from_desc="周三（10-28）晚上",
        first_to_desc="周六（10-31）下午",
    )
    reason = render_adjust_reason(material)
    assert "2 个学习任务" in reason and "等 2 处" in reason
    assert len(reason) >= 20


def test_adjuster_reason_postponed_and_removed() -> None:
    """有顺延：顺延话术（原定日 + 个数 + 目标日）；有 removed：移出话术。"""
    material = ReasonMaterial(
        moved_topics=["Transformer 专项"],
        moved_count=1,
        cause_desc="未完成且截止临近",
        first_from_desc="周三（10-28）晚上",
        first_to_desc="周六（10-31）上午",
        postponed_count=2,
        postponed_day_desc="周六（10-31）",
        postponed_to_desc="周日（11-01）",
    )
    reason = render_adjust_reason(material)
    assert reason.endswith(
        "并顺延了原定周六（10-31）的2个低优先级任务到周日（11-01）。"
    )
    material.removed_desc = "线性代数特征值专题 等 1 个"
    reason2 = render_adjust_reason(material)
    assert "因本周容量不足" in reason2 and "可在任务页单独安排" in reason2


def test_adjuster_reason_only_removed() -> None:
    """无可落位条目（只有移出）时不渲染残缺的「已从调整到」话术。"""
    material = ReasonMaterial(
        moved_topics=[],
        moved_count=0,
        cause_desc="未完成",
        removed_desc="线性代数特征值专题 等 2 个",
    )
    reason = render_adjust_reason(material)
    assert "移出计划" in reason
    assert "已从" not in reason
    assert "学习学习" not in reason


# ---------------------------------------------------------------------------
# 测试辅助（服务级数据构造：直插本周计划 / 任务 / 学习记录）
# ---------------------------------------------------------------------------


def _get_user_id(app_client: Any, user: dict[str, Any]) -> int:
    resp = app_client.get("/api/v1/auth/me", headers=user["headers"])
    return resp.json()["data"]["id"]


def _db():
    from app.db.session import SessionLocal

    return SessionLocal()


def _create_task(
    app_client: Any, user: dict[str, Any], title: str, deadline: datetime | None, priority: str
) -> int:
    payload: dict[str, Any] = {"title": title, "priority": priority}
    if deadline is not None:
        payload["deadline"] = deadline.isoformat()
    resp = app_client.post("/api/v1/tasks", headers=user["headers"], json=payload)
    assert resp.status_code == 200, resp.text
    return resp.json()["data"]["id"]


def _insert_records(uid: int, total_minutes: int) -> None:
    """近 7 天学习记录（控制「时长不足」全局条件的开关）。"""
    from app.models.record import LearningRecord

    today = datetime.now(TZ).date()
    per_day, rest = divmod(total_minutes, 6)
    with _db() as db:
        for i in range(6):
            db.add(
                LearningRecord(
                    user_id=uid,
                    content=f"学习记录 {i}",
                    duration_minutes=per_day + (rest if i == 0 else 0),
                    knowledge_points=["机器学习"],
                    study_date=today - timedelta(days=i),
                )
            )
        db.commit()


def _insert_week_plan(
    uid: int,
    items_spec: list[dict[str, Any]],
    capacity_day_offset: tuple[date, date] | None = None,
    include_rest: bool = True,
) -> int:
    """直插本周 active 计划（精确控制条目布局；返回 plan_id）。

    items_spec 每条：{date, start, end, topic, task_id, estimated, priority, status}

    include_rest=False 时不插入周五休息条目——用于「全部 done 无可调整项」
    类断言（A4）：休息条目 status=planned，周五过后会命中「未完成
    （plan_date < 今天）∧ 时长不足」进入移动集，使结果随运行日期漂移。
    """
    from app.models.enums import PlanItemStatus, PlanSource, PlanStatus, Priority
    from app.models.plan import LearningPlan, LearningPlanItem

    monday = _this_monday()
    start, end = capacity_day_offset or (monday, monday + timedelta(days=6))
    with _db() as db:
        plan = LearningPlan(
            user_id=uid, goal_id=None, title="本周计划", version=1,
            status=PlanStatus.ACTIVE, source=PlanSource.AGENT,
            start_date=start, end_date=end,
        )
        db.add(plan)
        db.flush()
        for spec in items_spec:
            db.add(
                LearningPlanItem(
                    plan_id=plan.id,
                    plan_date=spec["date"],
                    start_time=spec.get("start"),
                    end_time=spec.get("end"),
                    topic=spec["topic"],
                    task_id=spec.get("task_id"),
                    estimated_minutes=spec.get("estimated"),
                    priority=Priority(spec["priority"]) if spec.get("priority") else None,
                    status=PlanItemStatus(spec.get("status", "planned")),
                )
            )
        # 周五休息条目（include_rest=False 时跳过——见 docstring）
        if include_rest:
            db.add(
                LearningPlanItem(
                    plan_id=plan.id, plan_date=monday + timedelta(days=4),
                    start_time=None, end_time=None, topic="休息 / 复习",
                    task_id=None, estimated_minutes=None, priority=None,
                )
            )
        db.commit()
        return plan.id


def _item_specs_for_tasks(
    task_specs: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """任务规格（date/start/end/task_id/estimated/priority）→ 条目规格。"""
    return [
        {
            "date": t["date"], "start": t["start"], "end": t["end"],
            "topic": t["topic"], "task_id": t["task_id"],
            "estimated": t["estimated"], "priority": t["priority"],
        }
        for t in task_specs
    ]


def _set_profile(app_client: Any, user: dict[str, Any], minutes: int) -> None:
    resp = app_client.put(
        "/api/v1/profile", headers=user["headers"], json={"daily_study_minutes": minutes}
    )
    assert resp.status_code == 200, resp.text


def _snapshot_items(plan_id: int) -> list[dict[str, Any]]:
    """读取某计划全部条目的逐字段快照（D3 断言用）。"""
    from sqlalchemy import select

    from app.models.plan import LearningPlanItem

    with _db() as db:
        items = db.execute(
            select(LearningPlanItem).where(LearningPlanItem.plan_id == plan_id)
        ).scalars().all()
        return [
            {
                "plan_date": i.plan_date.isoformat(),
                "start_time": i.start_time.isoformat() if i.start_time else None,
                "end_time": i.end_time.isoformat() if i.end_time else None,
                "topic": i.topic,
                "task_id": i.task_id,
                "estimated_minutes": i.estimated_minutes,
                "priority": i.priority.value if i.priority else None,
                "status": i.status.value if i.status else None,
            }
            for i in sorted(items, key=lambda x: (x.plan_date, x.start_time or time(0, 0)))
        ]


# ---------------------------------------------------------------------------
# A 组：服务级用例（调整路径零 LLM）
# ---------------------------------------------------------------------------


def _mock_adjust_llm(
    monkeypatch: pytest.MonkeyPatch, decision: dict[str, Any]
) -> None:
    """注入 AI 调整决策 JSON（monkeypatch 共享的 llm.chat）。"""

    async def fake(_messages: list[Any]) -> str:
        return json.dumps(decision, ensure_ascii=False)

    monkeypatch.setattr("app.services.plan.llm.chat", fake)


def _llm_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    """AI 不可用（服务类失败）。"""
    from app.core.response import BizException

    async def dead(_messages: list[Any]) -> str:
        raise BizException(3000, "AI 服务不可用", 502)

    monkeypatch.setattr("app.services.plan.llm.chat", dead)


def _item_id(
    plan_id: int,
    *,
    task_id: int | None = None,
    topic: str | None = None,
) -> int:
    """按 task_id / topic 定位计划条目 id（AI 决策只引用 item_id）。"""
    from sqlalchemy import select

    from app.models.plan import LearningPlanItem

    with _db() as db:
        stmt = select(LearningPlanItem.id).where(
            LearningPlanItem.plan_id == plan_id
        )
        if task_id is not None:
            stmt = stmt.where(LearningPlanItem.task_id == task_id)
        if topic is not None:
            stmt = stmt.where(LearningPlanItem.topic == topic)
        return int(db.execute(stmt).scalars().first())


def test_a1_version_chain_and_reason(
    app_client: Any, user_a: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    """D3：AI 要求移动 → 版本链 + AI reason 原样落库。"""
    _set_profile(app_client, user_a, 90)
    uid = _get_user_id(app_client, user_a)
    now = datetime.now(TZ)
    monday = _this_monday()
    overdue_id = _create_task(app_client, user_a, "Transformer 作业", now + timedelta(hours=24), "high")
    _insert_records(uid, 540)  # 时长充足 → 只有截止临近触发

    plan_id = _insert_week_plan(
        uid,
        _item_specs_for_tasks(
            [
                {"date": monday, "start": time(19, 0), "end": time(20, 0), "topic": "Transformer 作业",
                 "task_id": overdue_id, "estimated": 60, "priority": "high"},
                {"date": monday + timedelta(days=1), "start": time(19, 0), "end": time(20, 0), "topic": "常规复习",
                 "task_id": None, "estimated": 60, "priority": "medium"},
            ]
        ),
    )
    old_snapshot = _snapshot_items(plan_id)
    ai_reason = "Transformer 作业 未完成且截止临近，已从周一晚上调整到本周后续空闲时段。"
    _mock_adjust_llm(
        monkeypatch,
        {
            "needs_adjustment": True,
            "reason": ai_reason,
            "items": [
                {"item_id": _item_id(plan_id, task_id=overdue_id), "action": "move"}
            ],
        },
    )

    resp = app_client.post(f"/api/v1/plans/{plan_id}/adjust", headers=user_a["headers"], json={})
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data["adjusted"] is True

    new_plan = data["plan"]
    assert new_plan["version"] == 2
    assert new_plan["parent_plan_id"] == plan_id
    assert new_plan["start_date"] == (monday).isoformat()
    assert new_plan["end_date"] == (monday + timedelta(days=6)).isoformat()

    reason = data["adjust_reason"]
    assert reason == ai_reason  # AI 理由原样落库
    assert new_plan["adjust_reason"] == reason

    with _db() as db:
        from app.models.plan import LearningPlan

        old = db.get(LearningPlan, plan_id)
        assert old.status == "archived"
    assert _snapshot_items(plan_id) == old_snapshot  # 旧版条目逐字段不变


def test_a2_diff_consistency_with_endpoint(
    app_client: Any, user_a: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    """D4：调整随返 diff == diff 端点重算（幂等一致性——同函数构造性结果）。"""
    _set_profile(app_client, user_a, 90)
    uid = _get_user_id(app_client, user_a)
    # 固定在本周周四中午：本周仍有未来时段，避免周日运行时本周已无
    # 未来日期导致 moved 变 removed 的日期敏感。
    fixed_now = datetime.combine(
        _this_monday() + timedelta(days=3), time(12, 0)
    ).replace(tzinfo=TZ)
    monkeypatch.setattr("app.services.plan._beijing_now", lambda: fixed_now)
    now = fixed_now
    monday = _this_monday()
    task_id = _create_task(app_client, user_a, "临期测验复习", now + timedelta(hours=20), "high")
    _insert_records(uid, 540)
    plan_id = _insert_week_plan(
        uid,
        _item_specs_for_tasks(
            [{"date": monday, "start": time(19, 0), "end": time(20, 0), "topic": "临期测验复习",
              "task_id": task_id, "estimated": 60, "priority": "high"}]
        ),
    )
    _mock_adjust_llm(
        monkeypatch,
        {
            "needs_adjustment": True,
            "reason": "临期测验复习任务未完成且截止临近。",
            "items": [
                {"item_id": _item_id(plan_id, task_id=task_id), "action": "move"}
            ],
        },
    )
    resp = app_client.post(f"/api/v1/plans/{plan_id}/adjust", headers=user_a["headers"], json={})
    data = resp.json()["data"]
    assert data["adjusted"] is True
    new_id = data["plan"]["id"]

    # moved 三要素齐全且真实对应两版条目
    moved = data["diff"]["moved"]
    assert moved, data["diff"]
    entry = moved[0]
    assert entry["topic"] == "临期测验复习"
    assert entry["from_date"] == monday.isoformat()
    new_dates = {i["plan_date"] for i in _snapshot_items(new_id)}
    assert entry["to_date"] in new_dates
    assert entry["reason"]

    # 幂等重算：调整随返 == 端点重算
    resp2 = app_client.get(f"/api/v1/plans/{new_id}/diff", headers=user_a["headers"])
    assert resp2.status_code == 200, resp2.text
    assert resp2.json()["data"] == data["diff"]


def test_a3_llm_unavailable_returns_error(
    app_client: Any, user_a: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    """AI 不可用 → 502/3000，计划保持 active，不产生新版本（不回退规则）。"""
    _set_profile(app_client, user_a, 90)
    uid = _get_user_id(app_client, user_a)
    now = datetime.now(TZ)
    monday = _this_monday()
    task_id = _create_task(app_client, user_a, "截止任务", now - timedelta(hours=2), "high")
    plan_id = _insert_week_plan(
        uid,
        _item_specs_for_tasks(
            [{"date": monday, "start": time(19, 0), "end": time(20, 0), "topic": "截止任务",
              "task_id": task_id, "estimated": 60, "priority": "high"}]
        ),
    )
    _llm_unavailable(monkeypatch)
    resp = app_client.post(f"/api/v1/plans/{plan_id}/adjust", headers=user_a["headers"], json={})
    assert resp.status_code == 502
    assert resp.json()["code"] == 3000

    with _db() as db:
        from sqlalchemy import func, select

        from app.models.plan import LearningPlan

        count = db.scalar(
            select(func.count()).select_from(
                select(LearningPlan).where(LearningPlan.user_id == uid).subquery()
            )
        )
        assert count == 1
        assert db.get(LearningPlan, plan_id).status == "active"


def test_a3b_invalid_llm_output_returns_error(
    app_client: Any, user_a: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    """AI 输出不是合法 JSON / 引用不存在的条目 → 502/3000，不调整。"""
    _set_profile(app_client, user_a, 90)
    uid = _get_user_id(app_client, user_a)
    monday = _this_monday()
    plan_id = _insert_week_plan(
        uid,
        [{"date": monday, "start": time(19, 0), "end": time(20, 0), "topic": "任意条目",
          "task_id": None, "estimated": 60, "priority": "medium"}],
    )

    async def bad_json(_messages: list[Any]) -> str:
        return "这不是 JSON"

    monkeypatch.setattr("app.services.plan.llm.chat", bad_json)
    resp = app_client.post(f"/api/v1/plans/{plan_id}/adjust", headers=user_a["headers"], json={})
    assert resp.status_code == 502 and resp.json()["code"] == 3000

    _mock_adjust_llm(
        monkeypatch,
        {
            "needs_adjustment": True,
            "reason": "该调整",
            "items": [{"item_id": 999999, "action": "move"}],
        },
    )
    resp2 = app_client.post(f"/api/v1/plans/{plan_id}/adjust", headers=user_a["headers"], json={})
    assert resp2.status_code == 502 and resp2.json()["code"] == 3000


def test_a3c_rejects_done_item(
    app_client: Any, user_a: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    """AI 选中 done 条目 → 视为输出不合法，不调整。"""
    uid = _get_user_id(app_client, user_a)
    monday = _this_monday()
    plan_id = _insert_week_plan(
        uid,
        [{"date": monday, "start": time(19, 0), "end": time(20, 0), "topic": "已完成项",
          "task_id": None, "estimated": 60, "priority": "medium", "status": "done"}],
        include_rest=False,
    )
    _mock_adjust_llm(
        monkeypatch,
        {
            "needs_adjustment": True,
            "reason": "尝试调整已完成项",
            "items": [
                {"item_id": _item_id(plan_id, topic="已完成项"), "action": "move"}
            ],
        },
    )
    resp = app_client.post(f"/api/v1/plans/{plan_id}/adjust", headers=user_a["headers"], json={})
    assert resp.status_code == 502 and resp.json()["code"] == 3000


def test_a4_nothing_to_adjust(
    app_client: Any, user_a: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    """A4：AI 判断无需调整 → adjusted=false、计划数不变、无新版本。"""
    uid = _get_user_id(app_client, user_a)
    monday = _this_monday()
    plan_id = _insert_week_plan(
        uid,
        [
            {"date": monday, "start": time(19, 0), "end": time(20, 0), "topic": "已完成项",
             "task_id": None, "estimated": 60, "priority": "medium", "status": "done"}
        ],
        include_rest=False,
    )
    ai_reason = "本周任务安排合理，无需调整。"
    _mock_adjust_llm(
        monkeypatch,
        {"needs_adjustment": False, "reason": ai_reason, "items": []},
    )
    resp = app_client.post(f"/api/v1/plans/{plan_id}/adjust", headers=user_a["headers"], json={})
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data["adjusted"] is False
    assert data["adjust_reason"] == ai_reason
    assert data["diff"] == {"base_plan_id": None, "moved": [], "added": [], "removed": []}

    with _db() as db:
        from sqlalchemy import func, select

        from app.models.plan import LearningPlan

        count = db.scalar(
            select(func.count()).select_from(
                select(LearningPlan).where(LearningPlan.user_id == uid).subquery()
            )
        )
        assert count == 1


def test_a5_done_preserved(
    app_client: Any, user_a: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    """裁决 #13：done 条目原样迁移（位置不变、状态保持、不进 diff）。"""
    _set_profile(app_client, user_a, 90)
    uid = _get_user_id(app_client, user_a)
    now = datetime.now(TZ)
    monday = _this_monday()
    done_task = _create_task(app_client, user_a, "已完成学习", now + timedelta(days=5), "low")
    urgent_task = _create_task(app_client, user_a, "紧急补课", now + timedelta(hours=10), "high")
    _insert_records(uid, 540)
    plan_id = _insert_week_plan(
        uid,
        _item_specs_for_tasks(
            [
                {"date": monday, "start": time(19, 0), "end": time(20, 0), "topic": "已完成学习",
                 "task_id": done_task, "estimated": 60, "priority": "low"},
                {"date": monday + timedelta(days=2), "start": time(19, 0), "end": time(20, 0),
                 "topic": "紧急补课", "task_id": urgent_task, "estimated": 60, "priority": "high"},
            ]
        ),
    )
    with _db() as db:
        from app.models.plan import LearningPlanItem
        from sqlalchemy import select

        item = db.execute(
            select(LearningPlanItem).where(
                LearningPlanItem.plan_id == plan_id, LearningPlanItem.task_id == done_task
            )
        ).scalar_one()
        item.status = "done"
        db.commit()

    _mock_adjust_llm(
        monkeypatch,
        {
            "needs_adjustment": True,
            "reason": "紧急补课临近截止，需要调整。",
            "items": [
                {"item_id": _item_id(plan_id, task_id=urgent_task), "action": "move"}
            ],
        },
    )
    resp = app_client.post(f"/api/v1/plans/{plan_id}/adjust", headers=user_a["headers"], json={})
    data = resp.json()["data"]
    assert data["adjusted"] is True
    new_id = data["plan"]["id"]
    done_items = [i for i in _snapshot_items(new_id) if i["task_id"] == done_task]
    assert len(done_items) == 1 and done_items[0]["status"] == "done"
    assert done_items[0]["plan_date"] == monday.isoformat()  # 位置不变
    assert not any(
        m["task_id"] == done_task for m in data["diff"]["moved"]
    )


def test_a6_postpone_scenario(
    app_client: Any, user_a: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    """A6：周六容量不足 → 顺延周六 low 条目到周日（moved diff 含牺牲条目）。"""
    _set_profile(app_client, user_a, 120)
    uid = _get_user_id(app_client, user_a)
    # 与 A2 同因：固定本周周四中午，保证周六/周日仍在未来。
    fixed_now = datetime.combine(
        _this_monday() + timedelta(days=3), time(12, 0)
    ).replace(tzinfo=TZ)
    monkeypatch.setattr("app.services.plan._beijing_now", lambda: fixed_now)
    now = fixed_now
    monday = _this_monday()
    saturday, sunday = monday + timedelta(days=5), monday + timedelta(days=6)
    urgent = _create_task(app_client, user_a, "紧急专项", now + timedelta(hours=12), "high")
    low_sat = _create_task(app_client, user_a, "周六低优练习", None, "low")
    _insert_records(uid, 700)  # 700 ≥ 120×7×0.6=504 → 时长充足

    plan_id = _insert_week_plan(
        uid,
        _item_specs_for_tasks(
            [
                {"date": monday, "start": time(19, 0), "end": time(20, 0), "topic": "紧急专项",
                 "task_id": urgent, "estimated": 60, "priority": "high"},
                {"date": saturday, "start": time(14, 0), "end": time(15, 0), "topic": "周六低优练习",
                 "task_id": low_sat, "estimated": 60, "priority": "low"},
                {"date": saturday, "start": time(15, 0), "end": time(16, 0), "topic": "周六占位B",
                 "task_id": None, "estimated": 60, "priority": "medium"},
                {"date": saturday, "start": time(9, 0), "end": time(10, 0), "topic": "周六占位C",
                 "task_id": None, "estimated": 60, "priority": "medium"},
            ]
        ),
    )
    _mock_adjust_llm(
        monkeypatch,
        {
            "needs_adjustment": True,
            "reason": "紧急专项临近截止，调整到周末空闲时段。",
            "items": [{"item_id": _item_id(plan_id, task_id=urgent), "action": "move"}],
        },
    )
    resp = app_client.post(f"/api/v1/plans/{plan_id}/adjust", headers=user_a["headers"], json={})
    data = resp.json()["data"]
    assert data["adjusted"] is True

    moved = data["diff"]["moved"]
    # 紧急条目移到周末
    urgent_move = next(m for m in moved if m["task_id"] == urgent)
    assert urgent_move["to_date"] in (saturday.isoformat(), sunday.isoformat())
    # 容量不足触发牺牲时，牺牲条目也应被顺延（出现在 moved 中）
    for m in moved:
        if m["task_id"] not in (urgent, None):
            assert m["to_date"] > m["from_date"]


def test_a7_removed_and_a8_task_sync(
    app_client: Any, user_a: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    """A7+A8：AI 指定移出 → 任务保留且 scheduled_date 置空；moved 任务同步。"""
    _set_profile(app_client, user_a, 120)
    uid = _get_user_id(app_client, user_a)
    now = datetime.now(TZ)
    monday = _this_monday()
    saturday, sunday = monday + timedelta(days=5), monday + timedelta(days=6)
    urgent = _create_task(app_client, user_a, "满周紧急任务", now + timedelta(hours=12), "high")
    victim = _create_task(app_client, user_a, "被移出的低优任务", None, "low")
    _insert_records(uid, 700)

    specs = [
        {"date": monday, "start": time(19, 0), "end": time(20, 0), "topic": "满周紧急任务",
         "task_id": urgent, "estimated": 60, "priority": "high"},
        {"date": saturday, "start": time(14, 0), "end": time(15, 0), "topic": "被移出的低优任务",
         "task_id": victim, "estimated": 60, "priority": "low"},
        {"date": saturday, "start": time(15, 0), "end": time(16, 0), "topic": "周六占位B",
         "task_id": None, "estimated": 60, "priority": "medium"},
        {"date": saturday, "start": time(9, 0), "end": time(10, 0), "topic": "周六占位C",
         "task_id": None, "estimated": 60, "priority": "medium"},
        {"date": sunday, "start": time(14, 0), "end": time(15, 0), "topic": "周日占位A",
         "task_id": None, "estimated": 60, "priority": "medium"},
        {"date": sunday, "start": time(15, 0), "end": time(16, 0), "topic": "周日占位B",
         "task_id": None, "estimated": 60, "priority": "medium"},
        {"date": sunday, "start": time(9, 0), "end": time(10, 0), "topic": "周日占位C",
         "task_id": None, "estimated": 60, "priority": "medium"},
    ]
    plan_id = _insert_week_plan(uid, _item_specs_for_tasks(specs))
    _mock_adjust_llm(
        monkeypatch,
        {
            "needs_adjustment": True,
            "reason": "满周紧急任务临近截止需调整；被移出的低优任务移出本周计划。",
            "items": [
                {"item_id": _item_id(plan_id, task_id=urgent), "action": "move"},
                {"item_id": _item_id(plan_id, task_id=victim), "action": "drop"},
            ],
        },
    )
    resp = app_client.post(f"/api/v1/plans/{plan_id}/adjust", headers=user_a["headers"], json={})
    data = resp.json()["data"]
    assert data["adjusted"] is True

    removed = data["diff"]["removed"]
    removed_ids = {r["task_id"] for r in removed}
    # AI 明确移出的任务必然进 removed
    assert victim in removed_ids, data["diff"]

    with _db() as db:
        from app.models.task import Task

        # A7：removed 任务保留在 tasks 表
        for r in removed:
            if r["task_id"] is not None:
                task = db.get(Task, r["task_id"])
                assert task is not None
        # A8：被移动任务 scheduled_date == 新 plan_date；removed 任务置空
        for m in data["diff"]["moved"]:
            if m["task_id"] is not None:
                task = db.get(Task, m["task_id"])
                assert task is not None
                assert task.scheduled_date.isoformat() == m["to_date"], (
                    task.scheduled_date, m["to_date"]
                )
        for r in removed:
            if r["task_id"] is not None:
                task = db.get(Task, r["task_id"])
                assert task.scheduled_date is None
    assert "移出本周计划" in data["adjust_reason"]


def test_a9_permission_and_period_invariant(
    app_client: Any,
    user_a: dict[str, Any],
    user_b: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A9：越权 404/1005；archived 调整 1007；调整前后周期逐字段相等。"""
    _set_profile(app_client, user_a, 90)
    uid = _get_user_id(app_client, user_a)
    now = datetime.now(TZ)
    monday = _this_monday()
    task_id = _create_task(app_client, user_a, "周期校验任务", now + timedelta(hours=12), "high")
    _insert_records(uid, 540)
    plan_id = _insert_week_plan(
        uid,
        _item_specs_for_tasks(
            [{"date": monday, "start": time(19, 0), "end": time(20, 0), "topic": "周期校验任务",
              "task_id": task_id, "estimated": 60, "priority": "high"}]
        ),
    )
    with _db() as db:
        from app.models.plan import LearningPlan

        old_plan = db.get(LearningPlan, plan_id)

    # 越权：user_b 访问 user_a 的计划（权限校验先于 AI 调用）
    resp_b = app_client.post(f"/api/v1/plans/{plan_id}/adjust", headers=user_b["headers"], json={})
    assert resp_b.status_code == 404
    assert resp_b.json()["code"] == 1005

    _mock_adjust_llm(
        monkeypatch,
        {
            "needs_adjustment": True,
            "reason": "周期校验任务临近截止。",
            "items": [
                {"item_id": _item_id(plan_id, task_id=task_id), "action": "move"}
            ],
        },
    )

    # 正常调整 → 周期不变
    resp = app_client.post(f"/api/v1/plans/{plan_id}/adjust", headers=user_a["headers"], json={})
    assert resp.status_code == 200
    new_plan = resp.json()["data"]["plan"]

    # archived 再调整 → 1007
    resp2 = app_client.post(f"/api/v1/plans/{plan_id}/adjust", headers=user_a["headers"], json={})
    assert resp2.status_code == 400
    assert resp2.json()["code"] == 1007

    # 不存在的 plan_id → 404/1005
    resp3 = app_client.post("/api/v1/plans/999999/adjust", headers=user_a["headers"], json={})
    assert resp3.status_code == 404 and resp3.json()["code"] == 1005

    # 周期不变（裁决 #10）
    assert new_plan["start_date"] == old_plan.start_date.isoformat()
    assert new_plan["end_date"] == old_plan.end_date.isoformat()


def test_a10_transaction_atomicity(
    app_client: Any, user_a: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    """D14：版本链落库中途异常 → 无半截版本、旧 active 未被动。"""
    import asyncio

    from app.services.plan import adjust_plan

    _set_profile(app_client, user_a, 90)
    uid = _get_user_id(app_client, user_a)
    now = datetime.now(TZ)
    monday = _this_monday()
    task_id = _create_task(app_client, user_a, "原子性任务", now + timedelta(hours=12), "high")
    _insert_records(uid, 540)
    plan_id = _insert_week_plan(
        uid,
        _item_specs_for_tasks(
            [{"date": monday, "start": time(19, 0), "end": time(20, 0), "topic": "原子性任务",
              "task_id": task_id, "estimated": 60, "priority": "high"}]
        ),
    )

    _mock_adjust_llm(
        monkeypatch,
        {
            "needs_adjustment": True,
            "reason": "原子性任务临近截止。",
            "items": [
                {"item_id": _item_id(plan_id, task_id=task_id), "action": "move"}
            ],
        },
    )

    def boom_factory(**_kwargs: Any) -> Any:
        raise RuntimeError("注入的版本链落库失败")

    monkeypatch.setattr("app.services.plan.LearningPlanItem", boom_factory)
    with _db() as db:
        with pytest.raises(RuntimeError):
            asyncio.run(adjust_plan(db, uid, plan_id))

    monkeypatch.undo()
    with _db() as db:
        from sqlalchemy import func, select

        from app.models.plan import LearningPlan

        count = db.scalar(
            select(func.count()).select_from(
                select(LearningPlan).where(LearningPlan.user_id == uid).subquery()
            )
        )
        assert count == 1  # 无半截新版本
        old = db.get(LearningPlan, plan_id)
        assert old.status == "active"  # 旧 active 未被动（归档已回滚）
        assert old.version == 1