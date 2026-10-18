"""P4 AI 拆解流程 mock 验证（任务 8.3，ASGI 直调）。

运行：cd backend && .venv/Scripts/python scripts/verify_p4_breakdown.py

验证方式：mock ``app.services.llm.chat``（goal.py 以 ``llm.chat`` 模块
属性方式调用，patch 点正确）+ ``TestClient`` / ``httpx.ASGITransport``
进程内直调 app 对象，不起 uvicorn、不发真实网络请求。

覆盖用例（tasks.md 8.3，对应验收②与全部裁定规则）：
    1.  ```json 包裹容错 → 拆解成功落库、roadmap_updated_at 刷新；
    2.  非 JSON 两次失败 → 3000/502「AI 解析失败」，原 roadmap 不变；
    3.  首次失败、纠错重试第二次成功（design 2.4.2 重试路径）；
    4.  空树（根 children=[]）两次失败 → 3000；单子节点树成功（裁定③）；
    5.  5 层树截断为 ≤4 层、第 4 层节点保留、第 5 层丢弃（裁定②）；
    6.  叶子入掌握度：新叶 0 分、source=goal_breakdown；
    7.  幂等：预置非零分数不被覆盖（规则 7）、重复拆解无重复记录（规则 8）；
    8.  并发互斥：同目标两笔并发 → 一笔成功、一笔 1007/400「正在拆解中」，
        完成后标志清除可再次拆解（裁定⑦）；
    9.  服务类异常包装：上游抛 APITimeoutError → 3000「AI 服务暂时不可用」，
        无原始英文堆栈透传；
    10. 配置缺失：清空 LLM_* 三项 → 3000「AI 服务未配置」，客户端未构造
        （未发起上游请求）。
"""

from __future__ import annotations

import asyncio
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
_TMP_DB = _TMP_DB_DIR / "p4_breakdown.db"
if _TMP_DB.exists():
    _TMP_DB.unlink()
os.environ["DATABASE_URL"] = f"sqlite:///{_TMP_DB.as_posix()}"

import _sandbox_patch  # noqa: F401,E402  （IPv6 socketpair 补丁，须先于 TestClient）

import httpx  # noqa: E402
import openai  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.core.config import settings  # noqa: E402
from app.db.session import SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402
from app.models.base import Base  # noqa: E402
from app.models.enums import MasterySource  # noqa: E402
from app.models.mastery import KnowledgeMastery  # noqa: E402
from app.models.user import User  # noqa: E402
from app.services import goal as goal_service  # noqa: E402
from app.services import llm  # noqa: E402

Base.metadata.create_all(engine)

client = TestClient(app)

PASSED: list[str] = []
FAILED: list[str] = []

# goal.py 以「llm.chat(...)」模块属性方式调用 —— patch 点即 llm 模块。
LLM_CHAT = "app.services.llm.chat"

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
TREE_JSON = json.dumps(TREE_NORMAL, ensure_ascii=False)
TREE_FENCED = f"```json\n{TREE_JSON}\n```"
GARBAGE = "抱歉，我无法按要求输出 JSON，这是一段纯文本解释。"
TREE_EMPTY_JSON = '{"name":"机器学习","children":[]}'
TREE_SINGLE_CHILD: dict = {
    "name": "机器学习",
    "children": [{"name": "监督学习", "children": []}],
}
# 用例 6/7 专用树：叶子名与其他用例隔离，避免预置分数时撞唯一约束。
TREE_MASTERY: dict = {
    "name": "前端就业",
    "children": [
        {
            "name": "基础",
            "children": [
                {"name": "HTML", "children": []},
                {"name": "CSS", "children": []},
            ],
        },
        {"name": "框架", "children": [{"name": "Vue", "children": []}]},
    ],
}
TREE_MASTERY_JSON = json.dumps(TREE_MASTERY, ensure_ascii=False)


def chain_tree(depth: int) -> dict:
    """构造 depth 层链式单枝树（节点名标记所在层级，供截断断言）。"""
    node: dict = {"name": f"第{depth}层", "children": []}
    for level in range(depth - 1, 0, -1):
        node = {"name": f"第{level}层", "children": [node]}
    return node


def tree_depth(node: dict) -> int:
    """计算树深度（根为 1）。"""
    children = node.get("children") or []
    if not children:
        return 1
    return 1 + max(tree_depth(child) for child in children)


def tree_names(node: dict) -> set[str]:
    """收集树内全部节点名。"""
    names = {node["name"]}
    for child in node.get("children") or []:
        names |= tree_names(child)
    return names


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


def create_goal(headers: dict[str, str], title: str) -> int:
    """创建目标并返回 id。"""
    resp = client.post("/api/v1/goals", json={"title": title}, headers=headers)
    assert resp.status_code == 200 and resp.json()["code"] == 0, resp.text
    return resp.json()["data"]["id"]


def breakdown(headers: dict[str, str], goal_id: int):
    """发起 AI 拆解请求。"""
    return client.post(f"/api/v1/goals/{goal_id}/breakdown", headers=headers)


def get_roadmap(headers: dict[str, str], goal_id: int) -> dict:
    """查询目标知识树（data 部分）。"""
    resp = client.get(f"/api/v1/goals/{goal_id}/roadmap", headers=headers)
    assert resp.status_code == 200 and resp.json()["code"] == 0, resp.text
    return resp.json()["data"]


def mastery_map(headers: dict[str, str]) -> dict[str, dict]:
    """拉取当前用户全量掌握度，构造 知识点 -> 记录 映射。"""
    resp = client.get(
        "/api/v1/knowledge-mastery?page=1&page_size=100", headers=headers
    )
    assert resp.status_code == 200 and resp.json()["code"] == 0, resp.text
    return {i["knowledge_point"]: i for i in resp.json()["data"]["items"]}


def main() -> None:
    from sqlalchemy import func, select

    user_a, headers_a = register_and_login("p4bd_a")

    print("用例 1：```json 包裹容错")
    g1 = create_goal(headers_a, "6个月掌握机器学习")
    with patch(LLM_CHAT, new=AsyncMock(return_value=TREE_FENCED)) as mock_chat:
        resp = breakdown(headers_a, g1)
    body = resp.json()
    check("1a code=0/200", resp.status_code == 200 and body["code"] == 0, resp.text)
    data = body.get("data") or {}
    check("1b roadmap 解析正确", data.get("roadmap") == TREE_NORMAL, str(data.get("roadmap")))
    check("1c roadmap_updated_at 刷新", data.get("roadmap_updated_at") is not None)
    check("1d 仅调用 LLM 1 次", mock_chat.await_count == 1)
    rm = get_roadmap(headers_a, g1)
    check("1e 落库确认", rm["roadmap"] == TREE_NORMAL and rm["roadmap_updated_at"] is not None)

    print("用例 2：非 JSON 两次失败（失败不变量）")
    before = get_roadmap(headers_a, g1)
    with patch(LLM_CHAT, new=AsyncMock(return_value=GARBAGE)) as mock_chat:
        resp = breakdown(headers_a, g1)
    body = resp.json()
    check("2a 3000/502", resp.status_code == 502 and body["code"] == 3000, resp.text)
    check("2b message 含「AI 解析失败」", "AI 解析失败" in body.get("message", ""), str(body))
    check("2c 两次尝试后放弃", mock_chat.await_count == 2)
    check("2d 原 roadmap 不变", get_roadmap(headers_a, g1) == before)

    print("用例 3：首次失败、纠错重试成功")
    g2 = create_goal(headers_a, "考研计算机408")
    with patch(
        LLM_CHAT, new=AsyncMock(side_effect=[GARBAGE, TREE_JSON])
    ) as mock_chat:
        resp = breakdown(headers_a, g2)
    body = resp.json()
    check("3a 重试后成功", resp.status_code == 200 and body["code"] == 0, resp.text)
    check("3b roadmap 正确", (body.get("data") or {}).get("roadmap") == TREE_NORMAL)
    check("3c 恰好两次调用", mock_chat.await_count == 2)

    print("用例 4：空树判定与单子节点树")
    g3 = create_goal(headers_a, "保研英语提升")
    with patch(LLM_CHAT, new=AsyncMock(return_value=TREE_EMPTY_JSON)) as mock_chat:
        resp = breakdown(headers_a, g3)
    body = resp.json()
    check("4a 空树 3000/502", resp.status_code == 502 and body["code"] == 3000, resp.text)
    check("4b 空树 message 含「AI 解析失败」", "AI 解析失败" in body.get("message", ""), str(body))
    check("4c 空树也重试两次", mock_chat.await_count == 2)
    single_json = json.dumps(TREE_SINGLE_CHILD, ensure_ascii=False)
    with patch(LLM_CHAT, new=AsyncMock(return_value=single_json)):
        resp = breakdown(headers_a, g3)
    body = resp.json()
    check(
        "4d 单子节点树成功（裁定③）",
        resp.status_code == 200
        and body["code"] == 0
        and (body.get("data") or {}).get("roadmap") == TREE_SINGLE_CHILD,
        resp.text,
    )

    print("用例 5：超 4 层截断（裁定②）")
    g4 = create_goal(headers_a, "ACM 竞赛算法")
    tree5_json = json.dumps(chain_tree(5), ensure_ascii=False)
    with patch(LLM_CHAT, new=AsyncMock(return_value=tree5_json)):
        resp = breakdown(headers_a, g4)
    body = resp.json()
    roadmap = (body.get("data") or {}).get("roadmap") or {}
    check("5a 截断属正常路径 code=0", resp.status_code == 200 and body["code"] == 0, resp.text)
    check("5b 落库深度 =4", tree_depth(roadmap) == 4, f"实际深度={tree_depth(roadmap)}")
    names = tree_names(roadmap)
    check("5c 第 4 层节点保留", "第4层" in names, str(names))
    check("5d 第 5 层被丢弃", "第5层" not in names, str(names))

    print("用例 6+7：叶子入掌握度与幂等规则")
    g5 = create_goal(headers_a, "前端就业冲刺")
    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.username == user_a))
        db.add(
            KnowledgeMastery(
                user_id=user.id,
                knowledge_point="CSS",
                mastery_score=60.0,
                source=MasterySource.RECORD,
            )
        )
        db.commit()
    with patch(LLM_CHAT, new=AsyncMock(return_value=TREE_MASTERY_JSON)):
        resp = breakdown(headers_a, g5)
    check("6a 拆解成功", resp.status_code == 200 and resp.json()["code"] == 0, resp.text)
    by_kp = mastery_map(headers_a)
    check("6b 全部叶子出现", {"HTML", "CSS", "Vue"} <= set(by_kp), str(set(by_kp)))
    check(
        "6c 新叶 0 分",
        by_kp.get("HTML", {}).get("mastery_score") == 0
        and by_kp.get("Vue", {}).get("mastery_score") == 0,
        str(by_kp),
    )
    check("6d source=goal_breakdown", by_kp.get("HTML", {}).get("source") == "goal_breakdown")
    check("6e 预置分数不被覆盖（规则 7）", by_kp.get("CSS", {}).get("mastery_score") == 60.0, str(by_kp.get("CSS")))
    with patch(LLM_CHAT, new=AsyncMock(return_value=TREE_MASTERY_JSON)):
        resp = breakdown(headers_a, g5)
    check("7a 重复拆解成功", resp.status_code == 200 and resp.json()["code"] == 0, resp.text)
    by_kp = mastery_map(headers_a)
    check(
        "7b 重复拆解分数不变（规则 7）",
        by_kp.get("CSS", {}).get("mastery_score") == 60.0
        and by_kp.get("HTML", {}).get("mastery_score") == 0,
        str(by_kp),
    )
    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.username == user_a))
        rows = db.execute(
            select(KnowledgeMastery.knowledge_point, func.count())
            .where(
                KnowledgeMastery.user_id == user.id,
                KnowledgeMastery.knowledge_point.in_(["HTML", "CSS", "Vue"]),
            )
            .group_by(KnowledgeMastery.knowledge_point)
        ).all()
    check("7c 同名叶子仅一条记录（规则 8）", len(rows) == 3 and all(c == 1 for _, c in rows), str(rows))

    print("用例 8：并发互斥（裁定⑦）")
    g6 = create_goal(headers_a, "并发互斥验证目标")

    async def slow_chat(messages: Any) -> str:
        await asyncio.sleep(0.5)
        return TREE_JSON

    async def run_two() -> tuple[httpx.Response, httpx.Response]:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://testserver"
        ) as ac:
            with patch(LLM_CHAT, new=slow_chat):
                r1, r2 = await asyncio.gather(
                    ac.post(f"/api/v1/goals/{g6}/breakdown", headers=headers_a),
                    ac.post(f"/api/v1/goals/{g6}/breakdown", headers=headers_a),
                )
        return r1, r2

    r1, r2 = asyncio.run(run_two())
    check(
        "8a 一笔成功一笔 400",
        sorted([r1.status_code, r2.status_code]) == [200, 400],
        f"{r1.status_code}/{r2.status_code}",
    )
    loser = r2 if r2.status_code != 200 else r1
    loser_body = loser.json()
    check(
        "8b 第二笔 1007「正在拆解中」",
        loser_body.get("code") == 1007 and "正在拆解中" in loser_body.get("message", ""),
        str(loser_body),
    )
    check("8c 互斥标志已清除", g6 not in goal_service._breakdown_in_progress)
    with patch(LLM_CHAT, new=AsyncMock(return_value=TREE_JSON)):
        resp = breakdown(headers_a, g6)
    body = resp.json()
    check("8d 完成后可再次拆解", resp.status_code == 200 and body["code"] == 0, resp.text)
    check("8e roadmap 数据完好", (body.get("data") or {}).get("roadmap") == TREE_NORMAL)

    print("用例 9：服务类异常包装（规则 5.4.1-4a）")
    g7 = create_goal(headers_a, "超时验证目标")

    class _FakeCompletions:
        async def create(self, **kwargs: Any):
            raise openai.APITimeoutError(
                request=httpx.Request("POST", "http://llm.test/v1/chat/completions")
            )

    class _FakeChat:
        def __init__(self) -> None:
            self.completions = _FakeCompletions()

    class _FakeClient:
        def __init__(self) -> None:
            self.chat = _FakeChat()

    with patch("app.services.llm.get_chat_client", return_value=_FakeClient()):
        resp = breakdown(headers_a, g7)
    body = resp.json()
    check("9a 3000/502", resp.status_code == 502 and body["code"] == 3000, resp.text)
    check("9b message 含「AI 服务暂时不可用」", "AI 服务暂时不可用" in body.get("message", ""), str(body))
    check(
        "9c 无原始异常透传",
        "APITimeoutError" not in resp.text and "Traceback" not in resp.text,
        resp.text[:200],
    )
    check("9d 失败不落库", get_roadmap(headers_a, g7)["roadmap"] is None)

    print("用例 10：配置缺失")
    g8 = create_goal(headers_a, "未配置验证目标")
    with (
        patch.object(settings, "LLM_BASE_URL", ""),
        patch.object(settings, "LLM_API_KEY", ""),
        patch.object(settings, "LLM_MODEL", ""),
    ):
        llm.reset_clients()
        # 不 mock chat：走真实 chat() → get_chat_client() 在构造前即校验配置。
        resp = breakdown(headers_a, g8)
        client_not_built = llm._chat_client is None
    llm.reset_clients()
    body = resp.json()
    check("10a 3000/502", resp.status_code == 502 and body["code"] == 3000, resp.text)
    check("10b message 含「AI 服务未配置」", "AI 服务未配置" in body.get("message", ""), str(body))
    check("10c 客户端未构造（未发起上游请求）", client_not_built)
    check("10d 失败不落库", get_roadmap(headers_a, g8)["roadmap"] is None)

    # ---- 汇总与清理 --------------------------------------------------------
    print(f"\n结果：{len(PASSED)} PASS / {len(FAILED)} FAIL")
    if FAILED:
        print("失败用例：", FAILED)
    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.username == user_a))
        if user is not None:
            db.delete(user)
        db.commit()
    sys.exit(1 if FAILED else 0)


if __name__ == "__main__":
    main()