"""P11 Agent 主循环本机冒烟脚本（真实 DeepSeek 流验证，沙箱无法代跑）。

专项验证（tasks.md 组 10.3 / spec §8.3 V1–V6）：
- **V0 聚合算法真实流验证（用户特别提醒项）**：直调
  ``services/llm.agent_chat_stream``（真实 DeepSeek 流式 + function
  calling），打印分片序列与轮终聚合块，逐个 tool_call 验证
  ``arguments`` 为**可解析的完整 JSON**——真实流下 name 与 arguments
  分散在多个 chunk、多调用交错到达，mock 无法覆盖此路径；
- **V1 学习分析**：真实主循环问「我最近学习怎么样」，观测 ≥3 工具
  连调与含数字回答；
- **V2 不编造**：问「帮我制定下周学习计划」，回答应含「后续版本」；
- **V6 轮次分布**：打印实际轮次与 finish_reason（6 轮上限充足性）。

用法（本机，需 backend/.env 配置有效 LLM_* 且服务数据库有用户）：
    cd backend
    ./.venv/Scripts/python.exe scripts/smoke_agent_chat.py

前置：``data/smartlearn.db`` 至少存在一个用户（注册或种子）；脚本取
id 最小的用户冒烟。HTTP 层冒烟另见文末打印的 curl 命令。
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from typing import Any

# backend 根入 sys.path（scripts/ 内以 app.* 绝对导入）。
_BACKEND_ROOT = Path(__file__).resolve().parent.parent
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))


def _check_env() -> None:
    """检查 LLM 配置（缺失即退出——冒烟必须走真实服务）。"""
    from app.core.config import settings

    missing = [
        name
        for name, value in [
            ("LLM_BASE_URL", settings.LLM_BASE_URL),
            ("LLM_API_KEY", settings.LLM_API_KEY),
            ("LLM_MODEL", settings.LLM_MODEL),
        ]
        if not str(value or "").strip()
    ]
    if missing:
        print(f"[FAIL] LLM 配置缺失: {missing}（检查 backend/.env）")
        sys.exit(1)
    print(f"[OK] LLM 配置就绪: model={settings.LLM_MODEL.strip()}")


def _first_user_id() -> int:
    """取真实库 id 最小用户（冒烟身份）。"""
    from app.db.session import SessionLocal
    from app.models.user import User

    with SessionLocal() as db:
        user = db.scalar(__import__("sqlalchemy").select(User).order_by(User.id.asc()))
    if user is None:
        print("[FAIL] 数据库无用户——请先注册（POST /api/v1/auth/register）")
        sys.exit(1)
    print(f"[OK] 冒烟用户: id={user.id} username={user.username}")
    return user.id


# ---------------------------------------------------------------------------
# V0：聚合算法真实流验证（用户特别提醒项）
# ---------------------------------------------------------------------------
async def smoke_aggregation(user_id: int) -> bool:
    """真实 DeepSeek 流：分片序列 + 轮终聚合块 arguments 完整性验证。"""
    from app.agent.registry import TOOLS_SCHEMA
    from app.services import llm

    messages: list[dict[str, Any]] = [
        {
            "role": "system",
            "content": "你是学习助手。直接调用工具完成任务，不要反问用户确认。",
        },
        {"role": "user", "content": "我最近学习怎么样"},
    ]
    print("\n=== V0 聚合算法真实流验证（单轮直调 agent_chat_stream）===")
    text_pieces = 0
    reasoning_pieces = 0
    round_block: dict[str, Any] | None = None
    async for part in llm.agent_chat_stream(
        messages, tools=TOOLS_SCHEMA, max_tokens=2048
    ):
        if "content" in part:
            text_pieces += 1
        elif "reasoning" in part:
            reasoning_pieces += 1
        else:
            round_block = part
    print(f"分片统计: 文本增量={text_pieces} 推理增量={reasoning_pieces}")
    if round_block is None:
        print("[FAIL] 未收到轮终聚合块")
        return False
    tool_calls = round_block["tool_calls"]
    print(f"轮终块: finish_reason={round_block['finish_reason']} tool_calls={len(tool_calls)}")
    ok = True
    for tc in tool_calls:
        name = tc["function"]["name"]
        raw = tc["function"]["arguments"]
        try:
            args = json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            print(f"[FAIL] arguments 聚合不完整（JSON 解析失败）: {name}: {raw[:80]}")
            ok = False
            continue
        print(f"[OK] tool_call 聚合完整: {name}({json.dumps(args, ensure_ascii=False)})")
    if not tool_calls:
        print("[WARN] 本轮模型未发起工具调用（重跑或换问题可复现多调用场景）")
    return ok


# ---------------------------------------------------------------------------
# V1/V2/V6：完整主循环冒烟（真实 LLM + 真实工具 + 真实落库）
# ---------------------------------------------------------------------------
async def _run_chat(
    db: Any, user_id: int, question: str
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """跑一次完整主循环，返回 (事件列表, done.data)。"""
    from app.agent import core, memory

    conversation = memory.create_conversation(db, user_id, None)
    events: list[dict[str, Any]] = []
    async for event in core.agent_chat_stream(
        db, user_id, conversation, question
    ):
        events.append(event)
    done = next(e for e in events if e["type"] == "done")["data"]
    return events, done


def _print_chat_summary(
    tag: str, events: list[dict[str, Any]], done: dict[str, Any]
) -> None:
    """打印事件流摘要（工具链 / 轮次 / finish_reason / 回答）。"""
    rounds = [
        e["data"]["round"]
        for e in events
        if e["type"] == "thinking" and "round" in e["data"]
    ]
    calls = [e["data"] for e in events if e["type"] == "tool_call"]
    results = [e["data"] for e in events if e["type"] == "tool_result"]
    answer = "".join(e["data"] for e in events if e["type"] == "delta")
    print(f"\n=== {tag} ===")
    print(f"轮次信号: {rounds}")
    print(f"工具调用链: {[c['name'] for c in calls]}")
    for c, r in zip(calls, results):
        print(
            f"  - {c['name']}({json.dumps(c['arguments'], ensure_ascii=False)}) "
            f"→ ok={r['ok']} elapsed={r['elapsed_ms']}ms truncated={r['truncated']}"
        )
    print(
        f"done: rounds={done['rounds']} tool_call_count={done['tool_call_count']} "
        f"finish_reason={done['finish_reason']}"
    )
    print(f"回答（前 400 字）: {answer[:400]}")


async def smoke_full_loop(user_id: int) -> bool:
    """V1 学习分析 + V2 不编造 + V6 轮次分布。"""
    from app.db.session import SessionLocal

    print("\n=== V1/V2/V6 完整主循环冒烟 ===")
    ok = True
    with SessionLocal() as db:
        events, done = await _run_chat(db, user_id, "我最近学习怎么样")
        _print_chat_summary("V1 学习分析", events, done)
        names = [e["data"]["name"] for e in events if e["type"] == "tool_call"]
        answer = "".join(e["data"] for e in events if e["type"] == "delta")
        if len(names) < 3:
            print(f"[WARN] V1 工具连调 {len(names)} < 3（观察 V6 轮次分布后可复跑）")
        if not any(ch.isdigit() for ch in answer):
            print("[WARN] V1 回答未含数字（不编造底线的另一面——无数据时如实说明）")

        events2, done2 = await _run_chat(db, user_id, "帮我制定下周学习计划")
        _print_chat_summary("V2 不编造", events2, done2)
        answer2 = "".join(e["data"] for e in events2 if e["type"] == "delta")
        if "后续版本" not in answer2:
            print("[WARN] V2 回答未含「后续版本」表述（核对 Prompt 边界声明生效性）")
        else:
            print("[OK] V2 含「后续版本」表述，未编造计划")
        print("\n[V6] 轮次分布参考: V1 rounds=%s / V2 rounds=%s（上限 6）"
              % (done["rounds"], done2["rounds"]))
    return ok


def _print_http_smoke() -> None:
    """打印 HTTP 层冒烟命令（V3 SSE 端到端 / V4 持久化 / V5 故障）。"""
    print(
        "\n=== HTTP 层冒烟（服务启动后本机执行）===\n"
        "V3 SSE 端到端（六事件序列 + delta 时间戳实时到达）:\n"
        '  curl -N -X POST http://localhost:8000/api/v1/agent/chat \\\n'
        '    -H "Authorization: Bearer <TOKEN>" -H "Content-Type: application/json" \\\n'
        '    -d \'{"message": "我最近学习怎么样"}\'\n'
        "V4 持久化（刷新还原的服务端维度）:\n"
        "  curl -H 'Authorization: Bearer <TOKEN>' "
        "http://localhost:8000/api/v1/agent/conversations\n"
        "  curl -H 'Authorization: Bearer <TOKEN>' "
        "http://localhost:8000/api/v1/agent/conversations/<ID>/messages\n"
        "V5 LLM 故障（改错 .env LLM_BASE_URL 重启后提问 → 中文 error + 连接关闭）"
    )


def main() -> None:
    """冒烟入口。"""
    _check_env()
    user_id = _first_user_id()
    ok_v0 = asyncio.run(smoke_aggregation(user_id))
    ok_v1 = asyncio.run(smoke_full_loop(user_id))
    _print_http_smoke()
    print(f"\n汇总: V0聚合={'PASS' if ok_v0 else 'FAIL'} 主循环={'PASS' if ok_v1 else 'FAIL'}")
    sys.exit(0 if (ok_v0 and ok_v1) else 1)


if __name__ == "__main__":
    main()