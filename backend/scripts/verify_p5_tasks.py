"""P5 任务 CRUD / 状态流转 / 筛选 / 分页 / 看板 / 统计回归验证（任务 8，ASGI 直调）。

运行：cd backend && .venv/Scripts/python scripts/verify_p5_tasks.py

验证方式：``fastapi.testclient.TestClient`` 进程内直调 app 对象
（不起 uvicorn、不发真实网络请求，规避沙箱 IPv4 回环拦截）。

覆盖用例（tasks.md 8.2 / 8.3，对照验收①②③④）：
     1. 创建任务（合法表单）→ code=0、status=todo、source=manual
     2. 创建参数校验：title 空 / 超长、priority / estimated_minutes 越界、
        知识点超 20 / 空串、携带 status（中文提示）、goal / course 引用 404
     3. 筛选组合：overdue+priority（验收①）、overdue=false 含无截止、
        knowledge_point 精确匹配（裁定⑩）、keyword 大小写不敏感、
        全参数同传不 422（P4 422 规避专项）
     4. 分页边界：105 条 → 100 + 5 两页（验收④）、page_size=150 → 422、
        默认 id 降序（决策⑧）
     5. 状态流转合法链：五边全通；completed_at 首次写入后不覆盖（裁定⑤）
     6. 非法流转拒绝：todo→done → 1007 + 中文提示（验收③）、
        done 后回退、同状态、被拒后状态与 completed_at 不变
     7. 搁置回退边：in_progress→todo（裁定㉑）
     8. PUT 编辑：部分更新、携带 status / completed_at / source / user_id
        → 422、越权 404
     9. 看板分列：四列齐全、每任务恰归一列、列内优先级降序、用户隔离
    10. 统计口径：DB 直插构造跨周 / 跨日数据；时区边界
        （北京周一 00:30 = UTC 周日 16:30 计入本周，裁定㉒专项）
    11. 删除与关联保留：删除后 404、learning_record 的 task_id 置空
        （FK SET NULL，裁定⑱）
    12. 未登录访问全部端点 → 401/1003
"""

from __future__ import annotations

import os
import sys
import uuid
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

_SCRIPTS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(_SCRIPTS_DIR.parent))
sys.path.insert(0, str(_SCRIPTS_DIR))

# 沙箱 data/ 目录间歇性写锁（P2 起已知问题）：验证脚本改用 backend 下的
# 临时数据库（环境变量优先级高于 .env），不污染正式 data/smartlearn.db。
_TMP_DB_DIR = _SCRIPTS_DIR.parent / "tmp_verify"
_TMP_DB_DIR.mkdir(exist_ok=True)
_TMP_DB = _TMP_DB_DIR / "p5_tasks.db"
if _TMP_DB.exists():
    _TMP_DB.unlink()
os.environ["DATABASE_URL"] = f"sqlite:///{_TMP_DB.as_posix()}"

import _sandbox_patch  # noqa: F401,E402  （IPv6 socketpair 补丁，须先于 TestClient）

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import select  # noqa: E402

from app.db.session import SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402
from app.models.base import Base, utc_now  # noqa: E402
from app.models.course import Course  # noqa: E402
from app.models.enums import Priority, TaskStatus  # noqa: E402
from app.models.record import LearningRecord  # noqa: E402
from app.models.task import Task  # noqa: E402
from app.models.user import User  # noqa: E402
from app.services.task import (  # noqa: E402
    _today_bounds_utc,
    _week_bounds_utc,
)

# 建表（临时库，无种子数据；用例自含全部前置数据）。
Base.metadata.create_all(engine)

client = TestClient(app)

PASSED: list[str] = []
FAILED: list[str] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    """记录单条断言结果。"""
    if cond:
        PASSED.append(name)
        print(f"  [PASS] {name}")
    else:
        FAILED.append(name)
        print(f"  [FAIL] {name} {detail}")


def register_and_login(prefix: str) -> tuple[str, dict[str, str]]:
    """注册临时用户并返回 (username, Authorization 头)。"""
    username = f"{prefix}_{uuid.uuid4().hex[:8]}"
    resp = client.post(
        "/api/v1/auth/register",
        json={"username": username, "password": "pass123456", "confirm_password": "pass123456"},
    )
    assert resp.status_code == 200 and resp.json()["code"] == 0, f"注册失败: {resp.text}"
    token = resp.json()["data"]["access_token"]
    return username, {"Authorization": f"Bearer {token}"}


def create_task(headers: dict[str, str], **overrides: Any) -> dict:
    """创建任务并返回响应 JSON。"""
    payload: dict[str, Any] = {"title": "学习 Transformer Attention"}
    payload.update(overrides)
    resp = client.post("/api/v1/tasks", json=payload, headers=headers)
    return resp.json()


def patch_status(
    headers: dict[str, str], task_id: int, status: str
) -> tuple[int, dict]:
    """PATCH 状态流转并返回 (HTTP 状态码, 响应 JSON)。"""
    resp = client.patch(
        f"/api/v1/tasks/{task_id}/status",
        json={"status": status},
        headers=headers,
    )
    return resp.status_code, resp.json()


def get_user_id(username: str) -> int:
    """按用户名查用户 id。"""
    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.username == username))
        assert user is not None
        return user.id


def main() -> None:
    now = utc_now()

    # 用户 A（主流程）、B（越权）、C（筛选+分页）、D（统计 DB 直插）、E（空数据）。
    user_a, headers_a = register_and_login("p5task_a")
    _, headers_b = register_and_login("p5task_b")
    user_c, headers_c = register_and_login("p5task_c")
    user_d, headers_d = register_and_login("p5task_d")
    _, headers_e = register_and_login("p5task_e")

    # ------------------------------------------------------------------
    print("用例 1：创建任务（合法表单）")
    resp = client.post(
        "/api/v1/tasks",
        json={
            "title": "学习 Transformer Attention",
            "description": "精读论文并整理笔记",
            "knowledge_points": ["Transformer", "Attention"],
            "priority": "high",
            "estimated_minutes": 90,
            "deadline": (now + timedelta(days=3)).isoformat(),
        },
        headers=headers_a,
    )
    body = resp.json()
    check("1a code=0", resp.status_code == 200 and body["code"] == 0, str(body))
    task = body.get("data") or {}
    check("1b status=todo", task.get("status") == "todo")
    check("1c source=manual", task.get("source") == "manual")
    check("1d knowledge_points 回显", task.get("knowledge_points") == ["Transformer", "Attention"])
    check("1e completed_at=null", task.get("completed_at") is None)
    check("1f actual_minutes=null", task.get("actual_minutes") is None)
    main_task_id = task.get("id")
    check("1g 返回 id", isinstance(main_task_id, int))

    # ------------------------------------------------------------------
    print("用例 2：创建参数校验")
    resp = client.post("/api/v1/tasks", json={"title": ""}, headers=headers_a)
    check("2a title 空 422/1001", resp.status_code == 422 and resp.json()["code"] == 1001)
    resp = client.post("/api/v1/tasks", json={"title": "x" * 201}, headers=headers_a)
    check("2b title 超长 422/1001", resp.status_code == 422 and resp.json()["code"] == 1001)
    resp = client.post(
        "/api/v1/tasks", json={"title": "t", "priority": "urgent"}, headers=headers_a
    )
    check("2c priority 非法 422/1001", resp.status_code == 422 and resp.json()["code"] == 1001)
    resp = client.post(
        "/api/v1/tasks",
        json={"title": "t", "estimated_minutes": 0},
        headers=headers_a,
    )
    check("2d estimated_minutes=0 422/1001", resp.status_code == 422 and resp.json()["code"] == 1001)
    resp = client.post(
        "/api/v1/tasks",
        json={"title": "t", "knowledge_points": [f"kp{i}" for i in range(21)]},
        headers=headers_a,
    )
    check("2e 知识点超 20 个 422/1001", resp.status_code == 422 and resp.json()["code"] == 1001)
    resp = client.post(
        "/api/v1/tasks",
        json={"title": "t", "knowledge_points": ["A", ""]},
        headers=headers_a,
    )
    check("2f 知识点空串元素 422/1001", resp.status_code == 422 and resp.json()["code"] == 1001)
    resp = client.post(
        "/api/v1/tasks", json={"title": "t", "status": "todo"}, headers=headers_a
    )
    body = resp.json()
    check(
        "2g 携带 status 422 且中文提示",
        resp.status_code == 422 and body["code"] == 1001 and "状态流转接口" in body.get("message", ""),
        str(body),
    )
    resp = client.post(
        "/api/v1/tasks",
        json={"title": "t", "completed_at": "2026-01-01T00:00:00Z"},
        headers=headers_a,
    )
    check("2h 携带 completed_at 422/1001", resp.status_code == 422 and resp.json()["code"] == 1001)
    resp = client.post(
        "/api/v1/tasks", json={"title": "t", "goal_id": 999999}, headers=headers_a
    )
    check("2i goal_id 不存在 404/1005", resp.status_code == 404 and resp.json()["code"] == 1005)
    # 用户 B 的课程（DB 直插，课程写接口不在 P5 范围）。
    user_b_id = get_user_id(register_and_login("p5task_b")[0]) if False else None
    with SessionLocal() as db:
        user_b = db.scalar(select(User).where(User.username.like("p5task_b_%")))
        course_b = Course(user_id=user_b.id, name="B 的私有课程")
        db.add(course_b)
        db.commit()
        course_b_id = course_b.id
    resp = client.post(
        "/api/v1/tasks", json={"title": "t", "course_id": course_b_id}, headers=headers_a
    )
    check("2j course_id 他人 404/1005", resp.status_code == 404 and resp.json()["code"] == 1005)

    # ------------------------------------------------------------------
    print("用例 3：筛选组合（用户 C，5 条自控数据）")
    base = {
        "逾期高优": {"deadline": (now - timedelta(hours=2)).isoformat(), "priority": "high"},
        "逾期中优": {"deadline": (now - timedelta(hours=2)).isoformat(), "priority": "medium"},
        "未到期高优": {
            "deadline": (now + timedelta(days=2)).isoformat(),
            "priority": "high",
            "knowledge_points": ["Multi-Head Attention"],
        },
        "无截止": {"knowledge_points": ["Attention"]},
        "关键词": {"description": "涵盖 attention 机制", "deadline": (now + timedelta(days=3)).isoformat()},
    }
    for i, (name, kw) in enumerate(base.items()):
        payload = {"title": f"C-{name}-{i}"}
        if name == "关键词":
            payload["title"] = "学习 Transformer 基础"
        payload.update(kw)
        r = client.post("/api/v1/tasks", json=payload, headers=headers_c)
        assert r.json()["code"] == 0, r.text
    c_ids = {
        item["title"]: item["id"]
        for item in client.get("/api/v1/tasks?page_size=100", headers=headers_c).json()["data"]["items"]
    }
    overdue_high_id = c_ids["C-逾期高优-0"]
    no_deadline_id = c_ids["C-无截止-3"]
    kw_id = c_ids["学习 Transformer 基础"]

    resp = client.get(
        "/api/v1/tasks?overdue=true&priority=high&page_size=100", headers=headers_c
    )
    items = resp.json()["data"]["items"]
    check(
        "3a 逾期+高优筛选（验收①）",
        resp.json()["code"] == 0
        and [i["id"] for i in items] == [overdue_high_id]
        and items[0]["priority"] == "high",
        str(items),
    )
    resp = client.get("/api/v1/tasks?overdue=false&page_size=100", headers=headers_c)
    items = resp.json()["data"]["items"]
    got_ids = {i["id"] for i in items}
    overdue_ids = {c_ids["C-逾期高优-0"], c_ids["C-逾期中优-1"]}
    check(
        "3b overdue=false 含无截止且不含逾期",
        no_deadline_id in got_ids and not (got_ids & overdue_ids),
        str(got_ids),
    )
    resp = client.get(
        "/api/v1/tasks?knowledge_point=Attention&page_size=100", headers=headers_c
    )
    got_ids = {i["id"] for i in resp.json()["data"]["items"]}
    check(
        "3c knowledge_point 精确匹配（裁定⑩）",
        no_deadline_id in got_ids and c_ids["C-未到期高优-2"] not in got_ids,
        str(got_ids),
    )
    resp = client.get(
        "/api/v1/tasks?keyword=TRANSFORMER&page_size=100", headers=headers_c
    )
    got_ids = {i["id"] for i in resp.json()["data"]["items"]}
    check("3d keyword 大小写不敏感命中 title", kw_id in got_ids, str(got_ids))
    resp = client.get(
        "/api/v1/tasks?keyword=attention&page_size=100", headers=headers_c
    )
    got_ids = {i["id"] for i in resp.json()["data"]["items"]}
    check("3e keyword 命中 description", kw_id in got_ids, str(got_ids))
    resp = client.get("/api/v1/tasks?status=bad", headers=headers_c)
    check("3f 非法 status 422", resp.status_code == 422)
    resp = client.get(
        "/api/v1/tasks?page=1&page_size=20&status=todo&priority=high"
        "&course_id=1&knowledge_point=Attention&overdue=true&keyword=x",
        headers=headers_c,
    )
    check(
        "3g 全参数同传不 422（P4 专项）",
        resp.status_code == 200 and resp.json()["code"] == 0,
        resp.text,
    )

    # ------------------------------------------------------------------
    print("用例 4：分页边界（补 100 条至 105）")
    for i in range(100):
        r = client.post(
            "/api/v1/tasks", json={"title": f"P5分页-{i:03d}"}, headers=headers_c
        )
        assert r.json()["code"] == 0, r.text
    resp = client.get("/api/v1/tasks?page=1&page_size=100", headers=headers_c)
    data = resp.json()["data"]
    check("4a 首页 100 条 total=105（验收④）", len(data["items"]) == 100 and data["total"] == 105, str(data["total"]))
    resp = client.get("/api/v1/tasks?page=2&page_size=100", headers=headers_c)
    data = resp.json()["data"]
    check("4b 末页 5 条（验收④）", len(data["items"]) == 5, str(len(data["items"])))
    resp = client.get("/api/v1/tasks?page=1&page_size=150", headers=headers_c)
    check("4c page_size 越界 422（决策⑭）", resp.status_code == 422)
    resp = client.get("/api/v1/tasks?page=1&page_size=100", headers=headers_c)
    items = resp.json()["data"]["items"]
    check("4d 默认 id 降序（决策⑧）", items[0]["id"] > items[-1]["id"])

    # ------------------------------------------------------------------
    print("用例 5：合法流转链（五边全通）")
    r = create_task(headers_a, title="流转链任务")
    flow_id = r["data"]["id"]
    code, body = patch_status(headers_a, flow_id, "in_progress")
    check("5a todo→in_progress", code == 200 and body["data"]["status"] == "in_progress", str(body))
    code, body = patch_status(headers_a, flow_id, "done")
    completed_first = body["data"]["completed_at"]
    check(
        "5b in_progress→done 且 completed_at 写入",
        code == 200 and completed_first is not None,
        str(body),
    )
    code, body = patch_status(headers_a, flow_id, "review")
    check(
        "5c done→review 且 completed_at 保留",
        code == 200 and body["data"]["completed_at"] == completed_first,
        str(body),
    )
    code, body = patch_status(headers_a, flow_id, "done")
    check(
        "5d review→done 且 completed_at 不覆盖（裁定⑤）",
        code == 200 and body["data"]["completed_at"] == completed_first,
        str(body),
    )

    # ------------------------------------------------------------------
    print("用例 6：非法流转拒绝")
    r = create_task(headers_a, title="拒绝流转任务")
    rej_id = r["data"]["id"]
    code, body = patch_status(headers_a, rej_id, "done")
    check(
        "6a todo→done 1007/400 + 中文提示（验收③）",
        code == 400 and body["code"] == 1007 and "待办" in body["message"] and "已完成" in body["message"],
        f"{code} {body}",
    )
    code, body = patch_status(headers_a, rej_id, "todo")
    check("6b todo→todo 同状态 1007/400", code == 400 and body["code"] == 1007)
    code, body = patch_status(headers_a, flow_id, "todo")
    check("6c done→todo 1007/400", code == 400 and body["code"] == 1007)
    code, body = patch_status(headers_a, flow_id, "in_progress")
    check("6d done→in_progress 1007/400", code == 400 and body["code"] == 1007)
    r = create_task(headers_a, title="review 回退任务")
    r2_id = r["data"]["id"]
    patch_status(headers_a, r2_id, "in_progress")
    patch_status(headers_a, r2_id, "done")
    patch_status(headers_a, r2_id, "review")
    code, body = patch_status(headers_a, r2_id, "in_progress")
    check("6e review→in_progress 1007/400", code == 400 and body["code"] == 1007)
    resp = client.patch(
        f"/api/v1/tasks/{rej_id}/status", json={"status": "bad"}, headers=headers_a
    )
    check("6f 目标值非法枚举 422/1001", resp.status_code == 422 and resp.json()["code"] == 1001)
    resp = client.get(f"/api/v1/tasks/{rej_id}", headers=headers_a)
    detail = resp.json()["data"]
    check(
        "6g 被拒后 status 与 completed_at 均未变",
        detail["status"] == "todo" and detail["completed_at"] is None,
        str(detail),
    )
    code, body = patch_status(headers_a, 999999, "in_progress")
    check("6h 不存在任务 404/1005", code == 404 and body["code"] == 1005)

    # ------------------------------------------------------------------
    print("用例 7：搁置回退边（裁定㉑）")
    r = create_task(headers_a, title="搁置任务")
    hold_id = r["data"]["id"]
    patch_status(headers_a, hold_id, "in_progress")
    code, body = patch_status(headers_a, hold_id, "todo")
    check(
        "7a in_progress→todo 搁置成功且 completed_at=null",
        code == 200 and body["data"]["status"] == "todo" and body["data"]["completed_at"] is None,
        str(body),
    )
    patch_status(headers_a, hold_id, "in_progress")
    code, body = patch_status(headers_a, hold_id, "done")
    check(
        "7b 搁置后重新完成 completed_at 写入",
        code == 200 and body["data"]["completed_at"] is not None,
        str(body),
    )

    # ------------------------------------------------------------------
    print("用例 8：PUT 编辑")
    resp = client.put(
        f"/api/v1/tasks/{main_task_id}",
        json={
            "title": "学习 Transformer Attention（修订）",
            "actual_minutes": 45,
            "scheduled_date": "2026-10-20",
        },
        headers=headers_a,
    )
    body = resp.json()
    updated = body.get("data") or {}
    check(
        "8a 部分字段更新成功（含 actual_minutes / scheduled_date）",
        body["code"] == 0
        and updated.get("title") == "学习 Transformer Attention（修订）"
        and updated.get("actual_minutes") == 45
        and updated.get("scheduled_date") == "2026-10-20",
        str(body),
    )
    check("8b 编辑后 status 保持不变", updated.get("status") == "todo")
    resp = client.put(
        f"/api/v1/tasks/{main_task_id}", json={"status": "done"}, headers=headers_a
    )
    body = resp.json()
    check(
        "8c 携带 status 422 + 中文提示",
        resp.status_code == 422 and body["code"] == 1001 and "状态流转接口" in body.get("message", ""),
        str(body),
    )
    for field in ("completed_at", "source", "user_id"):
        resp = client.put(
            f"/api/v1/tasks/{main_task_id}", json={field: "x"}, headers=headers_a
        )
        check(
            f"8d 携带 {field} 422/1001",
            resp.status_code == 422 and resp.json()["code"] == 1001,
        )
    resp = client.put(
        f"/api/v1/tasks/{main_task_id}", json={"title": "越权"}, headers=headers_b
    )
    check("8e 越权 PUT 404/1005", resp.status_code == 404 and resp.json()["code"] == 1005)

    # ------------------------------------------------------------------
    print("用例 9：看板分列")
    for p in ("high", "medium", "low"):
        r = create_task(headers_a, title=f"看板-{p}", priority=p)
        assert r["code"] == 0, str(r)
    resp = client.get("/api/v1/tasks/board", headers=headers_a)
    body = resp.json()
    check("9a code=0 且四键齐全", body["code"] == 0 and set(body["data"]) == {"todo", "in_progress", "done", "review"}, str(body.get("data", {}).keys() if body.get("data") else body))
    board = body["data"]
    check(
        "9b 各列元素 status 与列一致",
        all(item["status"] == col for col in board for item in board[col]),
    )
    board_total = sum(len(board[col]) for col in board)
    resp = client.get("/api/v1/tasks?page_size=100", headers=headers_a)
    list_total = 0
    page = 1
    while True:
        d = client.get(
            f"/api/v1/tasks?page={page}&page_size=100", headers=headers_a
        ).json()["data"]
        list_total = d["total"]
        if page * 100 >= list_total:
            break
        page += 1
    check("9c 四列总数 = 列表 total（无遗漏无重复）", board_total == list_total, f"{board_total} vs {list_total}")
    todo_ids = [item["id"] for item in board["todo"]]
    prio = {
        item["id"]: item["priority"]
        for col in board for item in board[col]
    }
    kanban_ids = [i for i in todo_ids if prio[i] in ("high", "medium", "low") and str(prio.get(i))]
    hi = next(i for i, t in prio.items() if t == "high")
    md = next(i for i, t in prio.items() if t == "medium")
    lo = next(i for i, t in prio.items() if t == "low")
    check(
        "9d 列内优先级降序（high→medium→low）",
        todo_ids.index(hi) < todo_ids.index(md) < todo_ids.index(lo),
        str(todo_ids),
    )
    resp = client.get("/api/v1/tasks/board", headers=headers_b)
    b_board = resp.json()["data"]
    b_all = {item["id"] for col in b_board for item in b_board[col]}
    a_all = {item["id"] for col in board for item in board[col]}
    check("9e 用户 B 看板与 A 无交集（隔离）", not (a_all & b_all))

    # ------------------------------------------------------------------
    print("用例 10：统计口径（用户 D DB 直插，时间相对当前动态计算）")
    today_bj, today_start, today_end = _today_bounds_utc(now)
    week_start, week_end = _week_bounds_utc(now)
    user_d_id = get_user_id(user_d)

    def _t(
        title: str,
        status: TaskStatus,
        *,
        deadline: datetime | None = None,
        completed_at: datetime | None = None,
        scheduled_date: date | None = None,
    ) -> Task:
        return Task(
            user_id=user_d_id,
            title=title,
            status=status,
            priority=Priority.MEDIUM,
            deadline=deadline,
            completed_at=completed_at,
            scheduled_date=scheduled_date,
            knowledge_points=[],
        )

    day = timedelta(days=1)
    stat_tasks = [
        _t("t1-本周一凌晨完成", TaskStatus.DONE, deadline=week_start + day + timedelta(hours=2), completed_at=week_start + timedelta(minutes=30)),
        _t("t2-本周三完成", TaskStatus.DONE, deadline=week_start + 2 * day + timedelta(hours=2), completed_at=week_start + 2 * day + timedelta(hours=1)),
        _t("t3-本周五完成进复盘", TaskStatus.REVIEW, deadline=week_start + 4 * day + timedelta(hours=2), completed_at=week_start + 4 * day),
        _t("t4-本周四到期未做", TaskStatus.TODO, deadline=week_start + 3 * day + timedelta(hours=2)),
        _t("t5-上周日深夜完成", TaskStatus.DONE, deadline=week_start - 5 * day, completed_at=week_start - timedelta(minutes=30)),
        _t("t6-上周到期逾期", TaskStatus.TODO, deadline=week_start - 3 * day),
        _t("t7-上周到期已完成", TaskStatus.DONE, deadline=week_start - 3 * day, completed_at=week_start - 6 * day),
        _t("t8-今天到期", TaskStatus.TODO, deadline=today_start + timedelta(hours=12)),
        _t("t9-今天计划执行", TaskStatus.IN_PROGRESS, scheduled_date=today_bj),
        _t("t10-今天到期已完成", TaskStatus.DONE, deadline=today_start + timedelta(hours=12), completed_at=week_start - 6 * day),
    ]
    with SessionLocal() as db:
        db.add_all(stat_tasks)
        db.commit()

    resp = client.get("/api/v1/tasks/stats", headers=headers_d)
    stats = resp.json().get("data") or {}
    check("10a status_counts 四键之和 = total", stats.get("total") == 10 and sum(stats.get("status_counts", {}).values()) == 10, str(stats))
    sc = stats.get("status_counts") or {}
    check(
        "10b 各状态计数（done=5/review=1/todo=3/in_progress=1）",
        sc.get("done") == 5 and sc.get("review") == 1 and sc.get("todo") == 3 and sc.get("in_progress") == 1,
        str(sc),
    )
    t8_deadline = today_start + timedelta(hours=12)
    t4_deadline = week_start + 3 * day + timedelta(hours=2)
    expected_overdue = 1 + int(t6_expired := True) - 1 + int(t4_deadline < now) + int(t8_deadline < now)
    check(
        "10c overdue_count：过期 todo 计、过期 done 不计（裁定①）",
        stats.get("overdue_count") == 1 + int(t4_deadline < now) + int(t8_deadline < now),
        f"got={stats.get('overdue_count')} t4_past={t4_deadline < now} t8_past={t8_deadline < now}",
    )
    check(
        "10d 本周完成率 = 3/6 = 50.0（分子含 review，裁定②）",
        stats.get("weekly_completion_rate") == 50.0,
        str(stats.get("weekly_completion_rate")),
    )
    check(
        "10e 时区边界：北京周一 00:30（UTC 周日 16:30）计入本周（裁定㉒）",
        stats.get("weekly_completion_rate") == 50.0 and week_start == _week_bounds_utc(now)[0],
        f"week_start={week_start}",
    )
    check(
        "10f 北京上周日 23:30 完成的不计入本周分子",
        stats.get("weekly_completion_rate") == 50.0,
        "t5 completed_at=week_start-30min，若误计入则 rate=66.7",
    )
    check(
        "10g today_todo：deadline 今天 todo + scheduled 今天 in_progress = 2（裁定③）",
        stats.get("today_todo_count") == 2,
        str(stats.get("today_todo_count")),
    )
    resp = client.get("/api/v1/tasks/stats", headers=headers_e)
    empty = resp.json().get("data") or {}
    check(
        "10h 无任务用户全 0（含分母 0 → 0，spec 5.5.1 规则 1b/4b）",
        empty.get("total") == 0
        and empty.get("overdue_count") == 0
        and empty.get("weekly_completion_rate") == 0.0
        and empty.get("today_todo_count") == 0,
        str(empty),
    )

    # ------------------------------------------------------------------
    print("用例 11：删除与关联保留（FK SET NULL）")
    r = create_task(headers_a, title="待删除任务")
    del_id = r["data"]["id"]
    user_a_id = get_user_id(user_a)
    with SessionLocal() as db:
        db.add(
            LearningRecord(
                user_id=user_a_id,
                task_id=del_id,
                content="删除关联验证学习记录",
                duration_minutes=30,
                study_date=today_bj,
                knowledge_points=["验证"],
            )
        )
        db.commit()
    resp = client.delete(f"/api/v1/tasks/{del_id}", headers=headers_b)
    check("11a 越权 DELETE 404/1005", resp.status_code == 404 and resp.json()["code"] == 1005)
    resp = client.delete(f"/api/v1/tasks/{del_id}", headers=headers_a)
    body = resp.json()
    check("11b 删除成功 data 为被删对象", body["code"] == 0 and body["data"]["id"] == del_id)
    resp = client.get(f"/api/v1/tasks/{del_id}", headers=headers_a)
    check("11c 删除后 GET 404/1005", resp.status_code == 404 and resp.json()["code"] == 1005)
    with SessionLocal() as db:
        rec = db.scalar(
            select(LearningRecord).where(
                LearningRecord.user_id == user_a_id,
                LearningRecord.content == "删除关联验证学习记录",
            )
        )
    check(
        "11d learning_record 仍在且 task_id 置空（裁定⑱）",
        rec is not None and rec.task_id is None,
        f"rec={rec}",
    )

    # ------------------------------------------------------------------
    print("用例 12：未登录访问")
    for method, url in (
        ("get", "/api/v1/tasks"),
        ("get", "/api/v1/tasks/board"),
        ("get", "/api/v1/tasks/stats"),
        ("get", "/api/v1/tasks/1"),
        ("post", "/api/v1/tasks"),
        ("put", "/api/v1/tasks/1"),
        ("delete", "/api/v1/tasks/1"),
        ("patch", "/api/v1/tasks/1/status"),
    ):
        resp = getattr(client, method)(url)
        check(
            f"12 {method.upper()} {url} 401/1003",
            resp.status_code == 401 and resp.json()["code"] == 1003,
            f"{resp.status_code}",
        )

    # ---- 汇总与清理 --------------------------------------------------------
    print(f"\n结果：{len(PASSED)} PASS / {len(FAILED)} FAIL")
    if FAILED:
        print("失败用例：", FAILED)
    cleanup(user_a, user_c, user_d)
    sys.exit(1 if FAILED else 0)


def cleanup(*usernames: str) -> None:
    """删除临时用户（FK CASCADE 级联清理其任务、课程与学习记录）。"""
    with SessionLocal() as db:
        for username in usernames:
            like = username if username.endswith("%") else username
            user = db.scalar(select(User).where(User.username == like))
            if user is None and not like.endswith("%"):
                user = db.scalar(
                    select(User).where(User.username.like(f"{like}_%"))
                )
            if user is not None:
                db.delete(user)
        db.commit()


if __name__ == "__main__":
    main()