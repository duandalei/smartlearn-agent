# TASKS_AGENT_ABSORB_ASK —— L2 · Agent 吸收 Ask（自动知识库检索 + 来源展示 + 隐藏独立问答页）编码任务清单

> **变更说明（2026-10-25，公共库能力已移除）**：`search_knowledge_base` 的 `scope` 参数已删除，检索恒为当前用户个人库；「个人库为空不得静默扩大为 public/all」规则随之简化为「无命中即据实说明」。下文涉及 scope 三档的历史条目仅作演进记录。

> feature：`agent_absorb_ask`（L2 批次）
> 状态：已实施并通过 G1–G5（2026-10-25）；含来源卡引用过滤与 A2/A6 日期敏感修复补丁。
> 上游输入：`.codeartsdoer/specs/agent_absorb_ask/spec.md`（294 行定稿，含 5 处定点修订：统一检索范围口径默认 all、冲突以检索内容为准、个人库为空不得静默扩大、多次检索按 (item_id, chunk_index) 去重、来源卡片必须挂在最终回答下方）；`docs/designs/DESIGN_AGENT_ABSORB_ASK.md`（611 行定稿，含 2 处修正：① 历史回放来源按用户轮次 flush 到本轮最后一个 assistant 块——pendingSources 暂存 + lastAssistant 游标 + user 分支前置 flush + 循环末尾终态 flush，不使用 blockIndex；② §2.4 最终门禁为全量 `pytest -q` + `npm run build`）
> 产物落点：本文档落在 `docs/tasks/TASKS_AGENT_ABSORB_ASK.md`（对齐 `TASKS_DEMO_RESET.md`、`TASKS_PLAN_REPORT_FRONTEND.md` 既有惯例）
> 代码事实基线：2026-10-24 工作区（本文所有「文件:行号」均经本次实际读取复核，与 design「代码事实核对基线」一致）
> 后端测试基线：206 passed（P13 基线；本特性新增 6 个后端用例后应为 212 passed，若基线有变以开工实测为准并记录原因）
>
> **编号读法**：「验收 §x.x.x-n」指 spec 各章业务规则及 a/b/c 验收条件条目；「design §x.x.x-X」指 design 章节（A=Prompt 策略 / B=SSE 与后端数据 / C=前端数据流与展示 / D=单一入口收敛）。

---

## 非目标（写死，任何任务不得越界）

1. **不做 L3 范围**：不合并两套会话存储、不合并两套 SSE 协议、不重写 Agent 会话/SSE 架构（spec §1.4-1/2/6）。
2. **不删除既有问答资产**：`/chat/qa`、`/chat/history` 后端接口、`frontend/src/views/AskView.vue`、`frontend/src/components/ask/*` 全部保留、行为不变（spec §1.4-3/4、§5.3.1 规则 3）。
3. **不新增任何依赖**：前后端均不引入新依赖（不碰 `frontend/package.json`、后端依赖清单；spec §1.4-5、§4.5-4）。
4. **不改库结构、不改契约**：`agent_messages` 等库表零变更；`/chat/qa`、`/chat/history` 契约不变；tool_result 事件既有六字段名称/语义/序位冻结（spec §4.5-1/2/3）。
5. **不 commit**：本轮及实现阶段产出物均不执行任何 git commit。
6. **不进入下游阶段**：本清单完成后停止并汇报，等待确认；编码由实现阶段执行。

## 最终门禁（写死，组 6 逐条验收）

| # | 门禁 | 判据 |
|---|------|------|
| G1 | 后端全量测试 | `cd backend && ./.venv/Scripts/python.exe -m pytest -q` → **0 failed**（基线 206 + 新增 6 = 212 passed；基线若变须记录原因） |
| G2 | 前端构建 | `cd frontend && npm run build` → **exit 0**（含 vue-tsc 类型检查链路） |
| G3 | 手工场景 1–7 | 组 6.3 七条手工场景全部走查通过并记录 |
| G4 | 改动范围 | `git status --short -uall` 与开工基线对比：改动仅限本文「实现前置约定 6」白名单（含 `backend/tests/test_plan_adjust.py` 日期敏感修复例外）；`frontend/src/components/ask/**`、`frontend/src/views/AskView.vue`、`frontend/src/types/index.ts`、`frontend/src/api/**`、`frontend/package.json` 及 `backend/app/` 其余文件零改动 |
| G5 | 冻结资产行为 | `/chat/qa`、`/chat/history` 接口与 AskView 链路代码原样存在（grep 佐证），路由表无 component 形态的 ask 记录 |

调试期允许单文件快跑（`pytest backend/tests/test_agent_chat_stream.py backend/tests/test_agent_prompt.py -q`、`npx vue-tsc --noEmit`），但**收尾门禁必须是全量两条**（design §2.4）。

---

## 0. 任务总览与依赖关系

**分组结构**（6 组，共 19 个子任务）：

```
组1 后端 Prompt 与 ToolSpec（1.1 → 1.3；1.2 → 1.3）────────────┐
组2 后端 SSE sources（2.1 → 2.2 → 2.3）───────────────────────┤ 组1 与组2 零文件交集，可并行
                                                                ↓
组3 前端类型与 AgentView 数据流（3.1 → 3.2 → 3.3 → {3.4 ∥ 3.5}；3.6 仅依赖 3.1）
                                                                ↓
组4 前端展示组件（4.1 → 4.2；依赖组3 的 3.1/3.3 类型与字段）─────┤
组5 单一入口与文档（5.1 ∥ 5.2；与组1–4 全并行）─────────────────┤
                                                                ↓
组6 全量门禁（6.1 后端全量 → 6.2 前端构建 → 6.3 手工走查 + 范围核对；依赖组1–5 全部）
```

**关键路径**：2.1 → 2.2 → 2.3 → 3.2 → 3.3 → 3.5 → 4.1 → 4.2 → 6.1 → 6.2 → 6.3。

**可并行标注**：
- 组 1 与组 2 零文件交集（prompts.py/registry.py/test_agent_prompt.py vs core.py/test_agent_chat_stream.py），可完全并行。
- 组 3 与组 1/组 2 零文件交集（前端 vs 后端）；但 `data.sources` 的真值表口径（design §2.1.3-B）是 3.2/3.4 的输入语义，**建议组 2 先行或同步评审**，代码层面允许并行。
- 组 3 内部：3.4 与 3.5 在 3.2/3.3 完成后可并行（实时路径 vs 历史路径，函数不同区块）。
- 组 5 与组 1–4 全部并行（菜单/路由/文档，零代码交集）。
- 组 6 串行收尾，不可提前。

**实现前置约定**（全文适用，各任务不再重复）：
1. **改动面收敛**：后端只动 `backend/app/agent/prompts.py`、`backend/app/agent/core.py`、`backend/app/agent/registry.py` 三个产品文件 + `backend/tests/test_agent_chat_stream.py`、`backend/tests/test_agent_prompt.py` 两个测试文件；前端只动 `frontend/src/types/agent.ts`、`frontend/src/views/AgentView.vue`、`frontend/src/components/agent/MessageItem.vue`、`frontend/src/layouts/MainLayout.vue`、`frontend/src/router/index.ts` 五个文件 + 新增 `frontend/src/components/agent/KnowledgeSources.vue` 一个文件；文档只动 `docs/DEMO_SCRIPT.md`、`README.md`、（可选）`docs/designs/DESIGN_AGENT_CHAT.md`。
2. **兼容铁律**（spec §4.5-1）：tool_result 事件六字段（call_id/name/ok/elapsed_ms/summary/truncated）名称、语义、序位冻结；`sources` 仅以「可选新增、键可缺席」方式出现——检索失败与非检索工具时**键不出现**，检索成功空命中时为 `[]`（design §2.1.3-B 真值表）。
3. **复用约定**：`components/ask/SourceCard.vue` 为 Ask 保留资产，**import 复用、零改动**（design §1.2.5）；`QaSourceItem`/`KnowledgeScope` 以 `import type` 从 `@/types` 复用，**禁止在 agent.ts 重定义**（design §2.1.3-C 类型决策）；跳转执行统一在视图层（AgentView），渲染组件不持 router（对齐现有 `card-toggle` 透传模式）。
4. **单一口径**：`normalizeSources` 是实时 SSE 与历史回放两条路径共用的唯一规范化入口（design §2.1.3-C），240 截断 / (item_id, chunk_index) 去重 / ≤20 限量只在这一处定义前端口径；后端口径在 `_extract_sources` 单点定义——双闸门对齐 spec §5.2.1 规则 5。
5. **测试纪律**：既有测试全部零改动——`test_agent_chat_stream.py:216-224` 精确键集合断言、`test_agent_prompt.py` 既有用例、`test_plan_report_tools.py` 的 `_CONTRACT_TOOL_NAMES` 12 工具名单；本特性只**新增**用例。
6. **白名单**（供 G4 核对）：`backend/app/agent/{prompts,core,registry}.py`、`backend/tests/{test_agent_chat_stream,test_agent_prompt}.py`、`frontend/src/types/agent.ts`、`frontend/src/views/AgentView.vue`、`frontend/src/components/agent/{KnowledgeSources.vue(新增),MessageItem.vue}`、`frontend/src/layouts/MainLayout.vue`、`frontend/src/router/index.ts`、`docs/DEMO_SCRIPT.md`、`README.md`、（可选）`docs/designs/DESIGN_AGENT_CHAT.md`、`docs/tasks/TASKS_AGENT_ABSORB_ASK.md`。
   **例外（已知日期敏感测试修复）**：`backend/tests/test_plan_adjust.py` 的 A2/A6 使用固定「本周周四中午」的 `_beijing_now`，解决周日运行时本周已无未来时段的既有日期敏感；不属 L2 功能改动，G4 核对时单独列出。
7. **文案与常量**：用户可见文案全部简体中文；新常量（`SEARCH_TOOL_NAME`/`SOURCE_CONTENT_MAX_LEN`/`SOURCES_MAX_COUNT` 及前端同名单量）一律模块级定义、函数体引用常量名（对齐 O8 常量引用铁律，design §2.1.2 常量行）。
8. **prompt 锚点纪律**：新增规则文案不得含「今天是」字串（保护 `test_prompt_single_source_of_prompt` 单源断言，design §1.2.3）；锚点短语以定稿文案为准，候选（「先检索再回答」「未指明范围时默认检索全部」「你的笔记里没有找到」「不得静默扩大」「以检索内容为准」「通用知识补充」「暂时无法读取笔记或资料」「不得调用 search_knowledge_base」）已经 design §2.1.3-A 核对在现 prompts.py 全文零出现，实现时若微调措辞须重新核对零撞车。

---

## 1. 后端 Prompt 与 ToolSpec：检索行为规则锚定

> 目标：把 spec §5.1.1 八条业务规则落成 `_GUIDE_SECTION` 内的静态规则子块与 search ToolSpec 的参数口径补句，并使每条规则可被关键词级自动化断言（spec §4.4-2）。
> 依据：design §2.1.3-A、§1.2.3；spec §5.1.1 全部规则、§6.2。
> 本组与组 2 零文件交集，可并行。

### 1.1 扩写 `_GUIDE_SECTION`「知识型问题检索作答规则」子块（8 条）

- [x] 在 `backend/app/agent/prompts.py` 的 `_GUIDE_SECTION`（行 77-90）内，将现有单行「- 知识型问题：search_knowledge_base；」（行 83）扩写为「知识型问题检索作答规则」多行子块，逐条覆盖 8 条规则：① 先检索再回答（知识型问题必须先调用 `search_knowledge_base` 再组织回答，禁止仅凭记忆直接回答）；② scope 判定映射（「我的笔记/我上传的/资料里/文档里」→ personal；「公共资料/公共课程资料」→ public；**未指明范围时默认 all**，即使问题像公共概念也不得改变默认口径）；③ 个人库为空红线（如实说「你的笔记里没有找到」，随后可给通用解释，**不得静默扩大**为 public/all 重检并展示公共来源）；④ 冲突优先级（检索内容与通用知识不一致时**以检索内容为准**并说明差异，不得用通用知识覆盖或改写笔记事实）；⑤ 两段式结构（先讲检索到的内容并标注来源序号，再以「**通用知识补充**」明确区分自有知识；禁止把通用知识标注为笔记/资料来源；来源信息由来源卡片承载，回答用连贯自然语言）；⑥ 任务型零检索（任务/计划/学习记录/掌握度/报告/目标管理类走对应工具，**不得调用 search_knowledge_base**）；⑦ 检索为空话术（明确说明「你的笔记/资料里没有找到相关记录」再给通用解释）；⑧ 检索失败话术（如实说「暂时无法读取笔记或资料」再给通用解释；禁止伪造来源、禁止假装检索成功）。
- **涉及文件**：`backend/app/agent/prompts.py`（修改；预估 +30 行）
- **实现要点**：只扩写 `_GUIDE_SECTION` 静态字符串常量的内部——七段模板结构与 `build_system_prompt` 函数体（prompts.py:208-244）零改动；保持「典型场景的工具路径引导」其余行与结尾「执行指令：直接调用工具完成任务，不要反问用户确认。」原样；新文案不得含「今天是」（前置约定 8）。
- **对应章节**：spec §5.1.1-1/2a/2b/2c/3/4/5/6/7/8、§4.4-2、§6.2-2/3；design §2.1.3-A、§1.2.3。
- **完成判据**：`cd backend && ./.venv/Scripts/python.exe -m pytest tests/test_agent_prompt.py -q` 全部通过（既有用例零回归）；`grep -n "今天是" backend/app/agent/prompts.py` 命中数与改动前一致（仅日期段一处）；`grep -n "通用知识补充" backend/app/agent/prompts.py` 命中。
- **依赖**：无。

### 1.2 补 `registry.py` search ToolSpec description 的 scope 判定口径

- [x] 在 `backend/app/agent/registry.py` 的 `search_knowledge_base` ToolSpec（行 215-232）description 尾部追加一句 scope 填法口径：「scope 填法：用户说『我的笔记/我上传的/资料里/文档里』用 personal；明确说『公共资料/公共课程资料』用 public；未指明范围一律用默认 all（即使问题像公共概念）；用户限定 personal 无命中时直接据实回答，不得自行改用 public/all 重试」。
- **涉及文件**：`backend/app/agent/registry.py`（修改；预估 +4 行）
- **实现要点**：仅追加句子到 description 字符串末尾，不改三要素结构（何时调用/参数填法/返回结构）；`SearchKnowledgeBaseParams` schema 零改动（scope 默认值 all 为既有行为，tools.py 参数模型不动）；其余 11 个 ToolSpec 零改动。
- **对应章节**：spec §5.1.1-2a/2b/2c、§6.2-1/2/3；design §2.1.3-A 末段（ToolSpec 同步裁决）。
- **完成判据**：`cd backend && ./.venv/Scripts/python.exe -m pytest tests/test_plan_report_tools.py tests/test_agent_prompt.py -q` 全部通过（12 工具名单与既有断言零回归）；`grep -n "未指明范围一律用默认 all" backend/app/agent/registry.py` 命中。
- **依赖**：无（与 1.1 并行）。

### 1.3 `test_agent_prompt.py` 新增锚点断言用例 + 回归

- [x] 在 `backend/tests/test_agent_prompt.py` 新增 2 个用例：① `build_system_prompt` 产物逐一断言 8 条规则的锚点短语 `in prompt`（前置约定 8 候选清单，每条规则至少 1 个锚点；组装方式沿用既有用例的 monkeypatch 预取模式）；② 直读 `TOOLS_SCHEMA` 中 `search_knowledge_base` 条目的 description，断言含「未指明范围一律用默认 all」（不经 LLM）。随后运行全文件确认既有用例零回归。
- **涉及文件**：`backend/tests/test_agent_prompt.py`（修改；预估 +35 行）
- **实现要点**：新用例只增不改；prompt 组装入口与既有用例同款（monkeypatch `TOOL_MAP` 预取或直接调用约定以既有文件内 fixture 为准）；锚点短语与 1.1/1.2 定稿文案逐字一致——**实现顺序上本任务在 1.1/1.2 文案定稿后执行**。
- **对应章节**：spec §4.4-2（关键词级可断言）；design §2.1.3-B 测试清单末两行、§2.4-2。
- **完成判据**：`cd backend && ./.venv/Scripts/python.exe -m pytest tests/test_agent_prompt.py -q` → 全部通过且总数 = 既有数 + 2；故意把某锚点从 prompts.py 临时删掉再跑 → 新用例① 失败（验证断言有效性后还原）。
- **依赖**：1.1、1.2（文案定稿）。

---

## 2. 后端 SSE sources：tool_result 可选扩展

> 目标：`tool_result` 事件在六字段兼容前提下，仅当 `search_knowledge_base` 检索成功时可选携带 `sources`（空命中 `[]`、失败/其余工具键不出现），并由 4 个新用例锁定行为。
> 依据：design §2.1.3-B、§1.2.1、§1.2.2、§2.2.2-(1)(2)；spec §4.5-1、§6.1、§6.3。
> 组内串行：2.1 → 2.2 → 2.3。

### 2.1 core.py 三常量 + `_extract_sources` 纯函数

- [x] 在 `backend/app/agent/core.py` 常量区（行 100-113 附近）新增 3 个模块级常量：`SEARCH_TOOL_NAME: str = "search_knowledge_base"`、`SOURCE_CONTENT_MAX_LEN: int = 240`、`SOURCES_MAX_COUNT: int = 20`；并在 SSE 事件构造辅助区新增模块级纯函数 `_extract_sources(result: dict[str, Any]) -> list[dict[str, Any]] | None`。
- **涉及文件**：`backend/app/agent/core.py`（修改；预估 +30 行）
- **实现要点**：真值表逐分支实现（design §2.1.3-B）：result 含 `"error"` 键 → `None`；无 error 但 `results` 缺失或非 list → `None`；`results == []` → `[]`；正常命中 → 逐条提取六字段白名单（content/source_title/score/item_id/chunk_index/scope），单条 `content` 超 `SOURCE_CONTENT_MAX_LEN` 截断、必填字段不合格（content/source_title 非 str、scope 不在 {personal, public}）整条丢弃，总量超 `SOURCES_MAX_COUNT` 取前 20；`mode` 字段不进 sources；**宁缺勿假**——任何情况不构造占位条目；函数内部不抛异常。
- **对应章节**：spec §4.1-1/2、§6.1、§6.3-2/3/4；design §2.1.3-B（`_extract_sources` 提取函数）、§2.2.2-(2)。
- **完成判据**：`cd backend && ./.venv/Scripts/python.exe -m pytest tests/test_agent_chat_stream.py -q` 既有用例全部通过（本任务尚未接线，行为零变化）；`grep -n "SEARCH_TOOL_NAME\|SOURCE_CONTENT_MAX_LEN\|SOURCES_MAX_COUNT\|_extract_sources" backend/app/agent/core.py` 命中 4 类符号。
- **依赖**：无（组内起点；与组 1 可并行）。

### 2.2 `_tool_result_event` 可选尾参 + 派发循环门控接线

- [x] 在 `backend/app/agent/core.py` 做两处接线：① `_tool_result_event`（行 139-158）签名追加可选尾参 `sources: list[dict[str, Any]] | None = None`，组装 data 时 `None` → 键不出现，非 `None`（含 `[]`）→ `data["sources"] = sources`；② 工具派发第二遍循环（行 524-546 的 `yield _tool_result_event(...)` 处，现行 538-540）改为先算 `sources = _extract_sources(result) if name == SEARCH_TOOL_NAME else None`，再传入构造器。
- **涉及文件**：`backend/app/agent/core.py`（修改；预估 +15 行）
- **实现要点**：仅此一处接线——主循环其余控制流（CP-2、轮收口、O5）零改动；六字段的名称/语义/序位不变（spec §4.5-1）；检索失败路径由既有 error 信封表达（`ok=False` + summary 中文文案），sources 不承担错误表达；`SEARCH_TOOL_NAME` 门控只引用常量名（前置约定 7）。
- **对应章节**：spec §4.5-1、§6.3-1/2/3；design §2.1.3-B（扩展签名、派发循环接线、空 vs 不出现口径锁定）、§1.2.1（精确键集合兼容约束）。
- **完成判据**：`cd backend && ./.venv/Scripts/python.exe -m pytest tests/test_agent_chat_stream.py -q` 既有用例全部通过——特别核对行 216-224 精确键集合断言（该用例三工具均非 search，键集合必须逐字节不受影响）；`grep -n "sources" backend/app/agent/core.py` 命中点仅限本组新增区域。
- **依赖**：2.1。

### 2.3 `test_agent_chat_stream.py` 新增 4 用例（命中 / 空命中 / 失败 / 截断限量）

- [x] 在 `backend/tests/test_agent_chat_stream.py` 新增 4 个用例（沿用既有 `_install_fake_llm` 模式 + 按实现要点二选一注入假检索）：① **命中**——工具返回 `{mode:"online", results:[2 条合法六字段]}` → 断言该工具 tool_result 含 `sources` 键、长度 2、每条六字段齐、content ≤240，且同事件内六旧字段仍在；② **空命中**——`results=[]` → `sources == []` 且键存在、`ok is True`；③ **失败**——返回 `{"error":"..."}` → 无 `sources` 键、`ok is False`；④ **截断与限量**——构造 25 条、单条 content 300 字 → sources 恰 20 条、每条 content ≤240。
- **涉及文件**：`backend/tests/test_agent_chat_stream.py`（修改）
- **实现要点**：新用例只增不改；测试假数据优先 `monkeypatch.setattr(tools_module, "search_knowledge", fake_async)`（`tools_module = app.agent.tools`），让真实 `search_knowledge_base` 包装函数返回 fake 的 `{mode, results}`；或者 `monkeypatch.setitem(app.agent.registry.TOOL_MAP, "search_knowledge_base", fake_tool)`（dict 原地修改，core 的引用可见）。**禁止** patch `app.agent.tools.TOOL_MAP`（不存在——`TOOL_MAP` 在 `app.agent/registry.py`，`core.py` 以 `from app.agent.registry import TOOL_MAP` 持有同一 dict 引用；`tools.search_knowledge_base` 内部调用模块全局 `search_knowledge`）。用例④ 的 25 条数据由循环构造，避免 25 段字面量；断言 sources 元素 scope 取值仅 personal/public。
- **对应章节**：spec §6.3-1/2/3/4、§4.5-1、§5.1.1-5/8（空与失败的结构表达）；design §2.1.3-B 测试清单表格、§2.4-1。
- **完成判据**：`cd backend && ./.venv/Scripts/python.exe -m pytest tests/test_agent_chat_stream.py -q` → 全部通过且总数 = 既有数 + 4；四个新用例逐一 `-k` 单跑均通过。
- **依赖**：2.2。

---

## 3. 前端类型与 AgentView 数据流

> 目标：类型层扩展三类型承载 sources；AgentView 落地单一口径规范化、块级保序去重合并、实时与历史双路径接线、跳转与空态提示。
> 依据：design §2.1.3-C、§2.2.2-(3)(4)(5)、§2.3.2；spec §5.2.1、§5.2.3、§6.1、§6.3。
> 组内顺序：3.1 → 3.2 → 3.3 →（3.4 与 3.5 可并行）→ 3.6（仅依赖 3.1，可提前插入）。

### 3.1 `types/agent.ts` 三类型扩展（import type 复用 QaSourceItem）

- [x] 在 `frontend/src/types/agent.ts` 顶部追加 `import type { QaSourceItem } from '@/types'`，并扩展三处：`AgentToolResultData`（行 37-44）加可选字段 `sources?: QaSourceItem[]`；`ToolResultView`（行 140-147）加 `sources: QaSourceItem[] | null`（该次检索来源；null=非检索/失败/历史缺失）；`AssistantViewMessage`（行 187-194）加 `sources: QaSourceItem[]`（块级聚合、去重后 ≤20，默认 []）。
- **涉及文件**：`frontend/src/types/agent.ts`（修改；预估 +14 行）
- **实现要点**：type-only import（编译后零运行时代码；方向 agent.ts → index.ts 单向，不违反裁决 #2——design §2.1.3-C 类型决策）；**禁止在 agent.ts 重定义来源六字段**；`KnowledgeScope` 随 QaSourceItem 一并复用不另导；各新字段附注释标明语义与三态（含 null 与 [] 的区别）。
- **对应章节**：spec §6.1（六字段）、§6.3-1；design §2.1.3-C（类型扩展）、§2.3.2 类图。
- **完成判据**：`cd frontend && npx vue-tsc --noEmit` exit 0；`grep -n "重定义\|interface QaSourceItem" frontend/src/types/agent.ts` 零命中（无重复定义）；`grep -cn "sources" frontend/src/types/agent.ts` ≥ 3。
- **依赖**：无（组内起点；语义上建议组 2 已定 sources 真值表）。

### 3.2 AgentView.vue 新增 `normalizeSources` 单一口径纯函数

- [x] 在 `frontend/src/views/AgentView.vue` script 模块级新增纯函数 `normalizeSources(raw: unknown): QaSourceItem[]` 与前端常量（与后端同名同值）：`SOURCES_MAX_COUNT = 20`、`SOURCE_CONTENT_MAX_LEN = 240`。
- **涉及文件**：`frontend/src/views/AgentView.vue`（修改；预估 +35 行）
- **实现要点**：逐条六字段白名单校验——scope 仅认 `'personal'|'public'`、score 强制 `Number()`（NaN 置 0）、title/content 强制 `String()`，item_id/chunk_index 可空但非空时须为数；任一硬字段不合格整条丢弃；content 超 240 截断；按 `(item_id ?? 'x') + ':' + (chunk_index ?? 'x')` 键去重（'x' 占位区分 null 与数值 0）；总量 ≤20；全坏返回 `[]`；实时/历史两路径共用（对 SSE 已截断数据再过一遍是幂等——design §2.1.3-C）；纯函数零副作用、不 import api。
- **对应章节**：spec §5.2.1-5、§5.2.3-1、§6.3-4/6；design §2.1.3-C（normalizeSources 段）、§2.2.2-(5)。
- **完成判据**：`cd frontend && npx vue-tsc --noEmit` exit 0；`grep -n "normalizeSources" frontend/src/views/AgentView.vue` 命中定义点（调用点在 3.4/3.5 落地后再核）。
- **依赖**：3.1。

### 3.3 AgentView.vue 新增 `mergeAssistantSources` + 两处创建点 `sources: []` 初始化

- [x] 在 `frontend/src/views/AgentView.vue` 新增模块级函数 `mergeAssistantSources(block: AssistantViewMessage, incoming: QaSourceItem[]): void`；并在两处创建点为 assistant 块补 `sources: []` 初始化：`placeholderAssistant`（行 101-110）与 `buildViewMessages` 新建 assistant 块（行 310-317）。
- **涉及文件**：`frontend/src/views/AgentView.vue`（修改；预估 +20 行）
- **实现要点**：合并且保序去重——以 `Map<string, QaSourceItem>` 按键（同 3.2 去重键）保序，首现位次保留（对齐 SourceCard「同文档多片段不去重、编号连续」惯例，此处去重仅针对**多次检索的重复命中**，spec §6.3-6）；合并后总长超 `SOURCES_MAX_COUNT` 截断；写回 `block.sources = [...map.values()]`；两处初始化杜绝 undefined（实时 reactive 路径经 placeholderAssistant 自动获得初始化）。
- **对应章节**：spec §6.3-4/5/6、§4.2-2；design §2.1.3-C（mergeAssistantSources 段、创建点初始化段）、§2.2.2-(5)。
- **完成判据**：`npx vue-tsc --noEmit` exit 0；`grep -n "sources: \[\]" frontend/src/views/AgentView.vue` 命中恰 2 处创建点。
- **依赖**：3.2。

### 3.4 AgentView.vue `onToolResult` 实时路径追加（写卡片级 + 块级合并）

- [x] 在 `frontend/src/views/AgentView.vue` 的 `onToolResult` 回调（行 181-216）内追加：`data.sources !== undefined` 时先经 `normalizeSources(data.sources)` 规范化，写入配对卡片的 `segment.call.result.sources`（未配对 hit=false 降级分支同样写入新卡 result）；随后执行块级合并 `mergeAssistantSources(assistant, normalized)`。
- **涉及文件**：`frontend/src/views/AgentView.vue`（修改；预估 +10 行）
- **实现要点**：`data.sources` 不存在（undefined）时零行为变化（非检索工具/失败路径兼容）；两处 result 字面量（配对分支与降级分支）均补 `sources` 字段写入；既有的配对查找、滚动跟随逻辑零改动。
- **对应章节**：spec §5.2.1-1/7（实时来源落块）、§6.3-1；design §2.1.3-C（实时路径 onToolResult 段）。
- **完成判据**：`npx vue-tsc --noEmit` exit 0；`grep -n "normalizeSources" frontend/src/views/AgentView.vue` 命中含 onToolResult 内调用点。
- **依赖**：3.2、3.3。

### 3.5 AgentView.vue `buildViewMessages` 历史回放按用户轮次 flush 到本轮最后一个 assistant 块

- [x] 改造 `frontend/src/views/AgentView.vue` 的 `buildViewMessages`（行 300-369）：① 循环开始前声明 `let pendingSources: QaSourceItem[] = []` 与 `let lastAssistant: AssistantViewMessage | null = null`；② assistant 分支（行 309-332）新建块初始化 `sources: []`（3.3 已落）后更新 `lastAssistant = block`；③ tool 分支（行 334-366）追加——`msg.tool_name === 'search_knowledge_base'` 且 parseOk 且 parsed 无 `error` 键时，对 parsed.results 调 `normalizeSources`，写入 `card.result.sources`（卡片级可溯）并并入 `pendingSources`（块级暂存，不立即挂块）；④ user 分支（行 305-308）前置 flush——`pendingSources.length && lastAssistant` 时 `mergeAssistantSources(lastAssistant, pendingSources)` 并清空；⑤ 循环结束后同一 flush 逻辑再执行一次（覆盖最后一轮无后继 user 的收尾）；⑥ 解析失败/无 results/非数组 → `card.result.sources = null`、pendingSources 不并入，单条 try/catch 不抛出（沿用既有 parseOk 门控模式）。
- **涉及文件**：`frontend/src/views/AgentView.vue`（修改；预估 +25 行）
- **实现要点**：**不使用 blockIndex**——游标方案为纯局部变量增量；既有 `cardIndex` 配对逻辑零改动；一轮里 tool 之后无最终回答块（流中断/落库残缺）时来源挂到 `lastAssistant`（拥有工具调用的块），属可接受降级（仍在该轮回答区）；flush 逻辑抽成局部闭包避免两处复制。
- **对应章节**：spec §5.2.1-3/7、§5.2.3-1、§4.2-2、§6.3-5；design §2.1.3-C（历史路径 8 步）、§1.2.4（cardIndex 局限与轮次 flush 修法）、§2.6 风险表「历史多 assistant 块挂错块」行。
- **完成判据**：`npx vue-tsc --noEmit` exit 0；`grep -n "pendingSources\|lastAssistant" frontend/src/views/AgentView.vue` 命中且不出现在组件其他无关区域；本任务的回放效果由组 6.3 手工场景 5 终验（不在本任务虚报行为断言）。
- **依赖**：3.2、3.3。

### 3.6 AgentView.vue `onSourceNavigate` 跳转 + 空态轻提示

- [x] 在 `frontend/src/views/AgentView.vue` 新增 `onSourceNavigate(source: QaSourceItem): void`——与 `AskView.onNavigate`（AskView.vue:175-185）同构：`item_id == null` 直接 return，`router.push` 至 `/knowledge-base`，query 为 `item_id` 字符串化 + `chunk_index` 可空省略；并在空态区（行 550-566）el-empty 与快捷问题之间追加一行小字常量提示：「可以直接问知识库——我会自动检索你的笔记和公共资料，并在回答下方标注来源」。
- **涉及文件**：`frontend/src/views/AgentView.vue`（修改；预估 +12 行）
- **实现要点**：跳转守卫双保险（SourceCard 已前置拦截 item_id 为空，此处再拦一次）；空态提示为模块级文案常量 + 12px placeholder 灰字样式，**不动 el-empty 主文案、不动 QUICK_QUESTIONS 四项**；router 实例沿用组件既有获取方式。
- **对应章节**：spec §5.2.1-2（点击跳转）、§5.2.1-6（入口提示）、§5.2.3-2（缺 item_id 降级）；design §2.1.3-C（onSourceNavigate 段、空态轻提示段）。
- **完成判据**：`npx vue-tsc --noEmit` exit 0；`grep -n "onSourceNavigate\|/knowledge-base" frontend/src/views/AgentView.vue` 命中；`grep -n "标注来源" frontend/src/views/AgentView.vue` 命中。
- **依赖**：3.1（模板接线 `@source-navigate` 在 4.2 落地）。

---

## 4. 前端展示组件：来源区渲染与事件透传

> 目标：新增来源区容器组件（零复制复用 SourceCard），并把来源区以正确槽位插入 MessageItem（segments 之后、finishHint 之前），navigate 事件逐级透传到 AgentView。
> 依据：design §2.1.3-C（MessageItem 渲染位置、KnowledgeSources 契约）、§2.2.2-(3)(4)、§1.2.5；spec §5.2.1-1/4/7、§5.2.3-2。

### 4.1 新建 `components/agent/KnowledgeSources.vue`（复用 SourceCard 零复制）

- [x] 新建 `frontend/src/components/agent/KnowledgeSources.vue`：props `{ sources: QaSourceItem[]; citedIndices?: number[] }`，emits `(e: 'navigate', source: QaSourceItem)`；**只渲染 `citedIndices` 中的来源（原始 1-based 序号保留）**，回答未引用任何来源时不渲染；结构为容器 div（「参考来源」小标题行，12px 灰字）+ `v-for` 渲染 `@/components/ask/SourceCard.vue`（index 使用原始序号，与回答中 [n] 引用序号对齐）；容器仅加 6px 纵向堆叠间距与 4px 上外边距（对齐 MessageItem 块内 8px gap 节奏）。
- **涉及文件**：`frontend/src/components/agent/KnowledgeSources.vue`（新增；预估 85 行）
- **实现要点**：**import 复用、零改动 ask 资产**（design §1.2.5）；父级以 `v-if` 保证非空才挂载，本组件不处理空态；单条 item_id 为空的降级由 SourceCard 内部 `canNavigate` 自治（纯展示、无跳转按钮），本组件不做额外分支；navigate 原样上抛不拦截；`<script setup lang="ts">`，首行注释回链 spec/design 章节。
- **对应章节**：spec §5.2.1-1（卡片完整性：标题/片段/归属）、§5.2.3-2；design §2.2.2-(3)。
- **完成判据**：`cd frontend && npx vue-tsc --noEmit` exit 0；`grep -n "components/ask/SourceCard" frontend/src/components/agent/KnowledgeSources.vue` 命中（复用佐证）；`git status --short frontend/src/components/ask/` 输出为空（ask 资产零改动）。
- **依赖**：3.1（QaSourceItem 类型可引）。

### 4.2 MessageItem.vue 槽位插入 + `source-navigate` 透传 + AgentView 模板接线

- [x] 在 `frontend/src/components/agent/MessageItem.vue` 的 assistant 块模板中，于 segments v-for 模板结束标签（行 109）之后、finish-hint div（行 112）之前插入 `<KnowledgeSources v-if="assistant.sources.length" :sources="assistant.sources" :cited-indices="citedIndices" @navigate="(s) => emit('source-navigate', s)" />`；新增 computed `citedIndices`（从 text segments 用 `/\[(\d+)\]/g` 提取 1-based 序号）；emits 追加 `(e: 'source-navigate', source: QaSourceItem): void`；并在 `frontend/src/views/AgentView.vue` 模板 MessageItem 使用处（行 569-574）追加 `@source-navigate="onSourceNavigate"` 接线。
- **涉及文件**：`frontend/src/components/agent/MessageItem.vue`（修改；预估 +12 行）、`frontend/src/views/AgentView.vue`（修改；+1 行模板属性）
- **实现要点**：来源区**严格位于 segments 之后、finishHint 之前**（spec §5.2.1-7）；块末固定区其余（finishHint → statsText → error → stopped）顺序不变；MessageItem 自身不持 router（透传模式对齐 `card-toggle`）；`v-if="assistant.sources.length"` 保证空集合/检索失败/历史缺源（null 经 3.3 初始化恒为数组）时无来源区（spec §5.2.1-4）。
- **对应章节**：spec §5.2.1-4/7、§5.2.1-2（emit 链路一环）；design §2.1.3-C（MessageItem 渲染位置段）、§2.2.2-(4)。
- **完成判据**：`cd frontend && npx vue-tsc --noEmit` exit 0；`grep -n "source-navigate" frontend/src/components/agent/MessageItem.vue frontend/src/views/AgentView.vue` 两文件均命中；`grep -n "KnowledgeSources" frontend/src/components/agent/MessageItem.vue` 命中且行号位于 segments v-for 结束与 finish-hint 之间。
- **依赖**：4.1、3.3（`assistant.sources` 字段存在）、3.6（onSourceNavigate 存在）。

---

## 5. 单一入口收敛与文档口径同步

> 目标：主导航只留「AI 助手」；`/ask` 旧地址 redirect 至 `/ai-agent`；README/DEMO_SCRIPT 口径同步；全部既有问答资产保留。
> 依据：design §2.1.3-D；spec §5.3.1 全部规则、§5.3.3-1。
> 本组与组 1–4 零文件交集，可全并行。

### 5.1 MainLayout.vue 删菜单项 + router/index.ts ask 路由改 redirect

- [x] 删除 `frontend/src/layouts/MainLayout.vue` 行 35 的 `{ index: '/ask', title: 'AI 问答', icon: 'ChatLineRound' }` 菜单项（其余 9 项与图标映射零改动）；将 `frontend/src/router/index.ts` 行 67-72 的 ask 路由改为 `{ path: 'ask', redirect: '/ai-agent' }` 形态（去掉 component/name/meta），并保留紧邻注释「AI 问答入口已收敛至 AI 助手；AskView.vue 与 /chat/qa 链路完整保留作回退，仅不再路由可达」（注释风格对齐行 85-90 settings 先例）。
- **涉及文件**：`frontend/src/layouts/MainLayout.vue`（修改；−1 行）、`frontend/src/router/index.ts`（修改；−4/+3 行）
- **实现要点**：路由守卫（行 105-117）零改动——redirect 在守卫之后生效，未登录访问 `/ask` 仍先跳 `/login`（行为与现状一致，design §2.1.3-D）；`AskView.vue` import 语句随 component 移除而删除，但 `frontend/src/views/AskView.vue` 文件本体**不删不改**；菜单 v-for 渲染逻辑无任何分支新增。
- **对应章节**：spec §5.3.1-1/2/3、§5.3.3-1；design §2.1.3-D。
- **完成判据**：`cd frontend && npm run build` exit 0；`grep -n "AI 问答" frontend/src/layouts/MainLayout.vue` 零命中；`grep -n "redirect: '/ai-agent'" frontend/src/router/index.ts` 命中；`grep -rn "component.*AskView" frontend/src/router/index.ts` 零命中；`ls frontend/src/views/AskView.vue frontend/src/components/ask/` 文件俱在。
- **依赖**：无（与组 1–4 并行；行为验收归组 6.3 场景 6）。

### 5.2 DEMO_SCRIPT / README /（可选）DESIGN_AGENT_CHAT 文案口径

- [x] 改写 `docs/DEMO_SCRIPT.md` 两处：行 41（第二幕口播词）「…是后面 AI 问答和分析的依据…」→「…是后面 AI 助手知识库问答和分析的依据…」；行 72（常见问题 2）「走『AI 问答』页 `/ask`」→「在『AI 助手』页（`/ai-agent`）直接提问」；第 3 幕口播词末尾可选补一句演示口径（非新增步骤）：「它也能直接回答知识型问题——比如问『我的笔记里特征值分解在 PCA 里起什么作用』，它会先检索我的笔记再回答，并在回答下方给出可点击的来源卡片」。核对 `README.md`：行 217 附近「RAG 问答演示」为数据集用途描述可保留（实现时确认口径，若改则为「AI 助手知识库问答演示」）；行 3 简介句末可选追加「知识库问答能力已并入 AI 助手（`/ai-agent`）」。可选：`docs/designs/DESIGN_AGENT_CHAT.md` 的 tool_result 契约处补一句 optional sources 说明（2 行）。
- **涉及文件**：`docs/DEMO_SCRIPT.md`（修改；±8 行）、`README.md`（修改；±2 行）、（可选）`docs/designs/DESIGN_AGENT_CHAT.md`（修改；+2 行）
- **实现要点**：不新增独立 Ask 页面步骤（spec §5.3.1-4）；`.codeartsdoer/**` 需求文档不动；备用预置问题四个与公共文档强相关的内容保留（命中率高，design §2.6 风险表第一行缓解依据）。
- **对应章节**：spec §5.3.1-4；design §2.1.3-D（替换点表）、§2.6 未决点 3。
- **完成判据**：`grep -n "走『AI 问答』页\|/ask" docs/DEMO_SCRIPT.md` → 不再命中「走『AI 问答』页 `/ask`」表述（`/ask` 字串仅在 redirect 说明类语境出现或零命中）；`grep -n "AI 助手知识库问答" docs/DEMO_SCRIPT.md` 命中；`grep -n "打开 AI 问答" README.md docs/DEMO_SCRIPT.md` 零命中。
- **依赖**：无（与 5.1 并行）。

---

## 6. 全量门禁与手工走查

> 目标：以写死的最终门禁收口——全量测试、全量构建、七条手工场景、改动范围核对。
> 依据：design §2.4（修正后口径：全量 `pytest -q` + `npm run build`）；spec §4.2、§4.5、§5.1.3、§5.2.3、§5.3.3。
> 本组依赖组 1–5 全部完成，组内串行：6.1 → 6.2 → 6.3。

### 6.1 后端全量测试门禁

- [x] 执行 `cd backend && ./.venv/Scripts/python.exe -m pytest -q`，要求 0 failed；passed 总数 = 开工基线 + 6（组 1.3 新增 2 + 组 2.3 新增 4；基线 206 则应为 212），若基线有变必须记录实测基线与原因。
- **涉及文件**：无（纯验证）
- **实现要点**：必须是全量而非单文件（design §2.4 修正点②）；失败必须贴原文输出，禁止虚报；特别关注 `test_agent_chat_stream.py:216-224` 精确键集合断言与 `test_plan_report_tools.py` 12 工具名单用例的通过状态。
- **对应章节**：spec §4.4-2、§4.5-1；design §2.4。
- **完成判据**：命令输出尾行 `N passed`（N = 基线 + 6）且 0 failed、exit 0。
- **依赖**：组 1、组 2。

### 6.2 前端全量构建门禁

- [x] 执行 `cd frontend && npm run build`，要求 exit 0（含 vue-tsc 类型检查链路与 vite build）。
- **涉及文件**：无（纯验证）
- **实现要点**：构建警告如实记录；类型错误必须修复不得豁免；确认构建产物不引入新依赖（`git diff frontend/package.json frontend/package-lock.json` 为空）。
- **对应章节**：spec §4.5-4（零新增依赖佐证）；design §2.4。
- **完成判据**：exit 0；`git diff --stat frontend/package.json frontend/package-lock.json` 无输出。
- **依赖**：组 3、组 4、组 5.1。

### 6.3 手工场景 1–7 走查 + 改动范围核对

- [x] 启动前后端，逐条走查七条手工场景并记录结果；随后执行 `git status --short -uall` 与开工基线对比，核对改动仅限前置约定 6 白名单。
- **涉及文件**：无（纯验证；走查记录附于实现阶段汇报）
- **实现要点**（前置 + 七场景逐条判据）：
  0. **前置**：启动前后端后，在知识库上传 `data/uploads/1/2_linear_algebra_notes.md` 的副本，等待状态到 `indexed`；否则个人库为空，场景 1/3 无法验证「个人库来源卡」；
  1. **个人笔记问答**——提问「我的笔记里特征值分解在 PCA 里起什么作用？」→ 回答下方出现来源卡且归属徽章显示「个人库」（spec §5.2.1-1a）；
  2. **公共资料问答**——提问公共资料相关问题（如「机器学习中过拟合是什么？」）→ 来源卡归属显示「公共库」；
  3. **笔记无命中**——限定「我的笔记」提问笔记中不存在的概念 → 回答明确说「你的笔记里没有找到」类表述 + 通用解释 + **无来源卡、无公共来源**（spec §5.1.1-2c/5）；
  4. **任务/计划问题**——说「帮我安排下周学习」→ 全程无 `search_knowledge_base` 工具卡（spec §5.1.1-6）；
  5. **多轮历史回放**——完成一次带来源的回答后刷新页面重进会话 → 来源卡仍在且内容与实时一致，且出现在**最终回答文本下方**（segments 之后、finishHint 之前），不在工具调用块上方或仅藏于工具卡内（spec §5.2.1-3/7）；
  6. **入口收敛**——左侧菜单无「AI 问答」；浏览器直接访问 `/ask` → 自动跳 `/ai-agent`；Agent 空态提示「可以直接问知识库——我会自动检索你的笔记和公共资料，并在回答下方标注来源」可见（spec §5.3.1-1/2、§5.2.1-6）；
  7. **Agent 回归**——既有工具调用（如「我最近学习怎么样」三工具链）、多轮对话、停止生成、会话新建/切换/重命名/删除功能全部正常。
- **对应章节**：spec §5.1.1 全部、§5.2.1 全部、§5.3.1-1/2、§4.2-2；design §2.4-5（多轮回放人工用例）、§2.6 风险表走查项。
- **完成判据**：七场景全过并逐条记录；`git status --short -uall` 增量文件全部落在白名单内，`frontend/src/components/ask/`、`frontend/src/views/AskView.vue`、`frontend/src/types/index.ts`、`frontend/src/api/`、`frontend/package.json` 零改动条目；`backend/app/` 改动条目恰为 prompts.py / core.py / registry.py 三件。
- **依赖**：6.1、6.2。

---

## 7. spec 验收条件 → 任务映射表（覆盖率自检）

### §5.1.1 自动检索与作答（8 条规则 + 2a/2b/2c 子项）

| spec 验收条件 | 覆盖任务 | 判定点 |
|---|---|---|
| §5.1.1-1 先检索后作答 | 1.1（规则①）+ 1.3 | 1.3 锚点断言 + 6.3 场景 1/2 |
| §5.1.1-2a 措辞→personal | 1.1（规则②）+ 1.2 | 1.3 锚点断言 + 6.3 场景 1 |
| §5.1.1-2b 未指明默认 all | 1.1（规则②）+ 1.2 | 1.3 锚点断言（prompt + ToolSpec 双锚点） |
| §5.1.1-2c 个人库空不静默扩大 | 1.1（规则③）+ 1.2 | 1.3 锚点断言 + 6.3 场景 3 |
| §5.1.1-3 两段式结构 | 1.1（规则⑤） | 1.3 锚点断言（「通用知识补充」） |
| §5.1.1-4 冲突以检索为准 | 1.1（规则④） | 1.3 锚点断言（「以检索内容为准」） |
| §5.1.1-5 空检索诚实作答 | 1.1（规则⑦）+ 2.1（空命中 `[]`）+ 4.2（v-if 不渲染） | 2.3 用例② + 6.3 场景 3 |
| §5.1.1-6 任务型零检索 | 1.1（规则⑥） | 1.3 锚点断言 + 6.3 场景 4（结构性旁证：既有三工具用例无 search） |
| §5.1.1-7 自然语言作答 | 1.1（规则⑤后半：来源由卡片承载） | 1.3 锚点断言 + 6.3 场景 1/2 |
| §5.1.1-8 检索失败禁伪造 | 1.1（规则⑧）+ 2.1（error→None）+ 2.2（键不出现） | 2.3 用例③ |

### §5.2.1 来源展示与跳转（7 条）

| spec 验收条件 | 覆盖任务 | 判定点 |
|---|---|---|
| §5.2.1-1 卡片完整性（标题/片段/归属） | 4.1（SourceCard 复用）+ 3.1（六字段类型） | 6.3 场景 1/2 |
| §5.2.1-2 点击跳转定位 | 3.6（onSourceNavigate）+ 4.1/4.2（emit 透传链） | 6.3 场景 1/2 点击验证 |
| §5.2.1-3 历史回放一致 | 3.5（轮次 flush）+ 3.2（normalizeSources 口径收敛） | 6.3 场景 5 |
| §5.2.1-4 空结果不展示 | 4.2（v-if）+ 2.1（`[]` 口径） | 2.3 用例② + 6.3 场景 3 |
| §5.2.1-5 数量长度受控（20/240） | 2.1（后端闸门）+ 3.2（前端闸门） | 2.3 用例④ |
| §5.2.1-6 空态入口提示 | 3.6 | 6.3 场景 6 顺带目检（空态提示可见） |
| §5.2.1-7 来源挂最终回答下方（含多轮历史） | 4.2（槽位：segments 后、finishHint 前）+ 3.5（flush 到本轮最后一个 assistant 块） | 6.3 场景 5 |

### §5.2.3 展示异常场景（2 条）

| spec 验收条件 | 覆盖任务 | 判定点 |
|---|---|---|
| §5.2.3-1 历史来源损坏降级 | 3.2（全坏返回 `[]`）+ 3.5（parseOk 门控 + `card.result.sources = null`） | 3.5 静态核对 + 6.3 场景 5 变体（如可构造脏数据） |
| §5.2.3-2 缺 item_id 降级纯展示 | 4.1（SourceCard canNavigate 自治复用）+ 3.6（守卫双保险） | 4.1 静态 grep + 6.3 场景 1/2 |

### §5.3.1 单一入口收敛（4 条）+ §5.3.3

| spec 验收条件 | 覆盖任务 | 判定点 |
|---|---|---|
| §5.3.1-1 导航唯一入口 | 5.1（删菜单项） | 5.1 grep 判据 + 6.3 场景 6 |
| §5.3.1-2 /ask 自动引导 | 5.1（redirect） | 5.1 grep 判据 + 6.3 场景 6 |
| §5.3.1-3 回退能力保留 | 5.1（零删除：AskView/ask 组件//chat/qa//chat/history 保留） | 5.1 ls 判据 + 6.3 git status 核对（G4/G5） |
| §5.3.1-4 文档口径同步 | 5.2 | 5.2 grep 判据 |
| §5.3.3-1 旧书签访问无感跳转 | 5.1（redirect 在守卫后生效） | 6.3 场景 6 |

### §6 数据约束 + §4 DFX（逐节落点）

| spec 条目 | 覆盖任务 |
|---|---|
| §6.1 来源条目六字段（QaSourceItem） | 3.1（类型复用）+ 2.1（六字段白名单提取） |
| §6.2 scope 取值集合/默认值/表述映射 | 1.1 + 1.2（双锚点；schema 默认 all 既有零改动） |
| §6.3-1/2/3 可选性/空检索空集合/失败不出现 | 2.1 + 2.2（真值表）+ 2.3（用例①②③） |
| §6.3-4 条数上限 20 | 2.1 + 3.2/3.3（双闸门）+ 2.3 用例④ |
| §6.3-5 实时与历史一致 | 3.2（单一口径）+ 3.5 + 6.3 场景 5 |
| §6.3-6 多次检索 (item_id, chunk_index) 去重 | 3.3（mergeAssistantSources 保序去重）+ 3.4/3.5（两路径调用） |
| §4.1-1/2 240 字符/20 条 | 2.1 + 3.2 |
| §4.1-3 任务型零开销 | 1.1（规则⑥，不调用即零开销，零代码路径变化） |
| §4.2-1 失败禁伪造 | 1.1（规则⑧）+ 2.1/2.2 |
| §4.2-2 实时/历史一致 | 3.2 + 3.5 |
| §4.2-3 历史损坏不崩溃 | 3.2 + 3.5 |
| §4.3-1 个人库仅本人（沿用既有鉴权） | 零代码改动项——search_knowledge 既有 user_id 隔离不动（design §1.1.1 匹配度表），6.3 场景 1 旁证 |
| §4.4-1 问答链路完整保留 | 5.1 + 6.3（G5） |
| §4.4-2 规则关键词级可断言 | 1.3 |
| §4.5-1 tool_result 仅可选新增、六字段冻结 | 2.2（可选尾参 + 键不出现策略）+ 2.3（既有精确键集合断言回归） |
| §4.5-2/3 /chat/qa·/chat/history 契约与两套存储/SSE 现状 | 零改动承诺——6.3（G4/G5）核对 |
| §4.5-4 零新增依赖 | 6.2（package.json diff 为空） |

### 孤儿任务声明

**无孤儿任务**：全部 19 个子任务均可回溯至 spec 章节/验收条件或 spec 授权的工程验证要求——组 6（全量门禁与走查）来源 design §2.4（修正点② 写死的全量门禁）与 spec §4.2/§4.5 的可靠性、兼容性验收授权；组 5.2 文档任务来源 spec §5.3.1-4；其余每组任务描述中均已标注对应 spec 与 design 章节。spec §5.1.1/§5.2.1/§5.2.3/§5.3.1/§5.3.3/§6.1/§6.2/§6.3 及 §4.5-1 每条均有任务落点，**覆盖率 23/23（用户点名确认项）+ §4 DFX 与 §5.3.3 全部落点，缺 0**。

---

## 8. 实施与验收记录（2026-10-25）

- **G1 后端全量**：`212 passed`（基线 206 + 6 新增），0 failed。
- **G2 前端构建**：`npm run build` exit 0（含 vue-tsc 链路）。
- **G3 手工场景**：
  1. 个人笔记问答 → search `scope=personal`，来源卡「个人库」；
  2. 公共资料问答 → 来源卡「公共库」；
  3. 笔记无命中 → 回答「没有找到」+ 通用解释，**0 张来源卡**（来源卡仅展示回答实际引用的 [n]；检索命中留在工具卡审计）；
  4. 任务/计划问题 → `generate_learning_plan`，无 `search_knowledge_base`；
  5. 刷新重进会话 → 来源卡保留且位于最终回答文本下方（`sourceAfterLastText=true`）；
  6. 菜单无「AI 问答」，`/ask` 自动跳 `/ai-agent`；
  7. Agent 回归 → `get_learning_statistics/get_tasks/get_knowledge_mastery` 三工具链正常。
- **实施补丁 1（来源卡引用过滤）**：`MessageItem` 从 text segments 提取 `[n]`，`KnowledgeSources` 仅渲染被引用来源；未引用命中不展示；对应 spec §5.2.1-8。
- **实施补丁 2（日期敏感测试）**：`test_plan_adjust.py` A2/A6 固定 `_beijing_now` 到本周周四中午，解决周日运行时本周无未来时段的既有日期敏感；不属 L2 功能改动。
- **G4 改动范围**：L2 白名单 + `backend/tests/test_plan_adjust.py` 日期修复例外；`frontend/src/components/ask/**`、`AskView.vue`、`types/index.ts`、`api/**`、`package.json` 零改动。
- **G5 冻结资产**：`AskView.vue`、`components/ask/*`、`/chat/qa`、`/chat/history` 全部保留；路由无 component 形态的 ask 记录。

---

**回链**：spec `.codeartsdoer/specs/agent_absorb_ask/spec.md`；design `docs/designs/DESIGN_AGENT_ABSORB_ASK.md`；上游惯例 `docs/tasks/TASKS_DEMO_RESET.md`、`docs/tasks/TASKS_PLAN_REPORT_FRONTEND.md`。