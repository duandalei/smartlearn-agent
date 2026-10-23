"""学习报告生成测试（tasks.md 组 9.2：R1–R7）。

覆盖验收：D5（真实数字落库）/ D9（报告侧模板降级）/ D12（reports
列表倒序 + 类型过滤）；O1（模板降级含真实数字）/ O2（append 语义）。

mock 注入点：``app.services.report.llm.chat`` 三态（成功固定文本 /
抛错 / 挂起加速超时）；日期断言动态计算（北京口径）。
"""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone
from typing import Any

import pytest

TZ = timezone(timedelta(hours=8))


def _today() -> date:
    return datetime.now(TZ).date()


def _last_week_window() -> tuple[date, date]:
    """上周一 ~ 上周日（动态计算）。"""
    today = _today()
    this_monday = today - timedelta(days=today.weekday())
    last_sunday = this_monday - timedelta(days=1)
    return last_sunday - timedelta(days=6), last_sunday


def _db():
    from app.db.session import SessionLocal

    return SessionLocal()


def _get_user_id(app_client: Any, user: dict[str, Any]) -> int:
    resp = app_client.get("/api/v1/auth/me", headers=user["headers"])
    return resp.json()["data"]["id"]


def _install_report_llm(
    monkeypatch: pytest.MonkeyPatch, responder: Any
) -> None:
    """注入总结 LLM fake（三态）。"""

    async def fake(messages: list[dict[str, Any]]) -> str:
        result = responder(messages)
        if isinstance(result, Exception):
            raise result
        return result

    monkeypatch.setattr("app.services.report.llm.chat", fake)


def _generate(
    app_client: Any, user: dict[str, Any], payload: dict[str, Any]
) -> dict[str, Any]:
    resp = app_client.post("/api/v1/reports/generate", headers=user["headers"], json=payload)
    assert resp.status_code == 200, resp.text
    return resp.json()["data"]


def _seed_period_data(uid: int, start: date, end: date) -> None:
    """周期内 3 条记录共 145 分钟 + 2 done + 1 todo（R1 数据基础）。"""
    from app.models.enums import TaskSource, TaskStatus
    from app.models.record import LearningRecord
    from app.models.task import Task

    minutes = [60, 45, 40]
    kps = [["机器学习"], ["深度学习", "机器学习"], ["机器学习"]]
    with _db() as db:
        for i, m in enumerate(minutes):
            db.add(
                LearningRecord(
                    user_id=uid,
                    content=f"学习记录 {i}",
                    duration_minutes=m,
                    knowledge_points=kps[i],
                    mastery_level=70 + i,
                    study_date=start + timedelta(days=i),
                )
            )
        for i in range(2):
            db.add(
                Task(
                    user_id=uid, title=f"已完成任务{i}", priority="medium",
                    deadline=datetime.combine(end, datetime.max.time(), tzinfo=timezone.utc),
                    status=TaskStatus.DONE, source=TaskSource.MANUAL,
                    # 完成时间落在统计窗口内（北京日期 = end 当日）
                    completed_at=datetime.combine(
                        end, datetime.min.time(), tzinfo=timezone.utc
                    )
                    + timedelta(hours=12),
                )
            )
        db.add(
            Task(
                user_id=uid, title="未完成任务", priority="medium",
                deadline=datetime.combine(end, datetime.max.time(), tzinfo=timezone.utc),
                status=TaskStatus.TODO, source=TaskSource.MANUAL,
            )
        )
        db.commit()


def test_r1_real_numbers_persisted(
    app_client: Any, user_a: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    """D5：content 数字与库中聚合精确相等 + learning_reports 落行。"""
    _install_report_llm(monkeypatch, lambda _m: "本周总结文本。")
    uid = _get_user_id(app_client, user_a)
    start, end = _last_week_window()
    _seed_period_data(uid, start, end)

    data = _generate(app_client, user_a, {"report_type": "weekly"})
    assert data["report_type"] == "weekly"
    assert data["period_start"] == start.isoformat()
    assert data["period_end"] == end.isoformat()
    content = data["content"]
    assert content["total_minutes"] == 145  # 60+45+40
    assert content["task_completed"] == 2
    assert content["completion_rate"] == round(2 / 3 * 100, 1)
    assert content["top_direction"] == "机器学习"  # 3 次出现
    assert content["generated_by"] == "llm"
    assert data["summary"] == "本周总结文本。"

    with _db() as db:
        from sqlalchemy import select

        from app.models.report import LearningReport

        rows = db.execute(
            select(LearningReport).where(LearningReport.user_id == uid)
        ).scalars().all()
        assert len(rows) == 1
        assert rows[0].content["total_minutes"] == 145


def test_r2_period_resolution_dynamic(
    app_client: Any, user_a: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    """R2：weekly 缺省 → 上周一~上周日；带 period_end=某周三 → 该周周一~周三。"""
    _install_report_llm(monkeypatch, lambda _m: "总结")
    start, end = _last_week_window()
    data = _generate(app_client, user_a, {"report_type": "weekly"})
    assert data["period_start"] == start.isoformat()
    assert data["period_end"] == end.isoformat()

    # 带指定 period_end（上周三）→ 该周周一~周三
    wednesday = start + timedelta(days=2)
    data2 = _generate(
        app_client, user_a, {"report_type": "weekly", "period_end": wednesday.isoformat()}
    )
    assert data2["period_start"] == start.isoformat()
    assert data2["period_end"] == wednesday.isoformat()


def test_r3_llm_summary_path(
    app_client: Any, user_a: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    """R3：mock 固定文本 → summary == 该文本、generated_by == "llm"。"""
    _install_report_llm(monkeypatch, lambda _m: "这是 LLM 生成的周报总结，含 145 分钟学习。")
    data = _generate(app_client, user_a, {"report_type": "weekly"})
    assert data["summary"] == "这是 LLM 生成的周报总结，含 145 分钟学习。"
    assert data["content"]["generated_by"] == "llm"


def test_r4_template_fallback_real_numbers(
    app_client: Any, user_a: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    """D9 + O1 + 用户指令②：fake 抛错 → 模板降级仍成功、summary 含真实数字、结构同构。"""
    from app.core.response import BizException

    # LLM 路径数据
    _install_report_llm(monkeypatch, lambda _m: "LLM 周报总结。")
    uid = _get_user_id(app_client, user_a)
    start, end = _last_week_window()
    _seed_period_data(uid, start, end)
    llm_data = _generate(app_client, user_a, {"report_type": "weekly"})

    # 降级路径：fake 抛 BizException
    _install_report_llm(monkeypatch, lambda _m: BizException(3000, "AI 服务不可用", 502))
    rules_data = _generate(app_client, user_a, {"report_type": "weekly"})
    assert rules_data["content"]["generated_by"] == "template"
    summary = rules_data["summary"]
    assert "145" in summary and "2" in summary  # 真实数字非空泛鼓励
    assert "小时" in summary or "分钟" in summary

    # 用户指令②：两路径落库/响应结构完全同构（key 集合显式对比）
    assert set(llm_data.keys()) == set(rules_data.keys())
    assert set(llm_data["content"].keys()) == set(rules_data["content"].keys())

    # 落库行存在 + 无 502/500（_generate 内已断言 200）
    with _db() as db:
        from sqlalchemy import func, select

        from app.models.report import LearningReport

        count = db.scalar(
            select(func.count()).select_from(
                select(LearningReport).where(LearningReport.user_id == uid).subquery()
            )
        )
        assert count == 2


def test_r4b_template_fallback_timeout(
    app_client: Any, user_a: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    """D9：LLM 挂起 + 超时加速 → 模板降级（真实超时链路）。"""
    import asyncio

    async def hang(_messages: list[dict[str, Any]]) -> str:
        await asyncio.sleep(60)
        return ""

    monkeypatch.setattr("app.services.report.llm.chat", hang)
    monkeypatch.setattr("app.services.report.REPORT_LLM_TIMEOUT_S", 0.05)
    data = _generate(app_client, user_a, {"report_type": "weekly"})
    assert data["content"]["generated_by"] == "template"
    assert data["summary"]


def test_r5_zero_data_tolerance(
    app_client: Any, user_a: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    """R5：空数据用户生成日报 → 200 + 落库 + 0 类值 + 暂无学习记录文案。"""
    _install_report_llm(monkeypatch, lambda _m: "LLM 总结")
    data = _generate(app_client, user_a, {"report_type": "daily"})
    content = data["content"]
    assert content["total_minutes"] == 0
    assert content["task_completed"] == 0
    assert content["completion_rate"] == 0.0
    assert content["top_direction"] is None
    assert content["weak_points"] == []

    # 模板降级的空数据文案
    _install_report_llm(monkeypatch, lambda _m: "")
    data2 = _generate(app_client, user_a, {"report_type": "daily"})
    assert data2["content"]["generated_by"] == "template"
    assert "暂无学习记录" in data2["summary"]


def test_r6_append_and_descending_list(
    app_client: Any, user_a: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    """O2：同周期重复生成 append 两行；列表倒序第一条为第二次；类型过滤。"""
    _install_report_llm(monkeypatch, lambda _m: "第一次周报。")
    _generate(app_client, user_a, {"report_type": "weekly"})
    _install_report_llm(monkeypatch, lambda _m: "第二次周报。")
    _generate(app_client, user_a, {"report_type": "weekly"})
    _install_report_llm(monkeypatch, lambda _m: "第一次日报。")
    _generate(app_client, user_a, {"report_type": "daily"})

    resp = app_client.get("/api/v1/reports", headers=user_a["headers"])
    data = resp.json()["data"]
    assert data["total"] == 3
    summaries = [item["summary"] for item in data["items"]]
    assert summaries[0] == "第一次日报。"  # 最新在前
    assert set(summaries[1:]) == {"第一次周报。", "第二次周报。"}
    ids = [item["id"] for item in data["items"]]
    assert ids == sorted(ids, reverse=True)  # 倒序稳定

    resp_filtered = app_client.get(
        "/api/v1/reports?report_type=weekly", headers=user_a["headers"]
    )
    filtered = resp_filtered.json()["data"]
    assert filtered["total"] == 2
    assert all(item["report_type"] == "weekly" for item in filtered["items"])


def test_r7_invalid_params(app_client: Any, user_a: dict[str, Any]) -> None:
    """R7：report_type 非法 / period_end 晚于今天 / 格式错 → 422 + code=1001。"""
    resp = app_client.post(
        "/api/v1/reports/generate", headers=user_a["headers"], json={"report_type": "foo"}
    )
    assert resp.status_code == 422
    assert resp.json()["code"] == 1001

    tomorrow = (_today() + timedelta(days=1)).isoformat()
    resp2 = app_client.post(
        "/api/v1/reports/generate",
        headers=user_a["headers"],
        json={"report_type": "weekly", "period_end": tomorrow},
    )
    assert resp2.status_code == 422
    assert resp2.json()["code"] == 1001

    resp3 = app_client.post(
        "/api/v1/reports/generate",
        headers=user_a["headers"],
        json={"report_type": "weekly", "period_end": "not-a-date"},
    )
    assert resp3.status_code == 422

    # user_id 注入拒绝（extra=forbid）
    resp4 = app_client.post(
        "/api/v1/reports/generate",
        headers=user_a["headers"],
        json={"report_type": "weekly", "user_id": 1},
    )
    assert resp4.status_code == 422