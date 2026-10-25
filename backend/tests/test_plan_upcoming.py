"""`GET /plans/upcoming` 测试（「已生成但未开始」计划回读）。

覆盖验收：

- 空态返回 200 + data=null（与 /current 同构，非 404）；
- 只返回 start_date > 今天的最近一条 active 计划及条目；
- 本周 active / archived 未来计划不返回；
- 字面量路由不会被 /plans/{plan_id} 吃掉（返回 200 而非 422）。
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from typing import Any

TZ = timezone(timedelta(hours=8))


def _today() -> date:
    return datetime.now(TZ).date()


def _this_monday() -> date:
    return _today() - timedelta(days=_today().weekday())


def _db():
    from app.db.session import SessionLocal

    return SessionLocal()


def _get_user_id(app_client: Any, user: dict[str, Any]) -> int:
    resp = app_client.get("/api/v1/auth/me", headers=user["headers"])
    return resp.json()["data"]["id"]


def _insert_plan(
    uid: int,
    start: date,
    status: str,
    version: int,
    with_item: bool = True,
) -> int:
    """直插一条计划（可选一条条目），返回 plan id。"""
    from app.models.enums import PlanItemStatus, PlanSource, PlanStatus, Priority
    from app.models.plan import LearningPlan, LearningPlanItem

    with _db() as db:
        plan = LearningPlan(
            user_id=uid,
            goal_id=None,
            title=f"测试计划 v{version}",
            version=version,
            status=PlanStatus(status),
            source=PlanSource.AGENT,
            start_date=start,
            end_date=start + timedelta(days=6),
        )
        db.add(plan)
        db.flush()
        if with_item:
            db.add(
                LearningPlanItem(
                    plan_id=plan.id,
                    plan_date=start,
                    start_time=time(19, 0),
                    end_time=time(19, 45),
                    topic=f"计划 v{version} 的条目",
                    task_id=None,
                    estimated_minutes=45,
                    priority=Priority.MEDIUM,
                    status=PlanItemStatus.PLANNED,
                )
            )
        db.commit()
        return plan.id


def test_upcoming_empty_returns_null(
    app_client: Any, user_a: dict[str, Any]
) -> None:
    """无未来计划 → 200 + data=null（字面量路由不被 /{plan_id} 吃掉）。"""
    resp = app_client.get("/api/v1/plans/upcoming", headers=user_a["headers"])
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["data"] is None


def test_upcoming_returns_nearest_future_active_plan_with_items(
    app_client: Any, user_a: dict[str, Any]
) -> None:
    """本周 active + 下周 active + 更远未来 active → 只返回最近的下周计划。"""
    uid = _get_user_id(app_client, user_a)
    this_monday = _this_monday()
    next_monday = this_monday + timedelta(days=7)
    far_monday = this_monday + timedelta(days=21)

    current_id = _insert_plan(uid, this_monday, "active", version=1)
    next_id = _insert_plan(uid, next_monday, "active", version=2)
    _insert_plan(uid, far_monday, "active", version=3)

    resp = app_client.get("/api/v1/plans/upcoming", headers=user_a["headers"])
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data is not None
    assert data["plan"]["id"] == next_id
    assert data["plan"]["start_date"] == next_monday.isoformat()
    assert data["plan"]["end_date"] == (next_monday + timedelta(days=6)).isoformat()
    assert len(data["items"]) == 1
    assert data["items"][0]["topic"] == "计划 v2 的条目"

    # /current 语义不受影响
    current = app_client.get(
        "/api/v1/plans/current", headers=user_a["headers"]
    )
    assert current.status_code == 200, current.text
    assert current.json()["data"]["plan"]["id"] == current_id


def test_upcoming_ignores_archived_future_plan(
    app_client: Any, user_a: dict[str, Any]
) -> None:
    """未来计划是 archived → 不返回（只有 active 才算「可回读」）。"""
    uid = _get_user_id(app_client, user_a)
    next_monday = _this_monday() + timedelta(days=7)
    _insert_plan(uid, next_monday, "archived", version=1)

    resp = app_client.get("/api/v1/plans/upcoming", headers=user_a["headers"])
    assert resp.status_code == 200, resp.text
    assert resp.json()["data"] is None
