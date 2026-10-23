# 动态学习计划与学习成长报告（dynamic_plan_reports）编码任务规划

> feature: `dynamic_plan_reports` ｜ 阶段：编码任务规划（spec-task-agent 产出）
> 上游输入：`docs/specs/SPEC_DYNAMIC_PLAN_REPORTS.md`（R1 裁定定稿，644 行：13 项冲突裁决 + O1–O4 全部裁定 + D1–D14 验收标准 + 19 条领域术语 + 9 端点契约）、`docs/designs/DESIGN_DYNAMIC_PLAN_REPORTS.md`（1118 行定稿：含用户 2026-10-23 的 OP1/OP2 裁定——2.4.3-C 任务唯一性铁律三道保证 + G2/A8 断言 + 三窗口锚点定稿；决策 A1–A12；2.5.2 测试映射表；兼容性回归八项；文件清单与预估规模）、`docs/PROJECT_CONTEXT.md`（唯一技术契约：§4 分层铁律与 12 工具清单 / §5.2–5.4 响应体与错误码 / §6.4–6.7 数据模型 / §7.2 接口清单）
> 生成日期：2026-10-23 ｜ 状态：待用户确认
> 落盘路径说明：沿用 P9 起确立的对偶惯例——`SPEC_` ↔ `DESIGN_` ↔ `TASKS_`、`specs/` ↔ `designs/` ↔ `tasks/`（同 `docs/tasks/TASKS_AGENT_CHAT.md`），本文件落 `docs/tasks/TASKS_DYNAMIC_PLAN_REPORTS.md`
> 已裁决事项继承（不再重开）：spec 13 项冲突裁决（#1 API 路径以契约为准 / #2 `report_type` 参数名 / #3 周期定位组合 / #4 version per-user 单调 / #5 归档重生成 / #6 幽灵清理 agent+todo / #7 reports 倒序+标量分页 / #8 current 空态 200+null / #9 diff 无基线 200+空结构 / #10 调整周期不变 / #11 prompts 边界正向化（有意变更）/ #12 内嵌 LLM 30s + 慢日志照记 / #13 done/skipped 原样迁移）+ O1–O4 全部裁定 + design 决策 A1–A12 + **用户 OP1（任务落库双分支 + 「一个任务在整个计划里只出现一次」铁律）/ OP2（三窗口锚点 `[09:00, 14:00, 19:00]` 定稿）裁定（2026-10-23）**；本清单不重开任何设计决策
>
> **编号读法**：本文「决策 A5」指 design 2.8.2 设计决策；「验收 D3」指 spec §8.1 验收标准；「OP1/OP2」指 design 2.8.4 用户裁定定稿；「G2/A8/R1/T0/Q1」等指 design 2.5.2 pytest 用例组锚点；「V1–V6」指 spec §8.3 本机验证项；勿与 spec 修订记录 R1 混淆。

---

## 0. 任务总览与依赖关系

**分组结构**（11 组，共 32 个子任务；实现顺序即用户指定依赖链：schemas 校验（零 DDL）→ 纯函数引擎（先行可测）→ services 编排 → api 路由 → agent 接入 → 测试补齐 → 全量回归 → 收尾）：

```
组1 schemas出入参模型 ─────────────────────────────────────────────┐
组2 排程引擎scheduler(纯函数) ──→ 组4 services/plan ──→ 组6 api/v1路由 ─┤
组3 调整引擎adjuster(纯函数) ───→ ↑（同汇入组4）                    │
                                   └→ 组7 agent层(tools+registry+prompts) ─┤
组5 services/report（依赖组1；仅被组6/7消费，可与组4并行）──────────→ │
                                                                      ├─→ 组8 测试一/二（生成+调整，含引擎单测可先行）
                                                                      ├─→ 组9 测试三~六（查询diff+报告+工具+prompt断言）
                                                                      └─→ 组10 全量回归与冻结项审查 ──→ 组11 走查与本机验证交接
```

**关键路径**：1.1 → 2.1~2.3 → 3.1~3.3 → 4.1 → 4.2 → 6.1 → 8.1 → 8.2 → 10.3 → 11.1。

**可并行标注**：
- 组 1 / 组 2 / 组 3 相互零文件交集，可完全并行（组 2 与组 3 之间仅 `find_free_slot` 共享（决策 A12）——组 3 的 3.2 依赖组 2 的 2.4 落地）
- 组 5（report 服务）与组 4（plan 服务）零文件交集，可并行；两者都被组 6（路由）与组 7（工具）消费
- 组 8.1（引擎单测）**仅依赖组 2/3**——P11 经验「组完成即跑该组测试」的落实点：组 2/3 完成后即可编写并运行，先于组 4
- 组 9.4（test_agent_prompt 断言反转）仅依赖组 7.3，可与组 8 并行
- 组 7.2（registry 追加）依赖组 7.1（tools 4 实现）；组 7.1 依赖组 4 + 组 5
- 组 10.1（冻结项 diff 审查）可在任意里程碑先跑，正式收口在组 10

**实现前置约定**（全文适用，各任务不再重复）：
1. **运行环境**：后端一律使用 `backend/.venv`（`./.venv/Scripts/python.exe`）；系统 Anaconda 环境缺依赖不可用
2. **沙箱限制与 mock 惯例**：无外网，pytest 走 ASGI TestClient 直调（conftest 既有 `app_client` / `user_a` / `user_b` / `_isolated_runtime` autouse，零新增基建）；**LLM 必须 mock** 且注入形态与实现强耦合——plan.py / report.py 必须经 `from app.services import llm` 模块属性访问调用 `llm.chat`，注入点分别为 `monkeypatch.setattr("app.services.plan.llm.chat", fake)` 与 `monkeypatch.setattr("app.services.report.llm.chat", fake)`（P9/P11 同款惯例，design 2.5.1）；对话通道沿用 `monkeypatch.setattr("app.services.llm.agent_chat_stream", fake)`（P11 既有惯例零新增）；引擎单测（组 8.1）构造 dataclass 直测、不依赖 LLM 与 DB
3. **P11 经验继承**：测试分批跑（组完成即跑该组测试 + 里程碑全量回归）；**编造性失败要区分「实现缺失」与「环境性失败」**——失败先定位是断言对应的实现未落地（按任务清单补），还是沙箱环境问题（IPv6/网络类，查 conftest 既有补丁），禁止为过测试改断言迁就环境
4. **O8 同款常量铁律**：全部阈值/超时常量在模块级定义、函数体内以模块常量名直接引用（禁默认参数捕获），保证 `monkeypatch.setattr("app.services.plan.PLAN_LLM_TIMEOUT_S", 0.05)` 生效（design 2.5.3 加速点）
5. **日期敏感断言动态计算**（P7 惯例，design 2.5.3）：全部断言禁止硬编码日期——测试内以 `ZoneInfo("Asia/Shanghai")` 推导 `next_monday / friday / last_sunday / last_monday`（与被测代码同口径）
6. **既有基线（实测确认）**：pytest 全量 = **153 passed**；`scripts/test_tools.py` 现输出 76 PASS / 0 FAIL，其中 G0.1 断言「TOOLS_SCHEMA 恰 8 个」——**P12 注册 4 工具后此断言属 tasks 阶段计划内更新**（组 10.2，design 1.1.3-E 唯一许可改动点）；本阶段交付后全量应为 153 + 新增五文件用例数
7. 每个新模块 docstring 须回链 design.md 章节号；代码标识符英文 snake_case、注释中文（契约 §8.4）；type hints 全覆盖；`biz` 异常统一经 `app.core.response.BizException`

**常量核对表**（四模块级，值与依据注释必写，全部仅测试可 monkeypatch——design 2.4.1/2.4.2/2.4.3-B/2.4.4；组 2.1 / 3.1 / 4.1 / 5.2 逐字落地，组 11.1 走查复核）：

| 模块 | 常量 | 值 | 依据（注释必写） |
|------|------|-----|------|
| `analytics/scheduler.py` | `REST_WEEKDAY` | `4` | O3 固定周五休息日（无特例） |
| `analytics/scheduler.py` | `DAY_SLOT_ANCHORS` | `[time(9,0), time(14,0), time(19,0)]` | **OP2 三窗口锚点定稿**（上午/下午/晚上） |
| `analytics/scheduler.py` | `DAY_SLOT_LIMITS` | `[time(14,0), time(19,0), time(23,0)]` | 各窗口上界（每窗 300 分钟，合计 840 ≥ 档案上限 600） |
| `analytics/scheduler.py` | `CANDIDATE_MAX_MINUTES` | `240` | 单窗口可容纳上限（超者进 unplaced） |
| `analytics/scheduler.py` | `CANDIDATE_MIN_MINUTES` | `15` | 低于 15 分钟的学习块无意义 |
| `analytics/adjuster.py` | `DEADLINE_URGENT_HOURS` | `48` | spec §4.4-1 截止临近阈值（含逾期） |
| `analytics/adjuster.py` | `RECENT_MINUTES_RATIO` | `0.6` | spec §4.4-1 近 7 天时长不足比例 |
| `analytics/adjuster.py` | `RECENT_WINDOW_DAYS` | `7` | 近期时长评估窗口 |
| `services/plan.py` | `PLAN_LLM_TIMEOUT_S` | `30.0` | spec §4.1-1；决策 A3（外层 wait_for） |
| `services/report.py` | `REPORT_LLM_TIMEOUT_S` | `30.0` | 同上（**两模块各自定义同值，刻意不共用**——模块独立 monkeypatch 前提） |

**明确不改动清单（冻结项，防越界——design 1.1.3-E）**：

| 文件 | 不改动理由 | 验证方式 |
|------|-----------|---------|
| `backend/app/agent/core.py` / `memory.py` | SPEC §5.6.1-6：TOOL_MAP 动态派发（core.py:528）对 8→12 零感知 | 组 10.1 `git diff` 为空（D13） |
| `backend/app/services/llm.py` | `chat` / `chat_stream` / `agent_chat_stream` / 客户端构造区零改动（P4/P9/P11 三条依赖链）；30s 超时在调用方实现（决策 A3） | 组 10.1 diff 为空 + 全量回归 |
| `backend/app/agent/tools.py` 既有 8 工具实现区 + 横切私有区（`tool_endpoint` 等） | 纯追加铁律（参照 P11 对 llm.py 先例）；仅文件末尾追加 4 工具 | 组 10.1 diff 呈纯追加 |
| `backend/app/models/*.py` 全部 DDL | SPEC 范围总则：零 DDL（learning_plans/items/reports/tasks 沿用契约 §6） | 组 10.1 diff 为空 |
| `backend/app/analytics/` 既有 4 模块（advice/statistics/trend/weakness） | 复用不重写（SPEC §3.2）；scheduler/adjuster 为新增文件不触碰 | 组 10.1 diff 为空 |
| `backend/app/api/v1/plans.py` 既有 2 端点 / `reports.py` 详情端点 | P3 契约零行为变更（`list_reports` 改写是裁决 #7 计划内行为变更，唯一例外） | 组 9.1 Q3 回归 + 组 10.1 |
| `backend/app/api/v1/__init__.py` | plans_router / reports_router 已挂载，新路由在既有 router 内扩展 | 组 10.1 diff 为空 |
| `backend/app/services/task.py` / `goal.py` / `record.py` / `profile.py` | 只读消费（聚合输入经 ORM 查询），无改动触点 | 组 10.1 diff 为空 |
| `backend/app/schemas/plan.py` / `report.py` 既有出参模型 | SPEC §4.5-5：`PlanOut`/`PlanItemOut`/`ReportOut` 零删改仅追加 | 组 10.1 diff 呈纯追加 |
| 全部前端文件 | **本阶段禁止创建任何前端文件**（PlanView.vue / ReportsView.vue / plan.ts 扩展属后续阶段单独下达） | 组 11.1 `git status frontend/` 零改动 |

> **范围铁律重申**：本阶段只做后端（4 新增后端模块 + 6 扩展文件 + 5 新增测试文件 + 1 测试更新 + test_tools.py 计划内更新）；零 DDL、零前端、`core.py`/`memory.py`/`llm.py` 既有方法零改动（git diff 为空是 D13 验收项）。

---

## 1. schemas 出入参模型追加（零 DDL 前置）

**写作说明**：本组是全部后续任务的数据契约基础，零 DDL（模型是传输/计算对象，落库仍写既有四表——design 2.3.1-3）。模型层级与字段唯一来源：design 2.3.2-A。既有 `PlanOut` / `PlanItemOut` / `ReportOut` 零删改。

### 1.1 schemas/plan.py 追加九个出入参模型

- [ ] **要点**：
  - 文件末尾追加区逐字对齐 design 2.3.2-A：`PlanGenerateIn`（零字段 + `extra="forbid"`，防 user_id 注入）、`PlanAdjustIn`（零字段 + `extra="forbid"`）、`UnplacedTaskOut`（`task_id: int | None` / `title: str` / `reason: str`）、`PlanGenerateOut`（`plan: PlanOut` / `items: list[PlanItemOut]` / `unplaced_tasks: list[UnplacedTaskOut]` / `generated_by: Literal["llm", "rules"]`）、`DiffEntryMoved`（topic / task_id / from_date / from_time / to_date / to_time / reason）、`DiffEntryAdded`（topic / task_id / plan_date / start_time / reason）、`DiffEntryRemoved`（topic / task_id / from_date / reason）、`PlanDiffOut`（`base_plan_id: int | None` + moved/added/removed 三列表）、`PlanAdjustOut`（`plan: PlanOut` / `adjust_reason: str | None` / `diff: PlanDiffOut` / `adjusted: bool`）
  - **单一输出 schema 落实（用户指令②）**：`generated_by="llm"` 与 `"rules"` 两条生成路径共用 `PlanGenerateOut`——降级路径与正常路径同构，差异仅 `generated_by` 一个标记字段（design 2.3.1-1，结构性保证非纪律约定）
  - 模型命名与 SPEC 第 2 章领域术语一一对应（`UnplacedTask` / `DiffEntry`）
- **涉及文件**：修改 `backend/app/schemas/plan.py`（追加 ~90 行）
- **完成判定**：`cd backend && ./.venv/Scripts/python.exe -m py_compile app/schemas/plan.py` 通过；`./.venv/Scripts/python.exe -c "from app.schemas.plan import PlanGenerateOut, PlanAdjustOut, PlanDiffOut; PlanGenerateIn()` 不抛错、`PlanGenerateIn(user_id=1)` 抛 ValidationError` 输出核对
- **依赖**：无
- **决策锚点**：design 2.3.2-A；SPEC §6.1/§6.2

### 1.2 schemas/report.py 追加 ReportGenerateIn（period_end 校验）

- [ ] **要点**：
  - `ReportGenerateIn`：`report_type: Literal["daily", "weekly", "monthly"]`（必填）+ `period_end: date | None`（可选）；`model_config = ConfigDict(extra="forbid")`
  - **period_end ≤ 今天校验**用 `model_validator(mode="after")` + 北京时区今天（`ZoneInfo("Asia/Shanghai")` 本地定义不跨层导入），错误消息中文含格式示例（如「period_end 不得晚于今天（YYYY-MM-DD）」）——422/1001 由全局处理器转换，schema 层零额外代码
  - **不接受 period_start**（由类型与 period_end 推导，防首尾矛盾——SPEC §6.3）
- **涉及文件**：修改 `backend/app/schemas/report.py`（追加 ~25 行）
- **完成判定**：`./.venv/Scripts/python.exe -m py_compile app/schemas/report.py` 通过；`ReportGenerateIn(report_type="weekly", period_end=date.today() + timedelta(days=1))` 抛 ValidationError；`ReportGenerateIn(report_type="foo")` 抛 ValidationError
- **依赖**：无（可与 1.1 并行）
- **决策锚点**：SPEC §5.4.1-1 / §6.3；design 2.4.6-B

**里程碑验证（组 1 结束）**：
```bash
cd backend && ./.venv/Scripts/python.exe -m py_compile app/schemas/plan.py app/schemas/report.py && \
./.venv/Scripts/python.exe -c "from app.schemas.plan import PlanGenerateIn, PlanAdjustIn, PlanGenerateOut, PlanDiffOut, PlanAdjustOut, UnplacedTaskOut, DiffEntryMoved, DiffEntryAdded, DiffEntryRemoved; from app.schemas.report import ReportGenerateIn; print('SCHEMAS_OK')" && \
git diff app/schemas/plan.py app/schemas/report.py | grep "^-" | grep -v "^---" | wc -l   # 输出 0 = 既有模型零删改
```

---

## 2. 排程引擎 analytics/scheduler.py（纯函数，先行可测）

**写作说明**：新增 `backend/app/analytics/scheduler.py`（~230 行）。公开接口唯一来源：design 2.4.1；布局算法：design 2.4.1 六步。**零依赖铁律**：纯函数、不 import services / models / agent（分层铁律，对齐 statistics.py 先例）；**LLM 候选与纯规则候选同构（决策 A8）**——降级路径是「换候选源」不是「换管线」。

### 2.1 模块骨架 + 常量表 + 引擎数据契约对象

- [ ] **要点**：
  - 模块 docstring：职责声明（排程引擎纯函数，O4「确定性引擎决定何时学」）+ 回链 design 2.4.1
  - 常量表五项逐字落地组 0 核对表（`REST_WEEKDAY` / `DAY_SLOT_ANCHORS` / `DAY_SLOT_LIMITS` / `CANDIDATE_MAX_MINUTES` / `CANDIDATE_MIN_MINUTES`），每项注释写依据（OP2/OP3 锚点），仅测试可 monkeypatch
  - 引擎内部 dataclass（不进 schemas/，design 2.3.2-B）：`ScheduleCandidate`（topic / knowledge_points / estimated_minutes / priority / related_task_id / deadline?）、`ScheduleInput`（candidates / daily_capacity_minutes / week_days / rest_weekday=4 / now）、`ScheduledItem`（plan_date / start_time / end_time / topic / knowledge_points / estimated_minutes / priority / related_task_id——**日期时间 100% 引擎推导**）、`UnplacedTask`（topic / related_task_id / 原因中文）、`ScheduleOutput`（placed / unplaced）
  - **OP2 三窗口锚点落地**：`DAY_SLOT_ANCHORS = [time(9,0), time(14,0), time(19,0)]`——支撑「周六下午」等真实时段语义（reason 模板的「上午/下午/晚上」中文转换的数据基础）
- **涉及文件**：新增 `backend/app/analytics/scheduler.py`
- **完成判定**：`./.venv/Scripts/python.exe -m py_compile app/analytics/scheduler.py` 通过；`grep -n "from app.services\|from app.models\|from app.agent" app/analytics/scheduler.py` 零命中（零依赖静态核查）
- **依赖**：无（可与组 1 / 组 3 并行）
- **决策锚点**：design 2.4.1；A1（引擎位置）；A6/OP2（三窗口）；A8（候选同构）

### 2.2 next_week_window 周期推导 + build_rule_candidates 降级候选构造

- [ ] **要点**：
  - `next_week_window(today: date) -> tuple[date, date]`：`days_ahead = 7 - today.weekday()`（周一=0）→ `(today + days_ahead, today + days_ahead + 6)`——「下一个完整自然周」固定语义（SPEC 领域术语）
  - `build_rule_candidates(overdue_tasks, due_soon_tasks, roadmap_leaves, weak_points, ...) -> list[ScheduleCandidate]`：**降级路径的纯规则候选**（顺序铁律：逾期 → 临期 → roadmap/薄弱点顺序，SPEC O4）；逾期/临期候选携带 `related_task_id` 与 deadline（引擎排序依据）；roadmap/薄弱点候选无 related_task_id（落库时新建任务）
  - **降级与正常路径同构（用户指令②核心）**：两条路径产出同型 `ScheduleCandidate` 列表、共用同一引擎与同一 `PlanGenerateOut`——差异仅 `generated_by` 标记（决策 A8 构造性保证）
- **涉及文件**：修改 `backend/app/analytics/scheduler.py`
- **完成判定**：`py_compile` 通过；单测断言由组 8.1 固化（降级候选顺序：逾期在前、含 related_task_id）
- **依赖**：2.1（同文件）
- **决策锚点**：design 2.4.1 公开接口；O4 / A8

### 2.3 build_week_schedule 布局算法（硬约束的构造性保证）

- [ ] **要点**：
  - `build_week_schedule(schedule_input: ScheduleInput) -> ScheduleOutput` 核心纯函数，六步逐字落地（design 2.4.1）：
    1. **候选排序**：`deadline` 非空者升序在前（逾期/临期优先排在周期前段，SPEC 规则 5.1.1-6 ③）→ 同级按 priority 权重（high=0 < medium=1 < low=2）→ 同级按输入顺序稳定排序
    2. **逐日贪心装入**：日期游标从 `week_days[0]`（周一）顺序前进，**跳过周五**（`REST_WEEKDAY=4`，O3 无特例）；每日维护 `remaining = daily_capacity_minutes` 与时段游标
    3. **三窗口锚点分配（OP2）**：条目在当前窗口内从游标处连续排布（`end = start + estimated_minutes`）；放不下当前窗口则移下一锚点（09:00→14:00→19:00）；三窗口全满该日结束；**单条目 > CANDIDATE_MAX_MINUTES(240) 直接进 unplaced**（原因「单条目时长超出可排时段窗口」）
    4. **约束构造性**：日容量——装入前检查 `estimated_minutes <= remaining`，不足顺延至下一可用日、全周期无可容日进 unplaced；时段唯一——游标单调前进，结构性无重复 `(plan_date, start_time)`；时长自洽——`end_time` 由计算得出恒等
    5. **unplaced 截断**：装不下的候选进 `unplaced`（透传 topic/related_task_id + 中文原因），**不因容量不足失败**（SPEC 规则 5.1.1-9）
    6. **休息条目不在引擎内生成**：引擎只排任务候选；周五休息条目（`topic="休息 / 复习"`、start/end/task_id/estimated/priority 全 None）由 plan_svc 在引擎输出后注入（SQLite 唯一索引对 NULL 不判重，design 1.2.6-①）
  - 注释写明「构造性保证 vs 校验后修复」的 rationale 摘要（design 2.1.3-A 五条之 1：约束满足是构造性事实——游标单调 ⇒ 无冲突、逐日计数 ⇒ 不超限）
- **涉及文件**：修改 `backend/app/analytics/scheduler.py`
- **完成判定**：`py_compile` 通过；G1/D1 引擎侧断言（每日合计 ≤ 容量、start_time 无重复、周五跳过、逾期在前段、end-start=estimated）由组 8.1 固化
- **依赖**：2.1
- **决策锚点**：design 2.4.1 布局算法；OP2/OP3；SPEC 规则 5.1.1-6

### 2.4 find_free_slot 空闲时段查询辅助（两引擎共享单一来源）

- [ ] **要点**：
  - 模块内公开 `find_free_slot(occupied, day_capacity_used, daily_capacity, estimated_minutes) -> (date, time) | None` 形态的辅助函数（签名以实现为准，语义：给定某日已占条目与容量，返回该日可容纳 `estimated_minutes` 的最早 (日期, 起始时刻)，跨日递进查找）——**决策 A12：adjuster 重排复用本辅助与 DAY_SLOT 常量，防两引擎时段口径漂移**
  - 游标逻辑与 2.3 的三窗口锚点完全同源（同一常量、同一推进规则）
- **涉及文件**：修改 `backend/app/analytics/scheduler.py`
- **完成判定**：`py_compile` 通过；`find_free_slot` 行为由组 8.1 引擎单测覆盖（含「周六满→周日空闲」场景，A6 用例前置）
- **依赖**：2.3（复用窗口常量与游标逻辑）
- **决策锚点**：A12（跨模块共享时段常量单一来源）

**里程碑验证（组 2 结束）**：
```bash
cd backend && ./.venv/Scripts/python.exe -m py_compile app/analytics/scheduler.py && \
./.venv/Scripts/python.exe -c "from app.analytics.scheduler import next_week_window, build_week_schedule, build_rule_candidates, find_free_slot, ScheduleInput, DAY_SLOT_ANCHORS, REST_WEEKDAY; from datetime import time; assert DAY_SLOT_ANCHORS == [time(9,0), time(14,0), time(19,0)] and REST_WEEKDAY == 4; print('SCHEDULER_OK')"
# OP2 锚点值 + O3 周五常量的可执行断言
```

---

## 3. 调整引擎 analytics/adjuster.py（纯函数 + reason 模板，零 LLM）

**写作说明**：新增 `backend/app/analytics/adjuster.py`（~260 行）。公开接口唯一来源：design 2.4.2；reason 模板：design 2.4.2-C。**纯确定性铁律（SPEC 规则 5.2.1-8）**：不调 LLM、不碰 DB（数据由 plan.py 读库后传入）；**diff 计算函数与 `GET /plans/{id}/diff` 端点共用同一个函数**——幂等重算一致性是「同函数」的构造性结果（D4）。

### 3.1 模块骨架 + 三条件阈值常量 + evaluate_move_set 评估函数

- [ ] **要点**：
  - 常量三项逐字落地（`DEADLINE_URGENT_HOURS=48` / `RECENT_MINUTES_RATIO=0.6` / `RECENT_WINDOW_DAYS=7`，spec §4.4-1 锁定，仅测试可 monkeypatch）
  - 快照 dataclass（design 2.3.2-B）：`AdjustContext`（items / tasks / recent_minutes / daily_capacity / now / week_days）、`ItemSnapshot`（旧版条目只读快照：item_id / plan_date / start_time / end_time / topic / task_id / estimated_minutes / priority / status）、`TaskSnapshot`（deadline / status）、`AdjustmentResult`（new_items / diff / reason_material）、`ReasonMaterial`（模板变量素材）
  - `evaluate_move_set(context: AdjustContext) -> list[ItemSnapshot]`：三条件量化——**未完成**（`status != "done"` 且（`plan_date < 今天` 或关联任务 `status != "done"`））∧（**截止临近**（`deadline - now <= 48h` 含已逾期）∨ **近期时长不足**（近 7 天 < `容量 × 7 × 0.6`））→ 移动集
  - 注释注明时长不足是**全局条件**（命中则全部未完成条目可移动，非逐条目判定）
- **涉及文件**：新增 `backend/app/analytics/adjuster.py`
- **完成判定**：`./.venv/Scripts/python.exe -m py_compile app/analytics/adjuster.py` 通过；`grep -n "from app.services\|from app.models\|import asyncio" app/analytics/adjuster.py` 零命中（纯函数 + 零 LLM 静态核查）
- **依赖**：无（骨架）；3.2 依赖组 2.4（find_free_slot 共享）
- **决策锚点**：design 2.4.2；A2；SPEC 规则 5.2.1-2

### 3.2 apply_adjustment 纯确定性重排 + diff 计算

- [ ] **要点**：
  - `apply_adjustment(context, move_set) -> AdjustmentResult`，算法五步逐字（design 2.4.2-A）：
    1. **原样迁移**：`status in (done, skipped)` 与未进移动集条目原样复制（plan_date/start_time/end_time/task_id/status 锚定不动——diff 无噪音条目，裁决 #13）
    2. **移动集重排**：寻找周期内 `plan_date > max(原日期, 今天)` 的空闲容量（经 scheduler 的 `find_free_slot`，决策 A12）；同等空闲度**优先周末**（weekday ≥ 5 优先，SPEC 5.2.1-6）
    3. **低优先级顺延**：目标日容量不足时从该日非 done/skipped 条目按 **low → medium** 顺序选牺牲条目（**high 不顺延**）挪到更晚空闲时段；牺牲条目记录 from→to 合并进 moved diff（reason「为紧急任务腾出时段顺延」）
    4. **removed 兜底**：周期全满 → 低优先级条目移出计划（reason「容量不足顺延不出，移出计划」）；移动集自身无法安排同样移出并如实写 reason（SPEC 5.2.3-3）
    5. **done/skipped 原样保持**（裁决 #13 历史事实不可篡改）
  - **diff 计算**：新布局 vs 旧版条目按 `task_id`（优先）与 `(topic, from位置)` 对齐：位置变化 → moved（from_date/from_time/to_date/to_time/reason 五要素）；新版多出 → added（调整路径通常空）；新版缺失且非 done → removed；**diff 计算函数与端点重算共用同一实现**（D4 幂等）
- **涉及文件**：修改 `backend/app/analytics/adjuster.py`
- **完成判定**：`py_compile` 通过；A6（顺延）/A7（removed）/A2（diff 三要素）引擎侧断言由组 8.1 固化
- **依赖**：3.1、组 2.4（find_free_slot）
- **决策锚点**：design 2.4.2-A；裁决 #10/#13；A12

### 3.3 render_adjust_reason 模板渲染（具体任务名与时段，≥20 字符红线）

- [ ] **要点**：
  - `render_adjust_reason(material: ReasonMaterial) -> str`——**用户最高优先级指令③落地（禁止空话模板）**，分段拼接非单一 format（design 2.4.2-C 模板主体逐字）：
    - 段1（必有）：`检测到你本周的{moved_topics}学习任务{cause_desc}，`
    - 段2（单任务移动）：`已从{from_desc}调整到{to_desc}。`；段2'（多任务）：`已分别调整到后续空闲时段（{首条 from_desc} → {首条 to_desc} 等 {moved_count} 处）。`
    - 段3（有顺延时追加）：`并顺延了原定{postponed_day_desc}的{postponed_count}个低优先级任务到{postponed_to_desc}。`
    - 段4（有 removed 时追加）：`因本周容量不足，{removed_desc}任务已移出计划，可在任务页单独安排。`
  - 中文转换纯函数：`_weekday_cn(d)`（`周一`~`周日` + `（MM-DD）`）、`_slot_cn(t)`（<12:00 上午 / <18:00 下午 / 否则晚上 / None 空串）
  - **质量红线（结构性保证）**：模板只引用 ReasonMaterial 真实字段（全部来自新旧两版条目计算）——编造不可能发生；所有日期/时段由纯函数转换——与库中数据恒一致；段2/2'/3/4 依素材有无拼接——无顺延不出现顺延话术；**拼接结果恒 ≥ 20 字符**（段1 单任务最短已 40+ 字符，D3 断言天然满足）；**from_desc/to_desc 必含「从 → 到」日期表述**（如「周三（10-28）晚上 → 周六（10-31）下午」）
  - 三场景示例（单任务移动 / 多任务移动 / 任务被顺延）写入模块 docstring 作为锚定样例
- **涉及文件**：修改 `backend/app/analytics/adjuster.py`
- **完成判定**：`py_compile` 通过；模板三场景文案断言（含任务名、含从→到日期、≥20 字符、无顺延不出现顺延话术）由组 8.1 固化
- **依赖**：3.1（同文件；ReasonMaterial 定义）
- **决策锚点**：design 2.4.2-C；SPEC 规则 5.2.1-4；用户指令③

**里程碑验证（组 3 结束）**：
```bash
cd backend && ./.venv/Scripts/python.exe -m py_compile app/analytics/adjuster.py && \
./.venv/Scripts/python.exe -c "from app.analytics.adjuster import evaluate_move_set, apply_adjustment, render_adjust_reason, DEADLINE_URGENT_HOURS, RECENT_MINUTES_RATIO; assert DEADLINE_URGENT_HOURS == 48 and RECENT_MINUTES_RATIO == 0.6; print('ADJUSTER_OK')"
```

---

## 4. services/plan.py 计划编排服务（生成/调整/查询/diff）

**写作说明**：新增 `backend/app/services/plan.py`（~420 行）——本阶段核心编排层。公开接口四函数唯一来源：design 2.4.3；LLM 编排三分支与 30s 总窗：design 2.4.3-B；任务落库与唯一性铁律：design 2.4.3-C（OP1 裁定定稿）；事务边界：design 2.1.3-D。**HTTP 端点与 Agent 工具复用同一 service 函数（单一业务事实来源，SPEC §5.7 注）**。

### 4.1 生成路径：输入聚合 + 规划 LLM 三分支 + 30s 总窗

- [ ] **要点**：
  - `async def generate_plan(db: Session, user_id: int) -> dict`
  - **输入聚合**（只读四查询，design 2.4.3-A-1）：档案（`daily_study_minutes` 缺省 60，P10 契约同款）→ active 目标 roadmap 叶子（本地实现提取、注释说明与 goal.py 私有函数同构不共享）→ 掌握度薄弱升序（`get_mastery_list`）→ 逾期/临期任务（deadline 升序，含 id/title/estimated/priority/knowledge_points——**任务池按 id 天然去重，唯一性铁律第一道保证**）
  - **候选获取三分支**（决策 A7 总窗方案）：prompt（候选来源 JSON + **「禁止输出任何日期时间字段」硬指令** + 输出格式示例 + 「每个任务最多出现一次」明示）→ `asyncio.wait_for(_call_with_retry(...), timeout=PLAN_LLM_TIMEOUT_S)`——**首调 + 解析失败重试合计 ≤ 30s 总窗**（锁定 HTTP 35s 上限不破）；解析流水线：`json.loads`（剥 ```json 围栏，参照 goal.py 惯例）→ `PlanCandidatesLLM.model_validate`（`extra="forbid"` 结构性无日期字段）+ **`related_task_id` 合法集合语义校验**（不在输入聚合合法任务 id 集合 → 视为解析失败，防编造）
  - **服务类失败（BizException）不重试直接降级**；两次解析失败 / 超时 / 服务失败 → `build_rule_candidates` 纯规则候选，`generated_by="rules"`（O4「降级不失败」）；LLM 正常 → `generated_by="llm"`
  - **唯一性铁律第二道保证（LLM 候选 related_task_id 去重）**：LLM 对同一任务输出多条候选时只保留排序最优一条、其余丢弃
  - LLM 调用形态：`from app.services import llm` 模块属性访问（mock 注入形态，前置约定 2）；降级记元数据级日志（user_id / 降级原因 / 耗时——禁打印 prompt 与响应正文，spec §4.3-4）
  - 引擎调用：`build_week_schedule(ScheduleInput(...))` → 布局 + unplaced → **注入周五休息条目**（topic=`休息 / 复习`、start/end/task_id/estimated/priority 全 None）
- **涉及文件**：新增 `backend/app/services/plan.py`
- **完成判定**：`./.venv/Scripts/python.exe -m py_compile app/services/plan.py` 通过；三分支行为断言由组 8.2 的 G3/G4 固化
- **依赖**：组 1.1（出参模型）、组 2（scheduler + 常量 + build_rule_candidates）
- **决策锚点**：design 2.4.3-A/B；A3（wait_for 30s）；A4（schema 无日期字段）；A7（总窗）；O4

### 4.2 生成路径：落库事务（OP1 双分支 + 唯一性铁律 + 幽灵清理 + 同周期判定）

- [ ] **要点**：
  - **同周期判定三分类**（design 2.4.3-A-4）：目标周与既有 active 区间**不重叠** → 并存保留（D7 多周并存，SPEC 规则 5.1.1-4 前半）；**完全同周期**（`(start_date, end_date)` 逐字段相等）→ 归档旧版 + 幽灵清理 + 新建（D8 重新生成语义，裁决 #5）；**部分重叠** → 抛 `BizException(1007)`（「与现有计划周期冲突」不自动归档，SPEC 5.1.3-3）
  - **落库事务顺序（单 commit，design 2.1.3-D）**：(1) 归档旧版 + 幽灵清理 → (2) 候选落任务 → (3) unplaced 候选建/复用任务 → (4) 新建计划头（`version = 用户 max version + 1`（裁决 #4）、`status="active"`、`source="agent"`、`parent=null`、`adjust_reason=null`）→ (5) 建 items（引擎布局 + 回填 task_id）→ 单次 `db.commit()`；中途异常由 `get_db` teardown 整体回滚（D14 无半截产物）
  - **OP1 双分支落库（用户裁定定稿）**：候选带 `related_task_id` → **复用该任务**（仅同步 `scheduled_date=plan_date`，不新建任务行、不动 priority/goal_id/status——那是用户数据）；候选无 `related_task_id` → **新建任务**（`title=topic`、knowledge_points、estimated_minutes、scheduled_date、priority、goal_id（聚合所得，无目标时 null）、`source="agent"`、`status="todo"`）→ 条目 `task_id` 回填指向它；**unplaced 候选同样建/复用任务但 `scheduled_date=None`**（任务页可见、数据不丢失，决策 A9）；休息条目不建任务
  - **任务唯一性铁律第三道保证（落库断言兜底）**：落库前断言已回填的 task_id 集合无重复，违例抛 `BizException(5000)`（理论不可达，兜底）——「一个任务在整个计划里只出现一次，任务页不出现重复行」
  - **幽灵任务清理**（裁决 #6）：归档旧版前，删除其条目关联任务中 `source="agent" AND status="todo"` 者；`in_progress/done/review` 已流转或 `source="manual"` 一律保留（已流转是用户事实）；**只删任务不动旧版条目**（archived 版本条目必须原样保留，D3「旧版条目逐字段不变」）
  - 注释注明事务窗口最小化：引擎与 LLM 编排全部在事务外完成（计算无副作用），事务内仅纯落库
- **涉及文件**：修改 `backend/app/services/plan.py`
- **完成判定**：`py_compile` 通过；G2（落库四字段 + task_id 回填 + **同 plan 内 task_id 无重复**——OP1 断言）/G5/G6/G7/G8/G9/G10 由组 8.2 固化
- **依赖**：4.1
- **决策锚点**：design 2.4.3-C/E；**OP1 裁定**（三道保证逐条入代码）；A5/A9；裁决 #4/#5/#6

### 4.3 调整路径：adjust_plan 编排（版本链 + 任务同步，零 LLM）

- [ ] **要点**：
  - `async def adjust_plan(db: Session, user_id: int, plan_id: int | None) -> dict`（plan_id 属 HTTP 路径；工具路径缺省时定位当前 active——`start_date <= 今天 <= end_date`）
  - **定位与校验**：plan_id 不存在/越权 → `BizException(1005, 404)`（「不可见即不存在」）；目标非 active → `BizException(1007, 400)`「仅可调整生效中的计划」（SPEC 5.2.3-2）
  - **读快照**（全部只读一次聚合）：旧版条目 + 关联任务快照 + 近 7 天学习时长 + 档案容量 → 构造 `AdjustContext`
  - **评估与分支**：`evaluate_move_set` 为空 → **不新建版本**，返回 `{adjusted: false, reason: "当前计划无需调整"}`（SPEC 规则 5.2.1-9）；非空 → `apply_adjustment` 纯确定性重排 + `render_adjust_reason`
  - **版本链事务（单 commit）**：(1) 旧版置 archived（行与条目零修改）→ (2) 新建计划头（`version+1`、active、`parent_plan_id=旧版 id`、`adjust_reason=reason`、**start/end 与旧版逐字段相等**——周期不变规则，裁决 #10）→ (3) 新建全部条目（迁移 + 重排布局，done/skipped 状态保持）→ (4) **任务同步**：被移动条目关联任务 `scheduled_date` 同步更新为新 `plan_date`、removed 条目任务 `scheduled_date` 置空（同一事务）——**OP1 调整路径同步义务：否则任务页与计划页对不上（A8 断言覆盖）** → commit
  - **零 LLM 断言前提**：本函数体不出现任何 `llm.` 调用（纯确定性，SPEC 规则 5.2.1-8 / D10）
- **涉及文件**：修改 `backend/app/services/plan.py`
- **完成判定**：`py_compile` 通过；`grep -n "llm" app/services/plan.py` 命中仅限 generate 路径（adjust 函数体内零命中）；A1/A8/A9/A10 断言由组 8.3 固化
- **依赖**：4.1（同文件先建骨架与事务惯例）、组 3（adjuster 三函数）
- **决策锚点**：design 2.4.3；**OP1（调整同步义务）**；裁决 #10/#13；SPEC 规则 5.2.1-3/9/11

### 4.4 查询路径：get_current_plan + get_plan_diff

- [ ] **要点**：
  - `def get_current_plan(db: Session, user_id: int) -> dict | None`：返回 `start_date <= 今天 <= end_date` 且 `status="active"` 的计划及全部条目；items 按 `plan_date` 升序、同日 `start_time` 升序（None 排最前——休息条目）；无匹配返回 `None`（HTTP 200 + `data=null`，**非 404**，裁决 #8）
  - `def get_plan_diff(db: Session, user_id: int, plan_id: int) -> dict`：404 定位（越权/不存在统一 1005/404）→ 对比该计划与 `parent_plan_id` 指向版本的条目，**按两版条目现值重算**（复用 adjuster 的 diff 计算函数——D4 幂等一致性）；`parent_plan_id=null`（首版）返回 `{base_plan_id: null, moved: [], added: [], removed: []}`（200 空结构，裁决 #9）
- **涉及文件**：修改 `backend/app/services/plan.py`
- **完成判定**：`py_compile` 通过；Q1/Q2 断言由组 9.1 固化
- **依赖**：4.3（diff 复用 adjuster 同一计算函数）
- **决策锚点**：design 2.4.3 公开接口；裁决 #8/#9；SPEC 规则 5.3.1-1/3/4/5

**里程碑验证（组 4 结束）**：
```bash
cd backend && ./.venv/Scripts/python.exe -m py_compile app/services/plan.py && \
./.venv/Scripts/python.exe -c "from app.services.plan import generate_plan, adjust_plan, get_current_plan, get_plan_diff; from app.services.plan import PLAN_LLM_TIMEOUT_S; assert PLAN_LLM_TIMEOUT_S == 30.0; print('PLAN_SVC_OK')" && \
grep -c "find_free_slot\|build_week_schedule\|evaluate_move_set\|apply_adjustment\|render_adjust_reason" app/services/plan.py   # ≥5 = 引擎调用点齐全（编排层不内联布局逻辑）
```

---

## 5. services/report.py 报告编排服务

**写作说明**：新增 `backend/app/services/report.py`（~330 行）。周期推导与七要素聚合唯一来源：design 2.4.4；复用映射表红线（design 1.2.4）：**掌握度/薄弱点/趋势逻辑零重写**（⑤ 直接调 `get_mastery_list` 取前 3、⑦ 调 `get_trend` slope）；周期窗口聚合是 analytics 从未交付过的口径，属新增 ORM 查询落在本层（分层合法）。

### 5.1 周期推导 resolve_period + 七要素聚合 collect_statistics

- [ ] **要点**：
  - `resolve_period(report_type: str, period_end: date | None, today: date) -> tuple[date, date]`（纯函数）：daily → 缺省昨天、start=end；weekly → 缺省上周日、start=所在周周一（`end - weekday(end)`）；monthly → 缺省上月末日、start=所在月首日；`period_end > today` 已由 schema 层拒绝
  - `collect_statistics(db, user_id, start, end) -> dict` 七要素（**全部本地 ORM 聚合，禁止任何数字来自 LLM——SPEC §5.4.1-2 红线**）：
    - ① `total_minutes`：周期内 `learning_records.duration_minutes` 合计（窗口 `study_date between`，北京自然日口径）
    - ② `task_completed`：`completed_at` 落周期内的 tasks 计数；③ `completion_rate`：周期内截止任务中 done 占比（分子含 review，P5 惯例）
    - ④ `top_direction`：周期内 `learning_records.knowledge_points` JSON 摊平 Counter 聚合取最大项（写法参照 weakness.py recent Counter）
    - ⑤ `weak_points`：调 `get_mastery_list` 取前 3 映射 `{knowledge_point, mastery_score}`（**零重写排除逻辑**）
    - ⑥ `progress`：对上一等长周期重复 ①③ 与自评均值聚合（三差值对象；平均掌握度口径 = 周期内 `learning_records.mastery_level` 均值——决策 A11，knowledge_mastery 无历史快照）
    - ⑦ `advice`：三规则自建（周期内逾期 + 薄弱点 + 趋势 slope；**不复用 advice.generate_advice——口径污染，决策 A10**）
  - **零数据容错**：周期内无记录无任务 → 全 0/null/[]、`top_direction=null`、`weak_points=[]`、advice 如实引导（SPEC 规则 5.4.1-7）
  - **统计本身异常**（ORM 查询抛错）→ 上抛 500/5000，不落半截报告（SPEC 5.4.3-2）
- **涉及文件**：新增 `backend/app/services/report.py`
- **完成判定**：`./.venv/Scripts/python.exe -m py_compile app/services/report.py` 通过；`grep -n "get_mastery_list\|get_trend" app/services/report.py` 各 ≥1 命中（复用锚点）；R1/R2/R5 断言由组 9.2 固化
- **依赖**：组 1.2（ReportGenerateIn）；可与组 4 并行
- **决策锚点**：design 2.4.4-A/B、1.2.4 复用映射表；A10/A11；O1

### 5.2 总结双路径 generate_report + 模板降级 + append 落库

- [ ] **要点**：
  - `async def generate_report(db: Session, user_id: int, data: ReportGenerateIn) -> dict`：`resolve_period` → `collect_statistics` → 总结双路径：
  - **LLM 路径**：prompt（统计 JSON + 「中文、面向学生、必须引用其中的真实数字、给出可执行建议」指令）→ `asyncio.wait_for(llm.chat(messages), timeout=REPORT_LLM_TIMEOUT_S)`（`from app.services import llm` 模块属性访问）；成功非空 → `summary=文本`、`generated_by="llm"`
  - **模板降级路径（O1）**：失败/超时/空文本 → `render_template_summary(stats, report_type)`——模板含全部真实数字（「本周学习 {hours} 小时，完成任务 {n} 个，完成率 {rate}%。学习最多的方向是{direction}；最需要加强的知识点是{weak}。建议{advice首条}」）；空数据分支「本周期暂无学习记录，建议从 {首薄弱点或兴趣方向} 开始」；`generated_by="template"`；**报告仍落库、接口仍成功——LLM 失败不构成业务失败，错误码 3000 不用于此路径**
  - `render_template_summary(stats: dict, report_type: str) -> str` 为模块公开纯函数（design 2.4.4 签名）
  - **落库（append，O2）**：`LearningReport(report_type, period_start, period_end, summary, content=七要素 dict + generated_by)` 单行 insert + commit——`content` 经 JSONType 直赋 dict（禁手动 json 序列化）；**旧行永不 UPDATE**（审计轨迹）
  - **降级与正常路径同构（用户指令②）**：两路径产出完全相同的落库结构与 API 响应结构，差异仅 `content.generated_by` 一个标记字段（随报告持久化，可审计）
- **涉及文件**：修改 `backend/app/services/report.py`
- **完成判定**：`py_compile` 通过；`from app.services.report import REPORT_LLM_TIMEOUT_S` 断言 == 30.0；R3/R4/R6 断言由组 9.2 固化
- **依赖**：5.1（同文件）
- **决策锚点**：design 2.4.4-C/D；O1/O2；A3

**里程碑验证（组 5 结束）**：
```bash
cd backend && ./.venv/Scripts/python.exe -m py_compile app/services/report.py && \
./.venv/Scripts/python.exe -c "from app.services.report import generate_report, resolve_period, collect_statistics, render_template_summary, REPORT_LLM_TIMEOUT_S; assert REPORT_LLM_TIMEOUT_S == 30.0; print('REPORT_SVC_OK')"
```

---

## 6. api/v1 路由扩展（薄委托，零业务逻辑）

**写作说明**：`api/v1/plans.py` 81 → ~200 行（4 新路由）；`api/v1/reports.py` 80 → ~160 行（generate + list 改写）。**路由顺序硬约束（design 1.2.3-③ 实测）**：`/plans/generate`、`/plans/current` 字面量路由必须声明在 `/plans/{plan_id}` 之前（FastAPI 按声明序匹配，否则 `generate`/`current` 被解析为 plan_id → 422）——既有 `get_plan` 函数位置后移，`git diff` 呈计划内编辑；`api/v1/__init__.py` 零改动（router 已挂载，实测 plans.py:23 / reports.py:22）。

### 6.1 plans.py 四新路由（generate / current / adjust / diff）

- [ ] **要点**：
  - 四路由声明于既有 `get_plan` 之前，全部 `Depends(get_current_user)` + `success()` 包装、薄委托 services（404/1005/1007 由服务层 BizException → 全局处理器转换）：
    - `POST /generate`：请求体 `PlanGenerateIn`（空对象）→ `await plan.generate_plan(db, current_user.id)` → `success(data=...)`；异常 1003/1007/5000
    - `GET /current`：`plan.get_current_plan(db, current_user.id)` → 无计划 `success(data=None)`（200 + null 空态语义，**非 404**）；仅 1003
    - `POST /{plan_id}/adjust`：请求体 `PlanAdjustIn` + 路径 plan_id → `await plan.adjust_plan(db, current_user.id, plan_id)`；1003/1005/1007
    - `GET /{plan_id}/diff`：`plan.get_plan_diff(db, current_user.id, plan_id)`；1003/1005
  - docstring 逐端点写清周期语义（generate 恒为下一个完整自然周；adjust 无可调整项时 `adjusted=false`）
- **涉及文件**：修改 `backend/app/api/v1/plans.py`
- **完成判定**：`./.venv/Scripts/python.exe -m py_compile app/api/v1/plans.py` 通过；`grep -n "@router" app/api/v1/plans.py` 输出顺序中 `/generate` 与 `/current` 行号先于 `/{plan_id}`；`git diff app/api/v1/__init__.py` 为空
- **依赖**：组 1.1、组 4
- **决策锚点**：design 2.4.6-A、2.2.2-(1)~(4)；裁决 #8/#9

### 6.2 reports.py：generate 路由 + list_reports 改写（倒序 + 类型过滤 + 标量分页）

- [ ] **要点**：
  - `POST /generate`：请求体 `ReportGenerateIn`（`period_end > today` 已在模型 validator 拒绝 → 422/1001）→ `await report.generate_report(db, current_user.id, payload)` → `success(data=报告对象)`；1003/1001/5000
  - **`list_reports` 改写（裁决 #7 唯一计划内行为变更）**：逐字复刻 `list_goals` 标量分页写法（design 2.2.2-(6) 签名）——`page: Annotated[int, Query(ge=1)] = 1`、`page_size: Annotated[int, Query(ge=1, le=100)] = 10`、`report_type: Annotated[Literal[...] | None, Query()] = None`；**禁止混用 `PaginationParams` 查询参数模型**（契约 §5.3 实测约束：混入标量后模型不展开被误判必填致 422）；`paginate(order_by=[desc(LearningReport.created_at), desc(LearningReport.id)], filters=[user_id] + ([type] if 有))`——**created_at 倒序 + id 倒序 tie-break 保证分页稳定**；docstring 保留 list_goals 同款实现约束注释
  - 既有 `get_report` 详情端点保留不动（P3 零行为变更）
- **涉及文件**：修改 `backend/app/api/v1/reports.py`
- **完成判定**：`py_compile` 通过；R6/R7/Q4 断言由组 9.2 / 9.1 固化
- **依赖**：组 1.2、组 5
- **决策锚点**：design 2.4.6-B、2.2.2-(6)；裁决 #7；O2

**里程碑验证（组 6 结束）**：
```bash
cd backend && ./.venv/Scripts/python.exe -m py_compile app/api/v1/plans.py app/api/v1/reports.py && \
./.venv/Scripts/python.exe -c "from app.main import app; routes = [r.path for r in app.routes]; assert '/api/v1/plans/generate' in routes and '/api/v1/plans/current' in routes and '/api/v1/reports/generate' in routes; print('ROUTES_OK')" && \
git diff app/api/v1/__init__.py | wc -l   # 输出 0 = router 挂载零改动
```

---

## 7. agent 层接入（tools 4 工具 + registry 追加 + prompts 边界改写）

**写作说明**：`tools.py` 715 → ~865 行（**文件末尾纯追加**，既有 8 工具与横切私有区零触碰）；`registry.py` 274 → ~344 行（`_TOOL_SPECS` 末尾追加 4 条 + import 扩展 + docstring 更新）；`prompts.py` 仅改 `_BOUNDARY_SECTION_TEMPLATE`（58-65 行）与 `_GUIDE_SECTION`（76-85 行）——**prompts.py 是本阶段对 P11 的唯一有意变更点（裁决 #11）**。`core.py` 零改动的接入证据链：registry 追加 → TOOLS_SCHEMA 自动 12 条 → 渲染进 Prompt 自动跟进 → core.py `TOOL_MAP[name]` 动态派发（core.py:528 既有行）。

### 7.1 tools.py 追加 4 参数模型 + 4 工具实现（纯追加铁律）

- [ ] **要点**：
  - 文件末尾追加区：4 个参数模型（`extra="forbid"`，全部标量字段——`_build_parameters_schema` 无 `$defs/$ref/anyOf` 天然兼容）+ 4 个 `@tool_endpoint` 装饰实现（全 async，对齐 TOOL_MAP 类型单一）+ import 区扩展（`from app.services.plan import ...` / `from app.services.report import ...`——依赖方向 agent→services 合法）：
    - `GetLearningPlanParams`（零字段）→ `get_learning_plan(db, user_id, params)` 薄委托 `plan.get_current_plan`：有计划返回 `{plan, items}`；**无计划返回说明性 dict `{plan: null, message: "当前没有进行中的学习计划"}`——非 error 信封**（无计划是正常状态不是失败，SPEC §5.6.1-3）
    - `GenerateLearningPlanParams`（零字段）→ `generate_learning_plan` 薄委托 `plan.generate_plan`：返回 `{plan, items, unplaced_tasks, generated_by}`（与 HTTP 端点同一函数）
    - `AdjustLearningPlanParams`：`plan_id: int | None = Field(default=None, ge=1)` → `adjust_learning_plan` 薄委托 `plan.adjust_plan`：缺省当前 active；无 active 时 `{"error": "当前没有进行中的学习计划"}` 信封
    - `GenerateLearningReportParams`：`report_type: Literal["daily","weekly","monthly"] | None = None`（缺省 weekly）→ `generate_learning_report` 薄委托 `report.generate_report`：周期取最近完整周期（**LLM 不算日期**）
  - 慢日志 300ms 经 `tool_endpoint` 装饰自动继承（内嵌 LLM 必然触发，照记为规划耗时观测信号非故障，裁决 #12）
- **涉及文件**：修改 `backend/app/agent/tools.py`（末尾追加 ~150 行）
- **完成判定**：`./.venv/Scripts/python.exe -m py_compile app/agent/tools.py` 通过；`git diff app/agent/tools.py | grep "^-" | grep -v "^---" | wc -l` 输出 0（纯追加）；T1–T5 断言由组 9.3 固化
- **依赖**：组 4、组 5
- **决策锚点**：design 2.4.5-A、2.2.2-(7)；裁决 #1（工具入口）/ #12

### 7.2 registry.py 追加 4 条 ToolSpec（TOOLS_SCHEMA 8→12）

- [ ] **要点**：
  - import 区扩展（4 函数 + 4 参数模型）；`_TOOL_SPECS` **末尾追加 4 条**（顺序对齐契约 §4 清单：get_learning_plan / generate_learning_plan / adjust_learning_plan / generate_learning_report）；docstring「P12 接入」段更新为交付说明（文档性改动）
  - 每条 `description` 三要素长文案（何时调用 / 参数填法 / 返回结构），与既有 8 条风格逐字对齐；文案要点（design 2.2.2-(7)）：`generate_learning_plan` 声明「不需要任何参数，恒生成下一个完整自然周」；`adjust_learning_plan` 声明「**计划调整会生成新版本并给出具体理由（含调整到哪天、顺延了什么）**」；两个生成工具声明「生成失败时自动降级规则/模板模式，仍会返回可用结果」
  - **`TOOLS_SCHEMA` / `TOOL_MAP` 零代码改动**（列表推导自动 12 条）——工具名集合相等是构造性事实；**不新增 `get_plan_diff` 独立工具**（diff 由 adjust 返回值携带，任务书明令）
  - **D13 断言目标**：本文件改动仅「追加 4 条 ToolSpec + import + docstring」，无既有条目修改
- **涉及文件**：修改 `backend/app/agent/registry.py`（追加 ~70 行）
- **完成判定**：`./.venv/Scripts/python.exe -m py_compile app/agent/registry.py` 通过；`./.venv/Scripts/python.exe -c "from app.agent.registry import TOOLS_SCHEMA, TOOL_MAP; assert len(TOOLS_SCHEMA) == 12 and set(TOOL_MAP) == {s['function']['name'] for s in TOOLS_SCHEMA}; print('12_TOOLS_OK')"`；T0 断言（12 条与契约 §4 逐字一致）由组 9.3 固化
- **依赖**：7.1（import 4 新函数）
- **决策锚点**：design 2.4.5-B；SPEC 规则 5.6.1-1；裁决 #1/#3

### 7.3 prompts.py 边界文案改写（裁决 #11，唯一有意变更）

- [ ] **要点**：
  - `_BOUNDARY_SECTION_TEMPLATE` 由「学习计划的生成与调整、学习报告生成将在后续版本提供……」**改写为正向能力声明**：「学习计划的生成与调整、学习报告生成能力已可用（generate_learning_plan / adjust_learning_plan / generate_learning_report）」+ **两句护栏**：「计划调整会生成新版本并给出具体理由」「生成失败时自动降级为规则模式，仍返回可用结果」
  - `_GUIDE_SECTION` 追加 4 工具场景引导行：「制定下周学习计划 → generate_learning_plan；调整本周计划 → adjust_learning_plan；生成日报/周报/月报 → generate_learning_report；查看当前计划 → get_learning_plan」
  - **动态工具清单段零改动**（`_render_boundary_section` 从 `TOOLS_SCHEMA` 名集合生成，8→12 自动跟进）；**P11「不编造」底线不变**：`_FORBIDDEN_SECTION` 禁止事项段原样保留（回答中的计划与数字仍必须来自工具返回结果）
- **涉及文件**：修改 `backend/app/agent/prompts.py`（~15 行变更）
- **完成判定**：`py_compile` 通过；渲染断言（含 12 工具名 + 正向声明 + **不含「后续版本提供」**）由组 9.4 固化；`git diff app/agent/prompts.py | grep "^-" | grep -v "^---"` 仅命中 `_BOUNDARY_SECTION_TEMPLATE` 与 `_GUIDE_SECTION` 两常量区
- **依赖**：7.2（渲染时 TOOLS_SCHEMA 已 12 条）
- **决策锚点**：design 2.4.5-C；裁决 #11；SPEC 规则 5.6.1-5

**里程碑验证（组 7 结束）**：
```bash
cd backend && ./.venv/Scripts/python.exe -m py_compile app/agent/tools.py app/agent/registry.py app/agent/prompts.py && \
./.venv/Scripts/python.exe -c "from app.agent.registry import TOOLS_SCHEMA, TOOL_MAP; names = [s['function']['name'] for s in TOOLS_SCHEMA]; assert len(names) == 12 and 'generate_learning_plan' in names and 'get_plan_diff' not in names; print('REGISTRY_12_OK')" && \
git diff app/agent/core.py app/agent/memory.py app/services/llm.py | wc -l   # 输出 0 = P11/P4 冻结项零改动
```

---

## 8. 测试一/二：引擎单测（可先行）+ test_plan_generate.py + test_plan_adjust.py

**写作说明**：新增 `backend/tests/test_plan_generate.py`（~380 行，含 scheduler 引擎单测 E 组 + G1–G10）与 `backend/tests/test_plan_adjust.py`（~340 行，含 adjuster 引擎单测 E 组 + A1–A10）。用例组唯一来源：design 2.5.2 前两行。**mock 注入形态**（前置约定 2）：`monkeypatch.setattr("app.services.plan.llm.chat", fake)` 三态（成功含 ```json 围栏与裸 JSON 两种 / 解析失败含 related_task_id 编造 / 抛 BizException 或 `asyncio.sleep(60)` 配合 `PLAN_LLM_TIMEOUT_S=0.05` 加速超时）；日期断言动态计算（design 2.5.3 口径）。**8.1 仅依赖组 2/3——按 P11 经验「组完成即跑该组测试」，可在组 4 之前先行编写运行**。

### 8.1 引擎单测（E 组：scheduler + adjuster 纯函数直测，先行可测）

- [ ] **覆盖**：
  - **scheduler E 组**（`test_plan_generate.py` 内，构造 dataclass 直测不依赖 app_client）：容量边界（每日合计 ≤ 容量、恰等边界）；周五休息（仅跳过、无任务条目排入周五）；时段冲突结构性不成立（同日 start_time 无重复、end-start=estimated 恒等）；三窗口推进（首窗放不下移 14:00、再移 19:00——**OP2 锚点断言**）；单条目 > 240 进 unplaced；逾期/临期排周期前段（deadline 升序）；`next_week_window`（今天周四 → 下周一~下周日，动态日期）；`build_rule_candidates`（逾期→临期→roadmap 顺序、逾期候选带 related_task_id——**降级同构断言**）
  - **adjuster E 组**（`test_plan_adjust.py` 内）：三条件阈值边界（deadline=now+47h 命中 / +49h 不命中；时长恰 0.6 比例边界）；移动重排（后续日期空闲、优先周末）；低优先级顺延（low 先于 medium、high 不顺延）；周期全满 removed（任务保留语义在数据结构层面）；**`render_adjust_reason` 三场景文案断言——单任务移动（含任务名 + 「从周三（MM-DD）晚上调整到周六（MM-DD）下午」从→到表述 + ≥20 字符）/ 多任务移动 / 有顺延（含顺延话术）+ 无顺延不出现顺延话术**
- **涉及文件**：新增 `backend/tests/test_plan_generate.py`、`backend/tests/test_plan_adjust.py`（先落引擎单测部分）
- **完成判定**：`cd backend && ./.venv/Scripts/python.exe -m pytest tests/test_plan_generate.py tests/test_plan_adjust.py -v -k "engine or scheduler or adjuster or reason" 全绿`（引擎用例以 `test_engine_/test_scheduler_/test_adjuster_` 前缀命名保证 -k 可选）
- **依赖**：组 2、组 3（**先行点：不依赖组 4–7**）
- **验收锚点**：D1/D3 引擎侧；OP2（三窗口）；**用户指令③（reason 模板具体性）**；A6/A12

### 8.2 test_plan_generate.py 服务级用例（G1–G10，mock LLM + 真实 SQLite）

- [ ] **覆盖**：
  - **G1 结构与容量（D1）**：demo 档案（daily_study_minutes=90）+ 种子任务（1 逾期 + 1 临期）→ 生成 → 断言 7 天条目、每日合计 ≤ 90、每日 start_time 无重复、周五仅休息条目、逾期/临期排在周期前段（日期动态计算：`start_date == next_monday.isoformat()`、条目 plan_date ∈ [next_monday, next_monday+6]）
  - **G2 落库（D2，OP1 断言）**：tasks 新增行全部 `source="agent"` / `status="todo"` / `scheduled_date=plan_date`；条目 task_id 一一回填；休息条目 `task_id=null`；**同 plan 内 task_id 无重复（任务唯一性铁律断言）**
  - **G3 LLM 候选一致性**：mock 返回固定候选 → 条目 topic 与候选一致且硬约束成立（`generated_by="llm"`）
  - **G4 降级（D9 计划侧）**：fake 抛错 / 挂起（PLAN_LLM_TIMEOUT_S=0.05 加速）→ 生成成功、条目来自任务池+roadmap、`generated_by="rules"`、**落库结构与 G2 同构（仅标记差异——降级同构断言）**
  - **G5 多周并存（D7）**：本周存在 active 时生成下周 → 两版同时 active、区间不重叠、本周未被归档
  - **G6 同周期重生成 + 幽灵清理（D8）**：旧版含 2 agent-todo + 1 agent-done → 对同一下周再生成 → 第二次 active、第一次 archived；仅 2 条 todo 被删除、done 保留且任务页可见
  - **G7 容量不足可解释**：构造 10 小时候选 vs 60 分钟/天 → 生成成功、每天不超限、`unplaced_tasks` 非空且对应任务仍在 tasks 表（scheduled_date=null）
  - **G8 无档案默认 / 无目标容错**：无档案用户 → 容量按 60 约束；删除目标后生成 → 成功且 `goal_id=null`
  - **G9 部分重叠 1007**：构造与目标区间部分重叠的 active → HTTP 400 + code=1007、不自动归档
  - **G10 事务原子性（D14）**：落库步骤间 monkeypatch 抛异常 → 库中零新增（计划/条目/任务）、旧 active 未被动
- **涉及文件**：修改 `backend/tests/test_plan_generate.py`
- **完成判定**：`./.venv/Scripts/python.exe -m pytest tests/test_plan_generate.py -v` 全绿（含 8.1 引擎组）
- **依赖**：8.1（同文件）、组 1.1、组 4、组 6.1（HTTP 端点）
- **验收锚点**：D1/D2/D7/D8/D9(计划)/D14；OP1（G2 重复断言）；SPEC §8.2 步骤 2

### 8.3 test_plan_adjust.py 服务级用例（A1–A10，零 LLM 环境）

- [ ] **覆盖**：
  - **A1 版本链（D3）**：构造「任务未完成 + 截止明天」（deadline=`now + timedelta(hours=24)` 真实阈值构造）→ 调整 → 新版 `version+1` / `parent_plan_id` 指向旧版 / 旧版 `status="archived"` 且行与条目逐字段快照不变 / `adjust_reason` 非空、含移动条目 topic 与「从 → 到」日期表述、长度 ≥ 20 字符
  - **A2 diff 三要素（D4）**：调整返回的 `moved[].from_date/to_date/reason` 齐全且日期真实对应两版 `plan_date`（∈ 两版条目 plan_date 集合）；**调整随返 diff == diff 端点重算 diff（幂等一致性——同函数构造性结果）**
  - **A3 纯确定性（D10）**：全部调整用例在「LLM 完全不可用」（plan 与 report 两个 fake 均抛错）环境下跑通
  - **A4 无可调整**：全部条目 done → 调整 → 计划数量不变、`adjusted=false`、无新版本
  - **A5 done 保持（裁决 #13）**：先完成一个条目再调整 → 新版该条目仍 done 且不在 moved/removed diff 中
  - **A6 顺延**：构造「周六已满 + 周日空闲」→ 被顺延的周六 low 条目出现在周日时段（moved diff 含牺牲条目）
  - **A7 removed**：周期全满 → 低优先级条目进 removed、其任务保留在 tasks 表
  - **A8 任务同步（D2 关联，OP1 调整路径断言）**：调整后查 tasks → **被移动任务 `scheduled_date` == 新条目 `plan_date`**；removed 任务 `scheduled_date` 为空
  - **A9 越权与状态**：他人/不存在 plan_id → 404 + 1005；对 archived 版本调整 → 400 + 1007；**调整前后两版本 `start_date/end_date` 逐字段相等（周期不变）**
  - **A10 事务原子性（D14）**：版本链落库中途 mock 异常 → 无半截版本、旧 active 未被动
- **涉及文件**：修改 `backend/tests/test_plan_adjust.py`
- **完成判定**：`./.venv/Scripts/python.exe -m pytest tests/test_plan_adjust.py -v` 全绿（含 8.1 引擎组）
- **依赖**：8.1（同文件）、组 1.1、组 4、组 6.1
- **验收锚点**：D3/D4/D10/D11(部分)/D14；OP1（A8 同步断言）；SPEC §8.2 步骤 3/4

**里程碑验证（组 8 结束）**：
```bash
cd backend && ./.venv/Scripts/python.exe -m pytest tests/test_plan_generate.py tests/test_plan_adjust.py -v 2>&1 | tail -3
# 引擎先行小里程碑（组 2/3 完成后即可跑）：
cd backend && ./.venv/Scripts/python.exe -m pytest tests/test_plan_generate.py tests/test_plan_adjust.py -v -k "engine or reason" 2>&1 | tail -3
```

---

## 9. 测试三~六：查询 diff + 报告 + 工具 + prompt 断言反转

**写作说明**：新增 `backend/tests/test_plan_query_diff.py`（~150 行，Q1–Q4）、`backend/tests/test_report_generate.py`（~300 行，R1–R7）、`backend/tests/test_plan_report_tools.py`（~320 行，T0–T7）；更新 `backend/tests/test_agent_prompt.py`（断言反转，~30 行变更）。用例组唯一来源：design 2.5.2 后四行。报告 mock：`monkeypatch.setattr("app.services.report.llm.chat", fake)`；工具对话 mock：`monkeypatch.setattr("app.services.llm.agent_chat_stream", fake)`（P11 惯例，预设 `tool_calls=[{name: "generate_learning_plan", arguments: "{}"}]`）。

### 9.1 test_plan_query_diff.py（Q1–Q4，D12 查询侧）

- [ ] **覆盖**：
  - **Q1 current 语义**：存在本周 active → 返回计划头 + items（排序 plan_date 升序、同日 start_time 升序、None 最前）；删除全部计划 → 200 且 `data=null`（**非 404**）
  - **Q2 diff 无基线**：对 generate 产物调 diff → 200 + `{base_plan_id: null, moved: [], added: [], removed: []}`
  - **Q3 P3 回归**：`GET /plans` 列表（分页、id 升序、双账号隔离）与 `GET /plans/{id}` 详情（越权 404/1005）行为不变
  - **Q4 鉴权**：未携带 token 调 current / diff / generate / adjust → HTTP 401 + code=1003
- **涉及文件**：新增 `backend/tests/test_plan_query_diff.py`
- **完成判定**：`./.venv/Scripts/python.exe -m pytest tests/test_plan_query_diff.py -v` 全绿
- **依赖**：组 6.1（可与其他测试组并行）
- **验收锚点**：D12(查询侧)/D11(部分)；裁决 #8/#9

### 9.2 test_report_generate.py（R1–R7，D5/D9/D12 报告侧）

- [ ] **覆盖**：
  - **R1 真实数字（D5）**：固定周期内插入 3 条记录共 145 分钟 + 2 个 done 任务 → 生成 weekly → `content.total_minutes == 145`、`task_completed == 2` 与库中聚合精确相等；`learning_reports` 新行存在
  - **R2 周期推导（动态日期）**：今天动态计算——weekly 缺省 → `period_start == last_monday`、`period_end == last_sunday`；带 `period_end=某周三` → 该周周一~周日
  - **R3 LLM 路径**：mock 返回固定文本 → `summary == 该文本`、`generated_by == "llm"`
  - **R4 模板降级（D9 报告侧，O1）**：fake 抛错 / 挂起（REPORT_LLM_TIMEOUT_S=0.05）→ 生成成功、**summary 含统计数字（非空泛鼓励）**、`generated_by == "template"`、落库行存在、无 502/500；**降级与 R3 落库结构同构（仅 generated_by 差异）**
  - **R5 零数据容错**：空数据用户生成日报 → 200 + 落库 + 数字全 0 类值 + summary 含「暂无学习记录」类文案
  - **R6 重复生成 append（O2）**：同周期同类型连生成两次 → 两行记录、`created_at` 后者新；`GET /reports` 列表倒序第一条为第二次结果；`?report_type=weekly` 过滤仅返该类型
  - **R7 入参非法**：`report_type="foo"` / `period_end` 晚于今天 / 格式错 → 422 + code=1001
- **涉及文件**：新增 `backend/tests/test_report_generate.py`
- **完成判定**：`./.venv/Scripts/python.exe -m pytest tests/test_report_generate.py -v` 全绿
- **依赖**：组 5、组 6.2
- **验收锚点**：D5/D9(报告)/D12(reports 列表)；O1/O2；SPEC §8.2 步骤 5

### 9.3 test_plan_report_tools.py（T0–T7，D6/D11）

- [ ] **覆盖**：
  - **T0 注册（D6 核心）**：`len(TOOLS_SCHEMA) == 12` 且名称集合与契约 §4 清单逐字一致（12 名硬编码断言）；`set(TOOL_MAP) == {spec 名集合}`；4 个新工具参数 schema 无 `$defs/$ref/anyOf`；**不设 get_plan_diff 工具**（`"get_plan_diff" not in TOOL_MAP`）
  - **T1–T4 逐工具 mock 场景**：`get_learning_plan` 有计划 `{plan, items}` / 无计划 `{plan: null, message}`（**说明性 dict 非信封**）；`generate_learning_plan` 返回四键集合；`adjust_learning_plan` 缺省当前 active / 无 active `{"error": "当前没有进行中的学习计划"}`；`generate_learning_report` 缺省 weekly 返回报告对象
  - **T5 非法参数**：adjust 传 `plan_id=0` → 中文信封（含参数名与合法值）；传 user_id → 注入特例拒绝文案（P10 惯例）
  - **T6 对话集成（D6 SSE）**：mock `agent_chat_stream` 预设 `tool_calls=[generate_learning_plan]` → SSE 走 tool_call / tool_result（**大结果 `truncated=true` 且 summary ≤ 500——7 天条目必然触发**）/ done；tool 消息落库 content 为完整 JSON（P11 完整回灌机制）
  - **T7 双账号隔离（D11）**：user_a 生成计划后 user_b 经工具与 HTTP 均不可见（404/1005）；工具层 user_id 注入正确性
- **涉及文件**：新增 `backend/tests/test_plan_report_tools.py`
- **完成判定**：`./.venv/Scripts/python.exe -m pytest tests/test_plan_report_tools.py -v` 全绿
- **依赖**：组 7（7.1/7.2）；T6 依赖 P11 通道既有实现（core.py 零改动）
- **验收锚点**：D6/D11；SPEC §5.6.1-2/3/4/7、§8.2 步骤 6

### 9.4 test_agent_prompt.py 断言反转（D6/D13，裁决 #11 计划内变更）

- [ ] **覆盖**：
  - `test_prompt_capability_boundary` 由「含『后续版本提供』」**反转为**：「含 12 工具名（动态清单与 TOOLS_SCHEMA 名集合一致）+ 正向能力声明锚点短语（如『已可用』/『生成新版本并给出具体理由』/『自动降级』）+ **不含『后续版本提供』**」
  - `test_prompt_scenario_guide` 补 4 工具引导行断言（generate_learning_plan / adjust_learning_plan / generate_learning_report / get_learning_plan 各命中）
  - 既有三要素 / 禁止事项 / 身份断言**零变更**（P11 不编造底线不变——禁止事项段原样保留的回归证明）
- **涉及文件**：修改 `backend/tests/test_agent_prompt.py`
- **完成判定**：`./.venv/Scripts/python.exe -m pytest tests/test_agent_prompt.py -v` 全绿（断言更新后非兼容性破坏，是 SPEC §4.5-2 声明的行为演进）
- **依赖**：组 7.3（可与组 8 并行）
- **验收锚点**：D6/D13；裁决 #11；SPEC §4.5-2

**里程碑验证（组 9 结束）**：
```bash
cd backend && ./.venv/Scripts/python.exe -m pytest tests/test_plan_query_diff.py tests/test_report_generate.py tests/test_plan_report_tools.py tests/test_agent_prompt.py -v 2>&1 | tail -3
```

---

## 10. 全量回归与冻结项审查（D13）

**写作说明**：本组是 D13 验收落地。冻结项以 git diff 审查为硬标准；既有套件以实测基线为硬标准（pytest 153 passed / test_tools.py 76 PASS）。**回归专项必含 P5 任务模块、P9 RAG、P11 Agent Chat 三条链——prompts.py 边界文案改写是唯一有意变更点，P11 相关断言（组 9.4 已反转）必须回归通过**。

### 10.1 冻结项 git diff 审查（core/memory/llm 零改动 + registry 仅追加 4 条）

- [ ] **要点**：
  - `git diff backend/app/agent/core.py backend/app/agent/memory.py` 为空（P11 主循环零改动，SPEC §5.6.1-6）
  - `git diff backend/app/services/llm.py` 为空（P4/P9/P11 三条依赖链，30s 超时在调用方实现）
  - `git diff backend/app/agent/tools.py` 呈**纯追加**（无删除/修改行）；`git diff backend/app/agent/registry.py` 呈「追加 4 条 ToolSpec + import + docstring」——**D13 断言「仅追加 4 条」的人工审查记录**
  - `git diff backend/app/models/` 为空（零 DDL）；`git diff backend/app/analytics/advice.py backend/app/analytics/statistics.py backend/app/analytics/trend.py backend/app/analytics/weakness.py` 为空（既有 4 模块零触碰）
  - `git diff backend/app/api/v1/__init__.py` 为空；`git diff backend/app/schemas/plan.py backend/app/schemas/report.py` 呈纯追加（既有出参模型零删改）
- **涉及文件**：审查冻结清单（无代码改动）
- **完成判定**：上述各 diff 命令按预期输出（空 / 纯追加），逐项记录审查结论
- **依赖**：组 1–9（冻结项理论上全程零改动，正式收口在本组）
- **验收锚点**：D13；design 2.6 回归清单

### 10.2 scripts/test_tools.py 计划内更新（G0.1 断言 8→12）

- [ ] **要点**：
  - `scripts/test_tools.py:330-331` 的「G0.1 TOOLS_SCHEMA 恰 8 个且名称一一对应」更新为 **12 个**（expected 名称集合追加 get_learning_plan / generate_learning_plan / adjust_learning_plan / generate_learning_report）——design 1.1.3-E 唯一许可的改动点；其余 75 用例（含 4 新工具可用后的既有工具行为）零变更
  - 重跑确认输出「**N PASS / 0 FAIL**」（N = 76，新工具不新增该脚本用例——工具行为断言归 pytest T 组）
- **涉及文件**：修改 `backend/scripts/test_tools.py`（仅 G0.1 断言行 + expected 集合）
- **完成判定**：`cd backend && ./.venv/Scripts/python.exe scripts/test_tools.py 2>&1 | grep "汇总"`（或等价汇总行）输出 0 FAIL；`git diff scripts/test_tools.py` 仅命中 G0.1 相关行
- **依赖**：组 7.2
- **验收锚点**：D13；design 1.1.3-E

### 10.3 全量回归（153 基线 + 新增全绿 + P5/P9/P11 专项）

- [ ] **要点**：
  - **全量**：`pytest tests/ -q` 全绿（153 基线 + 新增五文件用例数；**零 failed、零 error**）
  - **P11 Agent Chat 专项**（prompts.py 唯一有意变更点的回归）：`pytest tests/test_agent_chat_stream.py tests/test_agent_memory.py tests/test_agent_prompt.py -q` 全绿（test_agent_prompt 断言已按组 9.4 反转）
  - **P9 RAG 专项**：`pytest tests/test_rag_qa_stream.py tests/test_rag_qa_prompt.py tests/test_rag_qa_scope.py -q` 全绿（llm.py 零改动的行为证明）
  - **P5 任务模块专项**：全量回归覆盖（tasks 相关既有用例 + 新增 G2/A8 任务落库与同步断言互证——计划生成不改任务状态、调整只同步 scheduled_date）
  - **P3 只读端点**：Q3（plans 列表/详情）+ 既有 plans/reports 测试重跑；`GET /reports` 倒序+过滤属裁决 #7 计划内行为变更（R6 断言新行为）
  - 失败分诊（前置约定 3）：区分「实现缺失」（按任务清单回补）与「环境性失败」（查 conftest IPv6/socketpair 补丁），禁止改断言迁就
- **涉及文件**：无代码改动（回归验证，操作记录可存 `backend/tmp_verify/` 惯例）
- **完成判定**：全量 + 三个专项命令全部全绿；记录最终用例总数（153 + 新增 N）
- **依赖**：组 8、组 9、10.1、10.2
- **验收锚点**：D13（全量）；design 2.6 八项逐条

**里程碑验证（组 10 结束——全链路收口）**：
```bash
cd backend && ./.venv/Scripts/python.exe -m pytest tests/ -q 2>&1 | tail -1        # 全绿（153 基线 + 新增）
cd backend && ./.venv/Scripts/python.exe scripts/test_tools.py 2>&1 | grep "汇总"  # 0 FAIL
git diff --stat backend/app/agent/core.py backend/app/agent/memory.py backend/app/services/llm.py backend/app/models/ backend/app/api/v1/__init__.py   # 输出为空
git status --short frontend/ | wc -l                                                # 输出 0 = 零前端文件
```

---

## 11. 收尾走查与本机验证交接

### 11.1 代码走查与设计一致性核对

- [ ] **要点**：
  - **分层合规**：api 新端点零业务逻辑（薄委托）；`grep "from app.api" backend/app/services/plan.py backend/app/services/report.py` 零命中；scheduler/adjuster 零 import services/models/agent（组 2.1/3.1 已静态核查，正式复核）；工具层薄委托 services（`grep -n "TOOL_MAP" backend/app/agent/tools.py` 无新增派发点——工具实现不绕过 services 直访 ORM）
  - **常量走查**：组 0 十常量核对表逐项复核（模块级定义 + 注释依据 + 仅测试可 monkeypatch + 函数体直接引用无默认参数捕获）
  - **OP1/OP2 落实复核**：三道保证代码齐备（任务池去重 / related_task_id 去重 / 落库断言兜底）；双分支落库与调整 scheduled_date 同步；DAY_SLOT_ANCHORS 三窗口值
  - **docstring 回链**：scheduler/adjuster/plan/report 注明对应 design 章节号（2.4.1/2.4.2/2.4.3/2.4.4）
  - **隐私红线**：降级日志与元数据日志仅含 user_id/plan_id/version/report_type/耗时/降级原因——禁打印 LLM prompt/响应正文与用户业务数据（spec §4.3-4）
  - **契约核对**：snake_case 全程、type hints 全覆盖、JSONType 直赋 dict（report.content 禁手动序列化）、错误码沿用既有常量无新码位、单一输出 schema（两路径同构）
  - **前端禁令**：`git status frontend/` 零改动（PlanView.vue / ReportsView.vue / plan.ts 扩展属后续阶段单独下达）
- **涉及文件**：组 1–7 全部新增/改动文件（走查，无代码改动）
- **完成判定**：七项走查全部通过；与 design「下游交接说明」无偏差（未覆盖细节按 PROJECT_CONTEXT 总则处理并记录）
- **依赖**：组 10
- **验收锚点**：design 2.8.1 铁律逐条遵循清单

### 11.2 本机（真实 LLM）验证清单交接（V1–V6，沙箱 mock 无法覆盖）

- [ ] **要点**（沙箱网络全禁，以下留给用户本机执行；前置：`.env` LLM 配置有效、后端启动；承接 spec §8.3 与 design 2.5.4 全量）：
  1. **V1 真实计划生成对话（D6 核心）**：登录 demo → `curl -N POST /api/v1/agent/chat` 问「帮我制定下周学习计划」→ 观测真实调用 `generate_learning_plan`（tool_call 事件可见）、回答含具体 7 天安排（**非「后续版本提供」**）
  2. **V2 真实调整理由质量**：留一个任务未完成且截止明天 → 对话说「帮我调整一下这周的计划」→ 观测 `adjust_learning_plan` 被调用、回答转述的调整理由具体可读（含任务名、从→到日期）
  3. **V3 规划 LLM 质量人工评审**：生成计划条目的 topic 与用户目标 roadmap 相关、时段布局合理（三窗口语义自然）
  4. **V4 真实周报**：`POST /api/v1/reports/generate {"report_type":"weekly"}` → summary 为自然语言且含真实数字；`GET /api/v1/reports` 倒序可见
  5. **V5 LLM 故障降级**：改错 `.env` LLM_BASE_URL 重启 → 生成计划/报告仍成功（`generated_by` 降级标记）→ 还原恢复
  6. **V6 diff 端到端**：调整后 `GET /api/v1/plans/{id}/diff` → moved 清单可读（前端视图属后续阶段）
  7. **V7 demo 用户端到端走查（用户指定补充）**：答辩场景闭环——「生成下周计划 → 人为留一个任务未完成且截止明天 → Agent 调整并给出具体理由与 diff → 周报含真实数字」四步演示路径逐项核对
- **涉及文件**：无新增（操作验证，记录建议存 `backend/tmp_verify/`）
- **完成判定**：V1–V7 逐条核对通过（spec §8.3 全量承接 + demo 走查）
- **依赖**：组 10、11.1
- **验收锚点**：spec §8.3 V1–V6；D6 真实侧；SPEC §3.1 演示评审者场景

**里程碑验证（组 11 结束——全阶段收口）**：
```bash
git status --short frontend/ | wc -l     # 输出 0 = 前端禁令确认
git diff --stat | tail -8                 # 变更范围核对：4 新增后端模块 + 6 扩展文件 + 5 新增测试 + 2 测试更新 + 文档（+ 本 tasks.md）
```

---

## 附：任务 → 验收覆盖对照（D1–D14）

| 验收项 | 判定标准摘要（spec §8.1） | 覆盖任务 |
|---|---|---|
| D1 计划生成结构与容量 | 7 天条目 / 每日合计 ≤ 容量 / 逾期临期前段 / 周五休息 | 2.2/2.3（引擎）、8.1（E 组）、8.2（G1）；11.2 V3 |
| D2 计划落库为 agent 任务 | source=agent / status=todo / scheduled_date=plan_date / task_id 回填 / 休息条目 null | 4.2（OP1 双分支）、8.2（G2 含 task_id 无重复） |
| D3 动态调整版本链 | version+1 / parent 指向旧版 / 旧版零修改 / adjust_reason 具体且 ≥20 字符 | 3.3（模板）、4.3、8.1（reason 三场景）、8.3（A1）；11.2 V2 |
| D4 diff 结构化改动清单 | moved 三要素齐全且真实对应两版 plan_date / 幂等重算 | 3.2（diff 函数与端点共用）、8.3（A2）；11.2 V6 |
| D5 周报真实数字落库 | content 数字与库中聚合精确相等 | 5.1（七要素本地聚合）、9.2（R1）；11.2 V4 |
| D6 12 工具注册与真实调用 | TOOLS_SCHEMA==12 逐字一致 / Prompt 正向声明 / 对话 tool_call→done | 7.1/7.2/7.3、9.3（T0/T6）、9.4；11.2 V1 |
| D7 多周并存 | 两版同时 active、区间不重叠 | 4.2（同周期判定）、8.2（G5） |
| D8 同周期重生成 + 幽灵清理 | 第二次 active / agent-todo 删除、done 保留 | 4.2（幽灵清理）、8.2（G6） |
| D9 LLM 降级可用性 | generated_by=rules/template、产物落库、无 502 | 2.2（降级候选同构）、4.1/5.2（降级分支）、8.2（G4）、9.2（R4）；11.2 V5 |
| D10 调整纯确定性 | LLM 全不可用下全绿 / 无可调整 adjusted=false | 4.3（零 LLM）、8.3（A3/A4） |
| D11 鉴权与隔离 | 401/1003 / 双账号 404/1005 / user_id 服务端注入 | 6.1/6.2、8.3（A9）、9.1（Q4）、9.3（T5/T7） |
| D12 查询端点行为 | current 空态 200+null / diff 无基线空结构 / reports 倒序+过滤 / P3 回归 | 4.4、6.2、9.1（Q1–Q3）、9.2（R6） |
| D13 兼容性回归 | 全量绿 / core+memory+llm diff 空 / registry 仅追加 4 条 | 9.4（断言反转）、10.1/10.2/10.3 |
| D14 事务原子性 | 中途异常零残留、旧 active 未动 | 4.2/4.3（单 commit 编排）、8.2（G10）、8.3（A10） |

| 用户特别强调落实点 | 覆盖任务 |
|---|---|
| OP1 双分支落库 + 任务唯一性铁律（三道保证）+ 调整 scheduled_date 同步 | 4.1（第一道：任务池天然去重）、4.1（第二道：related_task_id 去重）、4.2（第三道：落库断言兜底 + 双分支）、4.3（同步义务）、8.2 G2（无重复断言）、8.3 A8（同步断言） |
| OP2 三窗口锚点 09:00/14:00/19:00 | 2.1（常量表）、2.3（窗口推进）、8.1（E 组锚点断言） |
| adjust_reason 具体任务名与时段（≥20 字符、含从→到日期） | 3.3（模板 + 中文转换）、8.1（三场景文案断言）、8.3 A1 |
| 降级路径与正常路径同构（generated_by 仅标记差异） | 2.2（候选同构 A8）、4.1/5.2（降级分支）、8.2 G4、9.2 R4（同构断言） |
| TOOLS_SCHEMA 8→12、D13「仅追加 4 条」 | 7.2（追加）、9.3 T0（12 断言）、10.1（diff 审查）、10.2（test_tools 8→12 计划内更新） |

| spec 需求条目 | 覆盖任务 |
|---|---|
| §5.1 计划生成（周期/版本快照/多周并存/混合模式/硬约束/任务落库/幽灵清理/容量可解释/容错） | 2.1–2.4、4.1、4.2、6.1、8.2 |
| §5.2 动态调整（评估/不可原地修改/reason/done 保持/移动顺延/周期不变/纯确定性/无可调整/diff 随返/任务同步） | 3.1–3.3、4.3、8.3 |
| §5.3 计划查询与 diff | 4.4、6.1、9.1 |
| §5.4 报告生成（周期推导/本地统计/LLM 总结/模板降级/真实数字/append/零数据） | 5.1、5.2、6.2、9.2 |
| §5.5 报告查询（倒序/过滤/详情兼容） | 6.2、9.2（R6）、9.1（Q3） |
| §5.6 Agent 工具接入（12 工具/签名信封/参数最小化/返回结构/Prompt 边界/主循环零改动/SSE 截断） | 7.1、7.2、7.3、9.3、9.4、10.1 |
| §4 DFX（30s 超时/35s 上限/降级不失败/落库原子性/版本不可变/鉴权/常量锁定/单一事实来源） | 组 0 常量表、4.1/4.2/5.2、10.1、11.1 |
| §6 数据约束（入参/落库逻辑约束四表） | 1.1、1.2、4.2、4.3、5.2 |
| 13 项冲突裁决 + O1–O4 + OP1/OP2 | 全部任务（组 0 前置约定 + 各任务决策锚点） |

> **沙箱可完成 vs 留本机总结**：组 1–11.1 全部任务沙箱内可完成（pytest mock LLM + ASGI 直调 + 临时 SQLite，沿用 P4/P9/P11 惯例）；**留本机项**仅 11.2 的 V1–V7（真实 LLM 冒烟、故障降级实测、diff 端到端、demo 用户答辩场景走查）。