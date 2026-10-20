"""P7 学习分析引擎与 Dashboard 验收脚本（ASGI 直调，G1–G11）。

运行：cd backend && .venv/Scripts/python scripts/verify_p7_dashboard.py

验证方式：``fastapi.testclient.TestClient`` 进程内直调 app 对象
（不起 uvicorn、不发真实网络请求，规避沙箱 IPv4 回环拦截）。

与 P6 脚本的关键差异：验收基线基于 demo 种子——建表后调用
``init_db()``（幂等入口）种入演示数据，再注册独立测试用户承载
空态（G2）与构造场景（G4/G5/G9）用例。

日期敏感期望全部按「动态期望口径」测试内推算（spec 附录）：
- overdue_task_count / streak_days / 趋势序列：先查库推算期望再断言；
- 严格递减 / slope / 衰减 37 天：测试内自行构造数据，不依赖种子埋点；
- 静态值硬编码：total_minutes=3175、total_record_count=30、
  avg_session_minutes≈105.8、task_completion_rate=45.0、avg_mastery=57.0。
"""

from __future__ import annotations

import os
import sys
import time
import uuid
from collections import Counter
from datetime import date, timedelta
from pathlib import Path
from typing import Any

_SCRIPTS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(_SCRIPTS_DIR.parent))
sys.path.insert(0, str(_SCRIPTS_DIR))

_TMP_DB_DIR = _SCRIPTS_DIR.parent / "tmp_verify"
_TMP_DB_DIR.mkdir(exist_ok=True)
_TMP_DB = _TMP_DB_DIR / "p7_dashboard.db"
if _TMP_DB.exists():
    _TMP_DB.unlink()
os.environ["DATABASE_URL"] = f"sqlite:///{_TMP_DB.as_posix()}"

import _sandbox_patch  # noqa: F401,E402  （IPv6 socketpair 补丁，须先于 TestClient）

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import func, select  # noqa: E402
from unittest.mock import patch  # noqa: E402

from app.db.init_db import init_db  # noqa: E402
from app.db.session import SessionLocal  # noqa: E402
from app.main import app  # noqa: E402
from app.models.base import utc_now  # noqa: E402
from app.models.enums import MasterySource, TaskStatus  # noqa: E402
from app.models.mastery import KnowledgeMastery  # noqa: E402
from app.models.record import LearningRecord  # noqa: E402
from app.models.task import Task  # noqa: E402
from app.models.user import User  # noqa: E402
from app.services.task import TZ_BEIJING  # noqa: E402

import app.services.mastery as mastery_module  # noqa: E402

init_db()

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


def bj_today() -> date:
    """北京今天（与接口统计口径一致）。"""
    return utc_now().astimezone(TZ_BEIJING).date()


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


def login_demo() -> dict[str, str]:
    """demo 用户登录，返回 Authorization 头。"""
    resp = client.post(
        "/api/v1/auth/login",
        json={"username": "demo", "password": "123456"},
    )
    assert resp.status_code == 200 and resp.json()["code"] == 0, (
        f"demo 登录失败: {resp.text}"
    )
    return {"Authorization": f"Bearer {resp.json()['data']['access_token']}"}


def get_user_id(username: str) -> int:
    """按用户名查用户 id。"""
    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.username == username))
        assert user is not None
        return user.id


def insert_record(
    user_id: int,
    study_date: date,
    minutes: int,
    kps: list[str] | None = None,
    mastery_level: int | None = None,
) -> None:
    """直插学习记录（不经 API，不触发掌握度重放）。"""
    with SessionLocal() as db:
        db.add(
            LearningRecord(
                user_id=user_id,
                task_id=None,
                course_id=None,
                content="P7 构造数据",
                duration_minutes=minutes,
                achievement=None,
                problems=None,
                knowledge_points=kps,
                mastery_level=mastery_level,
                study_date=study_date,
            )
        )
        db.commit()


def insert_mastery(
    user_id: int, kp: str, score: float, source: MasterySource
) -> None:
    """直插掌握度行。"""
    with SessionLocal() as db:
        db.add(
            KnowledgeMastery(
                user_id=user_id,
                knowledge_point=kp,
                mastery_score=score,
                source=source,
                updated_at=utc_now(),
            )
        )
        db.commit()


def mastery_map(user_id: int) -> dict[str, float]:
    """查询该用户全部掌握度行（不做排除过滤）。"""
    with SessionLocal() as db:
        rows = db.execute(
            select(
                KnowledgeMastery.knowledge_point,
                KnowledgeMastery.mastery_score,
            ).where(KnowledgeMastery.user_id == user_id)
        ).all()
    return {kp: float(score) for kp, score in rows}


def expected_series(user_id: int, days: int) -> list[tuple[date, int]]:
    """测试内推算期望趋势序列（SUM GROUP BY 补零，北京自然日）。"""
    today = bj_today()
    start = today - timedelta(days=days - 1)
    with SessionLocal() as db:
        rows = db.execute(
            select(
                LearningRecord.study_date,
                func.sum(LearningRecord.duration_minutes),
            )
            .where(
                LearningRecord.user_id == user_id,
                LearningRecord.study_date.between(start, today),
            )
            .group_by(LearningRecord.study_date)
        ).all()
    found = {d: int(m or 0) for d, m in rows}
    return [
        (start + timedelta(days=i), found.get(start + timedelta(days=i), 0))
        for i in range(days)
    ]


def expected_overdue(user_id: int) -> int:
    """测试内推算期望逾期数（与接口同口径）。"""
    now = utc_now()
    with SessionLocal() as db:
        return int(
            db.scalar(
                select(func.count())
                .select_from(Task)
                .where(
                    Task.user_id == user_id,
                    Task.deadline.is_not(None),
                    Task.deadline < now,
                    Task.status != TaskStatus.DONE,
                )
            )
            or 0
        )


def expected_streak(user_id: int) -> int:
    """测试内推算期望连续学习天数（anchor 今天/昨天不清零）。"""
    today = bj_today()
    with SessionLocal() as db:
        dates = set(
            db.scalars(
                select(LearningRecord.study_date)
                .where(LearningRecord.user_id == user_id)
                .distinct()
            )
        )
    anchor = today if today in dates else today - timedelta(days=1)
    n = 0
    while anchor in dates:
        n += 1
        anchor -= timedelta(days=1)
    return n


def recent_counts(user_id: int) -> Counter[str]:
    """测试内推算近 30 天知识点出现频次（Counter 同口径）。"""
    today = bj_today()
    start = today - timedelta(days=29)
    with SessionLocal() as db:
        rows = db.scalars(
            select(LearningRecord.knowledge_points).where(
                LearningRecord.user_id == user_id,
                LearningRecord.study_date.between(start, today),
            )
        )
    c: Counter[str] = Counter()
    for kps in rows:
        for kp in kps or []:
            c[kp] += 1
    return c


def lsq_slope(values: list[int]) -> float:
    """最小二乘斜率（测试内验算，与 analytics/trend.py 同公式）。"""
    n = len(values)
    if n <= 1:
        return 0.0
    x_mean = (n - 1) / 2
    y_mean = sum(values) / n
    numerator = sum(
        (i - x_mean) * (y - y_mean) for i, y in enumerate(values)
    )
    denominator = sum((i - x_mean) ** 2 for i in range(n))
    return round(numerator / denominator, 1)


def get_json(path: str, headers: dict[str, str]) -> dict[str, Any]:
    """GET 请求并断言 200 + code=0，返回 data。"""
    resp = client.get(path, headers=headers)
    assert resp.status_code == 200, f"{path} -> {resp.status_code}: {resp.text}"
    body = resp.json()
    assert body["code"] == 0, f"{path} code={body['code']}: {body['message']}"
    return body["data"]


ENDPOINTS = [
    "/api/v1/dashboard/overview",
    "/api/v1/dashboard/trend",
    "/api/v1/dashboard/mastery",
    "/api/v1/dashboard/weakness",
    "/api/v1/dashboard/advice",
]

print("========== G1 种子指标（demo，静态硬编码 + 动态推算） ==========")
demo_headers = login_demo()
demo_id = get_user_id("demo")

overview = get_json(ENDPOINTS[0], demo_headers)
check("G1 total_minutes=3175", overview["total_minutes"] == 3175,
      f"got {overview['total_minutes']}")
check("G1 total_record_count=30", overview["total_record_count"] == 30,
      f"got {overview['total_record_count']}")
check(
    "G1 avg_session_minutes≈105.8",
    abs(overview["avg_session_minutes"] - 105.8) < 0.05,
    f"got {overview['avg_session_minutes']}",
)
check(
    "G1 task_completion_rate=45.0",
    abs(overview["task_completion_rate"] - 45.0) < 0.05,
    f"got {overview['task_completion_rate']}",
)
check(
    "G1 avg_mastery=57.0",
    abs(overview["avg_mastery"] - 57.0) < 0.05,
    f"got {overview['avg_mastery']}",
)
exp_overdue = expected_overdue(demo_id)
check(
    "G1 overdue_task_count=动态推算值",
    overview["overdue_task_count"] == exp_overdue,
    f"got {overview['overdue_task_count']}, expect {exp_overdue}",
)
exp_streak = expected_streak(demo_id)
check(
    "G1 streak_days=动态推算值",
    overview["streak_days"] == exp_streak,
    f"got {overview['streak_days']}, expect {exp_streak}",
)

print("========== G9①② 衰减检查（demo 首访标记 + 同日不重复） ==========")
today_bj = bj_today()
check(
    "G9① 首访后进程内字典标记=北京今天",
    mastery_module._daily_decay_checked.get(demo_id) == today_bj,
    f"got {mastery_module._daily_decay_checked.get(demo_id)}",
)
seed_mastery = mastery_map(demo_id)
seed_expect = {
    "深度学习": 30.0, "概率论": 40.0, "动态规划": 45.0,
    "线性代数": 50.0, "英语阅读": 50.0, "SQL": 55.0, "机器学习": 60.0,
    "计算机网络": 70.0, "数据结构": 80.0, "Python": 90.0,
}
check(
    "G9① 种子掌握度 10 条原样（30/40/45 不被改写）",
    seed_mastery == seed_expect,
    f"got {seed_mastery}",
)

original_replay = mastery_module.replay_knowledge_points
replay_calls: list[tuple[int, set[str]]] = []


def counting_replay(db: Any, user_id: int, kps: Any) -> None:
    replay_calls.append((user_id, set(kps)))
    return original_replay(db, user_id, kps)


with patch.object(
    mastery_module, "replay_knowledge_points", side_effect=counting_replay
):
    overview_again = get_json(ENDPOINTS[0], demo_headers)
check(
    "G9② 同日再访不触发重放（replay 调用次数 0）",
    len(replay_calls) == 0,
    f"calls={replay_calls}",
)
check(
    "G9② 同日再访字典标记不变",
    mastery_module._daily_decay_checked.get(demo_id) == today_bj,
    f"got {mastery_module._daily_decay_checked.get(demo_id)}",
)
check(
    "G9② 再访 overview 正常返回",
    overview_again["total_minutes"] == 3175,
    f"got {overview_again['total_minutes']}",
)

print("========== G3 趋势结构（30/90/1/0/366） ==========")
trend30 = get_json(f"{ENDPOINTS[1]}?days=30", demo_headers)
exp30 = expected_series(demo_id, 30)
got30 = [(item["date"], item["minutes"]) for item in trend30["items"]]
check(
    "G3 days=30 恰 30 条且与动态推算序列逐日相等",
    len(got30) == 30 and got30 == [
        (d.isoformat(), m) for d, m in exp30
    ],
    f"len={len(got30)}",
)
check(
    "G3 days=30 升序且末条为北京今天",
    trend30["items"][-1]["date"] == today_bj.isoformat()
    and trend30["items"][0]["date"]
    == (today_bj - timedelta(days=29)).isoformat(),
    f"first={trend30['items'][0]['date']} last={trend30['items'][-1]['date']}",
)
trend90 = get_json(f"{ENDPOINTS[1]}?days=90", demo_headers)
check(
    "G3 days=90 恰 90 条",
    len(trend90["items"]) == 90,
    f"len={len(trend90['items'])}",
)
tail30 = [(item["date"], item["minutes"]) for item in trend90["items"][-30:]]
check(
    "G3 days=90 末 30 条与 days=30 序列完全一致（结构性断言）",
    tail30 == got30,
    "",
)
trend1 = get_json(f"{ENDPOINTS[1]}?days=1", demo_headers)
check(
    "G3 days=1 恰 1 条",
    len(trend1["items"]) == 1
    and trend1["items"][0]["date"] == today_bj.isoformat(),
    f"got {trend1['items']}",
)
for bad_days in (0, 366):
    resp = client.get(
        f"{ENDPOINTS[1]}?days={bad_days}", headers=demo_headers
    )
    check(
        f"G3 days={bad_days} -> 422 + code=1001",
        resp.status_code == 422 and resp.json()["code"] == 1001,
        f"status={resp.status_code} body={resp.json()}",
    )

print("========== G6 掌握度（升序 + 零分待学点排除） ==========")
mastery = get_json(ENDPOINTS[2], demo_headers)
items = mastery["items"]
check(
    "G6 种子恰 10 条且升序",
    len(items) == 10
    and all(
        items[i]["mastery_score"] <= items[i + 1]["mastery_score"]
        for i in range(len(items) - 1)
    ),
    f"len={len(items)}",
)
check(
    "G6 首条深度学习 30.0 / 末条 Python 90.0",
    items[0]["knowledge_point"] == "深度学习"
    and abs(items[0]["mastery_score"] - 30.0) < 0.01
    and items[-1]["knowledge_point"] == "Python"
    and abs(items[-1]["mastery_score"] - 90.0) < 0.01,
    f"first={items[0]} last={items[-1]}",
)
insert_mastery(demo_id, "待拆解新点", 0.0, MasterySource.GOAL_BREAKDOWN)
mastery_after = get_json(ENDPOINTS[2], demo_headers)
names_after = [i["knowledge_point"] for i in mastery_after["items"]]
check(
    "G6 插入零分待学点后仍 10 条且不含该点",
    len(mastery_after["items"]) == 10 and "待拆解新点" not in names_after,
    f"len={len(mastery_after['items'])}",
)
check(
    "G6 goal_breakdown 非零分（深度学习 30）仍在列",
    "深度学习" in names_after,
    f"names={names_after}",
)

print("========== G7 薄弱点 Top5（排序 + 频次 + 文案） ==========")
weakness = get_json(ENDPOINTS[3], demo_headers)
w_items = weakness["items"]
exp_recent = recent_counts(demo_id)
exp_order = ["深度学习", "概率论", "动态规划", "线性代数", "英语阅读"]
check(
    "G7 Top5 顺序（同分 50 线性代数频次高在前）",
    [i["knowledge_point"] for i in w_items] == exp_order,
    f"got {[i['knowledge_point'] for i in w_items]}",
)
check(
    "G7 recent_count 与动态推算一致",
    all(
        i["recent_count"] == exp_recent.get(i["knowledge_point"], 0)
        for i in w_items
    ),
    f"got {[(i['knowledge_point'], i['recent_count']) for i in w_items]}",
)
check(
    "G7 每条 advice 非空且含知识点名",
    all(
        i["advice"] and i["knowledge_point"] in i["advice"]
        for i in w_items
    ),
    "",
)
weakness_after = get_json(ENDPOINTS[3], demo_headers)
check(
    "G7 插入零分待学点后 Top5 不变",
    [i["knowledge_point"] for i in weakness_after["items"]] == exp_order,
    f"got {[i['knowledge_point'] for i in weakness_after['items']]}",
)

print("========== G8 建议（三规则，跳过 trend 风险） ==========")
advice = get_json(ENDPOINTS[4], demo_headers)
a_items = advice["items"]
check(
    "G8 种子恰 3 条且 type 顺序 overdue/weakness/streak",
    len(a_items) == 3
    and [i["type"] for i in a_items] == ["overdue", "weakness", "streak"],
    f"got {[(i['type'], i['title']) for i in a_items]}",
)
check(
    "G8 overdue content 含动态真实逾期数",
    str(exp_overdue) in a_items[0]["content"],
    f"content={a_items[0]['content']}, expect {exp_overdue}",
)
check(
    "G8 weakness content 含深度学习与 30",
    "深度学习" in a_items[1]["content"] and "30" in a_items[1]["content"],
    f"content={a_items[1]['content']}",
)
check(
    "G8 streak content 含动态连续天数",
    str(exp_streak) in a_items[2]["content"],
    f"content={a_items[2]['content']}, expect {exp_streak}",
)

print("========== G2 空用户（七字段全 0 + 空序列 + 空列表） ==========")
empty_name, empty_headers = register_and_login("p7empty")
empty_id = get_user_id(empty_name)
empty_overview = get_json(ENDPOINTS[0], empty_headers)
check(
    "G2 空用户 overview 七字段全 0",
    empty_overview == {
        "total_minutes": 0,
        "task_completion_rate": 0.0,
        "avg_mastery": 0.0,
        "streak_days": 0,
        "total_record_count": 0,
        "avg_session_minutes": 0.0,
        "overdue_task_count": 0,
    },
    f"got {empty_overview}",
)
empty_trend = get_json(f"{ENDPOINTS[1]}?days=7", empty_headers)
check(
    "G2 空用户 trend 全 0 序列 + slope=0.0 + risk_alert=null",
    len(empty_trend["items"]) == 7
    and all(i["minutes"] == 0 for i in empty_trend["items"])
    and empty_trend["slope"] == 0.0
    and empty_trend["risk_alert"] is None,
    f"got {empty_trend}",
)
empty_mastery = get_json(ENDPOINTS[2], empty_headers)
empty_weakness = get_json(ENDPOINTS[3], empty_headers)
empty_advice = get_json(ENDPOINTS[4], empty_headers)
check(
    "G2 空用户 mastery/weakness/advice items=[]",
    empty_mastery["items"] == []
    and empty_weakness["items"] == []
    and empty_advice["items"] == [],
    f"got {empty_mastery} {empty_weakness} {empty_advice}",
)

print("========== G5 风险预警（构造递减 / 全 0 / 非递减） ==========")
risk_name, risk_headers = register_and_login("p7riskdec")
risk_id = get_user_id(risk_name)
dec_values = [50, 40, 30, 20, 10]
for i, minutes in enumerate(dec_values):
    insert_record(
        risk_id,
        bj_today() - timedelta(days=4 - i),
        minutes,
        kps=["风险点"],
    )
risk_trend = get_json(f"{ENDPOINTS[1]}?days=5", risk_headers)
alert = risk_trend["risk_alert"]
check(
    "G5 严格递减触发 risk_alert 非空且四字段齐全",
    alert is not None
    and set(alert.keys()) == {"level", "title", "message", "suggestion"},
    f"got {alert}",
)
check(
    "G5 message 含首末真实分钟数（50 与 10）",
    alert is not None and "50" in alert["message"] and "10" in alert["message"],
    f"message={alert['message'] if alert else None}",
)
diagnosis_words = ["抑郁", "焦虑", "心理", "医疗", "诊断", "情绪问题"]
alert_text = (
    alert["title"] + alert["message"] + alert["suggestion"] if alert else ""
)
check(
    "G5 文案无医疗/心理诊断措辞",
    all(w not in alert_text for w in diagnosis_words),
    f"text={alert_text}",
)
check(
    "G5 空用户（全 0 五天）risk_alert=null（d1=0 不触发）",
    empty_trend["risk_alert"] is None,
    "",
)
flat_name, flat_headers = register_and_login("p7flat")
flat_id = get_user_id(flat_name)
for i in range(5):
    insert_record(
        flat_id, bj_today() - timedelta(days=4 - i), 30, kps=["平台点"]
    )
flat_trend = get_json(f"{ENDPOINTS[1]}?days=5", flat_headers)
check(
    "G5 相等序列（非严格递减）risk_alert=null",
    flat_trend["risk_alert"] is None,
    f"got {flat_trend['risk_alert']}",
)

print("========== G4 slope（构造序列验算 / 全 0 / days=1） ==========")
slope_name, slope_headers = register_and_login("p7slope")
slope_id = get_user_id(slope_name)
slope_values = [10, 15, 12, 30]
for i, minutes in enumerate(slope_values):
    insert_record(
        slope_id,
        bj_today() - timedelta(days=3 - i),
        minutes,
        kps=["斜率点"],
    )
slope_resp = get_json(f"{ENDPOINTS[1]}?days=4", slope_headers)
check(
    "G4 构造序列 slope=测试内最小二乘验算值",
    abs(slope_resp["slope"] - lsq_slope(slope_values)) < 0.001,
    f"got {slope_resp['slope']}, expect {lsq_slope(slope_values)}",
)
risk_slope = get_json(f"{ENDPOINTS[1]}?days=5", risk_headers)
check(
    "G4 递减序列 slope 为负且等于验算值",
    abs(risk_slope["slope"] - lsq_slope(dec_values)) < 0.001
    and risk_slope["slope"] < 0,
    f"got {risk_slope['slope']}, expect {lsq_slope(dec_values)}",
)
check(
    "G4 空用户 slope=0.0",
    empty_trend["slope"] == 0.0,
    "",
)
slope_d1 = get_json(f"{ENDPOINTS[1]}?days=1", slope_headers)
check(
    "G4 days=1 slope=0.0（除零保护）",
    slope_d1["slope"] == 0.0 and len(slope_d1["items"]) == 1,
    f"got {slope_d1['slope']}",
)

print("========== G9③④ 衰减检查（37 天扣分 / 失败隔离可重试） ==========")
decay_name, decay_headers = register_and_login("p7decay")
decay_id = get_user_id(decay_name)
insert_record(
    decay_id,
    bj_today() - timedelta(days=37),
    90,
    kps=["衰减验证点"],
    mastery_level=100,
)
insert_mastery(decay_id, "近期待学点", 40.0, MasterySource.RECORD)
insert_record(
    decay_id,
    bj_today() - timedelta(days=5),
    60,
    kps=["近期待学点"],
    mastery_level=90,
)
get_json(ENDPOINTS[0], decay_headers)
decay_map = mastery_map(decay_id)
check(
    "G9③ 37 天知识点按 (37-30)//7×2=2 扣分（EMA 30 → 28）",
    abs(decay_map.get("衰减验证点", -1) - 28.0) < 0.001,
    f"got {decay_map.get('衰减验证点')}",
)
check(
    "G9③ 30 天内知识点（近期待学点）不被改写",
    abs(decay_map.get("近期待学点", -1) - 40.0) < 0.001,
    f"got {decay_map.get('近期待学点')}",
)
check(
    "G9③ 重算成功后字典标记",
    mastery_module._daily_decay_checked.get(decay_id) == today_bj,
    f"got {mastery_module._daily_decay_checked.get(decay_id)}",
)

fail_name, fail_headers = register_and_login("p7fail")
fail_id = get_user_id(fail_name)
insert_record(
    fail_id,
    bj_today() - timedelta(days=37),
    90,
    kps=["失败重试点"],
    mastery_level=80,
)
with patch.object(
    mastery_module,
    "replay_knowledge_points",
    side_effect=RuntimeError("注入失败"),
):
    fail_overview = get_json(ENDPOINTS[0], fail_headers)
check(
    "G9④ 重放异常时 overview 仍 200 + code=0（返回旧数据）",
    fail_overview is not None and "total_minutes" in fail_overview,
    f"got {fail_overview}",
)
check(
    "G9④ 失败不标记（字典无该用户，同日可重试）",
    mastery_module._daily_decay_checked.get(fail_id) is None,
    f"got {mastery_module._daily_decay_checked.get(fail_id)}",
)
fail_map = mastery_map(fail_id)
check(
    "G9④ 失败后掌握度未被写入",
    "失败重试点" not in fail_map,
    f"got {fail_map}",
)
retry_overview = get_json(ENDPOINTS[0], fail_headers)
retry_map = mastery_map(fail_id)
check(
    "G9④ 同日重试成功（EMA 24 → 扣 2 = 22）且标记写入",
    abs(retry_map.get("失败重试点", -1) - 22.0) < 0.001
    and mastery_module._daily_decay_checked.get(fail_id) == today_bj,
    f"got {retry_map.get('失败重试点')}",
)

print("========== G8+ 构造递减数据后 advice 仍恰 3 条 ==========")
combo_name, combo_headers = register_and_login("p7combo")
combo_id = get_user_id(combo_name)
for i in range(5):
    insert_record(
        combo_id,
        bj_today() - timedelta(days=9 - i),
        60,
        kps=["节奏点"],
    )
for i, minutes in enumerate([50, 40, 30, 20, 10]):
    insert_record(
        combo_id,
        bj_today() - timedelta(days=4 - i),
        minutes,
        kps=["节奏点"],
    )
insert_mastery(combo_id, "组合薄弱点", 40.0, MasterySource.RECORD)
with SessionLocal() as db:
    db.add(
        Task(
            user_id=combo_id,
            title="组合逾期任务",
            deadline=utc_now() - timedelta(days=1),
            status=TaskStatus.TODO,
        )
    )
    db.commit()
combo_trend = get_json(f"{ENDPOINTS[1]}?days=10", combo_headers)
combo_advice = get_json(ENDPOINTS[4], combo_headers)
check(
    "G8+ 递减触发预警的用户 advice 仍恰 3 条（风险不在 advice 重复）",
    combo_trend["risk_alert"] is not None
    and len(combo_advice["items"]) == 3
    and [i["type"] for i in combo_advice["items"]]
    == ["overdue", "weakness", "streak"],
    f"alert={combo_trend['risk_alert'] is not None}, "
    f"advice={[i['type'] for i in combo_advice['items']]}",
)

print("========== G10 性能（5 接口各 < 500ms） ==========")
for path in ENDPOINTS:
    start = time.perf_counter()
    resp = client.get(path, headers=demo_headers)
    elapsed_ms = (time.perf_counter() - start) * 1000
    check(
        f"G10 {path.split('/')[-1]} < 500ms",
        resp.status_code == 200 and elapsed_ms < 500,
        f"{elapsed_ms:.1f}ms",
    )

print("========== G11 安全（未登录 401 / 跨用户隔离） ==========")
for path in ENDPOINTS:
    resp = client.get(path)
    check(
        f"G11 未登录 {path.split('/')[-1]} -> 401/1003",
        resp.status_code == 401 and resp.json()["code"] == 1003,
        f"status={resp.status_code} body={resp.json()}",
    )
iso_overview = get_json(ENDPOINTS[0], empty_headers)
iso_mastery = get_json(ENDPOINTS[2], empty_headers)
check(
    "G11 用户 B 看不到 demo 数据（total_minutes=0 且 mastery 为空）",
    iso_overview["total_minutes"] == 0 and iso_mastery["items"] == [],
    f"got {iso_overview['total_minutes']}, {len(iso_mastery['items'])}",
)

print("========== P7 Dashboard 验收汇总 ==========")
print(f"PASS: {len(PASSED)}  FAIL: {len(FAILED)}")
if FAILED:
    for name in FAILED:
        print(f"  FAILED -> {name}")
    sys.exit(1)
print("ALL GREEN (G1-G11)")