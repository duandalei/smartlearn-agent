# Agent 对话主循环（agent_chat）编码任务规划

> feature: `agent_chat` ｜ 阶段：编码任务规划（spec-task-agent 产出）
> 上游输入：`docs/specs/SPEC_AGENT_CHAT.md`（R3 裁定定稿：12 项裁决 + O1–O8 全部裁定 + 2 条 R2 补充约束 + 1 条 R3 补充约束 + D1–D13 验收标准 + SSE 六事件契约 + 六端点接口清单）、`docs/designs/DESIGN_AGENT_CHAT.md`（922 行定稿：core.py 状态机与常量表与 O5 三分支收尾 / llm.py 扩展方法与 tool_calls 聚合算法 / prompts.py 七段模板 / memory.py 成对截断算法 / 六端点设计 / mock 测试方案与 D 映射 / 兼容性回归 R1–R8 / 文件清单 / 决策 A1–A11 / 2.8.3 裁定落实对照表）、`docs/PROJECT_CONTEXT.md`（唯一技术契约：分层铁律 / 统一响应体 / §6.13–6.14 表结构 / §3 目录树）
> 生成日期：2026-10-22 ｜ 状态：待用户确认
> 落盘路径说明：沿用 P9 确立的对偶惯例——`SPEC_` ↔ `DESIGN_` ↔ `TASKS_`、`specs/` ↔ `designs/` ↔ `tasks/`（同 `docs/tasks/TASKS_RAG_QA.md`），本文件落 `docs/tasks/TASKS_AGENT_CHAT.md`
> 已裁决事项继承（不再重开）：spec 12 项裁决 + O1–O8 全部裁定（O5 含 15s 保护条件 / O6 2000 独立上限 / O7 最近 20 条成对截断 / O8 模块常量仅测试可 monkeypatch）+ R2 补充约束（finish_reason 三值真实反映 / tool_call 携带解析后参数对象）+ **R3 补充约束（上下文体积观测 OB-1，只观测不截断，D13）**；design 决策 A1–A11（主循环放 agent/core.py / user 消息落库在生成器首条语句 / 轮内成组落库 / 60s 软预算 / arguments 解析失败置 {} / thinking 两形态 / 总结复用 agent_chat_stream / 2000 两处同值各自定义 / 尾部对齐截断 / 全量取出后内存截窗 / 观测只记录不截断）；本清单不重开任何设计决策
>
> **编号读法**：本文「决策 A11」指 design 2.8.2 设计决策；「验收 D13」指 spec 8.1 验收标准；「OB-1」指 design 2.1.3-F 观测点；「CP-1/CP-2/CP-3/CP-4」指 design 2.1.3-C 预算检查点；「R1–R8」指 design 2.6 兼容性回归清单（勿与 spec 修订记录 R1–R3 混淆）。

---

## 0. 任务总览与依赖关系

**分组结构**（10 组，共 36 个子任务，实现顺序按 design 2.8.1 建议：llm 扩展方法 → memory → prompts → core 主循环 normal 路径 → 收尾分支 → api 端点 → 三个测试文件 → 回归）：

```
组1 llm.py扩展方法 ──→ 组4 core.py主循环 ─┬─→ 组5 schemas与api端点 ──→ 组8 SSE契约e2e ──→ 组9 兼容性回归 ──→ 组10 文档同步收尾
组2 memory.py ──────────┤                   │
组3 prompts.py ─────────┘                   │
        └─→ 组6 test_agent_prompt.py（仅依赖组3）─→ 组7 test_agent_memory.py（仅依赖组2+组5）─→ ↑（并入组9 全量回归）
```

**关键路径**：1.2 → 2.3 → 3.3 → 4.3 → 4.4 → 4.6 → 5.2 → 8.2 → 9.3 → 10.2。

**可并行标注**：
- 组 1 / 组 2 / 组 3 相互零文件交集，可完全并行（组 4 汇合三者）
- 组 4 内部：4.1 / 4.2 可先行（仅依赖本文件）；4.3–4.6 串行
- 组 5 内部：5.1 可与组 4 并行；5.2 依赖组 4；5.3 / 5.4 依赖组 2
- 组 6（依赖组 3）与组 7（依赖组 2 + 5.3/5.4）可与组 4 / 组 8 编写并行
- 组 8 依赖组 1–5 全部落地后运行
- 组 10.1（文档改动）无代码依赖，可任意时机执行

**实现前置约定**（全文适用，各任务不再重复）：
1. **运行环境**：后端一律使用 `backend/.venv`（实测可用：`./.venv/Scripts/python.exe`）；系统 Anaconda 环境缺依赖不可用于本阶段验证
2. **沙箱限制**：无外网，pytest 走 ASGI TestClient 直调（conftest 既有 `app_client` / `user_a` / `user_b` / `_isolated_runtime` autouse fixture，零新增基建）；**LLM 必须 mock**——`monkeypatch.setattr("app.services.llm.agent_chat_stream", 假流工厂)`（core.py 经 `from app.services import llm` 模块属性访问，P9 `_install_fake_llm` 同款形态）；工具层走真实实现（临时 SQLite 真实读写）
3. **O8 常量引用铁律**：预算/轮次常量必须在 `core.py` 模块级定义、**函数体内以模块常量名直接引用**（禁默认参数捕获、禁模块加载期求值）——`monkeypatch.setattr("app.agent.core.TOTAL_BUDGET_S", 1.0)` 才生效（design 2.4.1-C，D7 测试正确性的静态前提）
4. **P10 测试坑（新测试文件编写注意）**：`from datetime import time` 会覆盖 stdlib `time` 模块——core.py 依赖 `time.monotonic / time.perf_counter`，测试文件若需 datetime.time 一律改名 `dt_time` 导入；慢日志断言用自装 `logging.Handler` 捕获（P10 惯例，勿依赖 caplog 过滤行为差异时优先 Handler）
5. **既有基线（实测确认）**：P9 全量 `pytest tests/ -q` = **115 passed**；P10 `scripts/test_tools.py` 输出 **76 PASS / 0 FAIL**；本阶段交付后全量应为 115 + 新增三文件用例数
6. 每个新模块 docstring 须回链 design.md 章节号；代码标识符英文 snake_case，注释中文（契约 §8.4）；type hints 全覆盖

**十常量核对表**（core.py 模块级，全部锁定值 + 注释实测依据，禁止环境变量化——design 2.1.2；组 4.1 逐字落地，组 10.2 走查复核）：

| 常量 | 值 | 依据（注释必写） |
|------|-----|------|
| `MAX_ROUNDS` | `6` | P10 实测过度调用倾向；spec §4.1 规则 3 |
| `TOTAL_BUDGET_S` | `60.0` | 裁决 #8 循环总预算；O8 仅测试可 monkeypatch |
| `GRACEFUL_MIN_BUDGET_S` | `15.0` | O5 保护条件：剩余 < 15s 跳过总结调用走模板拼接 |
| `MAX_TOKENS` | `2048` | 裁决 #9：≥1024 红线 + 长总结余量（P10 实测 300 截断） |
| `SUMMARY_TRUNCATE` | `500` | tool_result 摘要截断长度（字符，序列化后计） |
| `CONTEXT_WINDOW` | `20` | O7：最近 20 条，成对边界截断禁孤儿 tool 消息 |
| `MESSAGE_MAX_LEN` | `2000` | O6：**独立于 P9 /chat/qa 的 500，两处各自定义刻意不共用**（决策 A8；schema 层 `AGENT_MESSAGE_MAX_LEN` 同值，行内注释互相指认） |
| `TOOL_NAME_MAX_LEN` | `50` | agent_messages.tool_name 列宽；非法工具名照存须截断 |
| `TOOL_CALL_ID_MAX_LEN` | `64` | agent_messages.tool_call_id 列宽；防御截断 |
| `CONTEXT_LOG_WARN_CHARS` | `30000` | R3 补充约束：上下文体积观测阈值（debug → warning 升级线） |

**明确不改动清单（冻结项，防越界——design 1.1.3-E）**：

| 文件 | 不改动理由 | 验证方式 |
|------|-----------|---------|
| `backend/app/agent/tools.py`（715 行）/ `backend/app/agent/registry.py`（273 行） | P10 冻结（spec §1.4 规则 1）；本阶段只消费 `TOOLS_SCHEMA` / `TOOL_MAP` | 组 9.2 git diff 为空（R2） |
| `backend/app/services/llm.py` 的 `chat` / `chat_stream` / 客户端构造区（既有 242 行） | spec §4.5 规则 1 契约零改动（P9 问答与 P4 目标拆解依赖）；扩展仅限文件末尾追加 | 组 9.1 git diff 审查（R1） |
| `backend/app/api/v1/__init__.py` | agent_router 已挂载（实测 `__init__.py:33,55`），新端点在既有 router 内扩展 | 组 9.2 diff 为空（R7） |
| `backend/app/models/`（含 agent.py，全部 DDL） | spec §4.5 规则 5：表结构沿用 §6.13/6.14 不改 | 组 9.2 diff 为空（R8） |
| `backend/app/api/v1/agent_messages.py`（93 行） | P3 全表验证端点，无需求触点 | 组 9.3 回归覆盖（R5） |
| `backend/app/api/v1/chat.py` / `backend/app/services/chat.py` | P9 通道零触点（SSE 模式只被复刻不被修改） | 组 9.3 全量回归 |
| `backend/scripts/test_tools.py`（1021 行，76 用例） | P10 测试套件，回归直接跑不修改 | 组 9.2 |

> **前端禁令（范围铁律）**：本阶段**禁止创建任何前端文件**——`AgentView.vue`、`src/api/agent.ts`、stores、路由条目等全部属后续阶段（spec 范围总则）；SSE 事件契约按前端可视化需求设计，前端仅作契约消费方验证背景。组 10.2 走查须确认 `frontend/` 目录零改动。

---

## 1. services/llm.py 扩展方法（agent_chat_stream）

**写作说明**：本组是全链路的地基（P10 工具层只能被 LLM 使用的唯一缺口在 LLM 调用侧——design 一、发现①）。追加在文件「对话能力」区末尾（242 → ~395 行），既有区一行不动（裁决 #4）。唯一设计来源：design 2.2.2-(8) + 2.4.2。

### 1.1 AgentStreamPart 类型组定义（3 TypedDict + TypeAlias）

- [ ] **要点**：
  - 在 `services/llm.py` 文件末尾追加类型组，签名逐字对齐 design 2.2.2-(8)：`AgentTextDelta = TypedDict("AgentTextDelta", {"content": str})`、`AgentReasoningDelta = TypedDict("AgentReasoningDelta", {"reasoning": str})`、`AgentRoundResult = TypedDict("AgentRoundResult", {"tool_calls": list[dict[str, Any]], "finish_reason": str})`、`AgentStreamPart: TypeAlias = AgentTextDelta | AgentReasoningDelta | AgentRoundResult`
  - docstring 注明：三形态可辨识联合（core.py 以键存在性判别：`"content" in part` / `"reasoning" in part` / 其余为轮终块）；`AgentRoundResult` 每轮流恰产出一次（流末聚合块）
  - 不触碰既有 `ChatMessage` TypedDict 与客户端构造区
- **涉及文件**：修改 `backend/app/services/llm.py`（仅末尾追加区）
- **完成判定**：`cd backend && ./.venv/Scripts/python.exe -m py_compile app/services/llm.py` 通过；`./.venv/Scripts/python.exe -c "from app.services.llm import AgentStreamPart, AgentRoundResult; print('ok')"` 输出 ok
- **依赖**：无
- **决策锚点**：裁决 #4（新增方法扩展，既有零改动）

### 1.2 agent_chat_stream 方法骨架（请求构造 + 异常包装 + finally close）

- [ ] **要点**：
  - `async def agent_chat_stream(messages: Sequence[dict[str, Any]], tools: Sequence[dict[str, Any]] | None = None, max_tokens: int = 2048) -> AsyncIterator[AgentStreamPart]`（design 2.2.2-(8) 签名逐字）
  - 请求构造：`get_chat_client().chat.completions.create(model=LLM_MODEL, messages=list(messages), stream=True, tools=tools, tool_choice="auto", max_tokens=max_tokens)`；**`tools=None` 时省略 tools / tool_choice 两键**（总结调用路径，模型协议上无法发起 tool_call——决策 A7）
  - 创建段异常沿用既有 `_SERVICE_ERRORS` 包装口径（BizException 3000/502「AI 服务暂时不可用，请稍后重试」）；**迭代段异常不包装**（与既有 chat_stream 一致，由 core.py 双兜）
  - `finally: await stream.close()` 释放上游连接（1.2.2 行为③，必须保留同款）
  - 模块 docstring 注明纯传输层定位：收协议 dict 发结构化块，消息结构由 core.py 构造函数单点保证
- **涉及文件**：修改 `backend/app/services/llm.py`
- **完成判定**：`./.venv/Scripts/python.exe -m py_compile app/services/llm.py` 通过；`git diff app/services/llm.py` 审查确认改动仅在文件末尾追加区（既有方法与构造区上下文行零变动）
- **依赖**：1.1（同文件先建类型）
- **决策锚点**：裁决 #4；design 1.2.2（迭代段异常未包装的现状是新方法设计输入）

### 1.3 tool_calls 流式增量聚合算法（index 分桶）

- [ ] **要点**：
  - 方法内私有聚合状态（design 2.4.2-B 伪代码逐字落地）：`pending: dict[int, dict]`（index → {id, name, args_parts}）+ `last_index: int = 0`（兼容不回 index 的端点）
  - 对每个 chunk 的 `choices[0]` 三通道分发：`delta.content` 非空 → `yield AgentTextDelta`；`delta.reasoning_content` 非空 → `yield AgentReasoningDelta`；`delta.tool_calls` 列表逐分片：`idx = tc.index`（缺失沿用 `last_index`）→ 分桶累加 `tc.function.arguments` 增量片段、记录 id / name（非空时）
  - `finish_reason` 非空时记录（末次非空值覆盖）；**流结束时**：`sorted(pending.items())` 按 index 升序还原调用顺序 → 构造 OpenAI 非流式形态 `[{"id": b.id or "", "type": "function", "function": {"name": b.name or "", "arguments": "".join(b.args_parts)}}]` → `yield AgentRoundResult{tool_calls, finish_reason: final_finish or "stop"}`
  - 防御三点写入注释：finish_reason 缺失默认 `"stop"`、id 缺失空串、arguments 是字符串增量累加（**解析职责在上层 core.py**，算法要点②）
  - 算法正确性核心注释：按 index 分桶——一轮可含多个并行 tool_call（D1 场景 3 工具），各调用 arguments 分片以 index 区分交错到达，同 index 累加、跨 index 不串
- **涉及文件**：修改 `backend/app/services/llm.py`（并入 1.2 的方法体）
- **完成判定**：`./.venv/Scripts/python.exe -m py_compile app/services/llm.py` 通过；聚合行为断言（多工具交错分片 / index 缺失兜底 / finish_reason 缺失默认）由组 8.2 固化（captured 调用参数与 fake 流往返）
- **依赖**：1.2
- **决策锚点**：design 2.4.2-B 算法要点①–⑤

**里程碑验证（组 1 结束）**：
```bash
cd backend && ./.venv/Scripts/python.exe -m py_compile app/services/llm.py && echo COMPILE_OK
git diff app/services/llm.py | head -40   # 人工审查：hunk 仅位于文件末尾追加区
```

---

## 2. memory.py 会话与消息持久化

**写作说明**：新增 `backend/app/agent/memory.py`（~270 行）。函数清单唯一来源：design 2.2.2-(9) 十函数；算法唯一来源：design 2.4.4。**直接操作 AgentConversation / AgentMessage 的边界裁定（裁决 #5）**：会话日志是组件自有元数据，「Agent 绝不直接访问数据库」铁律收窄为「LLM 工具决策通道访问学习业务数据必须经 tools.py / services」——模块 docstring 须注明该边界，仍禁触碰 tasks / learning_records 等业务表。

### 2.1 模块骨架与会话 CRUD 四函数

- [ ] **要点**：
  - 模块 docstring：职责声明 + 裁决 #5 边界注明 + 回链 design 2.2.2-(9) / 2.4.4
  - `create_conversation(db, user_id, title: str | None) -> AgentConversation`：新建会话行（title 可空；commit 后返回）；chat 自动新建与显式新建共用
  - `get_conversation_or_404(db, conversation_id, user_id) -> AgentConversation`：主键 + user_id 双过滤；不存在/越权统一抛 `BizException(CODE_NOT_FOUND, "资源不存在", 404)`（「不可见即不存在」）
  - `rename_conversation(db, conversation_id, user_id, title) -> dict`：404 定位 + title 更新 + updated_at 触碰 + commit；返回 ConversationOut 序列化
  - `delete_conversation(db, conversation_id, user_id) -> None`：404 定位 + `db.delete(conversation)`（ORM `cascade="all, delete-orphan"` 级联删消息——1.2.4 约束④已确认级联语义成立）+ commit
- **涉及文件**：新增 `backend/app/agent/memory.py`
- **完成判定**：`./.venv/Scripts/python.exe -m py_compile app/agent/memory.py` 通过
- **依赖**：无（`models/agent.py` 既有零改动）；可与组 1 / 组 3 并行
- **决策锚点**：裁决 #5；spec §5.4.1 规则 7/8/9

### 2.2 会话列表倒序与消息全量查询

- [ ] **要点**：
  - `list_conversations(db, user_id, page, page_size) -> dict`：复用 `services/readonly.py` 的 `paginate`，`order_by=[desc(AgentConversation.updated_at), desc(AgentConversation.id)]`（O2 倒序 + 同秒并列 id 倒序 tie-break 保证分页稳定）+ user_id 过滤
  - `list_messages(db, conversation_id, user_id) -> list[dict]`：**404 定位先于空列表判定**（会话不存在/越权 → 404/1005；会话存在无消息 → `[]`，spec 5.4.3 场景 3）→ 全量消息按 id 升序（对话还原顺序，O3 不分页）→ `MessageOut` 序列化
  - 出参零新增字段（P3 `MessageOut` 已含 role/content/tool_name/tool_calls/tool_call_id 全链，spec §6.5 规则 2）
- **涉及文件**：修改 `backend/app/agent/memory.py`
- **完成判定**：`./.venv/Scripts/python.exe -m py_compile app/agent/memory.py` 通过；倒序与全量断言由组 7.1 固化
- **依赖**：2.1
- **决策锚点**：O2 / O3 裁定；design 1.1.2（paginate 已支持 order_by 参数）

### 2.3 消息三形态落库三函数（含 O4 标题补全）

- [ ] **要点**：
  - `save_user_message(db, conversation, content) -> None`：user 消息落库（独立事务）；**首条消息标题补全**：conversation.title 为空时置 `content[:20]`（O4 截断 20 字符）+ updated_at 触碰
  - `save_round_messages(db, conversation, assistant_content, tool_calls, tool_results) -> None`：**轮内成组落库（一次事务）**——assistant(tool_calls) 消息（`tool_calls` JSONType 直存 list[dict]）+ 本轮全部 tool 消息（`tool_name` 截断 50 / `tool_call_id` 截断 64 / **content 存完整结果 JSON 字符串**，含 error 信封原样；非法工具名为「该工具不可用」信封——2.4.4-D 落库映射表逐字）；组内失败整体 rollback 不抛穿（成对语义：中断/失败时整组不出现，孤儿 tool 在数据层不可能——决策 A3）
  - `save_final_message(db, conversation, content) -> int | None`：最终 assistant 纯文本消息落库（独立事务）+ 触碰；失败 rollback + warning + 返回 `None`（→ done.message_id=null）
- **涉及文件**：修改 `backend/app/agent/memory.py`
- **完成判定**：`./.venv/Scripts/python.exe -m py_compile app/agent/memory.py` 通过；三形态落库链断言由组 8.2 固化
- **依赖**：2.1
- **决策锚点**：裁决 #6/#7/#12；决策 A3；O4；spec §6.4

### 2.4 updated_at 显式触碰与落库失败不抛穿

- [ ] **要点**：
  - 每组落库 commit 前显式执行 `conversation.updated_at = utc_now()`——**关键实测依据（design 1.2.4 约束①）**：`onupdate=utc_now` 只在该行自身 UPDATE 时触发，insert 子消息不会触碰会话行；显式赋值语义确定，不依赖 ORM 副作用。O2 倒序排序的数据正确性前提
  - 落库失败统一处理：组内 `db.rollback()` + `logger.warning`（**仅含 user_id / conversation_id / 异常类型，禁记消息原文与结果全文**——spec 4.3 规则 4 隐私红线）+ 不抛穿主链路
  - SQLite 写锁仅在 commit 瞬间短暂持有（最多 1+6+1=8 次毫秒级 commit，无争用风险——design 2.1.3-D）
- **涉及文件**：修改 `backend/app/agent/memory.py`（并入 2.3 的三函数结构，本任务是触碰与失败路径的显式核对项）
- **完成判定**：`./.venv/Scripts/python.exe -m py_compile app/agent/memory.py` 通过；落库失败不拖垮主链路由组 8.4 固化（monkeypatch save_final_message 抛异常 → 流仍 done 收尾且 message_id=null）
- **依赖**：2.3
- **决策锚点**：design 1.2.4 约束①；spec §4.2 规则 6/7

### 2.5 load_context_window 成对边界截断（O7）

- [ ] **要点**：
  - `load_context_window(db, conversation, limit: int = CONTEXT_WINDOW) -> list[dict]`——design 2.4.4-A 算法四步逐字：① 全量查询该会话全部消息（id 升序，A10：量级数十条毫秒级，先全量后内存截断）② `window = rows[-CONTEXT_WINDOW:]` 尾部对齐（含刚落库的本轮 user 消息）③ `while window and window[0].role == TOOL: window.pop(0)` 头部连续孤儿 tool 剔除 ④ 行 → OpenAI 协议 dict 三形态映射（user/assistant 纯文本 → {role, content}；assistant(tool_calls) → {role, content, tool_calls}；tool → {role, content, tool_call_id}，content 为完整结果 JSON 字符串原样）
  - 正确性论证写入 docstring：截断只发生在头部（尾部对齐）——tool 协议上必须紧跟其 assistant（id 更大），故头部孤儿只可能是 tool；连续剔除即合法边界，O(n) 无回溯（决策 A9）
  - system 消息不落库（裁决 #6）→ 窗口天然不含 system
- **涉及文件**：修改 `backend/app/agent/memory.py`
- **完成判定**：`./.venv/Scripts/python.exe -m py_compile app/agent/memory.py` 通过；成对截断断言由组 7.2 固化（构造 25 条历史含 tool 链 → 返回 ≤20 条且首条非孤立 tool）
- **依赖**：2.1
- **决策锚点**：O7；决策 A9 / A10

**里程碑验证（组 2 结束）**：
```bash
cd backend && ./.venv/Scripts/python.exe -m py_compile app/agent/memory.py && \
./.venv/Scripts/python.exe -c "from app.agent.memory import create_conversation, get_conversation_or_404, rename_conversation, delete_conversation, list_conversations, list_messages, save_user_message, save_round_messages, save_final_message, load_context_window; print('MEMORY_IMPORT_OK')"
```

---

## 3. prompts.py System Prompt 单一事实来源

**写作说明**：新增 `backend/app/agent/prompts.py`（~190 行）。七段模板结构唯一来源：design 2.4.3-A 表格；预取降级行为：spec §5.2.3。不 import api / services（预取经 TOOL_MAP 即 agent 包内依赖；TZ_BEIJING 本地定义不跨层导入）。

### 3.1 静态段模板常量与 TZ_BEIJING

- [ ] **要点**：
  - `TZ_BEIJING = timezone(timedelta(hours=8))` 模块级本地定义（不跨层导入）
  - 四个静态段常量（design 2.4.3-A ①⑤⑥⑦ 行内容逐字）：
    - ① 身份与风格：SmartLearn AI 学习助手；三条风格（中文回答 / 分点组织 / 给出可执行建议）
    - ⑤ 能力边界声明骨架：不可用能力「学习计划的生成与调整、学习报告生成将在后续版本提供」+ 替代建议（如用 create_task 手工安排）+ 禁止编造一份计划；**工具清单段从 `TOOLS_SCHEMA` 名集合动态生成**（P12 追加工具自动跟进，design 1.2.1 扩展点）
    - ⑥ 禁止事项逐项三条：不编造数据（任何学习数字必须来自工具返回结果）/ 不做医疗或心理诊断 / 不越权（不执行账号操作、不代替用户流转任务状态、不访问他人数据）
    - ⑦ 场景引导 + 执行指令：分析学习状态 = `get_learning_statistics` + `get_tasks` + `get_knowledge_mastery` 组合；**逐字指令「直接调用工具完成任务，不要反问用户确认」**（P10 实测：缺此指令模型反问用户）
- **涉及文件**：新增 `backend/app/agent/prompts.py`
- **完成判定**：`./.venv/Scripts/python.exe -m py_compile app/agent/prompts.py` 通过
- **依赖**：无（消费 `registry.TOOLS_SCHEMA`，零改动只读）
- **决策锚点**：spec §5.2.1 规则 4/5/6/7/8

### 3.2 动态段渲染（日期 / 档案 / 概况）

- [ ] **要点**：
  - ② 日期段：「今天是 {YYYY-MM-DD}」——`datetime.now(TZ_BEIJING).date().isoformat()`（三要素之一，恒在；P10 实测：缺日期则模型先调两个工具确认上下文）
  - ③ 档案段（三要素之二）：姓名 {name} / 专业 {major} / 年级 {grade} / 每日可学习时长 {daily_study_minutes} 分钟 + 当前目标 {current_goal_type} + 兴趣方向 {interest_directions}
  - ④ 概况段：近 7 天核心数字——累计学习 {total_minutes} 分钟 / 任务完成率 {task_completion_rate}% / 连续学习 {streak_days} 天 / 逾期任务 {overdue_task_count} 个（**取 overview 层字段；trend 层数字量过大不进 Prompt**，design 2.4.3-A）
- **涉及文件**：修改 `backend/app/agent/prompts.py`
- **完成判定**：`./.venv/Scripts/python.exe -m py_compile app/agent/prompts.py` 通过
- **依赖**：3.1（同文件）
- **决策锚点**：spec §5.2.1 规则 1/3

### 3.3 build_system_prompt 预取与降级

- [ ] **要点**：
  - `async def build_system_prompt(db: Session, user_id: int) -> str`——预取两次 TOOL_MAP 直调（**async，await**；裁决 #10/#11：不经 LLM 决策、不推 SSE）：`await TOOL_MAP["get_user_profile"](db, user_id, {})` 与 `await TOOL_MAP["get_learning_statistics"](db, user_id, {"days": 7})`
  - 降级条件：返回 `{"error"}` 信封**或抛异常** → 对应段（③或④）**整段省略** + `logger.warning`（降级原因）；**三要素中②⑦恒在**（「缺段不缺要素」，spec 5.2.3 场景 2）
  - 档案从未填写：P10 返回默认值结构（daily_study_minutes=60）按默认渲染，**不是降级**（spec 5.2.3 场景 1）
- **涉及文件**：修改 `backend/app/agent/prompts.py`
- **完成判定**：`./.venv/Scripts/python.exe -m py_compile app/agent/prompts.py` 通过；渲染断言（三要素 / 边界 / 降级 / 默认档案）由组 6 全量固化
- **依赖**：3.2
- **决策锚点**：裁决 #10/#11；spec §5.2.1 规则 2、§5.2.3

**里程碑验证（组 3 结束）**：
```bash
cd backend && ./.venv/Scripts/python.exe -m py_compile app/agent/prompts.py && \
grep -rn "今天是\|System Prompt\|system_prompt" app/ --include="*.py" -l   # 人工核对：Prompt 拼接点仅 app/agent/prompts.py（spec 5.2.1 规则 8 集中管理）
```

---

## 4. core.py Agent 主循环（ReAct + Function Calling）

**写作说明**：新增 `backend/app/agent/core.py`（~430 行）——本阶段核心。状态机唯一来源：design 2.1.3-A；逐步设计唯一来源：design 2.4.1-B 七步；O5 收尾：design 2.1.3-B 决策树。**O8 铁律全文适用**：预算/轮次常量函数体内以模块常量名直接引用，禁默认参数捕获。实现顺序按 design 2.8.1：4.3 先通 normal 路径，4.6 后补收尾分支。

### 4.1 常量表（十常量 + 事件/finish_reason 字面量）

- [ ] **要点**：
  - 十常量逐字落地组 0 核对表（值与依据注释逐条对齐 design 2.1.2 常量表，**禁止环境变量化**，对齐 P10 `SLOW_TOOL_MS` 锁定惯例）
  - 事件类型字面量常量：`EVENT_THINKING = "thinking"` / `EVENT_TOOL_CALL = "tool_call"` / `EVENT_TOOL_RESULT = "tool_result"` / `EVENT_DELTA = "delta"` / `EVENT_DONE = "done"` / `EVENT_ERROR = "error"`（spec §4.4 规则 3 前后端共用同一套字面量，core.py 单一来源）
  - finish_reason 字面量常量：`FINISH_NORMAL = "normal"` / `FINISH_MAX_ROUNDS = "max_rounds"` / `FINISH_TIMEOUT = "timeout"`
  - `MESSAGE_MAX_LEN` 行内注释与 `schemas/agent.py` 的 `AGENT_MESSAGE_MAX_LEN` 互相指认（决策 A8：两处各自定义同值，刻意不共用——O6 明令禁止的形态恰是抽成共用常量）
- **涉及文件**：新增 `backend/app/agent/core.py`
- **完成判定**：`./.venv/Scripts/python.exe -m py_compile app/agent/core.py` 通过；`./.venv/Scripts/python.exe -c "from app.agent.core import MAX_ROUNDS, TOTAL_BUDGET_S, GRACEFUL_MIN_BUDGET_S, MAX_TOKENS, SUMMARY_TRUNCATE, CONTEXT_WINDOW, MESSAGE_MAX_LEN, TOOL_NAME_MAX_LEN, TOOL_CALL_ID_MAX_LEN, CONTEXT_LOG_WARN_CHARS; assert (MAX_ROUNDS, TOTAL_BUDGET_S, GRACEFUL_MIN_BUDGET_S, MAX_TOKENS, SUMMARY_TRUNCATE, CONTEXT_WINDOW, MESSAGE_MAX_LEN, TOOL_NAME_MAX_LEN, TOOL_CALL_ID_MAX_LEN, CONTEXT_LOG_WARN_CHARS) == (6, 60.0, 15.0, 2048, 500, 20, 2000, 50, 64, 30000); print('CONSTANTS_OK')"` 输出 CONSTANTS_OK（**十常量核对表的可执行断言**）
- **依赖**：无
- **决策锚点**：design 2.1.2；O6/O8；决策 A8

### 4.2 六事件构造辅助函数（单一来源防散落拼 dict）

- [ ] **要点**：
  - 七函数逐字对齐 design 2.4.1-A：`_thinking_event(round)` → `{"type": "thinking", "data": {"round": int}}`；`_thinking_content_event(content)` → thinking 的 content 增量形态（决策 A6 两形态）；`_tool_call_event(call_id, name, arguments)` → `{"call_id", "name", "arguments"}`（**arguments 为解析后参数对象**，非字符串——R2 补充约束 2）；`_tool_result_event(call_id, name, ok, elapsed_ms, summary, truncated)` → 六字段；`_delta_event(text)` → data 为字符串分片；`_done_event(conversation_id, message_id, rounds, tool_call_count, finish_reason)` → **五字段**；`_error_event(code, message)` → `{code, message}`
  - 对齐 P9 services/chat.py 的事件构造模式（`_sources_event` 等同款结构）
- **涉及文件**：修改 `backend/app/agent/core.py`
- **完成判定**：`./.venv/Scripts/python.exe -m py_compile app/agent/core.py` 通过；字段集断言由组 8.2 固化
- **依赖**：4.1
- **决策锚点**：design 2.4.1-A；spec §6.2 事件载荷 18 条

### 4.3 主循环生成器：准备段 + 轮循环 + normal 自然结束分支

- [ ] **要点**：
  - `async def agent_chat_stream(db: Session, user_id: int, conversation: AgentConversation, message: str) -> AsyncIterator[dict[str, Any]]`（design 2.2.2-(10) 签名逐字）
  - **准备段**（design 2.4.1-B-1）：`started_at = time.monotonic()`（user 消息落库在生成器首条语句——决策 A2）→ `save_user_message`（含 O4 标题补全）→ `history = load_context_window(conversation)` → `system_prompt = await build_system_prompt(db, user_id)` → `messages = [{"role": "system", "content": system_prompt}] + history`（窗口尾部即本轮 user 消息——先落库后加载天然包含，无需重复拼接）
  - **轮循环**（round 从 1 起，design 2.4.1-B-2）：CP-1 轮前预算检查（剩余 ≤ 0 → 收尾 timeout）→ OB-1 观测（4.5，此处留调用位）→ `yield _thinking_event(round)` → 消费 `llm.agent_chat_stream(messages, tools=TOOLS_SCHEMA, max_tokens=MAX_TOKENS)`（**模块属性访问**：`from app.services import llm`——mock 注入形态，P9 惯例）：文本增量 → `yield _delta_event(chunk)` + 累积；推理增量 → `yield _thinking_content_event(chunk)`；LLM 异常 → error 终结（**双兜**：BizException 用其 code/message；原始异常 → 3000 + 按「是否已推过 delta」区分「回答生成中断，请重试」/「AI 服务暂时不可用，请稍后重试」——P9 同款口径）；轮终块 → 进 4.4 或自然结束
  - **自然结束分支（normal）**：`tool_calls == []` → 最终回答 = 本轮累积文本 → `save_final_message`（失败 message_id=null）→ `yield _done_event(..., FINISH_NORMAL)` → 元数据日志 → 终结。**normal 路径不经 O5 收尾**（最后一轮文本本身就是回答——finish_reason 判定表，R2 补充约束 1）
- **涉及文件**：修改 `backend/app/agent/core.py`
- **完成判定**：`./.venv/Scripts/python.exe -m py_compile app/agent/core.py` 通过；normal 路径端到端断言由组 8.2 固化（待组 5.2 端点就绪）
- **依赖**：4.2、组 1（llm.agent_chat_stream）、组 2（memory 三函数）、组 3（build_system_prompt）
- **决策锚点**：决策 A1/A2/A6；裁决 #8；design 2.1.3-A 状态机

### 4.4 工具执行段（派发 / 非法名兜底 / 错误信封 / 摘要截断 / 回灌 / 轮收口）

- [ ] **要点**：
  - **tool_call 事件**：逐条 `yield _tool_call_event(call_id, name, parsed_arguments)`——**arguments 解析**：`json.loads(function.arguments)` 失败 → 置 `{}`（spec §6.2 规则 6；决策 A5：空 dict 交给 P10 校验，必填参数工具返回 missing 信封供 LLM 自纠、无参工具照常执行）
  - **CP-2 工具前预算检查**（逐个检查）：剩余 ≤ 0 → **停止派发本轮剩余工具**（未执行的不派发、不产生对应 tool_result——超时截断以 done(timeout) 明示）→ 收尾 timeout，已执行结果进模板
  - **派发判定**：`name in TOOL_MAP` → `await TOOL_MAP[name](db, user_id, parsed_arguments)`（user_id 取认证结果注入，spec §4.3 规则 2；第二道 try/except 兜底：未预期异常 → `{"error": "工具执行失败，请稍后重试"}` 信封，spec 5.3.3 场景 2）；`name not in TOOL_MAP`（非法工具名）→ 不派发，结果 = `{"error": "该工具不可用"}`（ok=false，elapsed_ms=0）
  - **计时**：`perf_counter` 包裹派发整体（`elapsed_ms` 与 P10 慢日志同值口径，误差毫秒级语义一致）
  - **tool_result 事件**：`ok = "error" not in result`；summary 生成——成功：`json.dumps(result, ensure_ascii=False)` 超 `SUMMARY_TRUNCATE=500` 字符截断至 500 + `truncated=True`，否则原样 `truncated=False`；失败：信封中文文案原样 `truncated=False`
  - **回灌消息构造**：`{"role": "tool", "tool_call_id": call_id, "content": json.dumps(result, ensure_ascii=False)}`——**完整结果回灌**（裁决 #7：LLM 自纠与总结质量依赖；非法工具名同款信封格式，自纠通道统一）
  - **轮收口**：全部工具执行完 → `save_round_messages`（成组落库）→ `messages` 追加 assistant(tool_calls)（content=本轮文本，可为空串）+ 全部 tool 消息 → `round += 1` → 回轮循环顶部（CP-1 判定 `round > MAX_ROUNDS` → 收尾 max_rounds）
  - `tool_call_count += 1`（含失败与非法调用，spec §6.2 规则 15）
- **涉及文件**：修改 `backend/app/agent/core.py`
- **完成判定**：`./.venv/Scripts/python.exe -m py_compile app/agent/core.py` 通过；D3/D5 与错误信封断言由组 8.2/8.4 固化
- **依赖**：4.3
- **决策锚点**：决策 A5；裁决 #7；spec §5.1.1 规则 4/8/9/10、§5.3.1 规则 3/4

### 4.5 OB-1 上下文体积观测点（R3 补充约束 3——独立任务项，只观测不截断）

- [ ] **要点**：
  - **位置**：每轮 LLM 调用发起前（CP-1 预算检查通过后、`yield _thinking_event` 之前）——**OB-1 标签与 CP 系列刻意区分：CP 拦截调用，OB 只记录**，观测点对控制流零影响（design 2.1.3-F）
  - **统计口径**：`total_chars = len(json.dumps(messages, ensure_ascii=False))`（一次性序列化总长，含 role 等结构开销——量级观测足够；每轮一次、30k 字符级序列化毫秒以内，开销可忽略——决策 A11）
  - **日志行为**：常态 → `logger.debug`；`total_chars > CONTEXT_LOG_WARN_CHARS(30000)` → `logger.warning` 升级；**两种级别字段一致**：标签 `agent_context_size` + 三字段 `conversation_id / round / chars`（全为元数据，合规 spec 4.3 规则 4 日志脱敏）
  - **禁止事项（R3 核心）**：① **不得因此截断/修改回灌内容**——messages 原样发 LLM（Agent 完整性优先，R3 明示；裁决 #7 完整结果回灌依赖）；② 不得把观测写进 SSE 事件流（服务端运维信号，非前端契约）
  - 观测目的写入注释：归因「响应越来越慢」是否上下文膨胀所致（get_learning_records 单次 ≤100 条完整 JSON 回灌 × 6 轮累积的膨胀路径），供后续调参，本阶段不据此改变任何行为
- **涉及文件**：修改 `backend/app/agent/core.py`（并入 4.3 轮循环的观测调用位）
- **完成判定**：`./.venv/Scripts/python.exe -m py_compile app/agent/core.py` 通过；**D13 断言由组 8.5 固化**（caplog 断言 debug/warning 三字段 + captured messages 不截断逐字节一致验证）
- **依赖**：4.3（观测位在轮循环内）
- **决策锚点**：决策 A11；design 2.1.3-F（OB-1）；spec §4.1 规则 8 / §8 D13；2.8.3 补充 3

### 4.6 O5 三分支优雅收尾 + finish_reason 真实判定 + 元数据日志

- [ ] **要点**：
  - `_graceful_finish`（design 2.1.3-B 决策树逐弧）：`remaining = TOTAL_BUDGET_S - (time.monotonic() - started_at)`；
    - `remaining < GRACEFUL_MIN_BUDGET_S(15s)` **或触发源为 timeout** → **分支③ 模板拼接（零 LLM 调用）**：`_build_template_summary` 生成「已为你查询到以下信息：\n- {tool_name}：{结果摘要 ≤200 字}\n...」；**无任何工具结果时**兜底句「处理时间较长，暂未获取到足够信息，请稍后重试或换个问法。」；模板文本以单条 `delta` 事件推送（前端统一 delta 渲染路径）
    - 预算充足 → **分支① 总结调用**：`tools` 不传（None）、不计轮次、不推 thinking；消息 = 已有序列 + 收尾指令 user 消息「基于以上工具调用过程与结果，不要再调用任何工具，直接用中文分点生成最终总结回答，必须引用结果中的具体数字」；流式产出 → `yield delta *`；**防御：总结轮收到 tool_calls 非空时忽略取文本**（决策 A7）
    - 总结调用异常（BizException / 原始异常 / 流中断）→ **分支② 降级模板拼接**（同分支③文案）+ `logger.warning`（降级原因，含 user_id 不含消息原文）
  - **finish_reason 判定表**（R2 补充约束 1，design 2.1.3 判定逻辑逐字）：最后一轮纯文本 → `normal`（不经 O5）；第 6 轮仍含 tool_calls → `max_rounds`（循环顶部 `round > MAX_ROUNDS`）；任一预算检查点剩余 ≤ 0 → `timeout`（超时触发时剩余必 < 15s 保护线 → 必走模板拼接，不追加任何 LLM 调用——spec §5.1.1 规则 6 后半句）
  - **收尾落库与终结**：`save_final_message(收尾文本)` → `yield _done_event(conversation_id, message_id, rounds=实际轮数, tool_call_count, finish_reason)` → 元数据日志（user_id / conversation_id / rounds / tool_call_count / finish_reason / 事件计数 / 耗时——**禁打印消息原文与回答全文**）
- **涉及文件**：修改 `backend/app/agent/core.py`
- **完成判定**：`./.venv/Scripts/python.exe -m py_compile app/agent/core.py` 通过；D6/D7 三分支断言由组 8.3 固化
- **依赖**：4.4、4.5
- **决策锚点**：O5（含 15s 保护条件）；决策 A7；R2 补充约束 1；design 2.1.3-B/CP-3

**里程碑验证（组 4 结束）**：
```bash
cd backend && ./.venv/Scripts/python.exe -m py_compile app/agent/core.py && \
./.venv/Scripts/python.exe -c "from app.agent.core import agent_chat_stream, _graceful_finish, _build_template_summary; print('CORE_IMPORT_OK')" && \
grep -n "def.*\(TOTAL_BUDGET_S\|MAX_ROUNDS\|GRACEFUL_MIN_BUDGET_S\)=" app/agent/core.py; grep -n "TOTAL_BUDGET_S\s*=\s*[0-9]" app/agent/core.py | grep -v "^[0-9]*:TOTAL_BUDGET_S = 60.0" && echo "O8_VIOLATION" || echo "O8_OK"
# O8_OK = 函数签名无默认参数捕获常量（全部为模块级定义 + 函数体直接引用）
```

---

## 5. schemas 与 api 端点（六端点扩展宿主）

**写作说明**：`schemas/agent.py` 38 → ~110 行；`api/v1/agent.py` 80 → ~300 行（P3 会话只读端点为扩展宿主，design 1.1.2）。路由全部在既有 `router = APIRouter(prefix="/agent")` 内扩展，**`api/v1/__init__.py` 零改动**（agent_router 已挂载，实测 `__init__.py:33,55`）。固定路径（`/conversations`、`/chat`）先注册、参数路径（`/conversations/{id}`）后注册。

### 5.1 schemas/agent.py 三入参模型 + AGENT_MESSAGE_MAX_LEN

- [ ] **要点**：
  - `AGENT_MESSAGE_MAX_LEN = 2000` 模块常量（与 core.py `MESSAGE_MAX_LEN` **各自定义同值、行内注释互相指认**——决策 A8/O6：与 P9 /chat/qa 的 500 不得抽成共用常量，上限语义独立演化）
  - `AgentChatIn`：`message: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=AGENT_MESSAGE_MAX_LEN)]`（去首尾空白后判定，spec §6.1）+ `conversation_id: int | None`（`ge=1`，可选）；`model_config = ConfigDict(extra="forbid")` 对齐全仓入参惯例
  - `ConversationCreateIn`：`title: str | None`（可选，strip，≤200；空/缺省 → None，首条消息落库时按 O4 补截断标题）
  - `ConversationRenameIn`：`title: str`（必填 1..200，strip——空标题 422/1001）
  - 既有 `ConversationOut` / `MessageOut` 零改动（满足前端工具卡片还原，spec §6.5）
  - 越界输入经全局处理器自动 422 + 1001 中文提示，schema 层零额外代码
- **涉及文件**：修改 `backend/app/schemas/agent.py`
- **完成判定**：`./.venv/Scripts/python.exe -m py_compile app/schemas/agent.py` 通过；`./.venv/Scripts/python.exe -c "from app.schemas.agent import AgentChatIn; AgentChatIn(message='  ')"` 抛 ValidationError；422 行为由组 8.4 固化
- **依赖**：无（可与组 4 并行）
- **决策锚点**：O6；决策 A8；spec §6.1/§6.5

### 5.2 POST /agent/chat SSE 端点（受理阶段 + StreamingResponse）

- [ ] **要点**：
  - 路由函数签名（design 2.2.2-(1)）：`async def agent_chat(payload: AgentChatIn, db: Annotated[Session, Depends(get_db)], current_user: Annotated[User, Depends(get_current_user)]) -> StreamingResponse`
  - **受理阶段流程**（StreamingResponse 构造前）：① `payload.conversation_id` 携带时 `memory.get_conversation_or_404(db, conversation_id, current_user.id)`（越权/不存在 → BizException 1005/404 → 全局处理器 → 统一 JSON，流未开始）；② 未携带时 `memory.create_conversation(db, current_user.id)`（title 先置 None，生成器内首条 user 消息落库时补截断标题，O4）
  - **受理/流内错误口径（裁决 #10）**：受理阶段 401/1003、422/1001、404/1005 走统一响应体 JSON（路由正常声明 Depends 与请求体模型即可零额外代码——`StreamingResponse` 构造发生在受理检查之后，全局异常处理器自动产出）；流内错误走 SSE error 事件带内信令
  - **SSE 格式化必须在 api 层**（契约 §4 禁 services 拼接响应——决策 A1）：`_sse_format` 闭包逐字复刻 P9——`f"data: {json.dumps(event, ensure_ascii=False)}\n\n"`（中文原样）
  - `StreamingResponse(media_type="text/event-stream", headers={"Cache-Control": "no-cache"})`（spec §4.3 规则 5 双响应头，禁中间层缓冲）
  - 启动 `core.agent_chat_stream(db, current_user.id, conversation, payload.message)` 生成器驱动事件流；user_id 一律取认证结果注入，禁收客户端传入的 user_id / conversation_id 越界参数（conversation_id 仅作会话定位并校验归属）
- **涉及文件**：修改 `backend/app/api/v1/agent.py`
- **完成判定**：`./.venv/Scripts/python.exe -m py_compile app/api/v1/agent.py` 通过；受理错误三态与响应头由组 8.4 固化
- **依赖**：5.1、组 4（core 生成器）、组 2（受理阶段 memory 调用）
- **决策锚点**：裁决 #10；决策 A1；spec §5.1.1 规则 1/2/3、§5.6.2 细则 1

### 5.3 会话管理四端点（新建 / 重命名 / 删除 / 消息全量）

- [ ] **要点**：
  - `POST /agent/conversations`（O1）：`payload: ConversationCreateIn` → `memory.create_conversation` → `success(data=ConversationOut 序列化)`；异常 401/1003、422/1001
  - `PATCH /agent/conversations/{conversation_id}`（O1）：`payload: ConversationRenameIn` → `memory.rename_conversation`（404 定位 + 更新 + 触碰）→ `success(data=更新后 ConversationOut)`；异常 401/1003、422/1001、404/1005
  - `DELETE /agent/conversations/{conversation_id}`：`memory.delete_conversation`（级联删消息）→ `success(data=None)`（硬删除）；异常 401/1003、404/1005
  - `GET /agent/conversations/{conversation_id}/messages`（O3 全量）：`memory.list_messages` → `success(data=list[MessageOut])`；404 语义先于空列表判定
  - 四端点均为薄委托（路由层零业务逻辑）；GET 详情端点（P3 既有）**保留不动**（R5 回归覆盖）
  - 路由注册顺序：固定路径 `/conversations`（GET/POST）与 `/chat` 先注册，参数路径 `/conversations/{conversation_id}`（GET/PATCH/DELETE）与 `/conversations/{conversation_id}/messages` 后注册（段数不同无前缀冲突）
- **涉及文件**：修改 `backend/app/api/v1/agent.py`
- **完成判定**：`./.venv/Scripts/python.exe -m py_compile app/api/v1/agent.py` 通过；端点行为由组 7.1 / 组 8.4 固化
- **依赖**：5.1、组 2
- **决策锚点**：O1/O3；spec §5.5.1、§5.6.1

### 5.4 列表排序行为变更（O2：id 升序 → updated_at 倒序）

- [ ] **要点**：
  - 既有 `list_conversations` 函数追加 `order_by=[desc(AgentConversation.updated_at), desc(AgentConversation.id)]`（一处参数，`paginate` 已支持——design 1.1.2）；query 参数仅分页一组，`PaginationParams` 查询参数模型展开条件满足（契约 §5.3）
  - **这是对 P3 端点唯一的行为变更（O2 有意变更）**：属既有端点行为变更，回归须覆盖——R6 断言**新行为**而非旧行为（倒序 + 同秒并列 id 倒序 tie-break）
  - 空列表返回 `{items: [], total: 0}` 不报错
- **涉及文件**：修改 `backend/app/api/v1/agent.py`（既有函数，仅换 order_by 参数）
- **完成判定**：`./.venv/Scripts/python.exe -m py_compile app/api/v1/agent.py` 通过；倒序断言由组 7.1 固化（多会话按最近活跃倒序）
- **依赖**：5.3（同文件先扩）
- **决策锚点**：O2；R6

**里程碑验证（组 5 结束）**：
```bash
cd backend && ./.venv/Scripts/python.exe -m py_compile app/schemas/agent.py app/api/v1/agent.py && \
git diff app/api/v1/__init__.py | wc -l    # 输出 0 = R7 冻结项确认（agent_router 既有挂载，零改动）
```

---

## 6. 测试一：test_agent_prompt.py（Prompt 纯函数单测）

**写作说明**：新增 `backend/tests/test_agent_prompt.py`（~200 行），用例组唯一来源：design 2.5.2-A 九组。conftest 全部复用既有 fixture（零新增基建）。

### 6.1 六组核心断言（三要素 / 边界 / 禁止 / 引导 / 身份 / 目标）

- [ ] **覆盖**：
  - **三要素齐备**：渲染结果同时含——北京日期串（当日 `datetime.now(TZ_BEIJING).date().isoformat()`）、档案四要素字段（mock 档案数据渲染：姓名/专业/年级/每日可学习时长）、逐字指令原文「直接调用工具完成任务，不要反问用户确认」（spec 5.2.1 规则 1）
  - **能力边界声明**：含「后续版本」表述、8 工具清单（动态生成段与 `TOOLS_SCHEMA` 名集合一致）、禁止编造计划表述（D2 / 规则 6）
  - **禁止事项**：三条逐项（不编造 / 不诊断 / 不越权）各含锚点短语（规则 5）
  - **场景引导**：含三工具组合引导串 `get_learning_statistics` + `get_tasks` + `get_knowledge_mastery`（规则 7 / D1 机制侧）
  - **身份与风格**：身份串 + 三条风格要求（规则 4）
  - **当前目标**：含 current_goal_type 渲染值（规则 3）
- **涉及文件**：新增 `backend/tests/test_agent_prompt.py`
- **完成判定**：`cd backend && ./.venv/Scripts/python.exe -m pytest tests/test_agent_prompt.py -v` 全绿；日期/指令用精确包含断言（验收锚点）
- **依赖**：组 3
- **验收锚点**：验收 D2（Prompt 断言半）；spec 5.2.1 规则 1/3/4/5/6/7

### 6.2 三组降级与集中管理断言（预取降级 / 默认档案 / 集中管理）

- [ ] **覆盖**：
  - **预取降级**：monkeypatch `TOOL_MAP` 预取两项返回 `{"error"}` → 渲染缺档案/概况段、**日期与逐字指令仍恒在**（「缺段不缺要素」）、warning 已记（规则 2 / spec 5.2.3 场景 2；预取抛异常同款断言）
  - **默认档案**：无档案用户渲染默认值（daily_study_minutes=60），非降级（spec 5.2.3 场景 1）
  - **集中管理**：全局检索 Prompt 拼接点仅 prompts.py——测试内以 `subprocess` 或收集期断言 `grep -rln "system_prompt\|今天是" app/` 仅命中 `app/agent/prompts.py`（规则 8）
- **涉及文件**：修改 `backend/tests/test_agent_prompt.py`
- **完成判定**：`./.venv/Scripts/python.exe -m pytest tests/test_agent_prompt.py -v` 全绿（与 6.1 合并跑）
- **依赖**：6.1（同文件）
- **验收锚点**：spec 5.2.1 规则 2/8、5.2.3 场景 1/2

**里程碑验证（组 6 结束）**：
```bash
cd backend && ./.venv/Scripts/python.exe -m pytest tests/test_agent_prompt.py -v 2>&1 | tail -3
```

---

## 7. 测试二：test_agent_memory.py（memory 单测 + 端点行为）

**写作说明**：新增 `backend/tests/test_agent_memory.py`（~280 行），用例组唯一来源：design 2.5.2-B 八组。双账号隔离断言复用 `user_a` / `user_b` fixture。

### 7.1 会话 CRUD / 标题截断 / 列表倒序 / 空会话（D10）

- [ ] **覆盖**：
  - **会话 CRUD**：新建（title None / 显式值）；重命名（1..200 边界：空与 201 → 422/1001）；删除后列表不含、消息端点 404（D10 / spec 5.4.1 规则 1、7、8）
  - **标题截断**：首条 30 字符 user 消息 → title 为前 20 字符（O4）；显式新建空 title 同样在首条消息时补（规则 1）
  - **列表倒序**：多会话不同 updated_at → 倒序；同秒并列 id 倒序 tie-break（D10 / O2；R6 断言新行为）
  - **空会话**：显式新建后消息端点返回 `[]` 不报错（spec 5.4.3 场景 3）
- **涉及文件**：新增 `backend/tests/test_agent_memory.py`
- **完成判定**：`cd backend && ./.venv/Scripts/python.exe -m pytest tests/test_agent_memory.py -v` 全绿
- **依赖**：组 2、5.3、5.4
- **验收锚点**：验收 D10；O2/O4

### 7.2 隔离 / 窗口成对截断 / updated_at 触碰 / 消息全量（D9/D4/O7）

- [ ] **覆盖**：
  - **隔离**：双账号互查会话/消息 → 404/1005（user_a 建会话、user_b 读 → 404）（D9）
  - **窗口成对截断**：构造 25 条历史（含 tool 链）→ `load_context_window` 返回 ≤20 条且**首条非孤立 tool**；历史轮 assistant(tool_calls)+tool 成对出现（spec 5.4.1 规则 5 / O7）
  - **updated_at 触碰**：以「续聊会话在倒序列表升至首位」行为断言（spec 5.4.1 规则 4 验收原句——freezegun 难，行为级验证）
  - **消息全量**：多轮对话后消息端点全量返回、id 升序、含 tool_calls JSON 与 tool 消息（还原链完整，D4 / 规则 6）
- **涉及文件**：修改 `backend/tests/test_agent_memory.py`
- **完成判定**：`./.venv/Scripts/python.exe -m pytest tests/test_agent_memory.py -v` 全绿（与 7.1 合并跑）
- **依赖**：7.1（同文件）
- **验收锚点**：验收 D9/D4；O7

**里程碑验证（组 7 结束）**：
```bash
cd backend && ./.venv/Scripts/python.exe -m pytest tests/test_agent_memory.py -v 2>&1 | tail -3
```

---

## 8. 测试三：test_agent_chat_stream.py（SSE 契约 e2e，mock LLM + 真实工具）

**写作说明**：新增 `backend/tests/test_agent_chat_stream.py`（~470 行），用例组唯一来源：design 2.5.2-C 十六组 + R3 新增 D13 组。**mock 注入形态**（design 2.5.1）：`monkeypatch.setattr("app.services.llm.agent_chat_stream", fake)`（core.py 模块属性访问）；预算类 `monkeypatch.setattr("app.agent.core.TOTAL_BUDGET_S", 1.0)` / `monkeypatch.setattr("app.agent.core.GRACEFUL_MIN_BUDGET_S", 61.0)`；慢工具 `monkeypatch.setitem(TOOL_MAP, "get_tasks", slow_fake)`；落库失败 `monkeypatch.setattr("app.agent.memory.save_*", raiser)`。**P10 测试坑**：datetime.time 一律改名 `dt_time` 导入；慢日志断言用自装 `logging.Handler` 捕获（D8）。

### 8.1 假流工厂模块级辅助

- [ ] **要点**：
  - 模块级假流工厂（design 2.5.1 示意形态）：按脚本序列产出 `AgentStreamPart`（文本增量 / 轮终聚合块），`tc(call_id, name, args)` 辅助构造 OpenAI 形态 tool_call；**捕获每次调用收到的 (messages, tools, max_tokens)** 存入 `captured_calls`（D1 上下文断言 / D6「无第 7 次 LLM 调用」计数 / max_tokens 与 tools 透传断言的数据源）
  - 脚本形态示例：轮 1 三 tool_calls → 轮 2 文本含数字；「永远 tool_calls」脚本（D6）；「慢流」脚本（每片 `await asyncio.sleep`，D7）
- **涉及文件**：新增 `backend/tests/test_agent_chat_stream.py`
- **完成判定**：文件可被 pytest 收集（`./.venv/Scripts/python.exe -m pytest tests/test_agent_chat_stream.py --co -q` 无报错）
- **依赖**：组 1（AgentStreamPart 类型）——可早于组 4 编写，运行依赖组 1–5 全部
- **决策锚点**：design 2.5.1 注入点表

### 8.2 多工具事件序列 + 落库链 + 上下文回灌 + max_tokens（D1/D3/D4）

- [ ] **覆盖**：
  - **多工具事件序列**：脚本「轮 1 三 tool_calls（statistics/tasks/mastery）→ 轮 2 文本含数字」→ SSE 序列 `thinking{1} → tool_call×3 → tool_result×3 → thinking{2} → delta* → done`；`tool_call.arguments` 为 JSON 对象且 call_id 与 tool_result 一一对应；done 五字段与统计一致（rounds=2、tool_call_count=3、finish_reason=normal、conversation_id 新建）；**captured messages 断言**：含 system + 历史 + user + assistant(tool_calls) + tool×3 回灌序列（D1 / D3 / spec 5.1.1 规则 4）
  - **落库链**：上例后读库：user → assistant(tool_calls) → tool×3 → assistant(最终) 成对有序，tool_calls 含 arguments、tool_call_id 可关联（D4 / 规则 3）
  - **上下文回灌**：第二次请求带 conversation_id → captured messages 首条（system 后）非孤立 tool、历史成对出现（spec 5.4.1 规则 5）
  - **max_tokens 断言**：captured 调用参数 `max_tokens == 2048` 且 `tools == TOOLS_SCHEMA`（spec 5.1.1 规则 7——D6 前置：审查 LLM 调用点常量）
  - **续聊会话**：携带本人 id → done.conversation_id 同 id；列表该会话升至首位（updated_at 触碰行为级验证，spec 5.4.1 规则 4）
- **涉及文件**：修改 `backend/tests/test_agent_chat_stream.py`
- **完成判定**：`cd backend && ./.venv/Scripts/python.exe -m pytest tests/test_agent_chat_stream.py -v -k "sequence or persist or context or max_tokens or resume"` 全绿
- **依赖**：8.1、组 1–5 全部
- **验收锚点**：验收 D1（结构等价）/ D3 / D4

### 8.3 6 轮上限 + O5 三分支 + 60s 总预算（D6/D7）

- [ ] **覆盖**：
  - **6 轮上限**：脚本永远返回 tool_calls（每轮 1 个）→ 带 round 的 thinking 恰 6 条（**无第 7 条**）；done.finish_reason="max_rounds"；无 error；LLM 调用计数=6（总结调用另计）；落库 6 轮链完整（D6 / 规则 5）
  - **O5 总结分支①**：预算充足场景（默认 60s）→ 第 6 轮后捕获到**第 7 次 LLM 调用（tools 不传）**且无对应 thinking；总结产出以 delta 推送；done.finish_reason="max_rounds"（O5 分支①）
  - **O5 保护条件③**：`monkeypatch.setattr("app.agent.core.GRACEFUL_MIN_BUDGET_S", 61.0)`（调大保护线）→ 第 6 轮后**无总结 LLM 调用**（计数仍 6）、回答为模板文本（含「已为你查询到以下信息」）、finish_reason 仍 "max_rounds"（O5 分支③）
  - **60s 总预算**：`monkeypatch.setattr("app.agent.core.TOTAL_BUDGET_S", 1.0)`（必然 < 15s 保护线）+ 慢假流（每片 sleep）→ done.finish_reason="timeout"、无 error、无总结调用（模板拼接路径）、总耗时 ≤ 预算 + 单步容忍（D7 / 规则 6——**O8 常量 monkeypatch 生效性的运行时证明**）
  - **O5 分支②**（总结调用失败降级）：总结轮脚本抛 BizException → 回答为模板文本 + finish_reason 仍真实（design 2.1.3-B 降级链）
- **涉及文件**：修改 `backend/tests/test_agent_chat_stream.py`
- **完成判定**：`./.venv/Scripts/python.exe -m pytest tests/test_agent_chat_stream.py -v -k "rounds or graceful or budget or timeout"` 全绿
- **依赖**：8.2（复用假流工厂脚本形态）
- **验收锚点**：验收 D6/D7；O5/O8；R2 补充约束 1（finish_reason 三值真实）

### 8.4 异常与边界全家桶（D5/D8/D9/D11 + 落库失败 + 受理错误 + 摘要截断）

- [ ] **覆盖**：
  - **非法工具名**：脚本轮 1 含 `name="foo_bar"` → tool_result(ok=false, summary 含「该工具不可用」) 后对话继续至 done；进程无异常；落库 tool_name 照存（截断 50）（D5 / 规则 8）
  - **错误信封**：脚本轮 1 调 `get_learning_records` 参数 `days=999`（超出 1..365）→ tool_result(ok=false)、summary 为 P10 信封文案、后续轮正常（captured messages 中 tool content 为信封 JSON——LLM 收到错误文案，P10 自纠机制被消费）（spec 5.1.1 规则 9）
  - **摘要截断**：真实工具造大结果（注册后灌 100 条学习记录再问）→ tool_result.summary ≤500 字符且 truncated=true；小结果 truncated=false 且 summary 与结果一致（D3 / spec 5.3.1 规则 4）
  - **LLM 失败**：mock 创建即抛 BizException(3000) → 末条 error{3000, 中文}、无 done；**user 消息已落库**（裁决 #12 验收）；mock 流中途抛原始异常（首 delta 后）→ error 3000「回答生成中断，请重试」（D11 / spec 5.1.3 场景 1、2）
  - **落库失败**：monkeypatch `app.agent.memory.save_final_message` 抛异常 → 流仍 done 收尾、message_id=null、无 error 事件（spec 4.2 规则 6 / 5.4.3 场景 2）
  - **受理错误**：无 token → 401/1003 JSON（非 SSE）；空 message / 2001 字符 / 非整数 conversation_id → 422/1001；不存在或他人会话 id → 404/1005（D9 / spec 5.1.1 规则 1、2、3）
  - **慢工具日志**：`monkeypatch.setitem(TOOL_MAP, "get_tasks", slow_fake)`（asyncio.sleep 400ms 包真实实现）→ 自装 logging.Handler 捕获断言 `agent_tool_slow` 三字段行（tool_name/user_id/elapsed_ms）（D8——**P10 惯例 Handler 捕获**）
- **涉及文件**：修改 `backend/tests/test_agent_chat_stream.py`
- **完成判定**：`./.venv/Scripts/python.exe -m pytest tests/test_agent_chat_stream.py -v -k "illegal or envelope or truncate or llm_fail or save_fail or auth or slow"` 全绿
- **依赖**：8.2
- **验收锚点**：验收 D5/D8/D9/D11；裁决 #12

### 8.5 上下文体积观测用例组（D13——R3 新增）

- [ ] **覆盖**：
  - **debug 常态**：多轮脚本（≥2 轮）跑循环 → caplog（或自装 Handler）断言**每轮 LLM 调用前**有 debug 级 `agent_context_size` 行，三字段 `conversation_id / round / chars` 齐备且 round 从 1 递增（spec §4.1 规则 8a）
  - **warning 升级**：构造大上下文（预置长历史或多条大结果工具回灌，使某轮 `chars > 30000`）→ 该轮升 warning 同三字段；其余轮仍 debug（阈值边界：CONTEXT_LOG_WARN_CHARS=30000）
  - **captured messages 不截断验证**：同一脚本分别在「观测启用」与「观测代码移除/禁用日志」两种场景跑 → captured_calls 中 messages 内容**逐字节一致**（观测不改内容——不截断的直接验证，spec §8.2 步骤 9 后半）；实现形态：比对 captured messages 的 `json.dumps(..., sort_keys=True)` 全等
  - **不进 SSE 断言**：全部 SSE 事件中不出现 `agent_context_size` 或 chars 类字段（观测是服务端运维信号，非前端契约）
- **涉及文件**：修改 `backend/tests/test_agent_chat_stream.py`
- **完成判定**：`./.venv/Scripts/python.exe -m pytest tests/test_agent_chat_stream.py -v -k "context_size or observ"` 全绿
- **依赖**：8.2（复用假流工厂与 captured_calls 形态）
- **验收锚点**：**验收 D13**（R3 补充约束 3）；决策 A11；design 2.1.3-F（OB-1）

**里程碑验证（组 8 结束）**：
```bash
cd backend && ./.venv/Scripts/python.exe -m pytest tests/test_agent_chat_stream.py -v 2>&1 | tail -3
```

---

## 9. 兼容性回归（R1–R8）

**写作说明**：本组是 D12 验收的落地（design 2.6 八项逐条）。冻结项以 git diff 审查为硬标准；既有套件以实测基线为硬标准（P9 全量 115 passed、P10 套件 76 PASS / 0 FAIL）。

### 9.1 R1：llm.py 既有方法零改动 diff 审查

- [ ] **要点**：
  - `git diff backend/app/services/llm.py` 逐 hunk 人工审查：`ChatMessage` / `get_chat_client` / `_SERVICE_ERRORS` / `reset_clients` / `chat` / `chat_stream` / 客户端构造区**一行不动**；改动仅限文件末尾追加区（组 1 已在里程碑预检，此处正式复核并记录）
  - P9 依赖 `chat_stream` 的既有用例全绿（并入 9.3 全量跑）
- **涉及文件**：审查 `backend/app/services/llm.py`（无代码改动）
- **完成判定**：`git diff backend/app/services/llm.py | grep "^-" | grep -v "^---" | wc -l` 输出 0（无删除/修改行，纯追加）；或 diff hunk 全部位于文件末尾追加区的人工记录
- **依赖**：组 1
- **验收锚点**：R1 / D12

### 9.2 R2/R3/R7/R8：冻结项 diff 审查 + P10 套件回归

- [ ] **要点**：
  - **R2**：`git diff backend/app/agent/tools.py backend/app/agent/registry.py` 为空（P10 冻结）
  - **R7**：`git diff backend/app/api/v1/__init__.py` 为空（agent_router 既有挂载零改动）
  - **R8**：`git diff backend/app/models/` 为空（全部 DDL 零变更，spec §4.5 规则 5）
  - **R3**：直接跑 P10 工具测试套件（不修改，1021 行 76 用例）
- **涉及文件**：审查冻结清单（无代码改动）
- **完成判定**：三条 diff 命令全部输出空；`cd backend && ./.venv/Scripts/python.exe scripts/test_tools.py 2>&1 | grep "汇总"` 输出「**76 PASS / 0 FAIL**」
- **依赖**：组 1–8（冻结项理论上全程零改动，可在任意里程碑先跑，正式收口在本组）
- **验收锚点**：R2/R3/R7/R8 / D12

### 9.3 R4/R5/R6：P9 全量回归 + P3 端点 + 列表行为变更确认

- [ ] **要点**：
  - **R4**：`pytest tests/` 全量跑——既有 115 基线不被破坏（交付后应为 115 + 新增三文件用例数全绿）
  - **R5**：P3 详情端点行为不变——`GET /agent/conversations/{id}` 出参与 404 语义不变（含 `agent_messages.py` 两端点可见性）——组 7.1 详情用例 + 全量回归覆盖
  - **R6**：列表排序行为变更（O2 有意变更）——断言**新行为**（updated_at 倒序 + id tie-break）而非旧行为（组 7.1 倒序用例覆盖，此处确认变更即预期并记录）
- **涉及文件**：无代码改动（回归验证，操作记录可存 `backend/tmp_verify/` 沿用既有惯例）
- **完成判定**：`cd backend && ./.venv/Scripts/python.exe -m pytest tests/ -q 2>&1 | tail -1` 输出全绿（零 failed）；`./.venv/Scripts/python.exe -m pytest tests/test_rag_qa_stream.py tests/test_rag_qa_prompt.py tests/test_rag_qa_scope.py -q` 全绿（P9 SSE 通道零破坏专项）
- **依赖**：组 6、7、8、9.1、9.2
- **验收锚点**：R4/R5/R6 / D12

**里程碑验证（组 9 结束——全链路收口）**：
```bash
cd backend && ./.venv/Scripts/python.exe -m pytest tests/ -q 2>&1 | tail -1          # 全绿（115 基线 + 新增）
cd backend && ./.venv/Scripts/python.exe scripts/test_tools.py 2>&1 | grep "汇总"     # 76 PASS / 0 FAIL
git diff --stat backend/app/agent/tools.py backend/app/agent/registry.py backend/app/api/v1/__init__.py backend/app/models/   # 输出为空
```

---

## 10. 文档同步与收尾

### 10.1 PROJECT_CONTEXT §3 目录树更新（裁决 #1 交付义务）

- [ ] **要点**：
  - `docs/PROJECT_CONTEXT.md` §3 目录树 `agent/` 小节：`executor.py`（滞后项）改为实际交付——`tools.py`（8 个 Tool 实现）/ `registry.py`（TOOLS_SCHEMA / TOOL_MAP）/ `core.py`（LLM 工具调用主循环）/ `prompts.py`（系统提示词模板）/ `memory.py`（会话与消息持久化），并补简注（~8 行改动）
  - 该树此前已滞后于 P10 实际（registry.py 亦未列入）——本次一并补齐（裁决 #1 原文要求）
- **涉及文件**：修改 `docs/PROJECT_CONTEXT.md`（仅 §3 目录树 agent/ 小节）
- **完成判定**：`grep -A 7 "agent/" docs/PROJECT_CONTEXT.md | grep -E "core.py|memory.py|registry.py|prompts.py|tools.py"` 五文件全命中且 `executor.py` 不再出现
- **依赖**：无代码依赖（组 2/3/4 文件落地后语义才成立，建议收尾执行）
- **决策锚点**：裁决 #1；design 1.1.3-(D)

### 10.2 代码走查与设计一致性核对

- [ ] **要点**：
  - **分层合规**：api 层新端点无业务规则（薄委托 + SSE 格式化）；core.py 不 import api；`grep "from app.api" backend/app/agent/core.py` 零命中；memory.py docstring 含裁决 #5 边界注明；学习业务数据只经 TOOL_MAP（`grep -n "TOOL_MAP" backend/app/agent/core.py` 派发点唯一）
  - **O8 静态核查**：`grep -nE "def .*=\s*(TOTAL_BUDGET_S|MAX_ROUNDS|GRACEFUL_MIN_BUDGET_S)" backend/app/agent/core.py` 零命中（无默认参数捕获）；常量全部模块级定义
  - **OB-1 核查**：观测点在 CP-1 后 thinking 前；日志只 debug/warning 不截断；`agent_context_size` 不出现在任何 SSE 事件构造函数
  - **docstring 回链**：各新模块注明对应 design.md 章节号（2.4.1 core / 2.4.2 llm / 2.4.3 prompts / 2.4.4 memory / 2.2.2 接口）
  - **隐私红线**：全链路日志禁打印用户消息原文与回答全文（spec 4.3 规则 4）；落库失败 warning 含 user_id 不含原文；元数据日志字段清单核对
  - **契约核对**：snake_case 全程、type hints 全覆盖、无硬编码模型名/地址/Key（LLM 配置经 core/config 既有字段）、行为常量锁定 core.py 模块级、错误码沿用既有常量无新码位、`tool_calls` 落库直存 list 结构（JSONType 禁手动序列化）
  - **前端禁令核查**：`git status frontend/` 零改动——本阶段不创建任何前端文件（AgentView.vue / agent.ts 等属后续阶段）
- **涉及文件**：组 1–5 全部新增/改动文件（走查，无代码改动）
- **完成判定**：七项走查全部通过；与 design.md「下游交接说明」无偏差（未覆盖细节按 PROJECT_CONTEXT 总则处理并在提交说明记录）
- **依赖**：组 9
- **验收锚点**：design 2.8.1 铁律逐条遵循清单

### 10.3 本机真实 LLM 验证清单交接（V1–V6，沙箱 mock 无法覆盖）

- [ ] **要点**（沙箱网络全禁，以下留给用户本机执行；前置：`.env` LLM 配置有效、前后端启动）：
  1. **V1 真实学习分析（D1 真实数字）**：登录 → `curl -N POST /api/v1/agent/chat` 问「我最近学习怎么样」→ 观测 ≥3 工具连调、回答含真实统计数字
  2. **V2 真实不编造（D2）**：问「帮我制定下周学习计划」→ 回答含「后续版本」表述、无伪造计划条目
  3. **V3 SSE 端到端（D3）**：`curl -N` 观测六事件序列、delta 实时到达（时间戳）、大结果摘要截断
  4. **V4 持久化（D4）**：对话后重开会话列表/消息端点 → 历史完整（前端页面验证留待后续阶段）
  5. **V5 LLM 故障（D11）**：改错 `.env` LLM_BASE_URL 重启 → 中文错误提示、连接关闭、日志记录 → 还原恢复
  6. **V6 过度调用实测**：观察 deepseek-flash 实际轮次分布（验证 6 轮上限充足性与收尾自然度，供后续调参）
- **涉及文件**：无新增（操作验证，记录建议存 `backend/tmp_verify/`）
- **完成判定**：V1–V6 逐条核对通过（spec §8.3 全量承接）
- **依赖**：组 9、10.1、10.2
- **验收锚点**：spec §8.3 V1–V6

**里程碑验证（组 10 结束——全阶段收口）**：
```bash
git status --short frontend/ | wc -l                    # 输出 0 = 前端禁令确认（零前端文件）
grep -c "executor.py" docs/PROJECT_CONTEXT.md           # 输出 0 = 目录树滞后项已修正
git diff --stat | tail -5                                # 变更范围核对：仅设计许可的 4 个后端文件 + 3 个测试文件 + 1 个文档 + tasks.md 本身
```

---

## 附：任务 → 验收覆盖对照（D1–D13）

| 验收项 | 判定标准摘要（spec §8.1） | 覆盖任务 |
|---|---|---|
| D1 学习状态自动分析 | mock 3 工具连调 + 回答含具体数字 | 8.2（结构等价）；10.3 V1（真实数字） |
| D2 能力边界不编造 | Prompt 含边界声明 + 真实 LLM 不伪造 | 3.1、6.1（Prompt 断言）；10.3 V2 |
| D3 工具调用过程 SSE 可见 | tool_call 参数对象 / tool_result 耗时与 ≤500 摘要 | 4.2、4.4、8.2、8.4（摘要截断）；10.3 V3 |
| D4 会话持久化 | 落库链完整 + 刷新还原（服务端维度） | 2.3、7.2、8.2（落库链/回灌）；10.3 V4 |
| D5 非法工具名兜底 | 不崩溃、ok=false「该工具不可用」、对话继续 | 4.4、8.4 |
| D6 6 轮优雅收尾 | 恰 6 轮、max_rounds、无第 7 个 thinking；<15s 走模板 | 4.1、4.6、8.3（上限/总结分支/保护条件） |
| D7 60s 总预算与收尾保护 | 预算调小 + 慢 LLM → timeout、无总结调用 | 4.1、4.3（CP-1/CP-2）、4.6、8.3（O8 monkeypatch） |
| D8 工具慢日志 | >300ms → agent_tool_slow 三字段 | 4.4（elapsed_ms 同值口径）、8.4（Handler 捕获） |
| D9 鉴权与隔离 | 401/1003；双账号互不可见 404/1005 | 5.2、7.2、8.4（受理错误三态） |
| D10 会话管理端点 | 列表倒序/消息全量/删除级联/重命名/新建 | 2.1–2.2、5.3、5.4、7.1 |
| D11 异常可读提示 | LLM 失败 → error(3000) 中文、已推内容保留 | 4.3（双兜）、8.4；10.3 V5 |
| D12 兼容性回归 | llm 既有零改动 / P10 零改动 / P9 全绿 / P3 不变 | 9.1（R1）、9.2（R2/R3/R7/R8）、9.3（R4/R5/R6） |
| **D13 上下文体积观测（R3 新增）** | 每轮 debug 三字段；>30000 升 warning；**messages 不截断（逐字节一致）** | **4.5（OB-1 独立任务项）、8.5（caplog + captured messages 断言）** |

| spec 需求条目 | 覆盖任务 |
|---|---|
| §5.1 主循环（鉴权/校验/会话定位/循环执行/轮上限/总预算/max_tokens/非法名/信封回灌/工具执行/终结事件） | 4.3、4.4、4.6、5.1、5.2、8.2–8.4 |
| §5.2 System Prompt（三要素/预取/当前目标/风格/禁止/边界/引导/集中管理） | 3.1–3.3、6.1、6.2 |
| §5.3 SSE 事件流（信封格式/顺序/载荷/截断/真实流式） | 4.2、4.4、5.2、8.2、8.4 |
| §5.4 多轮会话与持久化（创建/user 落库/循环落库/触碰/回灌/还原/删除/重命名/隔离） | 2.1–2.5、5.3、7.1、7.2、8.2 |
| §5.5 会话管理接口（列表/消息/校验） | 2.2、5.3、5.4、7.1 |
| §5.6 接口清单与 SSE 契约（六端点/六事件） | 5.2、5.3、5.4、4.2 |
| §4.1–4.5 DFX（含 R3 规则 8 观测） | 4.1（常量）、4.5（OB-1）、9.1–9.3（兼容性）、10.2（隐私红线走查） |
| §6 数据约束（入参/事件载荷/落库两表） | 5.1、4.2、2.3 |
| 裁决 #1–#12 + O1–O8 + R2/R3 补充约束 | 全部任务（组 0 前置约定 + 各任务决策锚点） |