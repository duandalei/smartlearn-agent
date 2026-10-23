"""P10 Agent 工具层验收脚本（脱离 LLM 逐个验证 8 个工具）。

运行：cd backend && .venv/Scripts/python scripts/test_tools.py

验收标准映射（tasks.md 第 7 章）：
- 标准 1：G0–G10 用例矩阵全部 PASS、退出码 0；
- 标准 2：G0.1–G0.3 / G0.6（TOOLS_SCHEMA 结构 + 可序列化）；
  真实请求确认留本机冒烟（尾部「本机验证清单」）；
- 标准 3：真实 DeepSeek 冒烟（网络）——本机验证清单，不进沙箱脚本；
- 标准 4：G7 / G8 越权（真实他人资源）与不存在（大随机 id）合并文案
  一致断言、全程不抛异常。

离线策略（沙箱网络全禁）：
- sqlite 临时库（``tmp_verify/p10_tools.db``）+ Chroma 临时目录，
  环境变量优先级高于 ``.env``（P7/P9 已验证），运行前删除旧库规避
  sqlite data 锁脏残留；
- 在线向量化 monkeypatch 为不可用 → 本地兜底 → ``mode == "offline"``
  属 spec 4.2.2 验收路径（非缺陷），且避免沙箱在线重试超时；
- 不用 TestClient（工具层不经 HTTP），async 用例统一 ``asyncio.run``，
  每用例独立 ``with SessionLocal() as db`` 短事务（规避 sqlite data 锁）。
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import shutil
import sys
import time
from datetime import date, datetime, time as dt_time, timedelta, timezone
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# 环境隔离（必须在 import app 之前执行）
# ---------------------------------------------------------------------------
_SCRIPTS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(_SCRIPTS_DIR.parent))
sys.path.insert(0, str(_SCRIPTS_DIR))

_TMP_DIR = _SCRIPTS_DIR.parent / "tmp_verify"
_TMP_DIR.mkdir(exist_ok=True)
_TMP_DB = _TMP_DIR / "p10_tools.db"
_TMP_CHROMA = _TMP_DIR / "p10_chroma"
_TMP_UPLOADS = _TMP_DIR / "p10_uploads"
if _TMP_DB.exists():
    _TMP_DB.unlink()
shutil.rmtree(_TMP_CHROMA, ignore_errors=True)
shutil.rmtree(_TMP_UPLOADS, ignore_errors=True)
os.environ["DATABASE_URL"] = f"sqlite:///{_TMP_DB.as_posix()}"
os.environ["CHROMA_DIR"] = _TMP_CHROMA.as_posix()
os.environ["UPLOAD_DIR"] = _TMP_UPLOADS.as_posix()

import _sandbox_patch  # noqa: F401,E402 （IPv6 socketpair 补丁，无害防御）

# 在线向量化 monkeypatch 为不可用（模拟沙箱断网；本地兜底为真实路径）。
from app.core.response import BizException as _Biz  # noqa: E402

import app.rag.embedding as _embedding_module  # noqa: E402


def _embedding_unavailable() -> Any:
    raise _Biz(3000, "AI 服务未配置", http_status=502)


_embedding_module.get_embedding_client = _embedding_unavailable

from app.agent.registry import TOOLS_SCHEMA, TOOL_MAP  # noqa: E402
from app.agent import tools as tools_module  # noqa: E402
from app.core.response import BizException  # noqa: E402
from app.db.session import SessionLocal, engine  # noqa: E402
from app.models.base import Base  # noqa: E402
from app.models.course import Course  # noqa: E402
from app.models.enums import (  # noqa: E402
    KnowledgeItemStatus,
    KnowledgeScope,
    KnowledgeSourceType,
    MasterySource,
    Priority,
    TaskSource,
    TaskStatus,
)
from app.models.goal import LearningGoal  # noqa: E402
from app.models.knowledge import KnowledgeItem  # noqa: E402
from app.models.mastery import KnowledgeMastery  # noqa: E402
from app.models.record import LearningRecord  # noqa: E402
from app.models.task import Task  # noqa: E402
from app.models.user import User, UserProfile  # noqa: E402
from app.schemas.task import TaskCreate  # noqa: E402
from app.services.task import create_task as create_task_service  # noqa: E402
from app.services.task import TZ_BEIJING  # noqa: E402

PASSED: list[str] = []
FAILED: list[str] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    """逐项断言（沿用 verify_p7 的 check / PASSED / FAILED 模式）。"""
    if cond:
        PASSED.append(name)
        print(f"  [PASS] {name}")
    else:
        FAILED.append(name)
        print(f"  [FAIL] {name}  {detail}")


def call(tool_name: str, user_id: int, arguments: Any) -> dict[str, Any]:
    """经 TOOL_MAP 派发调用工具（每次新事件循环，独立短事务在外层开）。"""
    return asyncio.run(TOOL_MAP[tool_name](db, user_id, arguments))


# ---------------------------------------------------------------------------
# 造数（双用户 + 全场景数据底座；脚本作为测试基础设施可直插 ORM）
# ---------------------------------------------------------------------------
def seed_users() -> dict[str, int]:
    """直插三用户：user_a（主测）、user_b（越权对照）、user_c（空用户）。"""
    with SessionLocal() as session:
        users = [
            User(username="agent_a", email="agent_a@test.com", hashed_password="x"),
            User(username="agent_b", email="agent_b@test.com", hashed_password="x"),
            User(username="agent_c", email="agent_c@test.com", hashed_password="x"),
        ]
        session.add_all(users)
        session.flush()
        ids = {"a": users[0].id, "b": users[1].id, "c": users[2].id}
        session.commit()
    return ids


def seed_profile(user_ids: dict[str, int]) -> None:
    """user_a 显式建档（user_c 留空验证惰性默认）。"""
    with SessionLocal() as session:
        session.add(
            UserProfile(
                user_id=user_ids["a"],
                name="张三",
                school="示例大学",
                major="计算机科学",
                grade="大三",
                current_goal_type="考研",
                interest_directions=["机器学习", "算法"],
                daily_study_minutes=90,
            )
        )
        session.commit()


def _bj_today() -> date:
    """北京今天（日期敏感验收值动态计算口径）。"""
    return datetime.now(timezone.utc).astimezone(TZ_BEIJING).date()


def seed_tasks(user_ids: dict[str, int]) -> dict[str, int]:
    """user_a 任务矩阵（覆盖排序 / 过滤全场景）+ user_b 越权对照任务。"""
    today = _bj_today()

    def _dl(offset_days: int) -> datetime:
        return datetime(
            today.year, today.month, today.day, 12, 0, tzinfo=timezone.utc
        ) + timedelta(days=offset_days)

    with SessionLocal() as session:
        rows = {
            "t_past": Task(user_id=user_ids["a"], title="逾期任务", deadline=_dl(-3),
                           status=TaskStatus.TODO, priority=Priority.HIGH,
                           source=TaskSource.MANUAL),
            "t_future_1": Task(user_id=user_ids["a"], title="明日任务", deadline=_dl(1),
                               status=TaskStatus.TODO, priority=Priority.MEDIUM,
                               source=TaskSource.MANUAL),
            "t_future_2": Task(user_id=user_ids["a"], title="后日任务", deadline=_dl(2),
                               status=TaskStatus.IN_PROGRESS, priority=Priority.LOW,
                               source=TaskSource.MANUAL),
            "t_same_old": Task(user_id=user_ids["a"], title="同截止旧任务", deadline=_dl(3),
                               status=TaskStatus.TODO, priority=Priority.MEDIUM,
                               source=TaskSource.MANUAL),
            "t_same_new": Task(user_id=user_ids["a"], title="同截止新任务", deadline=_dl(3),
                               status=TaskStatus.TODO, priority=Priority.MEDIUM,
                               source=TaskSource.MANUAL),
            "t_no_deadline": Task(user_id=user_ids["a"], title="无截止任务",
                                  status=TaskStatus.TODO, priority=Priority.LOW,
                                  source=TaskSource.MANUAL),
            "t_done": Task(user_id=user_ids["a"], title="已完成任务", deadline=_dl(-1),
                           status=TaskStatus.DONE, priority=Priority.MEDIUM,
                           source=TaskSource.MANUAL),
            "t_review": Task(user_id=user_ids["a"], title="待复盘任务", deadline=_dl(-2),
                             status=TaskStatus.REVIEW, priority=Priority.MEDIUM,
                             source=TaskSource.MANUAL),
            "b_task": Task(user_id=user_ids["b"], title="用户B的任务",
                           status=TaskStatus.TODO, priority=Priority.MEDIUM,
                           source=TaskSource.MANUAL),
        }
        session.add_all(rows.values())
        session.flush()
        ids = {name: row.id for name, row in rows.items()}
        session.commit()
    return ids


def seed_records_and_courses(user_ids: dict[str, int]) -> dict[str, int]:
    """user_a 学习记录（今天 / 昨天 / 前天）+ 双方课程 + 双方目标。"""
    today = _bj_today()
    with SessionLocal() as session:
        course_a = Course(user_id=user_ids["a"], name="机器学习导论", semester="2026春")
        course_b = Course(user_id=user_ids["b"], name="用户B的课程", semester="2026春")
        goal_a = LearningGoal(user_id=user_ids["a"], title="考研上岸",
                              start_date=today - timedelta(days=30))
        goal_b = LearningGoal(user_id=user_ids["b"], title="用户B的目标",
                              start_date=today - timedelta(days=30))
        session.add_all([course_a, course_b, goal_a, goal_b])
        session.flush()
        session.add_all([
            LearningRecord(user_id=user_ids["a"], course_id=course_a.id,
                           content="学习线性代数", duration_minutes=60,
                           achievement="完成第二章", problems=None,
                           knowledge_points=["线性代数"], mastery_level=45,
                           study_date=today),
            LearningRecord(user_id=user_ids["a"], course_id=course_a.id,
                           content="学习概率论", duration_minutes=90,
                           achievement="完成例题", problems="贝叶斯公式不熟",
                           knowledge_points=["概率论"], mastery_level=55,
                           study_date=today - timedelta(days=1)),
            LearningRecord(user_id=user_ids["a"], course_id=None,
                           content="阅读论文", duration_minutes=45,
                           achievement=None, problems=None,
                           knowledge_points=["机器学习基础"], mastery_level=80,
                           study_date=today - timedelta(days=2)),
        ])
        session.commit()
        return {"course_a": course_a.id, "course_b": course_b.id,
                "goal_a": goal_a.id, "goal_b": goal_b.id}


def seed_mastery(user_ids: dict[str, int]) -> None:
    """user_a 掌握度：3 条非零 + 1 条零分待学点（验证排除口径）。"""
    with SessionLocal() as session:
        session.add_all([
            KnowledgeMastery(user_id=user_ids["a"], knowledge_point="线性代数",
                             mastery_score=30, source=MasterySource.SELF_REPORT),
            KnowledgeMastery(user_id=user_ids["a"], knowledge_point="概率论",
                             mastery_score=55, source=MasterySource.RECORD),
            KnowledgeMastery(user_id=user_ids["a"], knowledge_point="机器学习基础",
                             mastery_score=80, source=MasterySource.SELF_REPORT),
            KnowledgeMastery(user_id=user_ids["a"], knowledge_point="新拆解待学点",
                             mastery_score=0, source=MasterySource.GOAL_BREAKDOWN),
        ])
        session.commit()


def seed_knowledge(user_ids: dict[str, int]) -> dict[str, Any]:
    """知识库：公共 4 篇 + user_a / user_b 各 1 篇个人文档（离线流水线）。

    公共档按 ``data/public_kb/*.md`` 建档（模拟 db/init_db.py 种子），
    个人档写入临时 md 后直插（scope=personal），统一经
    ``process_document`` 走真实离线索引（本地兜底向量化真实入 Chroma）。
    """
    from app.core.config import PROJECT_ROOT
    from app.services.knowledge import process_document

    titles: dict[str, str] = {}
    personal_files: list[tuple[int, str, str]] = []
    with SessionLocal() as session:
        kb_dir = PROJECT_ROOT / "data" / "public_kb"
        files = sorted(kb_dir.glob("*.md"))
        assert files, f"公共文档种子目录为空: {kb_dir}"
        item_ids: list[int] = []
        for md_file in files:
            item = KnowledgeItem(
                user_id=None,
                title=md_file.stem,
                source_type=KnowledgeSourceType.MD,
                file_path=f"data/public_kb/{md_file.name}",
                scope=KnowledgeScope.PUBLIC,
                status=KnowledgeItemStatus.PENDING,
                chunk_count=0,
                file_size=md_file.stat().st_size,
            )
            session.add(item)
            session.flush()
            item_ids.append(item.id)
            titles[item.id] = md_file.stem
        upload_dir = Path(os.environ["UPLOAD_DIR"])
        for uid, stem, body in [
            (user_ids["a"], "用户A私有笔记",
             "# 用户A私有笔记\n\nTransformer 的自注意力机制把序列中每个位置的元素两两之间"
             "计算相关性权重，再对加权后的值向量求和得到输出表示。该机制使得模型能够在"
             "任意距离的词之间直接建立信息传递路径，用户A独有的学习笔记资料。"),
            (user_ids["b"], "用户B私有笔记",
             "# 用户B私有笔记\n\n卷积神经网络通过堆叠卷积层逐层扩大感受野，浅层提取边缘与"
             "纹理等局部特征，深层组合出语义更强的抽象表示。池化层在降采样同时保留显著"
             "特征，用户B独有的学习笔记资料。"),
        ]:
            target = upload_dir / str(uid) / f"p10_{stem}.md"
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(body, encoding="utf-8")
            item = KnowledgeItem(
                user_id=uid,
                title=stem,
                source_type=KnowledgeSourceType.MD,
                file_path=target.resolve().as_posix(),
                scope=KnowledgeScope.PERSONAL,
                status=KnowledgeItemStatus.PENDING,
                chunk_count=0,
                file_size=len(body.encode("utf-8")),
            )
            session.add(item)
            session.flush()
            personal_files.append((item.id, stem, body))
            titles[item.id] = stem
        session.commit()
    for item_id in item_ids:
        asyncio.run(process_document(item_id))
    for item_id, _stem, _body in personal_files:
        asyncio.run(process_document(item_id))
    return {"titles": titles, "personal": {stem: item_id for item_id, stem, _ in personal_files}}


# ---------------------------------------------------------------------------
# G0 注册表与 schema 横切断言
# ---------------------------------------------------------------------------
def g0_registry() -> None:
    print("G0 注册表与 schema 横切断言：")
    names = [s["function"]["name"] for s in TOOLS_SCHEMA]
    expected = {
        "get_user_profile", "get_learning_records", "get_tasks",
        "get_knowledge_mastery", "get_learning_statistics",
        "search_knowledge_base", "create_task", "update_task",
        "get_learning_plan", "generate_learning_plan",
        "adjust_learning_plan", "generate_learning_report",
    }
    check("G0.1 TOOLS_SCHEMA 恰 12 个且名称一一对应（P12：8→12）",
          len(TOOLS_SCHEMA) == 12 and set(names) == expected, f"{names}")
    check("G0.2 TOOL_MAP 键集合与 schema 工具名一致",
          set(TOOL_MAP) == set(names))

    g03 = g04 = True
    for schema in TOOLS_SCHEMA:
        func = schema["function"]
        ok = (
            schema["type"] == "function"
            and set(func) == {"name", "description", "parameters"}
        )
        params_text = json.dumps(func["parameters"])
        ok = ok and "$defs" not in params_text and "$ref" not in params_text
        ok = ok and "anyOf" not in params_text
        ok = ok and func["parameters"].get("additionalProperties") is False
        g03 = g03 and ok
        if "user_id" in func["parameters"].get("properties", {}):
            g04 = False
    check("G0.3 每个-schema 扁平（无 $defs/$ref/anyOf）且 additionalProperties=false", g03)
    check("G0.4 无任何工具含 user_id 属性", g04)

    model_fields = {
        "get_user_profile": [],
        "get_learning_records": ["days", "course_id"],
        "get_tasks": ["status", "due_before"],
        "get_knowledge_mastery": ["topic"],
        "get_learning_statistics": ["days"],
        "search_knowledge_base": ["query", "top_k", "scope"],
        "create_task": ["title", "description", "goal_id", "course_id",
                        "knowledge_points", "priority", "estimated_minutes", "deadline"],
        "update_task": ["task_id", "title", "description", "goal_id", "course_id",
                        "knowledge_points", "priority", "estimated_minutes",
                        "actual_minutes", "deadline", "scheduled_date"],
        "get_learning_plan": [],
        "generate_learning_plan": [],
        "adjust_learning_plan": ["plan_id"],
        "generate_learning_report": ["report_type"],
    }
    g04b = all(
        set(s["function"]["parameters"].get("properties", {})) == set(model_fields[s["function"]["name"]])
        for s in TOOLS_SCHEMA
    )
    check("G0.4b properties 键集合与参数模型字段集合一致", g04b)

    p12_names = {"get_learning_plan", "generate_learning_plan",
                 "adjust_learning_plan", "generate_learning_report"}
    registry_source = (_SCRIPTS_DIR.parent / "app" / "agent" / "registry.py").read_text(
        encoding="utf-8"
    )
    g05 = (
        p12_names == set(names) & p12_names
        and p12_names <= set(TOOL_MAP)
        and "P12 接入" in registry_source
        and all(n in registry_source for n in p12_names)
    )
    check("G0.5 已注册 4 个 P12 工具名且 docstring 含「P12 接入」交付说明", g05)

    try:
        json.dumps(TOOLS_SCHEMA)
        serializable = True
    except (TypeError, ValueError):
        serializable = False
    check("G0.6 TOOLS_SCHEMA 可整体 json.dumps", serializable)
    mastery_desc = next(
        s["function"]["description"] for s in TOOLS_SCHEMA
        if s["function"]["name"] == "get_knowledge_mastery"
    )
    check("G0.6b mastery description 逐字含「不含尚未开始学习的知识点」（裁定④）",
          "不含尚未开始学习的知识点" in mastery_desc)
    stats_desc = next(
        s["function"]["description"] for s in TOOLS_SCHEMA
        if s["function"]["name"] == "get_learning_statistics"
    )
    check("G0.6c statistics description 区分七指标全量累计与 trend 窗口口径",
          "全部历史累计" in stats_desc and "近 N 天窗口趋势" in stats_desc)


def g0_json_serializable_results(user_ids: dict[str, int], task_ids: dict[str, int],
                                 refs: dict[str, int]) -> None:
    print("G0.7 每个工具成功返回值可 json.dumps（无 ORM 残留）：")
    with SessionLocal() as session:
        global db
        db = session
        samples = {
            "get_user_profile": call("get_user_profile", user_ids["a"], {}),
            "get_learning_records": call("get_learning_records", user_ids["a"], {"days": 7}),
            "get_tasks": call("get_tasks", user_ids["a"], {}),
            "get_knowledge_mastery": call("get_knowledge_mastery", user_ids["a"], {}),
            "get_learning_statistics": call("get_learning_statistics", user_ids["a"], {"days": 7}),
            "search_knowledge_base": call("search_knowledge_base", user_ids["a"],
                                          {"query": "注意力机制", "top_k": 3}),
            "create_task": call("create_task", user_ids["a"], {"title": "G0.7 序列化探针任务"}),
            "update_task": call("update_task", user_ids["a"],
                                {"task_id": task_ids["t_future_1"], "estimated_minutes": 30}),
        }
    ok = True
    for tool_name, result in samples.items():
        try:
            json.dumps(result)
        except (TypeError, ValueError) as exc:
            ok = False
            print(f"    {tool_name} 不可序列化: {exc}")
    check("G0.7 八工具成功返回值均可 json.dumps", ok)
    _ = refs


# ---------------------------------------------------------------------------
# G1–G8 八工具正常路径与横切异常路径
# ---------------------------------------------------------------------------
def g1_user_profile(user_ids: dict[str, int]) -> None:
    print("G1 get_user_profile：")
    with SessionLocal() as session:
        global db
        db = session
        result = call("get_user_profile", user_ids["a"], {})
    fields_ok = (
        result.get("name") == "张三"
        and result.get("school") == "示例大学"
        and result.get("major") == "计算机科学"
        and result.get("grade") == "大三"
        and result.get("current_goal_type") == "考研"
        and result.get("interest_directions") == ["机器学习", "算法"]
        and result.get("daily_study_minutes") == 90
    )
    check("G1.1 完整字段断言（name/school/major/grade/goal/interests/daily）", fields_ok,
          str(result)[:200])

    with SessionLocal() as session:
        db = session
        result = call("get_user_profile", user_ids["c"], {})
    check("G1.2 无档案用户惰性默认（daily_study_minutes=60）",
          result.get("daily_study_minutes") == 60 and "error" not in result)

    with SessionLocal() as session:
        db = session
        result = call("get_user_profile", user_ids["a"], {"foo": 1})
    check("G1.3 多余参数 → error 且零字段专属文案",
          "error" in result and "不接受任何参数" in result["error"], str(result))

    with SessionLocal() as session:
        db = session
        result = call("get_user_profile", user_ids["a"], {"user_id": user_ids["a"]})
    check("G1.4 传 user_id → error「user_id 由系统注入，禁止传入」",
          "error" in result and "user_id 由系统注入" in result["error"], str(result))


def g2_learning_records(user_ids: dict[str, int], refs: dict[str, int]) -> None:
    print("G2 get_learning_records：")
    today = _bj_today()
    with SessionLocal() as session:
        global db
        db = session
        r7 = call("get_learning_records", user_ids["a"], {"days": 7})
        r30 = call("get_learning_records", user_ids["a"], {"days": 30})
    check("G2.1 days=7 窗口起止（首=今天−6、末=北京今天）",
          r7.get("start_date") == (today - timedelta(days=6)).isoformat()
          and r7.get("end_date") == today.isoformat(),
          f"{r7.get('start_date')}~{r7.get('end_date')}")
    check("G2.2 days=30 窗口起止（首=今天−29）",
          r30.get("start_date") == (today - timedelta(days=29)).isoformat())
    dates = [rec["study_date"] for rec in r7.get("records", [])]
    check("G2.3 记录按学习日期降序", dates == sorted(dates, reverse=True), str(dates))
    check("G2.4 total=3 且 records 含 content/duration/mastery_level 字段",
          r7.get("total") == 3 and all(
              {"content", "duration_minutes", "mastery_level", "study_date"} <= set(rec)
              for rec in r7.get("records", [])))

    with SessionLocal() as session:
        db = session
        other = call("get_learning_records", user_ids["a"], {"course_id": refs["course_b"]})
    check("G2.5 他人 course_id → records=[] 非 error",
          "error" not in other and other.get("records") == [] and other.get("total") == 0,
          str(other))

    with SessionLocal() as session:
        db = session
        e0 = call("get_learning_records", user_ids["a"], {"days": 0})
        e366 = call("get_learning_records", user_ids["a"], {"days": 366})
        eabc = call("get_learning_records", user_ids["a"], {"days": "abc"})
        eneg = call("get_learning_records", user_ids["a"], {"course_id": -1})
    check("G2.6 days=0 → error 含 1–365",
          "error" in e0 and "1–365" in e0["error"], str(e0))
    check("G2.7 days=366 → error 含 1–365",
          "error" in e366 and "1–365" in e366["error"], str(e366))
    check("G2.8 days='abc' → error 含整数提示",
          "error" in eabc and "整数" in eabc["error"], str(eabc))
    check("G2.9 course_id=-1 → error 含正整数",
          "error" in eneg and "正整数" in eneg["error"], str(eneg))


def g3_tasks(user_ids: dict[str, int], task_ids: dict[str, int]) -> None:
    print("G3 get_tasks：")
    with SessionLocal() as session:
        global db
        db = session
        result = call("get_tasks", user_ids["a"], {})
    tasks = result.get("tasks", [])
    got_titles = [t["title"] for t in tasks]
    # G0.7 已追加 1 条无截止探针任务（id 最大 → 无截止组内排最前）。
    expected_order = ["逾期任务", "待复盘任务", "已完成任务", "明日任务", "后日任务",
                      "同截止新任务", "同截止旧任务", "G0.7 序列化探针任务", "无截止任务"]
    check("G3.1 混合集排序（有截止升序在前、同截止新建在前、无截止最后）",
          got_titles == expected_order, f"{got_titles}")
    check("G3.2 total=9（含 G0.7 探针）且 tasks ≤ 100 截断",
          result.get("total") == 9 and len(tasks) <= 100)

    with SessionLocal() as session:
        db = session
        todo_only = call("get_tasks", user_ids["a"], {"status": "todo"})
        done_only = call("get_tasks", user_ids["a"], {"status": "done"})
    check("G3.3 status 过滤（todo=6 / done=1，过滤后全部同状态）",
          todo_only.get("total") == 6 and done_only.get("total") == 1
          and all(t["status"] == "todo" for t in todo_only.get("tasks", [])),
          f"{todo_only.get('total')}/{done_only.get('total')}")

    today = _bj_today()
    date_form = (today + timedelta(days=2)).isoformat()
    dt_form = datetime.combine(
        today + timedelta(days=2), dt_time(23, 59, 59), tzinfo=TZ_BEIJING
    ).isoformat()
    with SessionLocal() as session:
        db = session
        no_cutoff = call("get_tasks", user_ids["a"], {})
        by_date = call("get_tasks", user_ids["a"], {"due_before": date_form})
        by_dt = call("get_tasks", user_ids["a"], {"due_before": dt_form})
    check("G3.4 不传 due_before 时无截止任务在场",
          any(t["title"] == "无截止任务" for t in no_cutoff.get("tasks", [])))
    expected_filtered = ["逾期任务", "待复盘任务", "已完成任务", "明日任务", "后日任务"]
    check("G3.5 date 形式过滤（无截止被排除、当日任务在场）",
          [t["title"] for t in by_date.get("tasks", [])] == expected_filtered,
          str([t["title"] for t in by_date.get("tasks", [])]))
    check("G3.6 datetime 形式与 date 形式同界（北京当日 23:59:59 = 次日 00:00）",
          [t["title"] for t in by_dt.get("tasks", [])] == expected_filtered)

    with SessionLocal() as session:
        db = session
        bad_status = call("get_tasks", user_ids["a"], {"status": "finished"})
        bad_due = call("get_tasks", user_ids["a"], {"due_before": "明天"})
        empty_user = call("get_tasks", user_ids["c"], {})
    check("G3.7 status='finished' → error 含四枚举",
          "error" in bad_status and "todo" in bad_status["error"] and "review" in bad_status["error"],
          str(bad_status))
    check("G3.8 due_before='明天' → error 含 ISO 示例",
          "error" in bad_due and "ISO 8601" in bad_due["error"], str(bad_due))
    check("G3.9 空用户 → {tasks: [], total: 0}",
          empty_user == {"tasks": [], "total": 0}, str(empty_user))
    _ = task_ids


def g4_mastery(user_ids: dict[str, int]) -> None:
    print("G4 get_knowledge_mastery：")
    with SessionLocal() as session:
        global db
        db = session
        result = call("get_knowledge_mastery", user_ids["a"], {})
    items = result.get("items", [])
    scores = [it["mastery_score"] for it in items]
    names = [it["knowledge_point"] for it in items]
    check("G4.1 全量升序且不含零分待学点",
          scores == sorted(scores) and "新拆解待学点" not in names and result.get("total") == 3,
          str(names))
    with SessionLocal() as session:
        db = session
        topic = call("get_knowledge_mastery", user_ids["a"], {"topic": "概率论"})
        miss = call("get_knowledge_mastery", user_ids["a"], {"topic": "不存在的知识点"})
        empty_str = call("get_knowledge_mastery", user_ids["a"], {"topic": ""})
        wrong_type = call("get_knowledge_mastery", user_ids["a"], {"topic": 123})
    check("G4.2 topic 全名精确命中单条",
          topic.get("total") == 1 and topic.get("items", [{}])[0].get("mastery_score") == 55,
          str(topic))
    check("G4.3 topic 无命中 → 空列表非 error",
          miss.get("items") == [] and miss.get("total") == 0 and "error" not in miss)
    check("G4.4 topic='' → error（非全量语义特例文案）",
          "error" in empty_str and "省略该参数" in empty_str["error"], str(empty_str))
    check("G4.5 topic=123 → error 非空字符串",
          "error" in wrong_type and "非空字符串" in wrong_type["error"], str(wrong_type))


def g5_statistics(user_ids: dict[str, int]) -> None:
    print("G5 get_learning_statistics：")
    with SessionLocal() as session:
        global db
        db = session
        result = call("get_learning_statistics", user_ids["a"], {"days": 14})
        fresh = call("get_learning_statistics", user_ids["c"], {"days": 7})
    seven = {"total_minutes", "task_completion_rate", "avg_mastery", "streak_days",
             "total_record_count", "avg_session_minutes", "overdue_task_count"}
    check("G5.1 七指标平铺顶层 + trend 子对象",
          seven <= set(result) and "trend" in result, str(list(result)))
    trend = result.get("trend", {})
    today = _bj_today()
    items = trend.get("items", [])
    check("G5.2 days=14 → items 恰 14 条且末条北京今天",
          len(items) == 14 and items and items[-1]["date"] == today.isoformat()
          and trend.get("days") == 14,
          f"len={len(items)} last={items[-1]['date'] if items else None}")
    zero_days = [it for it in items if it["minutes"] == 0]
    check("G5.3 无记录日 minutes=0（补零序列）", len(zero_days) >= 1)
    check("G5.4 新用户七指标全 0 且 risk_alert=null",
          all(fresh.get(f) == 0 for f in seven) and fresh.get("trend", {}).get("risk_alert") is None,
          str({f: fresh.get(f) for f in seven}))

    with SessionLocal() as session:
        db = session
        bad = call("get_learning_statistics", user_ids["a"], {"days": 400})
    check("G5.5 days=400 → error 含 1–365",
          "error" in bad and "1–365" in bad["error"], str(bad))


def g6_search(user_ids: dict[str, int], kb: dict[str, Any]) -> None:
    print("G6 search_knowledge_base：")
    with SessionLocal() as session:
        global db
        db = session
        result = call("search_knowledge_base", user_ids["a"],
                      {"query": "注意力机制", "top_k": 5})
        personal = call("search_knowledge_base", user_ids["a"],
                        {"query": "注意力机制", "scope": "personal"})
        public_only = call("search_knowledge_base", user_ids["a"],
                           {"query": "注意力机制", "scope": "public"})
        b_personal = call("search_knowledge_base", user_ids["b"],
                          {"query": "注意力机制", "scope": "personal"})
        miss = call("search_knowledge_base", user_ids["a"],
                    {"query": "量子纠缠背后的咖啡烘焙工艺", "top_k": 3})
    six = {"content", "source_title", "score", "item_id", "chunk_index", "scope"}
    results = result.get("results", [])
    check("G6.1 命中结构（mode + 六字段 + score 降序 + ≤top_k）",
          result.get("mode") in ("online", "offline") and results and all(
              six <= set(r) for r in results) and len(results) <= 5
          and [r["score"] for r in results] == sorted((r["score"] for r in results), reverse=True),
          str(result)[:200])
    check("G6.2 沙箱降级验收路径（mode == 'offline'）",
          result.get("mode") == "offline", result.get("mode", ""))
    a_titles = {kb["titles"].get(r["item_id"], "") for r in personal.get("results", [])}
    check("G6.3 scope=personal 仅本人个人库（不含公共与他人文档）",
          personal.get("results") and a_titles == {"用户A私有笔记"},
          str(a_titles))
    p_scopes = {r["scope"] for r in public_only.get("results", [])}
    check("G6.4 scope=public 仅公共文档", public_only.get("results") and p_scopes == {"public"},
          str(p_scopes))
    check("G6.5 用户B的personal档不含用户A文档（双层库隔离）",
          all(r["item_id"] != kb["personal"]["用户A私有笔记"]
              for r in b_personal.get("results", [])),
          str(b_personal)[:200])
    relevant_max = max((r["score"] for r in results), default=0.0)
    miss_max = max((r["score"] for r in miss.get("results", [])), default=0.0)
    check("G6.6 无相关词 → score 显著低于相关词（或空 results）",
          "error" not in miss and miss_max < relevant_max,
          f"miss_max={miss_max} relevant_max={relevant_max}")

    with SessionLocal() as session:
        db = session
        e_empty = call("search_knowledge_base", user_ids["a"], {"query": ""})
        e_long = call("search_knowledge_base", user_ids["a"], {"query": "长" * 501})
        e_topk = call("search_knowledge_base", user_ids["a"], {"query": "x", "top_k": 0})
        e_scope = call("search_knowledge_base", user_ids["a"], {"query": "x", "scope": "xxx"})
    check("G6.7 query 空串 → error 含长度上限",
          "error" in e_empty and "1–500" in e_empty["error"], str(e_empty))
    check("G6.8 query 501 字符 → error 含长度上限",
          "error" in e_long and "1–500" in e_long["error"], str(e_long)[:120])
    check("G6.9 top_k=0 → error 含 1–20",
          "error" in e_topk and "1–20" in e_topk["error"], str(e_topk))
    check("G6.10 scope='xxx' → error 含合法枚举",
          "error" in e_scope and "personal" in e_scope["error"] and "all" in e_scope["error"],
          str(e_scope))


def _task_count(user_id: int) -> int:
    with SessionLocal() as session:
        rows = session.query(Task).filter(Task.user_id == user_id).all()
        return len(rows)


def g7_create_task(user_ids: dict[str, int], refs: dict[str, int]) -> None:
    print("G7 create_task：")
    with SessionLocal() as session:
        global db
        db = session
        result = call("create_task", user_ids["a"], {"title": "AI帮我加的任务"})
    check("G7.1 仅 title 成功（status=todo、source=agent、id 非空）",
          result.get("status") == "todo" and result.get("source") == "agent"
          and result.get("id") is not None and result.get("title") == "AI帮我加的任务",
          str(result)[:200])

    today = _bj_today()
    with SessionLocal() as session:
        db = session
        full = call("create_task", user_ids["a"], {
            "title": "全字段任务", "description": "描述",
            "goal_id": refs["goal_a"], "course_id": refs["course_a"],
            "knowledge_points": ["线性代数", "概率论"], "priority": "high",
            "estimated_minutes": 45, "deadline": (today + timedelta(days=4)).isoformat(),
        })
    check("G7.2 全字段创建成功（goal/course 归属通过、date 形式 deadline）",
          full.get("id") is not None and full.get("priority") == "high"
          and full.get("goal_id") == refs["goal_a"] and full.get("deadline") is not None,
          str(full)[:200])

    with SessionLocal() as session:
        db = session
        manual = create_task_service(session, user_ids["a"],
                                      TaskCreate(title="P5路径手工任务"))
    check("G7.3 service 直调（不传 source）→ source=manual（P5 兼容双路径，裁定①）",
          manual.get("source") == "manual", str(manual)[:120])

    with SessionLocal() as session:
        db = session
        e_prio = call("create_task", user_ids["a"], {"title": "x", "priority": "urgent"})
        e_title = call("create_task", user_ids["a"], {"title": ""})
        e_mins = call("create_task", user_ids["a"], {"title": "x", "estimated_minutes": 0})
        e_kps = call("create_task", user_ids["a"], {"title": "x", "knowledge_points": [f"kp{i}" for i in range(21)]})
        e_dl = call("create_task", user_ids["a"], {"title": "x", "deadline": "下周五"})
    check("G7.4 priority='urgent' → error 含三枚举",
          "error" in e_prio and "low" in e_prio["error"] and "high" in e_prio["error"], str(e_prio))
    check("G7.5 title='' → error 含 1–200",
          "error" in e_title and "1–200" in e_title["error"], str(e_title))
    check("G7.6 estimated_minutes=0 → error 正整数",
          "error" in e_mins and "正整数" in e_mins["error"], str(e_mins))
    check("G7.7 knowledge_points 21 个 → error 最多 20",
          "error" in e_kps and "20" in e_kps["error"], str(e_kps)[:120])
    check("G7.8 deadline='下周五' → error 含 ISO 示例",
          "error" in e_dl and "ISO 8601" in e_dl["error"], str(e_dl))

    before = _task_count(user_ids["a"])
    with SessionLocal() as session:
        db = session
        e_status = call("create_task", user_ids["a"], {"title": "x", "status": "done"})
        e_uid = call("create_task", user_ids["a"], {"title": "x", "user_id": user_ids["b"]})
        e_source = call("create_task", user_ids["a"], {"title": "x", "source": "manual"})
    after = _task_count(user_ids["a"])
    check("G7.9 传 status/user_id/source → error 且无任务落库（user_id 命中注入特例）",
          "error" in e_status and "title" in e_status["error"]
          and e_uid.get("error") == "user_id 由系统注入，禁止传入"
          and "error" in e_source and "title" in e_source["error"]
          and after == before,
          f"{e_status}|{e_uid}|{e_source}|{before}->{after}")

    before = _task_count(user_ids["a"])
    with SessionLocal() as session:
        db = session
        e_goal = call("create_task", user_ids["a"], {"title": "x", "goal_id": refs["goal_b"]})
        e_course = call("create_task", user_ids["a"], {"title": "x", "course_id": refs["course_b"]})
    after = _task_count(user_ids["a"])
    check("G7.10 他人 goal_id/course_id → error 合并文案且无任务落库",
          "error" in e_goal and "不属于当前用户" in e_goal["error"]
          and "error" in e_course and "不属于当前用户" in e_course["error"]
          and after == before,
          f"{e_goal}|{e_course}|{before}->{after}")


def g8_update_task(user_ids: dict[str, int], task_ids: dict[str, int],
                   refs: dict[str, int]) -> None:
    print("G8 update_task：")
    with SessionLocal() as session:
        global db
        db = session
        before = call("get_tasks", user_ids["a"], {})
    target = next(t for t in before["tasks"] if t["title"] == "明日任务")
    with SessionLocal() as session:
        db = session
        updated = call("update_task", user_ids["a"],
                       {"task_id": target["id"], "title": "明日任务（改名）"})
    diff_keys = [k for k in target if target[k] != updated.get(k)]
    check("G8.1 改 title 仅 title 变（其余字段前后快照一致）",
          updated.get("title") == "明日任务（改名）" and diff_keys == ["title", "updated_at"],
          f"diff={diff_keys}")

    desc_task = next(t for t in before["tasks"] if t["title"] == "后日任务")
    with SessionLocal() as session:
        db = session
        null_case = call("update_task", user_ids["a"],
                         {"task_id": desc_task["id"], "description": None})
    check("G8.2 description=null → 成功且原值保持（null 不清空）",
          "error" not in null_case and null_case.get("description") == desc_task["description"],
          str(null_case.get("description")))

    with SessionLocal() as session:
        db = session
        empty_update = call("update_task", user_ids["a"], {"task_id": target["id"]})
    check("G8.3 空更新（仅 task_id）→ error 提示至少一个字段",
          "error" in empty_update and "至少提供一个" in empty_update["error"], str(empty_update))

    with SessionLocal() as session:
        db = session
        foreign = call("update_task", user_ids["a"], {"task_id": task_ids["b_task"], "title": "x"})
        missing = call("update_task", user_ids["a"], {"task_id": 999999, "title": "x"})
    check("G8.4 越权（user_b 真实任务）与不存在（大随机 id）→ error 文案一致（合并表述，验收标准 4）",
          foreign.get("error") == missing.get("error") and "error" in foreign
          and "不属于当前用户" in foreign["error"] and "get_tasks" in foreign["error"],
          f"越权={foreign} 不存在={missing}")

    with SessionLocal() as session:
        db = session
        e_status = call("update_task", user_ids["a"],
                        {"task_id": target["id"], "status": "done"})
    with SessionLocal() as session:
        still = session.get(Task, target["id"])
        status_unchanged = still.status.value == "todo"
    check("G8.5 status='done' → error 含「不支持修改 status」且任务状态不变",
          "error" in e_status and "不支持修改 status" in e_status["error"]
          and "任务页" in e_status["error"] and status_unchanged,
          f"{e_status}|status={still.status.value}")

    with SessionLocal() as session:
        db = session
        e_foo = call("update_task", user_ids["a"], {"task_id": target["id"], "foo": 1})
        e_source = call("update_task", user_ids["a"], {"task_id": target["id"], "source": "agent"})
        e_completed = call("update_task", user_ids["a"], {"task_id": target["id"], "completed_at": "2026-01-01T00:00:00"})
        e_missing_id = call("update_task", user_ids["a"], {"title": "x"})
    check("G8.6 foo/source/completed_at → error 含合法字段清单",
          all("error" in e and "合法参数为" in e["error"] and "scheduled_date" in e["error"]
              for e in (e_foo, e_source, e_completed)),
          f"{e_foo}|{e_source}|{e_completed}")
    check("G8.7 task_id 缺失 → error 必填提示",
          "error" in e_missing_id and "task_id" in e_missing_id["error"], str(e_missing_id))

    with SessionLocal() as session:
        db = session
        before_task = call("get_tasks", user_ids["a"], {})
        e_course = call("update_task", user_ids["a"],
                        {"task_id": target["id"], "course_id": refs["course_b"]})
        after_task = call("get_tasks", user_ids["a"], {})
    after_target = next(t for t in after_task["tasks"] if t["id"] == target["id"])
    before_target = next(t for t in before_task["tasks"] if t["id"] == target["id"])
    check("G8.8 他人 course_id 更新 → error 合并文案且任务未变",
          "error" in e_course and "不属于当前用户" in e_course["error"]
          and after_target["course_id"] == before_target["course_id"],
          f"{e_course}|course_id={after_target['course_id']}")

    with SessionLocal() as session:
        db = session
        sched = call("update_task", user_ids["a"],
                     {"task_id": target["id"], "scheduled_date": (_bj_today() + timedelta(days=1)).isoformat()})
        e_sched = call("update_task", user_ids["a"],
                       {"task_id": target["id"], "scheduled_date": "明天"})
    check("G8.9 scheduled_date 合法 ISO 成功 / 非法 → error 含格式示例",
          sched.get("scheduled_date") is not None
          and "error" in e_sched and "ISO 日期格式" in e_sched["error"],
          f"{sched.get('scheduled_date')}|{e_sched}")


# ---------------------------------------------------------------------------
# G9 慢日志（monkeypatch 注入 sleep，不依赖真实慢查询）
# ---------------------------------------------------------------------------
class _LogCollector(logging.Handler):
    """自装 logging handler（捕获 app.agent.tools 的 warning 记录）。"""

    def __init__(self) -> None:
        super().__init__()
        self.records: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.records.append(self.format(record))


def g9_slow_log(user_ids: dict[str, int]) -> None:
    print("G9 慢日志（monkeypatch 注入 sleep(0.4)）：")
    real_get_board = tools_module.get_board

    def slow_get_board(session: Any, uid: int) -> dict[str, Any]:
        time.sleep(0.4)
        return real_get_board(session, uid)

    tools_module.get_board = slow_get_board
    collector = _LogCollector()
    tools_logger = logging.getLogger("app.agent.tools")
    tools_logger.addHandler(collector)
    tools_logger.setLevel(logging.WARNING)
    formatter = logging.Formatter("%(message)s")
    collector.setFormatter(formatter)
    try:
        with SessionLocal() as session:
            global db
            db = session
            result = call("get_tasks", user_ids["a"], {})
    finally:
        tools_module.get_board = real_get_board
        tools_logger.removeHandler(collector)
    slow_records = [r for r in collector.records if "agent_tool_slow" in r]
    check("G9.1 >300ms 触发 warning（含工具名/user_id/elapsed_ms 三字段）",
          bool(slow_records) and "tool_name=get_tasks" in slow_records[0]
          and f"user_id={user_ids['a']}" in slow_records[0]
          and "elapsed_ms=" in slow_records[0],
          str(slow_records))
    check("G9.2 elapsed_ms ≥ 400（sleep 注入生效）",
          bool(slow_records) and all(_extract_ms(r) >= 400 for r in slow_records),
          str(slow_records))
    check("G9.3 日志脱敏（不含任务标题等业务数据）",
          bool(slow_records) and "明日任务" not in slow_records[0]
          and "无截止任务" not in slow_records[0],
          str(slow_records))
    check("G9.4 慢日志不影响返回值（任务完整返回）",
          result.get("total", 0) >= 8, str(result.get("total")))


def _extract_ms(record_text: str) -> int:
    for chunk in record_text.split():
        if chunk.startswith("elapsed_ms="):
            try:
                return int(chunk.split("=", 1)[1])
            except ValueError:
                return -1
    return -1


# ---------------------------------------------------------------------------
# G10 arguments 防御
# ---------------------------------------------------------------------------
def g10_arguments_defense(user_ids: dict[str, int]) -> None:
    print("G10 arguments 防御：")
    with SessionLocal() as session:
        global db
        db = session
        as_str = call("get_user_profile", user_ids["a"], "不是dict")  # type: ignore[arg-type]
        as_none = call("get_tasks", user_ids["a"], None)  # type: ignore[arg-type]
        as_list = call("get_knowledge_mastery", user_ids["a"], ["topic"])  # type: ignore[arg-type]
    check("G10.1 str / None / list arguments → error「参数格式错误」不触达参数模型",
          all("error" in r and "参数格式错误" in r["error"] for r in (as_str, as_none, as_list)),
          f"{as_str}|{as_none}|{as_list}")


# ---------------------------------------------------------------------------
# 尾部：本机验证清单（离线提示，不执行网络调用）
# ---------------------------------------------------------------------------
SMOKE_GUIDE = """
============================== 本机验证清单（沙箱网络全禁，留本机执行） ==============================

V1. 真实 DeepSeek function calling 冒烟（验收标准 3 + 标准 2 真实请求部分）：
    cd backend && .venv/Scripts/python -c "
    import json
    from app.agent.registry import TOOLS_SCHEMA
    from app.services.llm import get_chat_client
    from app.core.config import settings
    client = get_chat_client()
    resp = client.chat.completions.create(
        model=settings.llm_model,
        messages=[{'role': 'user', 'content': '我还有哪些任务没做完'}],
        tools=TOOLS_SCHEMA,
    )
    msg = resp.choices[0].message
    assert msg.tool_calls, f'未返回 tool_calls: {msg}'
    first = msg.tool_calls[0]
    assert first.function.name == 'get_tasks', first.function.name
    args = json.loads(first.function.arguments)
    assert set(args) <= {'status', 'due_before'}, args
    print('冒烟通过:', first.function.name, args)
    "
    预期：打印「冒烟通过: get_tasks {...}」——tools=TOOLS_SCHEMA 直传真实请求
    成功即同时证明验收标准 2（OpenAI SDK 无格式校验错误）。

V2. （可选）把 TOOLS_SCHEMA 发给 DeepSeek 问知识型问题，确认它会选
    search_knowledge_base 而非 get_tasks（description 三要素生效）。

=====================================================================================================
"""


def main() -> None:
    print("P10 Agent 工具层验收（scripts/test_tools.py）\n")
    Base.metadata.create_all(engine)

    user_ids = seed_users()
    seed_profile(user_ids)
    task_ids = seed_tasks(user_ids)
    refs = seed_records_and_courses(user_ids)
    seed_mastery(user_ids)
    print("造数完成：三用户 / 任务矩阵 / 记录 / 掌握度 / 知识库（离线索引中）...")
    kb = seed_knowledge(user_ids)
    print()

    g0_registry()
    g0_json_serializable_results(user_ids, task_ids, refs)
    g1_user_profile(user_ids)
    g2_learning_records(user_ids, refs)
    g3_tasks(user_ids, task_ids)
    g4_mastery(user_ids)
    g5_statistics(user_ids)
    g6_search(user_ids, kb)
    g7_create_task(user_ids, refs)
    g8_update_task(user_ids, task_ids, refs)
    g9_slow_log(user_ids)
    g10_arguments_defense(user_ids)

    print()
    print(f"汇总：{len(PASSED)} PASS / {len(FAILED)} FAIL")
    if FAILED:
        print("失败项：")
        for name in FAILED:
            print(f"  - {name}")
        sys.exit(1)
    print(SMOKE_GUIDE)
    sys.exit(0)


if __name__ == "__main__":
    main()