"""计划查询与 diff 测试（tasks.md 组 9.1：Q1–Q4）。

覆盖验收：D12（查询侧——current 空态 200+null、diff 无基线空结构、
reports 倒序在 R 组）与 D11（部分——鉴权 401/1003）；Q3 为 P3 只读
端点行为回归。
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from typing import Any

import pytest

TZ = timezone(timedelta(hours=8))


def _this_monday() -> date:
    today = datetime.now(TZ).date()
    return today - timedelta(days=today.weekday())


def _db():
    from app.db.session import SessionLocal

    return SessionLocal()


def _get_user_id(app_client: Any, user: dict[str, Any]) -> int:
    resp = app_client.get("/api/v1/auth/me", headers=user["headers"])
    return resp.json()["data"]["id"]


def _insert_current_week_plan(uid: int, with_items: bool = True) -> int:
    """直插覆盖今天的 active 计划（Q1 current 语义）。"""
    from app.models.enums import PlanItemStatus, PlanSource, PlanStatus, Priority
    from app.models.plan import LearningPlan, LearningPlanItem

    monday = _this_monday()
    with _db() as db:
        plan = LearningPlan(
            user_id=uid, goal_id=None, title="本周计划", version=1,
            status=PlanStatus.ACTIVE, source=PlanSource.AGENT,
            start_date=monday, end_date=monday + timedelta(days=6),
        )
        db.add(plan)
        db.flush()
        if with_items:
            rest = LearningPlanItem(
                plan_id=plan.id, plan_date=monday + timedelta(days=4),
                start_time=None, end_time=None, topic="休息 / 复习",
                task_id=None, estimated_minutes=None, priority=None,
            )
            db.add(rest)
            db.add(
                LearningPlanItem(
                    plan_id=plan.id, plan_date=monday + timedelta(days=2),
                    start_time=time(19, 0), end_time=time(20, 0),
                    topic="周三晚上学习", task_id=None,
                    estimated_minutes=60, priority=Priority.MEDIUM,
                    status=PlanItemStatus.PLANNED,
                )
            )
            db.add(
                LearningPlanItem(
                    plan_id=plan.id, plan_date=monday + timedelta(days=1),
                    start_time=time(9, 0), end_time=time(10, 0),
                    topic="周二上午学习", task_id=None,
                    estimated_minutes=60, priority=Priority.MEDIUM,
                    status=PlanItemStatus.PLANNED,
                )
            )
        db.commit()
        return plan.id


def test_q1_current_semantics_and_ordering(
    app_client: Any, user_a: dict[str, Any]
) -> None:
    """Q1：current 返回计划头 + items（plan_date 升序、同日 start_time 升序、None 最前）。"""
    uid = _get_user_id(app_client, user_a)
    monday = _this_monday()
    _insert_current_week_plan(uid)

    resp = app_client.get("/api/v1/plans/current", headers=user_a["headers"])
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data is not None
    assert data["plan"]["status"] == "active"
    assert data["plan"]["start_date"] == monday.isoformat()

    items = data["items"]
    dates = [i["plan_date"] for i in items]
    assert dates == sorted(dates)
    # 周二(09:00) → 周三(19:00) → 周五休息(None 最前于周五当日)
    friday_idx = dates.index((monday + timedelta(days=4)).isoformat())
    assert items[friday_idx]["start_time"] is None
    assert items[friday_idx]["topic"] == "休息 / 复习"
    assert items[0]["topic"] == "周二上午学习"


def test_q1b_current_empty_returns_null(app_client: Any, user_a: dict[str, Any]) -> None:
    """Q1：无计划 → 200 且 data=null（非 404，裁决 #8）。"""
    resp = app_client.get("/api/v1/plans/current", headers=user_a["headers"])
    assert resp.status_code == 200
    assert resp.json()["data"] is None


def test_q2_diff_no_baseline(
    app_client: Any, user_a: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Q2：generate 产物（parent=null）diff → 200 + 空结构。"""
    from app.core.response import BizException

    async def dead(_messages: list[dict[str, Any]]) -> str:
        raise BizException(3000, "AI 服务不可用", 502)

    monkeypatch.setattr("app.services.plan.llm.chat", dead)
    resp = app_client.post("/api/v1/plans/generate", headers=user_a["headers"], json={})
    assert resp.status_code == 200, resp.text
    plan_id = resp.json()["data"]["plan"]["id"]

    resp2 = app_client.get(f"/api/v1/plans/{plan_id}/diff", headers=user_a["headers"])
    assert resp2.status_code == 200, resp2.text
    assert resp2.json()["data"] == {
        "base_plan_id": None, "moved": [], "added": [], "removed": []
    }


def test_q3_p3_plans_list_and_detail_regression(
    app_client: Any, user_a: dict[str, Any], user_b: dict[str, Any]
) -> None:
    """Q3：P3 行为回归——列表分页（id 升序、双账号隔离）与详情越权 404/1005。"""
    uid = _get_user_id(app_client, user_a)
    first = _insert_current_week_plan(uid)
    second = _insert_current_week_plan(uid)  # 同 user 多版本

    resp = app_client.get("/api/v1/plans?page=1&page_size=10", headers=user_a["headers"])
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data["total"] == 2
    ids = [item["id"] for item in data["items"]]
    assert ids == sorted(ids)

    # 双账号隔离：user_b 列表看不到 user_a 的计划
    resp_b = app_client.get("/api/v1/plans", headers=user_b["headers"])
    assert resp_b.json()["data"]["total"] == 0

    # 详情正常 + 越权 404/1005
    resp_detail = app_client.get(f"/api/v1/plans/{first}", headers=user_a["headers"])
    assert resp_detail.status_code == 200
    assert resp_detail.json()["data"]["id"] == first
    resp_cross = app_client.get(f"/api/v1/plans/{second}", headers=user_b["headers"])
    assert resp_cross.status_code == 404
    assert resp_cross.json()["code"] == 1005


def test_q4_auth_required(app_client: Any) -> None:
    """Q4：未携带 token → 401 + code=1003（current / diff / generate / adjust）。"""
    resp = app_client.get("/api/v1/plans/current")
    assert resp.status_code == 401 and resp.json()["code"] == 1003

    resp = app_client.get("/api/v1/plans/1/diff")
    assert resp.status_code == 401 and resp.json()["code"] == 1003

    resp = app_client.post("/api/v1/plans/generate", json={})
    assert resp.status_code == 401 and resp.json()["code"] == 1003

    resp = app_client.post("/api/v1/plans/1/adjust", json={})
    assert resp.status_code == 401 and resp.json()["code"] == 1003