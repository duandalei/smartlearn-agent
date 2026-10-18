"""P4 目标 CRUD 与知识树接口回归验证（任务 8.2，ASGI 直调）。

运行：cd backend && .venv/Scripts/python scripts/verify_p4_goals.py

验证方式：``fastapi.testclient.TestClient`` 进程内直调 app 对象
（不起 uvicorn、不发真实网络请求，规避沙箱 IPv4 回环拦截）。

覆盖用例（tasks.md 8.2）：
    1. 创建目标（合法表单）→ code=0、roadmap=null、status=active
    2. 参数校验：title 空 / 超长、goal_type 非法、end<start（1007）
    3. 列表分页 + status 筛选 + page_size 越界（按既有分页 schema 为
       le=100 → 422 拒绝；PROJECT_CONTEXT 5.3 契约行为，非静默截断）
    4. PUT 编辑（roadmap 不变；携带 roadmap 字段 422 拒绝）
    5. GET /roadmap（从未拆解 → data.roadmap=null）
    6. DELETE（删除后 404；越权 404；掌握度记录保留的 DB 直查断言）
    7. 未携带 Token → 401/1003
"""

from __future__ import annotations

import os
import sys
import uuid
from pathlib import Path
from typing import Any

_SCRIPTS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(_SCRIPTS_DIR.parent))
sys.path.insert(0, str(_SCRIPTS_DIR))

# 沙箱 data/ 目录间歇性写锁（P2 起已知问题）：验证脚本改用 backend 下的
# 临时数据库（环境变量优先级高于 .env），不污染正式 data/smartlearn.db。
_TMP_DB_DIR = _SCRIPTS_DIR.parent / "tmp_verify"
_TMP_DB_DIR.mkdir(exist_ok=True)
_TMP_DB = _TMP_DB_DIR / "p4_goals.db"
if _TMP_DB.exists():
    _TMP_DB.unlink()
os.environ["DATABASE_URL"] = f"sqlite:///{_TMP_DB.as_posix()}"

import _sandbox_patch  # noqa: F401,E402  （IPv6 socketpair 补丁，须先于 TestClient）

from fastapi.testclient import TestClient  # noqa: E402

from app.db.session import SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402
from app.models.base import Base  # noqa: E402
from app.models.goal import LearningGoal  # noqa: E402
from app.models.mastery import KnowledgeMastery  # noqa: E402
from app.models.user import User  # noqa: E402

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


def create_goal(headers: dict[str, str], **overrides: Any) -> dict:
    """创建目标并返回响应 JSON。"""
    payload: dict[str, Any] = {
        "title": "6个月掌握机器学习",
        "goal_type": "技能提升",
        "description": "从零基础到能独立完成机器学习项目",
        "start_date": "2026-10-17",
        "end_date": "2027-04-01",
    }
    payload.update(overrides)
    resp = client.post("/api/v1/goals", json=payload, headers=headers)
    return resp.json()


def main() -> None:
    # 用户 A（主角）与用户 B（越权测试）。
    user_a, headers_a = register_and_login("p4goal_a")
    _, headers_b = register_and_login("p4goal_b")

    print("用例 1：创建目标（合法表单）")
    body = create_goal(headers_a)
    check("1a code=0", body["code"] == 0, str(body))
    goal = body.get("data") or {}
    check("1b roadmap=null", goal.get("roadmap") is None, str(goal.get("roadmap")))
    check("1c status=active", goal.get("status") == "active")
    check("1d goal_type 回显", goal.get("goal_type") == "技能提升")
    goal_id = goal.get("id")
    check("1e 返回 id", isinstance(goal_id, int))

    print("用例 2：参数校验")
    resp = client.post("/api/v1/goals", json={"title": ""}, headers=headers_a)
    check("2a title 空 422/1001", resp.status_code == 422 and resp.json()["code"] == 1001)
    resp = client.post("/api/v1/goals", json={"title": "x" * 201}, headers=headers_a)
    check("2b title 超长 422/1001", resp.status_code == 422 and resp.json()["code"] == 1001)
    resp = client.post("/api/v1/goals", json={"title": "t", "goal_type": "非法类型"}, headers=headers_a)
    check("2c goal_type 非法 422/1001", resp.status_code == 422 and resp.json()["code"] == 1001)
    resp = client.post(
        "/api/v1/goals",
        json={"title": "t", "start_date": "2027-05-01", "end_date": "2027-04-01"},
        headers=headers_a,
    )
    body = resp.json()
    check("2d end<start 1007/400", resp.status_code == 400 and body["code"] == 1007, str(body))

    print("用例 3：列表分页与状态筛选")
    resp = client.get("/api/v1/goals?page=1&page_size=10", headers=headers_a)
    body = resp.json()
    data = body.get("data") or {}
    check("3a 分页结构", body["code"] == 0 and {"items", "total", "page", "page_size"} <= set(data))
    check("3b 仅含本人目标", all(i["user_id"] == goal["user_id"] for i in data["items"]))
    resp = client.get("/api/v1/goals?status=completed", headers=headers_a)
    items = resp.json()["data"]["items"]
    check("3c status 筛选生效", all(i["status"] == "completed" for i in items) and len(items) == 0)
    resp = client.get("/api/v1/goals?status=active", headers=headers_a)
    items = resp.json()["data"]["items"]
    check("3d active 筛选命中", any(i["id"] == goal_id for i in items))
    resp = client.get("/api/v1/goals?page=1&page_size=150", headers=headers_a)
    check("3e page_size 越界 422（分页 schema le=100）", resp.status_code == 422)
    resp = client.get("/api/v1/goals?status=bad_status", headers=headers_a)
    check("3f 非法 status 422", resp.status_code == 422)

    print("用例 4：PUT 编辑")
    resp = client.put(
        f"/api/v1/goals/{goal_id}",
        json={"title": "6个月掌握机器学习（修订）", "goal_type": "考研"},
        headers=headers_a,
    )
    body = resp.json()
    updated = body.get("data") or {}
    check("4a 编辑成功", body["code"] == 0 and updated.get("title") == "6个月掌握机器学习（修订）")
    check("4b roadmap 保持 null", updated.get("roadmap") is None)
    check("4c roadmap_updated_at 保持 null", updated.get("roadmap_updated_at") is None)
    resp = client.put(
        f"/api/v1/goals/{goal_id}",
        json={"roadmap": {"name": "篡改", "children": []}},
        headers=headers_a,
    )
    check("4d 携带 roadmap 字段 422 拒绝", resp.status_code == 422 and resp.json()["code"] == 1001)

    print("用例 5：GET /roadmap（从未拆解）")
    resp = client.get(f"/api/v1/goals/{goal_id}/roadmap", headers=headers_a)
    body = resp.json()
    check("5a code=0", body["code"] == 0)
    check("5b data.roadmap=null", (body.get("data") or {}).get("roadmap") is None, str(body))

    print("用例 6：越权与删除")
    resp = client.get(f"/api/v1/goals/{goal_id}", headers=headers_b)
    check("6a 用户 B 访问用户 A 目标 404/1005", resp.status_code == 404 and resp.json()["code"] == 1005)
    resp = client.delete(f"/api/v1/goals/{goal_id}", headers=headers_b)
    check("6b 用户 B 删除用户 A 目标 404/1005", resp.status_code == 404 and resp.json()["code"] == 1005)

    # 为验证「删除保留掌握度」，先经 DB 直插一条该用户的掌握度记录，
    # 再删目标并断言记录仍在（spec 5.1.1 规则 4a：删目标不抹学习历史）。
    with SessionLocal() as db:
        user = db.scalar(select_user(user_a))
        db.add(
            KnowledgeMastery(
                user_id=user.id,
                knowledge_point="删除保留验证点",
                mastery_score=42.0,
                source="record",
            )
        )
        db.commit()
    resp = client.delete(f"/api/v1/goals/{goal_id}", headers=headers_a)
    body = resp.json()
    check("6c 删除成功 data 为被删对象", body["code"] == 0 and body["data"]["id"] == goal_id)
    resp = client.get(f"/api/v1/goals/{goal_id}", headers=headers_a)
    check("6d 删除后再查 404/1005", resp.status_code == 404 and resp.json()["code"] == 1005)
    from sqlalchemy import select  # noqa: E402  （main 内局部导入，与 helper 风格一致）

    with SessionLocal() as db:
        user = db.scalar(select_user(user_a))
        kept = db.scalar(
            select(KnowledgeMastery).where(
                KnowledgeMastery.user_id == user.id,
                KnowledgeMastery.knowledge_point == "删除保留验证点",
            )
        )
    check("6e 删除目标后掌握度记录保留", kept is not None and kept.mastery_score == 42.0)
    left = db_scalar_count_goals(user_a)
    check("6f 目标确已删除", left == 0)

    print("用例 7：未携带 Token")
    resp = client.get("/api/v1/goals")
    check("7a 401/1003", resp.status_code == 401 and resp.json()["code"] == 1003)
    resp = client.post("/api/v1/goals/1/breakdown")
    check("7b breakdown 无 Token 401/1003", resp.status_code == 401 and resp.json()["code"] == 1003)

    # ---- 汇总与清理 --------------------------------------------------------
    print(f"\n结果：{len(PASSED)} PASS / {len(FAILED)} FAIL")
    if FAILED:
        print("失败用例：", FAILED)
    cleanup(user_a)
    sys.exit(1 if FAILED else 0)


def select_user(username: str):
    """构造按用户名查询 User 的语句（延迟导入避免顶层命名冲突）。"""
    from sqlalchemy import select

    return select(User).where(User.username == username)


def db_scalar_count_goals(username: str) -> int:
    """统计临时用户的剩余目标数。"""
    from sqlalchemy import func, select

    with SessionLocal() as db:
        user = db.scalar(select_user(username))
        return int(
            db.scalar(
                select(func.count()).select_from(LearningGoal).where(
                    LearningGoal.user_id == user.id
                )
            )
        )


def cleanup(*usernames: str) -> None:
    """删除临时用户（FK CASCADE 级联清理其目标与掌握度记录）。"""
    from sqlalchemy import delete, select

    with SessionLocal() as db:
        for username in usernames:
            user = db.scalar(select_user(username))
            if user is not None:
                db.delete(user)
        db.commit()


if __name__ == "__main__":
    main()