"""P6 学习记录 / 掌握度重放 / 任务回填 / timeline / stats 验收脚本（ASGI 直调）。

运行：cd backend && .venv/Scripts/python scripts/verify_p6_records.py

验证方式：``fastapi.testclient.TestClient`` 进程内直调 app 对象
（不起 uvicorn、不发真实网络请求，规避沙箱 IPv4 回环拦截）。

覆盖用例（tasks.md 5.1–5.4，对照验收①②③）：
     1. 验收①：库中无 Transformer → 提交自评 60 记录 → 自动 INSERT
        score=18、source='record'
     2. 验收②：追加自评 80（study_date 在后）→ 36.6，上升且 ≤100
     3. 乱序补记：先记 T-9 自评 80（24），补记 T-48 自评 100 →
        重放 45（断言 ≠ 46.8 错误增量值）
     4. mastery_level=null 记录创建成功且不触发掌握度变化
     5. 错题扣分（-3/题下限 0）；衰减边界 35→不扣 / 37→2 / 44→4 /
        衰减前 3 分距 100 天→0
     6. 40 天幂等专项：两次 recalculate_all 分数完全相等
        （可捕获误用 updated_at 基准的错误实现）
     7. 无学习记录知识点不衰减；种子保护（self_report /
        goal_breakdown 行不被抹 0、source 不被改写）
     8. 重放上限（8 条自评 100 → 94.24 ≤ 100）
     9. recalculate_all 与单点重放一致（含乱序补记后执行）+ 幂等
    10. 参数校验 422（时长 0/1500、自评 120、日期超前、知识点空串、
        携带 user_id、列表区间倒置、days 0/400）
    11. 越权 404/1005（他人 task / course / record，中文提示）
    12. PUT 部分更新；知识点 [A]→[B] 并集重放（A 回落、B 纳入）；
        mastery_level 80→null 退出聚合
    13. 任务回填全链路：90+30→120 → 改 30 为 50→140 → 删 50→90 →
        删空→NULL（断言非 0）→ 再记 45→恢复；解除关联→NULL；
        未触达任务手动值 60 保持
    14. 验收③：timeline days=30 → 恰 30 条、升序、首条 29 天前、
        末条今天、无记录天 0、同日合计；无记录用户全 0
    15. stats：weekly 上周日不计入；streak 三场景 2/2/0；total_count
    16. 回归：既有分页调用行为不变；六参数同传不 422；未登录全端
        点 401/1003
"""

from __future__ import annotations

import os
import sys
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

_SCRIPTS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(_SCRIPTS_DIR.parent))
sys.path.insert(0, str(_SCRIPTS_DIR))

# 沙箱 data/ 目录间歇性写锁（P2 起已知问题）：验证脚本改用 backend 下的
# 临时数据库（环境变量优先级高于 .env），不污染正式 data/smartlearn.db。
_TMP_DB_DIR = _SCRIPTS_DIR.parent / "tmp_verify"
_TMP_DB_DIR.mkdir(exist_ok=True)
_TMP_DB = _TMP_DB_DIR / "p6_records.db"
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
from app.models.enums import MasterySource  # noqa: E402
from app.models.mastery import KnowledgeMastery  # noqa: E402
from app.models.mistake import Mistake  # noqa: E402
from app.models.user import User  # noqa: E402
from app.services.mastery import recalculate_all  # noqa: E402
from app.services.task import TZ_BEIJING  # noqa: E402

# 建表（临时库，无种子数据；用例自含全部前置数据）。
Base.metadata.create_all(engine)

client = TestClient(app)

PASSED: list[str] = []
FAILED: list[str] = []

TODAY: datetime = datetime.now(TZ_BEIJING)
TODAY_STR: str = TODAY.date().isoformat()


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
        json={
            "username": username,
            "password": "pass123456",
            "confirm_password": "pass123456",
        },
    )
    assert resp.status_code == 200 and resp.json()["code"] == 0, (
        f"注册失败: {resp.text}"
    )
    token = resp.json()["data"]["access_token"]
    return username, {"Authorization": f"Bearer {token}"}


def get_user_id(username: str) -> int:
    """按用户名查用户 id。"""
    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.username == username))
        assert user is not None
        return user.id


def create_record(headers: dict[str, str], **overrides: Any) -> dict:
    """创建学习记录并返回响应 JSON。"""
    payload: dict[str, Any] = {
        "content": "Transformer Attention",
        "duration_minutes": 90,
        "study_date": TODAY_STR,
    }
    payload.update(overrides)
    resp = client.post("/api/v1/records", json=payload, headers=headers)
    return resp.json()


def get_mastery(user_id: int, kp: str) -> KnowledgeMastery | None:
    """DB 直查某用户某知识点的掌握度行。"""
    with SessionLocal() as db:
        return db.scalar(
            select(KnowledgeMastery).where(
                KnowledgeMastery.user_id == user_id,
                KnowledgeMastery.knowledge_point == kp,
            )
        )


def get_task_actual(user_id: int, task_id: int) -> int | None:
    """DB 直查任务 actual_minutes。"""
    from app.models.task import Task

    with SessionLocal() as db:
        task = db.scalar(
            select(Task).where(
                Task.id == task_id, Task.user_id == user_id
            )
        )
        return task.actual_minutes if task else None


def mastery_score(user_id: int, kp: str) -> float | None:
    """DB 直查掌握度分数。"""
    row = get_mastery(user_id, kp)
    return row.mastery_score if row else None


def api(method: str, url: str, headers: dict[str, str], **kw: Any) -> dict:
    """发起 API 请求并返回响应 JSON。"""
    resp = client.request(method, url, headers=headers, **kw)
    return resp.json()


def main() -> None:
    """执行全部验收用例并汇总。"""
    print(f"== P6 验收开始（北京今天 = {TODAY_STR}）==")

    # ------------------------------------------------------------------
    # 5.1 核心链路（验收①② + 乱序补记 + null 自评）
    # ------------------------------------------------------------------
    print("-- 5.1 掌握度核心链路 --")
    user_a, headers_a = register_and_login("a")
    uid_a = get_user_id(user_a)

    check("5.1-0 前置：库中无 Transformer 行", mastery_score(uid_a, "Transformer") is None)

    resp = create_record(
        headers_a, mastery_level=60, knowledge_points=["Transformer"]
    )
    check("5.1-1a 验收①：创建记录 code=0", resp["code"] == 0, str(resp))
    record_id_a1 = resp["data"]["id"]
    check(
        "5.1-1b 验收①：返回全量字段（含 id/created_at）",
        record_id_a1 > 0 and resp["data"]["created_at"] is not None,
    )
    row = get_mastery(uid_a, "Transformer")
    check(
        "5.1-1c 验收①：Transformer 自动 INSERT，score=18，source=record",
        row is not None
        and row.mastery_score == 18
        and row.source == MasterySource.RECORD,
        f"实际 {row.mastery_score if row else None}/{row.source if row else None}",
    )

    resp = create_record(
        headers_a, mastery_level=80, knowledge_points=["Transformer"]
    )
    check(
        "5.1-2a 验收②：追加自评 80 记录 code=0",
        resp["code"] == 0,
        str(resp),
    )
    score = mastery_score(uid_a, "Transformer")
    check(
        "5.1-2b 验收②：掌握度 36.6（18×0.7+80×0.3），上升且 ≤100",
        score is not None and abs(score - 36.6) < 0.01,
        f"实际 {score}",
    )

    # 乱序补记：先记 T-9 自评 80（24），再补记 T-48 自评 100 → 重放 45。
    kp_late = "乱序补记点"
    create_record(
        headers_a,
        mastery_level=80,
        knowledge_points=[kp_late],
        study_date=(TODAY - timedelta(days=9)).date().isoformat(),
    )
    score_1 = mastery_score(uid_a, kp_late)
    check("5.1-3a 乱序补记：首条（T-9）自评 80 → 24", score_1 is not None and abs(score_1 - 24) < 0.01, f"实际 {score_1}")
    create_record(
        headers_a,
        mastery_level=100,
        knowledge_points=[kp_late],
        study_date=(TODAY - timedelta(days=48)).date().isoformat(),
    )
    score_2 = mastery_score(uid_a, kp_late)
    check(
        "5.1-3b 乱序补记：补记 T-48 自评 100 → 重放 45（≠46.8 增量错误值）",
        score_2 is not None and abs(score_2 - 45) < 0.01,
        f"实际 {score_2}",
    )

    # mastery_level=null：创建成功且不触发掌握度变化。
    before = mastery_score(uid_a, "Transformer")
    resp = create_record(
        headers_a, mastery_level=None, knowledge_points=["Transformer"]
    )
    after = mastery_score(uid_a, "Transformer")
    check(
        "5.1-4 自评 null 记录创建成功且不触发掌握度变化",
        resp["code"] == 0 and before == after,
        f"code={resp['code']} before={before} after={after}",
    )

    # ------------------------------------------------------------------
    # 5.2 算法边界（错题 / 衰减 / 幂等 / 上限 / recalculate_all）
    # ------------------------------------------------------------------
    print("-- 5.2 掌握度算法边界 --")
    user_g, headers_g = register_and_login("g")
    uid_g = get_user_id(user_g)

    # 错题扣分：自评 60 → 18；2 道错题 → 12；共 5 道 → 3；共 20 道 → 0。
    kp_mis = "错题扣分点"
    create_record(
        headers_g, mastery_level=60, knowledge_points=[kp_mis]
    )
    with SessionLocal() as db:
        for _ in range(20):
            db.add(
                Mistake(
                    user_id=uid_g,
                    knowledge_point=kp_mis,
                    question=f"错题{_}",
                )
            )
        db.commit()
    # DB 直插错题后手动触发重放（经一次等价记录操作）。
    create_record(
        headers_g, mastery_level=60, knowledge_points=[kp_mis]
    )
    # 两条自评 60 → 18×0.7+60×0.3 = 30.6；20 道错题 → 下限 0。
    score_m = mastery_score(uid_g, kp_mis)
    check(
        "5.2-1 错题扣分：两条自评 60 聚合 30.6，20 道错题 → 下限 0",
        score_m is not None and score_m == 0,
        f"实际 {score_m}",
    )
    # 单独验证 -3/题：删 18 道错题剩 2 道 → 39.42-6 = 33.42。
    with SessionLocal() as db:
        ids = db.scalars(
            select(Mistake.id).where(
                Mistake.user_id == uid_g,
                Mistake.knowledge_point == kp_mis,
            )
        ).all()
        for mid in ids[:18]:
            obj = db.get(Mistake, mid)
            if obj is not None:
                db.delete(obj)
        db.commit()
    create_record(
        headers_g, mastery_level=60, knowledge_points=[kp_mis]
    )
    # 三条自评 60 → 30.6×0.7+60×0.3 = 39.42；2 道错题 → 33.42。
    score_m2 = mastery_score(uid_g, kp_mis)
    check(
        "5.2-2 错题扣分：三条自评 60 聚合 39.42，2 道错题 → 33.42",
        score_m2 is not None and abs(score_m2 - 33.42) < 0.01,
        f"实际 {score_m2}",
    )

    # 衰减边界：35→不扣 / 37→扣 2 / 44→扣 4 / 衰减前 3 分距 100 天→0。
    user_e, headers_e = register_and_login("e")
    uid_e = get_user_id(user_e)
    for days_ago, expected, label in (
        (35, 27.0, "35 天 → 不扣"),
        (37, 25.0, "37 天 → 扣 2"),
        (44, 23.0, "44 天 → 扣 4"),
        (100, 0.0, "3 分距 100 天 → 0"),
    ):
        kp = f"衰减{days_ago}"
        level = 10 if days_ago == 100 else 90
        create_record(
            headers_e,
            mastery_level=level,
            knowledge_points=[kp],
            study_date=(TODAY - timedelta(days=days_ago)).date().isoformat(),
        )
        got = mastery_score(uid_e, kp)
        check(
            f"5.2-3 衰减边界：{label}（期望 {expected}）",
            got is not None and abs(got - expected) < 0.01,
            f"实际 {got}",
        )

    # 40 天幂等专项：衰减基准 = study_date，两次 recalculate_all 必须一致。
    user_f, headers_f = register_and_login("f")
    uid_f = get_user_id(user_f)
    kp_p40 = "幂等40天点"
    create_record(
        headers_f,
        mastery_level=90,
        knowledge_points=[kp_p40],
        study_date=(TODAY - timedelta(days=40)).date().isoformat(),
    )
    got_first = mastery_score(uid_f, kp_p40)
    check(
        "5.2-4a 40 天场景：首次重放 27-2=25",
        got_first is not None and abs(got_first - 25) < 0.01,
        f"实际 {got_first}",
    )
    with SessionLocal() as db:
        row40 = db.scalar(
            select(KnowledgeMastery).where(
                KnowledgeMastery.user_id == uid_f,
                KnowledgeMastery.knowledge_point == kp_p40,
            )
        )
        assert row40 is not None
        # 模拟「上次学习后一直未写库」：把 updated_at 拨回 40 天前。
        row40.updated_at = utc_now() - timedelta(days=40)
        db.commit()
    with SessionLocal() as db:
        recalculate_all(db, uid_f)
    got_1 = mastery_score(uid_f, kp_p40)
    with SessionLocal() as db:
        recalculate_all(db, uid_f)
    got_2 = mastery_score(uid_f, kp_p40)
    check(
        "5.2-4b 40 天幂等：两次 recalculate_all 分数完全相等（均扣 2）",
        got_1 is not None and got_1 == got_2 and abs(got_1 - 25) < 0.01,
        f"第一次 {got_1} / 第二次 {got_2}",
    )

    # 无学习记录知识点不衰减 + 种子保护（recalculate_all 范围外保持原值）。
    user_h, _ = register_and_login("h")
    uid_h = get_user_id(user_h)
    with SessionLocal() as db:
        db.add(
            KnowledgeMastery(
                user_id=uid_h,
                knowledge_point="种子自评点",
                mastery_score=90,
                source=MasterySource.SELF_REPORT,
                updated_at=utc_now() - timedelta(days=90),
            )
        )
        db.add(
            KnowledgeMastery(
                user_id=uid_h,
                knowledge_point="种子待学点",
                mastery_score=0,
                source=MasterySource.GOAL_BREAKDOWN,
                updated_at=utc_now() - timedelta(days=90),
            )
        )
        db.commit()
        recalculate_all(db, uid_h)
    row_self = get_mastery(uid_h, "种子自评点")
    row_goal = get_mastery(uid_h, "种子待学点")
    check(
        "5.2-5a 种子保护：self_report 90 分保持且 source 不被改写",
        row_self is not None
        and row_self.mastery_score == 90
        and row_self.source == MasterySource.SELF_REPORT,
        f"实际 {row_self.mastery_score if row_self else None}/{row_self.source if row_self else None}",
    )
    check(
        "5.2-5b 种子保护：goal_breakdown 0 分保持（90 天未更新也不衰减）",
        row_goal is not None
        and row_goal.mastery_score == 0
        and row_goal.source == MasterySource.GOAL_BREAKDOWN,
        f"实际 {row_goal.mastery_score if row_goal else None}/{row_goal.source if row_goal else None}",
    )

    # 重放上限：8 条自评 100 → 100×(1-0.7^8) = 94.24，≤100 且单调。
    # （study_date 取近 7 天：避免触发时间衰减，纯验证 EMA 上限。）
    user_i, headers_i = register_and_login("i")
    uid_i = get_user_id(user_i)
    kp_cap = "重放上限点"
    for idx in range(8):
        create_record(
            headers_i,
            mastery_level=100,
            knowledge_points=[kp_cap],
            study_date=(TODAY - timedelta(days=idx)).date().isoformat(),
        )
    got_cap = mastery_score(uid_i, kp_cap)
    expected_cap = round(100 * (1 - 0.7**8), 2)
    check(
        f"5.2-6 重放上限：8 条自评 100 → {expected_cap} ≤ 100",
        got_cap is not None
        and got_cap <= 100
        and abs(got_cap - expected_cap) < 0.01,
        f"实际 {got_cap}",
    )

    # recalculate_all 与单点重放一致（含乱序补记后执行）+ 幂等。
    with SessionLocal() as db:
        recalculate_all(db, uid_a)
    score_r = mastery_score(uid_a, kp_late)
    score_t = mastery_score(uid_a, "Transformer")
    check(
        "5.2-7a recalculate_all 与单点一致：乱序补记点仍 45",
        score_r is not None and abs(score_r - 45) < 0.01,
        f"实际 {score_r}",
    )
    check(
        "5.2-7b recalculate_all 与单点一致：Transformer 仍 36.6",
        score_t is not None and abs(score_t - 36.6) < 0.01,
        f"实际 {score_t}",
    )
    with SessionLocal() as db:
        recalculate_all(db, uid_a)
    score_r2 = mastery_score(uid_a, kp_late)
    score_t2 = mastery_score(uid_a, "Transformer")
    check(
        "5.2-7c recalculate_all 幂等：连续两次结果一致",
        score_r == score_r2 and score_t == score_t2,
        f"{score_r}/{score_r2} {score_t}/{score_t2}",
    )

    # ------------------------------------------------------------------
    # 5.3 参数校验 / 越权 / PUT 语义 / 任务回填
    # ------------------------------------------------------------------
    print("-- 5.3 CRUD 校验与任务回填 --")
    user_c, headers_c = register_and_login("c")
    uid_c = get_user_id(user_c)

    # 参数校验 422。
    cases_422 = [
        ("时长 0", {"duration_minutes": 0}),
        ("时长 1500", {"duration_minutes": 1500}),
        ("自评 120", {"mastery_level": 120}),
        ("知识点空串", {"knowledge_points": [""]}),
        ("content 空串", {"content": ""}),
        (
            "携带 user_id",
            {"user_id": 1},
        ),
    ]
    for label, overrides in cases_422:
        resp = create_record(headers_c, **overrides)
        check(
            f"5.3-1 参数校验：{label} → 422/1001",
            resp["code"] == 1001,
            str(resp),
        )
    resp = create_record(
        headers_c, study_date=(TODAY + timedelta(days=1)).date().isoformat()
    )
    check(
        "5.3-2 学习日期超前 → 422 且中文提示",
        resp["code"] == 1001 and "学习日期不能晚于今天" in resp["message"],
        str(resp),
    )
    resp = api(
        "GET",
        f"/api/v1/records?start_date={TODAY_STR}&end_date="
        f"{(TODAY - timedelta(days=1)).date().isoformat()}",
        headers_c,
    )
    check(
        "5.3-3 列表区间倒置 → 422 且中文提示",
        resp["code"] == 1001 and "开始日期不能晚于结束日期" in resp["message"],
        str(resp),
    )
    resp = api("GET", "/api/v1/records/timeline?days=0", headers_c)
    check("5.3-4 timeline days=0 → 422", resp["code"] == 1001, str(resp))
    resp = api("GET", "/api/v1/records/timeline?days=400", headers_c)
    check("5.3-5 timeline days=400 → 422", resp["code"] == 1001, str(resp))

    # 越权 404/1005（B 为资源属主，C 为攻击者）。
    user_b, headers_b = register_and_login("b")
    uid_b = get_user_id(user_b)
    resp = api(
        "POST",
        "/api/v1/tasks",
        headers_b,
        json={"title": "B的任务"},
    )
    task_b = resp["data"]["id"]
    # courses API 仅开放 GET（P5 契约），B 的课程走 DB 直插造数。
    with SessionLocal() as db:
        course_b_obj = Course(user_id=uid_b, name="B的课程")
        db.add(course_b_obj)
        db.commit()
        db.refresh(course_b_obj)
        course_b = course_b_obj.id
    resp = create_record(headers_b, task_id=task_b, course_id=course_b)
    record_b = resp["data"]["id"]

    resp = create_record(headers_c, task_id=task_b)
    check(
        "5.3-6 越权：他人 task_id → 404/1005 中文提示",
        resp["code"] == 1005 and "关联的学习任务不存在" in resp["message"],
        str(resp),
    )
    resp = create_record(headers_c, course_id=course_b)
    check(
        "5.3-7 越权：他人 course_id → 404/1005 中文提示",
        resp["code"] == 1005 and "关联的课程不存在" in resp["message"],
        str(resp),
    )
    for method in ("GET", "PUT", "DELETE"):
        resp = api(
            method,
            f"/api/v1/records/{record_b}",
            headers_c,
            json={},
        )
        check(
            f"5.3-8 越权：{method} 他人记录 → 404/1005",
            resp["code"] == 1005,
            str(resp),
        )
    resp = api("GET", "/api/v1/records?page=1&page_size=100", headers_c)
    owner_ids = {item["user_id"] for item in resp["data"]["items"]}
    check(
        "5.3-9 列表隔离：C 查不到 B 的记录",
        uid_b not in owner_ids,
        str(owner_ids),
    )

    # PUT 部分更新：仅 duration_minutes → 其他不变。
    resp = create_record(
        headers_c,
        content="部分更新原内容",
        duration_minutes=30,
        mastery_level=80,
        knowledge_points=["RC_PART"],
        achievement="原成果",
    )
    rid_part = resp["data"]["id"]
    resp = api(
        "PUT",
        f"/api/v1/records/{rid_part}",
        headers_c,
        json={"duration_minutes": 60},
    )
    data = resp["data"]
    check(
        "5.3-10 PUT 部分更新：仅时长变化，其余字段保持",
        resp["code"] == 0
        and data["duration_minutes"] == 60
        and data["content"] == "部分更新原内容"
        and data["mastery_level"] == 80
        and data["knowledge_points"] == ["RC_PART"]
        and data["achievement"] == "原成果",
        str(data),
    )

    # 知识点 [A]→[B] 并集重放：A 回落 0、B 纳入 24。
    resp = create_record(
        headers_c, mastery_level=80, knowledge_points=["RC_KPA"]
    )
    rid_ab = resp["data"]["id"]
    check(
        "5.3-11a 知识点迁移前置：A = 24",
        abs((mastery_score(uid_c, "RC_KPA") or -1) - 24) < 0.01,
    )
    api(
        "PUT",
        f"/api/v1/records/{rid_ab}",
        headers_c,
        json={"knowledge_points": ["RC_KPB"]},
    )
    check(
        "5.3-11b 知识点 [A]→[B]：A 按剩余记录回落 0",
        mastery_score(uid_c, "RC_KPA") == 0,
        f"实际 {mastery_score(uid_c, 'RC_KPA')}",
    )
    check(
        "5.3-11c 知识点 [A]→[B]：B 纳入自评 80 → 24",
        abs((mastery_score(uid_c, "RC_KPB") or -1) - 24) < 0.01,
        f"实际 {mastery_score(uid_c, 'RC_KPB')}",
    )

    # mastery_level 80→null：退出聚合，分数回落。
    resp = create_record(
        headers_c, mastery_level=80, knowledge_points=["RC_KPC"]
    )
    rid_null = resp["data"]["id"]
    resp = api(
        "PUT",
        f"/api/v1/records/{rid_null}",
        headers_c,
        json={"mastery_level": None},
    )
    check(
        "5.3-12a mastery 80→null：更新成功且值为 null",
        resp["code"] == 0 and resp["data"]["mastery_level"] is None,
        str(resp),
    )
    check(
        "5.3-12b mastery 80→null：知识点退出聚合回落 0",
        mastery_score(uid_c, "RC_KPC") == 0,
        f"实际 {mastery_score(uid_c, 'RC_KPC')}",
    )

    # 任务回填全链路。
    resp = api("POST", "/api/v1/tasks", headers_c, json={"title": "回填任务"})
    task_fill = resp["data"]["id"]
    resp = api("POST", "/api/v1/tasks", headers_c, json={"title": "手动任务"})
    task_manual = resp["data"]["id"]
    api(
        "PUT",
        f"/api/v1/tasks/{task_manual}",
        headers_c,
        json={"actual_minutes": 60},
    )
    check(
        "5.3-13a 手动任务前置：actual_minutes=60",
        get_task_actual(uid_c, task_manual) == 60,
    )

    r1 = create_record(headers_c, task_id=task_fill, duration_minutes=90)
    check(
        "5.3-13b 回填：90 分钟记录 → actual=90",
        get_task_actual(uid_c, task_fill) == 90,
        f"实际 {get_task_actual(uid_c, task_fill)}",
    )
    r2 = create_record(headers_c, task_id=task_fill, duration_minutes=30)
    check(
        "5.3-13c 回填：+30 → 120",
        get_task_actual(uid_c, task_fill) == 120,
        f"实际 {get_task_actual(uid_c, task_fill)}",
    )
    api(
        "PUT",
        f"/api/v1/records/{r2['data']['id']}",
        headers_c,
        json={"duration_minutes": 50},
    )
    check(
        "5.3-13d 回填：30 改 50 → 140",
        get_task_actual(uid_c, task_fill) == 140,
        f"实际 {get_task_actual(uid_c, task_fill)}",
    )
    api("DELETE", f"/api/v1/records/{r2['data']['id']}", headers_c)
    check(
        "5.3-13e 回填：删除 50 那条 → 90",
        get_task_actual(uid_c, task_fill) == 90,
        f"实际 {get_task_actual(uid_c, task_fill)}",
    )
    api("DELETE", f"/api/v1/records/{r1['data']['id']}", headers_c)
    actual_after_clear = get_task_actual(uid_c, task_fill)
    check(
        "5.3-13f 回填：删空 → NULL（未知，非 0）",
        actual_after_clear is None,
        f"实际 {actual_after_clear}",
    )
    r3 = create_record(headers_c, task_id=task_fill, duration_minutes=45)
    check(
        "5.3-13g 回填：删空再记 45 → 恢复 45",
        get_task_actual(uid_c, task_fill) == 45,
        f"实际 {get_task_actual(uid_c, task_fill)}",
    )
    api(
        "PUT",
        f"/api/v1/records/{r3['data']['id']}",
        headers_c,
        json={"task_id": None},
    )
    check(
        "5.3-13h 回填：解除关联 → NULL",
        get_task_actual(uid_c, task_fill) is None,
        f"实际 {get_task_actual(uid_c, task_fill)}",
    )
    check(
        "5.3-13i 未触达任务手动值 60 全程保持",
        get_task_actual(uid_c, task_manual) == 60,
        f"实际 {get_task_actual(uid_c, task_manual)}",
    )

    # ------------------------------------------------------------------
    # 5.4 timeline / stats / 回归
    # ------------------------------------------------------------------
    print("-- 5.4 timeline / stats / 回归 --")
    user_t, headers_t = register_and_login("t")
    create_record(headers_t, duration_minutes=60)
    create_record(headers_t, duration_minutes=30)
    create_record(
        headers_t,
        duration_minutes=100,
        study_date=(TODAY - timedelta(days=5)).date().isoformat(),
    )

    resp = api("GET", "/api/v1/records/timeline?days=30", headers_t)
    data = resp["data"]
    items = data["items"]
    by_date = {it["date"]: it["minutes"] for it in items}
    check(
        "5.4-1a 验收③：timeline 30 条且升序",
        len(items) == 30
        and items == sorted(items, key=lambda x: x["date"]),
        f"实际 {len(items)} 条",
    )
    check(
        "5.4-1b 验收③：首条 29 天前、末条今天",
        items[0]["date"] == (TODAY - timedelta(days=29)).date().isoformat()
        and items[-1]["date"] == TODAY_STR,
        f"首 {items[0]['date']} 末 {items[-1]['date']}",
    )
    check(
        "5.4-1c 验收③：无记录天补 0（today-6）",
        by_date.get((TODAY - timedelta(days=6)).date().isoformat()) == 0,
        str(by_date),
    )
    check(
        "5.4-1d 同日合计：today = 60+30 = 90",
        by_date.get(TODAY_STR) == 90,
        f"实际 {by_date.get(TODAY_STR)}",
    )
    check(
        "5.4-1e today-5 = 100",
        by_date.get((TODAY - timedelta(days=5)).date().isoformat()) == 100,
        str(by_date),
    )

    # 无记录用户 → 全 0 序列。
    user_t2, headers_t2 = register_and_login("t2")
    resp = api("GET", "/api/v1/records/timeline?days=7", headers_t2)
    check(
        "5.4-2 无记录用户：7 条全 0 不报错",
        resp["code"] == 0
        and len(resp["data"]["items"]) == 7
        and all(it["minutes"] == 0 for it in resp["data"]["items"]),
        str(resp),
    )

    # stats：weekly 上周日不计入 + streak 三场景 + total_count。
    monday = TODAY.date() - timedelta(days=TODAY.weekday())
    user_d1, headers_d1 = register_and_login("d1")
    create_record(headers_d1, duration_minutes=60, study_date=monday.isoformat())
    create_record(headers_d1, duration_minutes=60, study_date=TODAY_STR)
    create_record(
        headers_d1,
        duration_minutes=100,
        study_date=(monday - timedelta(days=1)).isoformat(),
    )
    resp = api("GET", "/api/v1/records/stats", headers_d1)
    stats = resp["data"]
    check(
        "5.4-3 weekly：本周一 60 + 今天 60，上周日 100 不计入 → 120",
        stats["weekly_minutes"] == 120,
        str(stats),
    )

    _, headers_d2 = register_and_login("d2")
    create_record(headers_d2, duration_minutes=30, study_date=TODAY_STR)
    create_record(
        headers_d2,
        duration_minutes=30,
        study_date=(TODAY - timedelta(days=1)).date().isoformat(),
    )
    resp = api("GET", "/api/v1/records/stats", headers_d2)
    check(
        "5.4-4a streak：今天+昨天有、前天无 → 2",
        resp["data"]["streak_days"] == 2,
        str(resp["data"]),
    )

    _, headers_d3 = register_and_login("d3")
    create_record(
        headers_d3,
        duration_minutes=30,
        study_date=(TODAY - timedelta(days=1)).date().isoformat(),
    )
    create_record(
        headers_d3,
        duration_minutes=30,
        study_date=(TODAY - timedelta(days=2)).date().isoformat(),
    )
    resp = api("GET", "/api/v1/records/stats", headers_d3)
    check(
        "5.4-4b streak：今天无（从昨天起算）、昨天+前天有 → 2",
        resp["data"]["streak_days"] == 2,
        str(resp["data"]),
    )

    _, headers_d4 = register_and_login("d4")
    create_record(
        headers_d4,
        duration_minutes=30,
        study_date=(TODAY - timedelta(days=2)).date().isoformat(),
    )
    resp = api("GET", "/api/v1/records/stats", headers_d4)
    check(
        "5.4-4c streak：仅前天有 → 0",
        resp["data"]["streak_days"] == 0,
        str(resp["data"]),
    )
    check(
        "5.4-5 total_count：该用户 1 条",
        resp["data"]["total_count"] == 1,
        str(resp["data"]),
    )

    # 回归：既有分页调用 + 六参数同传 + 未登录。
    resp = api("GET", "/api/v1/records?page=1&page_size=10", headers_a)
    check(
        "5.4-6a 回归：既有仅分页调用行为不变",
        resp["code"] == 0 and resp["data"]["page"] == 1,
        str(resp),
    )
    url = (
        f"/api/v1/records?page=1&page_size=10&start_date="
        f"{(TODAY - timedelta(days=60)).date().isoformat()}"
        f"&end_date={TODAY_STR}&course_id=1&knowledge_point=Transformer"
    )
    resp = api("GET", url, headers_a)
    check(
        "5.4-6b 回归：六参数同传不 422",
        resp["code"] == 0,
        str(resp),
    )
    for method, urlx in (
        ("GET", "/api/v1/records"),
        ("POST", "/api/v1/records"),
        ("GET", "/api/v1/records/timeline"),
        ("GET", "/api/v1/records/stats"),
        ("GET", "/api/v1/records/1"),
        ("PUT", "/api/v1/records/1"),
        ("DELETE", "/api/v1/records/1"),
    ):
        resp = api(method, urlx, {}, json={"content": "x"})
        check(
            f"5.4-7 未登录 {method} {urlx} → 401/1003",
            resp["code"] == 1003,
            str(resp),
        )

    # ------------------------------------------------------------------
    print(f"\n== 汇总：PASSED {len(PASSED)} / FAILED {len(FAILED)} ==")
    if FAILED:
        print("失败用例：")
        for name in FAILED:
            print(f"  - {name}")
        sys.exit(1)
    print("全部 PASSED")


if __name__ == "__main__":
    main()