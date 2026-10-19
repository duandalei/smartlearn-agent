"""知识点名称规范化验收脚本（P6 交付后缺陷修复，tasks.md 组 6）。

运行：cd backend && .venv/Scripts/python scripts/verify_kp_normalization.py

验证方式：``TestClient`` 进程内直调 app 对象（A/B/D 组）+ mock
``app.services.llm.chat``（C 组，goal.py 以 ``llm.chat`` 模块属性方式
调用，patch 点正确），全程 ``backend/tmp_verify/kp_normalization.db``
临时库（建表无种子、用例自含前置数据），禁止触碰正式库
``data/smartlearn.db``（裁定①：存量数据零迁移）。

覆盖用例（tasks.md 6.1~6.4）：
    A 组 records 数组管线（spec 场景①②③⑦⑧）：
        A1 [" Transformer", "Transformer"] 创建 → 落库 ["Transformer"]
           且掌握度该知识点仅一行（不分裂，缺陷主场景复现）；
        A2 编辑为 ["Transformer", " Transformer "] → 仍单元素、
           掌握度更新既有行不新建；
        A3 ["   "] → 422/1001「知识点不能为空白」，不落库、
           不触发掌握度重放；
        A4 ["  " + "a"*99] → 成功（长度按 strip 后值判，规则 4b）；
        A5 ["a"*101] → 422/1001 长度文案；
        A6 [] → 允许（清空语义不变）；
        A7 [" Multi-Head Attention "] → 内部空格保留；
        A8 ["B", "A", "B "] → ["B", "A"] 去重保序。
    B 组 tasks 侧对称（spec 场景④）：
        B1 创建 [" Transformer", "Transformer"] → 落库与 GET 同值；
        B2 编辑 [" Transformer"] → 落库不变；
        B3 ["   "] 创建与编辑双路径 → 均 422/1001。
    C 组树管线 mock LLM（spec 场景⑪）：
        C1 叶子名带空白 → roadmap 与掌握度同源双写均无首尾空白；
        C2 纯空白叶子 → 重试一次后 502/3000「AI 解析失败」、
           Goal 状态不流转、掌握度零写入（树管线解析失败语义）；
        C3 同名叶子分处不同子树 → 树两节点均保留（不合并）且
           掌握度该名仅一行（唯一索引去重，并存语义）；
        C4 全正常树 → 清洗幂等，roadmap 输出==输入（回归锚点）。
    D 组双保险对拍（降级方案，前端行为由 build + 人工走查覆盖）：
        D1 后端函数三步语义断言（前端 utils/knowledge.ts 为
           「三步无校验版」同语义 TS 镜像：纯空白前端滤除、后端
           拦截 422——差异即双保险分工，前端体验优化、后端权威兜底）；
        D2 清洗幂等回归（二次清洗结果不变）。
"""

from __future__ import annotations

import json
import os
import sys
import uuid
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, patch

_SCRIPTS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(_SCRIPTS_DIR.parent))
sys.path.insert(0, str(_SCRIPTS_DIR))

# 沙箱 data/ 目录间歇性写锁（P2 起已知问题）：改用 backend 下临时数据库
# （环境变量优先级高于 .env），不污染正式 data/smartlearn.db。
_TMP_DB_DIR = _SCRIPTS_DIR.parent / "tmp_verify"
_TMP_DB_DIR.mkdir(exist_ok=True)
_TMP_DB = _TMP_DB_DIR / "kp_normalization.db"
if _TMP_DB.exists():
    _TMP_DB.unlink()
os.environ["DATABASE_URL"] = f"sqlite:///{_TMP_DB.as_posix()}"

import _sandbox_patch  # noqa: F401,E402  （IPv6 socketpair 补丁，须先于 TestClient）

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import func, select  # noqa: E402

from app.core.normalize import normalize_knowledge_points  # noqa: E402
from app.db.session import SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402
from app.models.base import Base  # noqa: E402
from app.models.enums import GoalStatus  # noqa: E402
from app.models.goal import LearningGoal  # noqa: E402
from app.models.mastery import KnowledgeMastery  # noqa: E402
from app.models.record import LearningRecord  # noqa: E402
from app.models.user import User  # noqa: E402

# 建表（临时库，无种子数据；用例自含全部前置数据）。
Base.metadata.create_all(engine)

client = TestClient(app)

PASSED: list[str] = []
FAILED: list[str] = []

# goal.py 以「llm.chat(...)」模块属性方式调用 —— patch 点即 llm 模块。
LLM_CHAT = "app.services.llm.chat"

TODAY_STR = "2026-10-19"


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


def get_user_id(username: str) -> int:
    """按用户名查用户 id。"""
    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.username == username))
        assert user is not None
        return user.id


def count_records(user_id: int) -> int:
    """DB 直查用户学习记录总数。"""
    with SessionLocal() as db:
        return int(
            db.scalar(select(func.count()).where(LearningRecord.user_id == user_id))
        )


def count_mastery(user_id: int, kp: str | None = None) -> int:
    """DB 直查用户掌握度行数（kp 给定时按知识点精确统计）。"""
    with SessionLocal() as db:
        stmt = select(func.count()).where(KnowledgeMastery.user_id == user_id)
        if kp is not None:
            stmt = stmt.where(KnowledgeMastery.knowledge_point == kp)
        return int(db.scalar(stmt))


def mastery_points(user_id: int) -> set[str]:
    """DB 直查用户全部掌握度知识点名集合。"""
    with SessionLocal() as db:
        rows = db.execute(
            select(KnowledgeMastery.knowledge_point).where(
                KnowledgeMastery.user_id == user_id
            )
        ).scalars()
        return set(rows)


def create_record_raw(headers: dict[str, str], **overrides: Any):
    """创建学习记录，返回原始 Response（供状态码断言）。"""
    payload: dict[str, Any] = {
        "content": "Transformer 学习",
        "duration_minutes": 30,
        "study_date": TODAY_STR,
    }
    payload.update(overrides)
    return client.post("/api/v1/records", json=payload, headers=headers)


def leaf_names(node: dict) -> list[str]:
    """DFS 收集树内全部叶子节点名（children 为空即叶子）。"""
    children = node.get("children") or []
    if not children:
        return [node["name"]]
    names: list[str] = []
    for child in children:
        names.extend(leaf_names(child))
    return names


# C 组 mock 树数据。
TREE_WS: dict = {
    "name": " Transformer 学习路线 ",
    "children": [
        {"name": " Transformer 基础 ", "children": []},
        {"name": "注意力机制", "children": []},
    ],
}
TREE_WS_CLEAN: dict = {
    "name": "Transformer 学习路线",
    "children": [
        {"name": "Transformer 基础", "children": []},
        {"name": "注意力机制", "children": []},
    ],
}
TREE_BLANK_LEAF: dict = {
    "name": "机器学习",
    "children": [{"name": "  ", "children": []}],
}
TREE_DUP_LEAF: dict = {
    "name": "深度学习",
    "children": [
        {"name": "视觉", "children": [{"name": "CNN", "children": []}]},
        {"name": "序列", "children": [{"name": "CNN ", "children": []}]},
    ],
}
TREE_NORMAL: dict = {
    "name": "机器学习",
    "children": [
        {
            "name": "数学基础",
            "children": [
                {"name": "线性代数", "children": []},
                {"name": "概率论", "children": []},
            ],
        },
        {"name": "编程基础", "children": [{"name": "Python", "children": []}]},
    ],
}


def create_goal(headers: dict[str, str], title: str) -> int:
    """创建目标并返回 id。"""
    resp = client.post("/api/v1/goals", json={"title": title}, headers=headers)
    assert resp.status_code == 200 and resp.json()["code"] == 0, resp.text
    return resp.json()["data"]["id"]


def breakdown(headers: dict[str, str], goal_id: int):
    """发起 AI 拆解请求。"""
    return client.post(f"/api/v1/goals/{goal_id}/breakdown", headers=headers)


def get_roadmap(headers: dict[str, str], goal_id: int) -> dict | None:
    """查询目标知识树（data.roadmap，失败路径返回 None）。"""
    resp = client.get(f"/api/v1/goals/{goal_id}/roadmap", headers=headers)
    assert resp.status_code == 200 and resp.json()["code"] == 0, resp.text
    return resp.json()["data"]["roadmap"]


def main() -> None:
    print("-- A 组 records 数组管线 --")
    user_a, headers_a = register_and_login("kpna")
    uid_a = get_user_id(user_a)

    resp = create_record_raw(
        headers_a,
        mastery_level=60,
        knowledge_points=[" Transformer", "Transformer"],
    )
    body = resp.json()
    check(
        "A1a 创建成功 code=0",
        resp.status_code == 200 and body["code"] == 0,
        resp.text,
    )
    check(
        "A1b 落库恰为 ['Transformer']（spec 场景①）",
        (body.get("data") or {}).get("knowledge_points") == ["Transformer"],
        str(body.get("data")),
    )
    check(
        "A1c 掌握度不分裂：'Transformer' 仅一行",
        count_mastery(uid_a, "Transformer") == 1,
        f"count={count_mastery(uid_a, 'Transformer')}",
    )
    check(
        "A1d 无带空白变体掌握度行",
        count_mastery(uid_a, " Transformer") == 0
        and count_mastery(uid_a, "Transformer ") == 0,
        str(mastery_points(uid_a)),
    )
    record_a1 = body["data"]["id"]

    resp = client.put(
        f"/api/v1/records/{record_a1}",
        json={"knowledge_points": ["Transformer", " Transformer "], "mastery_level": 80},
        headers=headers_a,
    )
    body = resp.json()
    check(
        "A2a 编辑成功 code=0",
        resp.status_code == 200 and body["code"] == 0,
        resp.text,
    )
    check(
        "A2b 编辑后仍单元素（spec 场景③）",
        (body.get("data") or {}).get("knowledge_points") == ["Transformer"],
        str(body.get("data")),
    )
    check(
        "A2c 掌握度更新既有行不新建",
        count_mastery(uid_a, "Transformer") == 1,
        f"count={count_mastery(uid_a, 'Transformer')}",
    )

    before_records = count_records(uid_a)
    before_mastery = count_mastery(uid_a)
    resp = create_record_raw(headers_a, knowledge_points=["   "])
    body = resp.json()
    check(
        "A3a 纯空白 → 422/1001",
        resp.status_code == 422 and body["code"] == 1001,
        resp.text,
    )
    check(
        "A3b message 含「知识点不能为空白」（spec 场景②）",
        "知识点不能为空白" in body.get("message", ""),
        str(body),
    )
    check(
        "A3c 不落库、不触发掌握度重放",
        count_records(uid_a) == before_records and count_mastery(uid_a) == before_mastery,
        f"records {before_records}->{count_records(uid_a)}, "
        f"mastery {before_mastery}->{count_mastery(uid_a)}",
    )

    resp = create_record_raw(headers_a, knowledge_points=["  " + "a" * 99])
    body = resp.json()
    check(
        "A4 strip 后 99 字符 → 成功（规则 4b）",
        resp.status_code == 200
        and body["code"] == 0
        and (body.get("data") or {}).get("knowledge_points") == ["a" * 99],
        resp.text,
    )

    resp = create_record_raw(headers_a, knowledge_points=["a" * 101])
    body = resp.json()
    check(
        "A5 101 字符 → 422/1001",
        resp.status_code == 422 and body["code"] == 1001,
        resp.text,
    )
    check(
        "A5b message 含长度文案",
        "知识点名称长度须为 1~100 字符" in body.get("message", ""),
        str(body),
    )

    resp = create_record_raw(headers_a, knowledge_points=[])
    body = resp.json()
    check(
        "A6 空数组 → 允许（清空语义不变）",
        resp.status_code == 200
        and body["code"] == 0
        and (body.get("data") or {}).get("knowledge_points") == [],
        resp.text,
    )

    resp = create_record_raw(headers_a, knowledge_points=[" Multi-Head Attention "])
    body = resp.json()
    check(
        "A7 内部空格保留（spec 场景⑦）",
        resp.status_code == 200
        and (body.get("data") or {}).get("knowledge_points") == ["Multi-Head Attention"],
        resp.text,
    )

    resp = create_record_raw(headers_a, knowledge_points=["B", "A", "B "])
    body = resp.json()
    check(
        "A8 去重保序 ['B', 'A']（spec 场景⑧）",
        resp.status_code == 200
        and (body.get("data") or {}).get("knowledge_points") == ["B", "A"],
        resp.text,
    )

    print("-- B 组 tasks 侧对称 --")
    user_b, headers_b = register_and_login("kpnb")

    resp = client.post(
        "/api/v1/tasks",
        json={"title": "Transformer 任务", "knowledge_points": [" Transformer", "Transformer"]},
        headers=headers_b,
    )
    body = resp.json()
    check(
        "B1a 创建成功且落库 ['Transformer']（spec 场景④）",
        resp.status_code == 200
        and body["code"] == 0
        and (body.get("data") or {}).get("knowledge_points") == ["Transformer"],
        resp.text,
    )
    task_b1 = body["data"]["id"]
    resp = client.get(f"/api/v1/tasks/{task_b1}", headers=headers_b)
    check(
        "B1b GET 返回同值",
        resp.status_code == 200
        and (resp.json().get("data") or {}).get("knowledge_points") == ["Transformer"],
        resp.text,
    )

    resp = client.put(
        f"/api/v1/tasks/{task_b1}",
        json={"knowledge_points": [" Transformer"]},
        headers=headers_b,
    )
    body = resp.json()
    check(
        "B2 编辑为 [' Transformer'] → 落库不变",
        resp.status_code == 200
        and (body.get("data") or {}).get("knowledge_points") == ["Transformer"],
        resp.text,
    )

    resp = client.post(
        "/api/v1/tasks",
        json={"title": "空白校验任务", "knowledge_points": ["   "]},
        headers=headers_b,
    )
    body = resp.json()
    check(
        "B3a 创建纯空白 → 422/1001",
        resp.status_code == 422 and body["code"] == 1001,
        resp.text,
    )
    check(
        "B3b message 含「知识点不能为空白」",
        "知识点不能为空白" in body.get("message", ""),
        str(body),
    )
    resp = client.put(
        f"/api/v1/tasks/{task_b1}",
        json={"knowledge_points": ["   "]},
        headers=headers_b,
    )
    body = resp.json()
    check(
        "B3c 编辑纯空白 → 422/1001",
        resp.status_code == 422 and body["code"] == 1001,
        resp.text,
    )

    print("-- C 组树管线（mock LLM）--")
    user_c, headers_c = register_and_login("kpnc")
    uid_c = get_user_id(user_c)

    g1 = create_goal(headers_c, "Transformer 学习路线")
    with patch(
        LLM_CHAT, new=AsyncMock(return_value=json.dumps(TREE_WS, ensure_ascii=False))
    ):
        resp = breakdown(headers_c, g1)
    body = resp.json()
    check(
        "C1a 带空白叶子拆解成功",
        resp.status_code == 200 and body["code"] == 0,
        resp.text,
    )
    roadmap = (body.get("data") or {}).get("roadmap") or {}
    check(
        "C1b roadmap 落库叶子名无首尾空白",
        roadmap == TREE_WS_CLEAN,
        str(roadmap),
    )
    points = mastery_points(uid_c)
    check(
        "C1c 掌握度行知识点无首尾空白（同源双写之一）",
        {"Transformer 基础", "注意力机制"} <= points,
        str(points),
    )
    check(
        "C1d 无带空白掌握度变体（同源双写之二）",
        " Transformer 基础 " not in points and " Transformer 学习路线 " not in points,
        str(points),
    )
    check(
        "C1e roadmap 叶子名与掌握度知识点一致（同源双写之三）",
        set(leaf_names(TREE_WS_CLEAN)) <= points,
        str(points),
    )

    g2 = create_goal(headers_c, "纯空白叶子目标")
    mastery_before = count_mastery(uid_c)
    with patch(
        LLM_CHAT,
        new=AsyncMock(return_value=json.dumps(TREE_BLANK_LEAF, ensure_ascii=False)),
    ) as mock_chat:
        resp = breakdown(headers_c, g2)
    body = resp.json()
    check(
        "C2a 纯空白叶子 → 502/3000（解析失败走重试兜底）",
        resp.status_code == 502 and body["code"] == 3000,
        resp.text,
    )
    check(
        "C2b message 含「AI 解析失败」",
        "AI 解析失败" in body.get("message", ""),
        str(body),
    )
    check("C2c 重试一次后放弃", mock_chat.await_count == 2)
    check("C2d roadmap 未落库", get_roadmap(headers_c, g2) is None)
    with SessionLocal() as db:
        goal_row = db.scalar(select(LearningGoal).where(LearningGoal.id == g2))
        goal_status_active = goal_row is not None and goal_row.status == GoalStatus.ACTIVE
    check("C2e Goal 状态不流转（仍 active）", goal_status_active)
    check(
        "C2f 掌握度零写入",
        count_mastery(uid_c) == mastery_before,
        f"{mastery_before}->{count_mastery(uid_c)}",
    )

    g3 = create_goal(headers_c, "同名叶子目标")
    with patch(
        LLM_CHAT,
        new=AsyncMock(return_value=json.dumps(TREE_DUP_LEAF, ensure_ascii=False)),
    ):
        resp = breakdown(headers_c, g3)
    body = resp.json()
    check(
        "C3a 同名叶子拆解成功",
        resp.status_code == 200 and body["code"] == 0,
        resp.text,
    )
    roadmap = (body.get("data") or {}).get("roadmap") or {}
    sub_names = [c["name"] for c in roadmap.get("children") or []]
    leaf_by_sub = {
        c["name"]: [leaf["name"] for leaf in (c.get("children") or [])]
        for c in roadmap.get("children") or []
    }
    check(
        "C3b 两个子树叶子均清洗为 'CNN'",
        leaf_by_sub.get("视觉") == ["CNN"] and leaf_by_sub.get("序列") == ["CNN"],
        str(roadmap),
    )
    check(
        "C3c 树两节点均保留（不去重不合并）",
        sub_names == ["视觉", "序列"] and leaf_names(roadmap).count("CNN") == 2,
        str(roadmap),
    )
    check(
        "C3d 掌握度 'CNN' 仅一行（唯一索引去重）",
        count_mastery(uid_c, "CNN") == 1,
        f"count={count_mastery(uid_c, 'CNN')}",
    )

    g4 = create_goal(headers_c, "全正常树目标")
    with patch(
        LLM_CHAT,
        new=AsyncMock(return_value=json.dumps(TREE_NORMAL, ensure_ascii=False)),
    ):
        resp = breakdown(headers_c, g4)
    body = resp.json()
    check(
        "C4a 全正常树拆解成功",
        resp.status_code == 200 and body["code"] == 0,
        resp.text,
    )
    check(
        "C4b 清洗幂等：输出==输入（回归锚点）",
        (body.get("data") or {}).get("roadmap") == TREE_NORMAL,
        str((body.get("data") or {}).get("roadmap")),
    )

    print("-- D 组双保险对拍 --")
    result = normalize_knowledge_points([" a ", "a", "b "])
    check(
        "D1a 后端三步语义：[' a ','a','b '] → ['a','b']",
        result == ["a", "b"],
        str(result),
    )
    raised = False
    try:
        normalize_knowledge_points([" a ", "a", ""])
    except ValueError as exc:
        raised = "知识点不能为空白" in str(exc)
    check(
        "D1b 纯空白后端拦截 ValueError（前端同输入返回 ['a']，差异即双保险分工）",
        raised,
    )
    idempotent = True
    for case in (
        [" Transformer", "Transformer"],
        [" Multi-Head Attention "],
        ["B", "A", "B "],
        ["  " + "a" * 99, "  " + "a" * 99],
        [],
    ):
        once = normalize_knowledge_points(list(case))
        twice = normalize_knowledge_points(list(once))
        if once != twice:
            idempotent = False
            print(f"    不幂等输入: {case!r} → {once!r} → {twice!r}")
    check("D2 清洗幂等：二次清洗结果不变", idempotent)

    # ---- 汇总与清理 --------------------------------------------------------
    print(f"\n结果：{len(PASSED)} PASS / {len(FAILED)} FAIL")
    if FAILED:
        print("失败用例：", FAILED)
    with SessionLocal() as db:
        for username in (user_a, user_b, user_c):
            user = db.scalar(select(User).where(User.username == username))
            if user is not None:
                db.delete(user)
        db.commit()
    sys.exit(1 if FAILED else 0)


if __name__ == "__main__":
    main()