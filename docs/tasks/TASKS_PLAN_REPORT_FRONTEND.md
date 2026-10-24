# 学习计划周视图与成长报告前端（plan_report_frontend）编码任务规划

> feature: `plan_report_frontend` ｜ 阶段：编码任务规划（spec-task-agent 产出）
> 上游输入：`docs/specs/SPEC_PLAN_REPORT_FRONTEND.md`（633 行定稿：6 项关键裁定 + 70 条验收条件 + 7 章节数据约束 + 附录 B 出入点澄清；已勘误——报告域 generated_by 为 `'llm'|'template'`，计划域为 `'llm'|'rules'`）、`docs/designs/DESIGN_PLAN_REPORT_FRONTEND.md`（959 行定稿：会话态状态机 A/B/C/D + 接口清单 7 函数 + 决策 D1–D15 + 2.7 验收映射 + 2.8 风险 R1–R9 + 2.9 文件清单 16 项）、`docs/PROJECT_CONTEXT.md`（唯一技术契约：§5 响应体/错误码、§7 前端约定、§8 编码规范）
> 生成日期：2026-10-24 ｜ 状态：已实施（组 1–8 完成；W1–W12 自动化走查通过，W13 可选未跑）
> 落盘路径说明：沿用对偶惯例——`SPEC_` ↔ `DESIGN_` ↔ `TASKS_`、`specs/` ↔ `designs/` ↔ `tasks/`（同 `docs/tasks/TASKS_DYNAMIC_PLAN_REPORTS.md`），本文件落 `docs/tasks/TASKS_PLAN_REPORT_FRONTEND.md`
> 已裁决事项继承（不再重开）：spec 附录 A 6 项裁定（#1 会话态混合加载 + 调整后服务端取数 / #2 「查看调整后的计划」= 展示层零请求切换、无放弃类按钮 / #3 生成按钮与空态文案如实写「下一周」/ #4 三时段行映射与休息条目独立区块 / #5 unplaced_tasks 独立提示卡 / #6 导出文件命名与 Markdown 结构）+ design 决策 D1–D15；本清单不重开任何设计决策
>
> **编号读法**：本文「决策 D1–D15」指 design 2.6 决策表；「验收 §x.x-x」指 spec 各章验收条件（§5 章为字母编号 a/b/c/d 条目）；「裁定 #1–#6」指 spec 附录 A；「R1–R9」指 design 2.8 风险表；「W1–W13」指本文 8.3 本机走查清单项。

---

## 0. 任务总览与依赖关系

**分组结构**（8 组，共 22 个子任务；实现顺序即依赖链：types → api / utils（并行）→ components（两域并行）→ views 编排（两页并行）→ 收尾走查）：

```
组1 types 域类型（1.1 plan / 1.2 report，互相并行）
   ├─→ 组2 api 层封装（2.1 plan 5 函数 / 2.2 report 2 函数，互相并行）──────┐
   └─→ 组3 utils 纯函数（3.1 plan / 3.2 report，互相并行；与组2零文件交集）─┤
              ├─→ 组4 components/plan 六件（4.1/4.3/4.4 并行；4.2 → 4.5；4.6 独立）─┐
              └─→ 组5 components/report/ReportCard（5.1；与组4并行）────────────────┤
   组2 + 组3 + 组4 ──→ 组6 views/PlanView.vue 状态机编排（6.1→6.2→6.3→6.4 串行）─────┤
   组2 + 组3 + 组5 ──→ 组7 views/ReportsView.vue 三 tab 编排（7.1→7.2；与组6并行）───┤
                                                                                     ↓
              组8 收尾走查（8.1 沙箱门禁与静态检查 → 8.2 设计一致性核对 → 8.3 本机走查交接）
```

**关键路径**：1.1 → 3.1 → 4.2 → 4.5 → 6.1 → 6.3 → 6.4 → 8.1 → 8.3。

**可并行标注**：
- 1.1 与 1.2 零文件交集，可完全并行
- 组 2 与组 3 在组 1 完成后可完全并行（api 只 import request + types；utils 只 import types）
- 组 4（components/plan）与组 5（components/report）零文件交集，可并行；组 4 内部 4.1/4.3/4.4 相互独立可并行，4.5 依赖 4.2（WeekGrid compact 形态复用）
- 组 6（PlanView）与组 7（ReportsView）零文件交集，可并行
- 8.1 的静态检查项可在任意里程碑先跑，正式收口在组 8

**实现前置约定**（全文适用，各任务不再重复）：
1. **沙箱门禁**：全部编码任务以 `cd frontend && npm run build`（= `vue-tsc --noEmit && vite build`，含类型检查）exit 0 为唯一沙箱构建判据；沙箱无后端联调环境（R1），交互类验收（请求序列 / 按钮锁 / 零请求切换 / tab 缓存 / 导出文件名 / 取数失败错误态）一律不在各任务内判定的「沙箱判据」中虚报，统一移交 8.3 本机走查（W1–W13）
2. **分层铁律**（design 2.1.2）：子组件禁止 `import '@/api/*'`、禁止出现 axios / 裸 fetch，全部请求收口在视图层；utils 层全为无副作用纯函数 + 只读常量，`downloadReportMarkdown` 是唯一副作用点（DOM a 元素 + URL 释放，单列函数隔离）；types 层零依赖
3. **catch 静默回滚**（design 1.2.1）：失败提示由既有 `request.ts` 拦截器统一 ElMessage（本批零改动），视图层 catch 只做状态回滚（解除 loading / 置错误态），禁止重复弹错；`GET /plans/current` 返回 `data=null` 是正常空态分支，**不得**走 catch
4. **复用约定**：`todayLocalStr` / `formatMinutes` 直接复用 `frontend/src/utils/record.ts`（禁 toISOString 的时区教训，决策 D10）；分页类型复用 `types/index.ts` 的 `PageResult<T>`（零改动）；UI 用 Element Plus 存量组件 + `--el-color-*` 主题变量，不硬编码色值
5. **报告域字面量铁律**（决策 D11，spec §6.7-8 勘误后口径）：报告域五路径——`frontend/src/types/report.ts`、`frontend/src/api/report.ts`、`frontend/src/utils/report.ts`、`frontend/src/components/report/`、`frontend/src/views/ReportsView.vue`——任何文件不得出现 `'rules'` 字面量；`generatedByLabel` 只映射 `'llm'`→「LLM 总结」、`'template'`→「规则模板」，其他/缺失 → `null`（不显示徽章）。`'rules'` 仅合法存在于计划域（`types/plan.ts` 的 `PlanGenerateResult.generated_by: 'llm' | 'rules'` 与 PlanView 降级判定）
6. **文案与命名**：用户可见文案全部简体中文（spec §4.4-4）；组件 PascalCase、函数 camelCase、常量 UPPER_SNAKE_CASE；全部新组件 `<script setup lang="ts">`；每个新文件首行注释回链 spec / design 章节号
7. **请求顺序事实**（走查基准，spec §5.3.1 规则 4）：调整流程 = `POST /plans/{id}/adjust` →（可选）`GET /plans/current` →（必要时）1..N 次 `GET /learning-plan-items`（page_size=100，MAX_PAGES=50 硬上限）；**全程不出现** `GET /plans/{id}/diff`（该端点仅供 5.4 回看路径）
8. **时间显示口径**：后端 time 字段 JSON 序列化为 `HH:MM:SS`（Pydantic 实测）；所有用户可见时间经 `utils/plan.ts#formatHm` 截取 `HH:MM`，禁止直接渲染原始值

**明确不改动清单（冻结项，防越界——design 2.9 零改动确认 + 用户非目标指令写死）**：

| 文件/范围 | 不改动理由 | 验证方式 |
|------|-----------|---------|
| `backend/` 全部 | 后端 P12 已冻结验收（206 passed），本批纯前端消费（spec §1.4-5、§4.5-1） | 8.1 `git status --short backend/` 输出为空 |
| `frontend/package.json` | 零新增 npm 依赖（spec §4.5-2）；导出用原生 Blob | 8.1 `git diff frontend/package.json` 为空 |
| `frontend/src/api/request.ts` | 拦截器契约 100% 复用（design 1.2.1） | 8.1 diff 为空 |
| `frontend/src/router/index.ts` | `/plans`、`/reports` 路由骨架已注册（design 1.1.1） | 8.1 diff 为空 |
| `frontend/src/stores/**` | 不引入 Pinia（决策 D12；会话态生命周期=页面正是期望语义） | 8.1 diff 为空 + 8.2 走查 |
| `frontend/src/types/index.ts` | `PageResult<T>` 直接复用；域类型落独立文件（决策 D1） | 8.1 diff 为空 |
| `frontend/src/components/PagePlaceholder.vue` | 其余骨架页继续使用，不删除不修改（design 1.2.4） | 8.1 diff 为空 |
| **不封装的端点** | `GET /plans` 列表、`GET /plans/{id}` 详情（附录 B #3：本批无消费场景）、`GET /reports/{id}`（列表出参已含全部字段） | 8.1 核对 api 导出函数清单恰为 5+2 |
| **不实现的能力** | 报告图表 / ECharts（spec §1.4-3，留后续批次）；历史版本双栏浏览（spec §1.4-2，回看为降级形态仅理由+清单）；计划条目编辑/新增/删除（spec §1.4-1）；报告删除/编辑（spec §1.4-3）；Dashboard 摘要卡接入（spec §1.4-6）；任何后端新接口（spec §1.4-5）；确认/提交/回滚类接口诉求（裁定 #2） | 8.2 走查逐项核对 |

> **范围铁律重申**：本批只改 `frontend/` 与 `docs/`——2 个视图文件替换骨架（PlanView.vue / ReportsView.vue）+ 14 个新增文件（types 2 + api 2 + utils 2 + components 7 + 本文档 1）；零新增依赖、零后端改动、零 Pinia、零路由改动。

---

## 1. types 域类型定义（全部任务的数据契约前置）

**写作说明**：新增 `frontend/src/types/plan.ts`（~180 行）与 `frontend/src/types/report.ts`（~120 行）两个独立域文件（决策 D1，对齐 `types/agent.ts` 先例），不追加 `types/index.ts`。传输层字段与后端 Pydantic 出参**逐字段 snake_case 对齐**（不做大小写转换）；视图层类型同文件分节（双层惯例）。类型层级唯一来源：design 2.3.2。

### 1.1 types/plan.ts：计划域传输层 + 视图层类型

- [x] **要点**：
  - 传输层（对齐 design 2.3.2 类图逐字段）：`Plan`（含 `user_id` 保留定义——与后端字段集严格一致是防漂移契约的一部分）、`PlanItem`、`UnplacedTask`、`PlanCurrent`、`PlanGenerateResult`、`PlanAdjustResult`、`PlanDiff`、`DiffEntryMoved` / `DiffEntryAdded` / `DiffEntryRemoved`
  - **计划域字面量锁定**：`PlanGenerateResult.generated_by: 'llm' | 'rules'`（计划域合法字面量，与报告域 `'template'` 不得混用——spec §6.4-4）
  - 视图层：`WeekSlot`（`'morning' | 'afternoon' | 'evening' | 'rest'`）、`WeekGridColumn`、`ItemHighlight`、`SessionPlan`（`{plan, items, origin: 'current'|'generate'|'adjust'}`）、`PendingNewPlan`（diff 预览持有：新 plan + 取回 items + diff + oldItems + adjustReason）
- **涉及文件**：新增 `frontend/src/types/plan.ts`
- **完成判定**：`cd frontend && npm run build` 通过（vue-tsc）；`grep -n "generated_by" frontend/src/types/plan.ts` 命中且为 `'llm' | 'rules'` 字面量联合；`grep -n "from "@/ frontend/src/types/plan.ts` 零命中（types 层零依赖）
- **依赖**：无
- **决策锚点**：design 2.3.2 / D1；spec §6.1 / §6.2 / §6.3 / §6.4 / §6.5；验收 §4.4-2

### 1.2 types/report.ts：报告域传输层 + 视图层类型（报告域字面量铁律落点①）

- [x] **要点**：
  - 传输层：`Report`、`ReportContent`（**全字段可选**——存量报告部分字段缺失的容错在类型上即 optional，spec §5.5.1 规则 6；`content: ReportContent | null`，JSONType 读出语义 null ≠ 空对象）、`ReportWeakPoint`、`ReportProgress`（`avg_mastery_diff: number | null`）、`ReportType`（`'daily' | 'weekly' | 'monthly'`）、`ReportListQuery`、`ReportGeneratePayload`（**仅 `{report_type}`**，无 period_end——spec §1.4-4）
  - **报告域字面量锁定（铁律，决策 D11）**：`ReportContent.generated_by: 'llm' | 'template' | null`——**不得**出现 `'rules'`；`'rules'` 是计划域 generate 的降级标记，与报告域无关
  - 视图层：`ReportTypeLabel` 映射常量类型（`Record<ReportType, string>` 的键约束）
- **涉及文件**：新增 `frontend/src/types/report.ts`
- **完成判定**：`npm run build` 通过；`grep -nE "\"rules\"|'rules'" frontend/src/types/report.ts` 零命中；`grep -n "'template'" frontend/src/types/report.ts` 命中；`grep -n "period_end" frontend/src/types/report.ts` 仅允许命中 `Report.period_end` 出参字段（`ReportGeneratePayload` 中不得出现）
- **依赖**：无（与 1.1 并行）
- **决策锚点**：design 2.3.1-4 / 2.3.2 / D1 / D11；spec §6.6 / §6.7；验收 §4.4-2

**里程碑验证（组 1 结束）**：
```bash
cd frontend && npm run build && \
grep -c "export" src/types/plan.ts src/types/report.ts && \
grep -nE "\"rules\"|'rules'" src/types/report.ts | wc -l   # 输出 0 = 报告域无 rules 字面量
```

---

## 2. api 层封装（HTTP 契约的 TS 投影，单请求粒度）

**写作说明**：新增 `frontend/src/api/plan.ts`（~90 行，5 函数）与 `frontend/src/api/report.ts`（~60 行，2 函数）。惯例对齐 `api/record.ts`：`fetchXxx / createXxx` 函数式封装、返回 `Promise<T>`、`as unknown as Promise<T>` 解包断言只落在本层。函数总表唯一来源：design 2.2.1。**多请求编排（翻页循环、current 命中判定）不在本层**——决策 D7：api 层保持单请求粒度，编排收口在视图层（组 6）。

### 2.1 api/plan.ts：计划域 5 函数

- [x] **要点**：
  - 逐字对齐 design 2.2.2 签名（1）–（5）：`fetchCurrentPlan(): Promise<PlanCurrent | null>`（null 是正常空态非错误）；`generatePlan(): Promise<PlanGenerateResult>`（POST 零字段体 `{}`）；`adjustPlan(planId: number): Promise<PlanAdjustResult>`（POST 零字段体 `{}`）；`fetchPlanDiff(planId: number): Promise<PlanDiff>`；`fetchLearningPlanItems(page: number, pageSize: number): Promise<PageResult<PlanItem>>`（`PageResult<T>` 复用 `types/index.ts`）
  - **明确不封装**（防画蛇添足，design 2.2.1 变更策略）：`GET /plans` 列表、`GET /plans/{id}` 详情——版本信息经 current / generate / adjust 响应的 plan 对象已可得（spec 附录 B #3）
  - 每个函数 docstring 注明端点、空态/异常语义与回链 spec 章节
- **涉及文件**：新增 `frontend/src/api/plan.ts`
- **完成判定**：`npm run build` 通过；`grep -c "^export" frontend/src/api/plan.ts` 输出 5（恰 5 个导出函数）；人工核对函数清单无列表/详情封装；`grep -n "axios\|fetch(" frontend/src/api/plan.ts` 零命中（统一经 `request.ts`）
- **依赖**：组 1
- **决策锚点**：design 2.2.1 / 2.2.2-(1)~(5)；spec §1.2 / §4.4-1 / 附录 B #1 #3

### 2.2 api/report.ts：报告域 2 函数

- [x] **要点**：
  - `fetchReports(query: ReportListQuery): Promise<PageResult<Report>>`（GET `/reports?report_type&page&page_size`，page 从 1 起）；`generateReport(payload: ReportGeneratePayload): Promise<Report>`（POST 请求体**仅 `{report_type}`**，不传 period_end——恒用后端缺省最近完整周期，spec §5.6.1 规则 1）
  - **不封装** `GET /reports/{id}` 详情（列表出参 ReportOut 已含全部字段，无详情页场景）
- **涉及文件**：新增 `frontend/src/api/report.ts`
- **完成判定**：`npm run build` 通过；`grep -c "^export" frontend/src/api/report.ts` 输出 2；`grep -n "period_end" frontend/src/api/report.ts` 零命中（生成入参不含 period_end）
- **依赖**：组 1（与 2.1 并行）
- **决策锚点**：design 2.2.1 / 2.2.2-(6)(7)；spec §5.5.1 规则 2 / §5.6.1 规则 1 / §1.4-4 / 附录 B #2

**里程碑验证（组 2 结束）**：
```bash
cd frontend && npm run build && \
grep -c "^export" src/api/plan.ts src/api/report.ts   # 输出 5 与 2
```

---

## 3. utils 纯函数层（网格 / 时段 / 高亮 / Markdown，零副作用）

**写作说明**：新增 `frontend/src/utils/plan.ts`（~170 行）与 `frontend/src/utils/report.ts`（~200 行）。全部无副作用纯函数 + 只读常量（`downloadReportMarkdown` 为唯一副作用点，单列隔离）；只 import types（+ `utils/record.ts` 复用项）。签名与关键分支唯一来源：design 2.2.2-(9)(10)。

### 3.1 utils/plan.ts：周网格构建 / 时段归属 / diff 高亮匹配

- [x] **要点**：
  - `WEEK_SLOTS` 只读常量（`['上午','下午','晚上']` 渲染序）；三窗口边界常量集中本文件单点维护（R8：上午 [09:00,14:00) / 下午 [14:00,19:00) / 晚上 [19:00,23:00)，与 spec 裁定 #4 对齐）
  - `buildWeekColumns(plan: Plan): WeekColumnMeta[]`：由 `plan.start_date` 推导 7 列 `{date, label}`（label 形如「周一 10-26」），逐列 +1 天；原生 Date 组件拼接，**禁 toISOString**（D10）
  - `slotOfItem(item: PlanItem): WeekSlot`（决策 D5）：`start_time=null` → `'rest'`；`'HH:MM'` 字符串字典序比较（ISO 短格式字典序=时间序）左闭右开三分支；早于 09:00 就近归 morning、≥23:00 就近归 evening，并 `console.warn`（防御性容错，spec §5.1.1 规则 3）
  - `buildWeekGrid(plan, items): WeekGridColumn[]`：rests 分区（休息条目不占三时段行）；`plan_date` 越界（不在 start~end）条目剔除 + `console.warn`（spec §5.1.3-3）；同时段内保持传入顺序（后端已排好，前端不重排）
  - `markDiffHighlights(items, diff, side: 'old'|'new'): Map<number, ItemHighlight>`（决策 D6）：业务键匹配——moved 左栏 `(task_id, from_date, from_time)` / 右栏 `(task_id, to_date, to_time)`；added 右栏 `(task_id, plan_date, start_time)`；removed 左栏 `(task_id, from_date)`；`task_id` 为 null 时降级 `topic + 位置` 键；时间字段 null 与字符串宽松相等比较；**匹配不上一律不渲染高亮、不报错**（防御性降级，R4）；多条 diff 命中同一条目按 moved > added > removed 取一
  - **红线注释**：diff 只用于高亮与清单，**严禁**作为新版本条目的数据来源（spec §5.3.1 规则 4-⑤）
- **涉及文件**：新增 `frontend/src/utils/plan.ts`
- **完成判定**：`npm run build` 通过；`grep -nE "axios|fetch\(|@/api" frontend/src/utils/plan.ts` 零命中（纯函数静态核查）；`grep -n "toISOString" frontend/src/utils/plan.ts` 零命中；`grep -n "formatHm" frontend/src/utils/plan.ts` 命中（前置约定 8 时间显示口径）；时段边界断言由 8.3-W1 走查覆盖（19:00→晚上行、14:00→下午行）
- **依赖**：组 1
- **决策锚点**：design 2.2.2-(9) / 2.4.3 / D4 / D5 / D6；spec §5.1.1 规则 2/3/4、§5.1.3-3、§5.3.1 规则 3

### 3.2 utils/report.ts：文案映射 / Markdown 拼装与下载（报告域字面量铁律落点②）

- [x] **要点**：
  - `REPORT_TYPE_LABELS: Record<ReportType, string>`（daily→日报 / weekly→周报 / monthly→月报）
  - `generatedByLabel(v: string | undefined | null): string | null`（决策 D11）：**只映射** `'llm'`→「LLM 总结」、`'template'`→「规则模板」；其他值/缺失 → `null`（不显示徽章）。**本函数及本文件任何位置不得出现 `'rules'` 字面量**——报告域降级标记是 `'template'`，计划域 `'rules'` 与本文件无关
  - `buildReportFilename(report)` 独立导出（便于走查复核）：`学习{类型中文名}_{period_start}_{period_end}.md`（裁定 #6，示例 `学习周报_2026-10-12_2026-10-18.md`）
  - `buildReportMarkdown(report): string`（spec §5.6.1 规则 5 固定结构）：一级标题含区间 → 引言块（区间重申 + `formatCreatedAtLocal` 生成时间）→ `## 摘要`（summary 空则整节省略）→ 七要素七节（每节空值落空态文案：`top_direction` 空→「本期暂无」、weak_points 空→「本期无明显薄弱知识点」、progress 的 `avg_mastery_diff` 为 null 省略该行、正负号保留）→ `## 建议` 有序列表 → `---` + 「生成方式：LLM 总结 / 规则模板」（generated_by 缺省整行省略）；**禁止拼出「undefined/null」字样**；content=null 时仅含标题/引言/摘要（若有）/结尾，不报错（spec §5.6.3-2）
  - `downloadReportMarkdown(report): void`：`new Blob([md], {type:'text/markdown;charset=utf-8'})` → `URL.createObjectURL` → 临时 `<a download>` click → remove → `revokeObjectURL`（同一宏任务内完成释放，禁止 URL 滞留，spec §5.6.1 规则 6）
  - `formatCreatedAtLocal(iso): string`：`'YYYY-MM-DD HH:mm'` 本地格式，原生 Date 组件拼接（禁 toISOString）
  - 复用 `utils/record.ts` 的 `formatMinutes`（时长换算），不重写
- **涉及文件**：新增 `frontend/src/utils/report.ts`
- **完成判定**：`npm run build` 通过；`grep -nE "\"rules\"|'rules'" frontend/src/utils/report.ts` 零命中（铁律静态核查）；`grep -n "'template'" frontend/src/utils/report.ts` 命中；`grep -n "toISOString" frontend/src/utils/report.ts` 零命中；`grep -n "revokeObjectURL" frontend/src/utils/report.ts` 命中；`grep -n "学习" frontend/src/utils/report.ts` 命中文件名模板
- **依赖**：组 1（与 3.1 并行）
- **决策锚点**：design 2.2.2-(10) / 2.4.6 / D10 / D11；spec §5.5.1 规则 7、§5.6.1 规则 4/5/6、§5.6.3-2/3、§4.3-2

**里程碑验证（组 3 结束）**：
```bash
cd frontend && npm run build && \
grep -nE "axios|fetch\(|@/api" src/utils/plan.ts src/utils/report.ts | wc -l   # 输出 0 = 纯函数零 IO
```

---

## 4. components/plan 六件（纯展示子组件，零请求）

**写作说明**：新增 `frontend/src/components/plan/` 目录共 6 件。契约范式对齐 `components/task/TaskStatsCards.vue`（design 1.2.3）：泛型字面量 props、数据可 null 容错、纯展示零请求、动作向上 emit、文案全中文、Element Plus 主题变量。**WeekGrid 是唯一被复用的网格组件**（决策 D13：主视图 + diff 双栏 compact 双形态），4.5 依赖 4.2 先行落地。

### 4.1 PlanInfoHeader.vue：计划信息头

- [x] **要点**：
  - 契约（design 2.4.4）：`Props: plan: Plan | null; isNextWeek: boolean; degraded: boolean`；`Emits: view-history`
  - 渲染：标题 + 周期文本「{start_date} ~ {end_date}」+ `v{version}` 徽章 + 生成方式徽章（`degraded=true` → 「规则降级」warning 色系；否则「LLM 规划」info 色系）+ `isNextWeek=true` → 「下周计划」tag（primary）+ `plan.parent_plan_id ≠ null` → 文字按钮「查看调整记录」（首版 null 不渲染入口，spec §5.4.1 规则 1）
- **涉及文件**：新增 `frontend/src/components/plan/PlanInfoHeader.vue`
- **完成判定**：`npm run build` 通过；`grep -nE "axios|fetch\(|@/api" frontend/src/components/plan/PlanInfoHeader.vue` 零命中；「规则降级」「LLM 规划」「下周计划」「查看调整记录」四处文案 grep 命中
- **依赖**：组 1
- **决策锚点**：design 2.4.4 / D3；spec §5.1.1 规则 7a/7b、§5.2.1 规则 3a/3b、§5.4.1 规则 1a/1b

### 4.2 WeekGrid.vue：周视图网格（主视图 + compact 双形态）

- [x] **要点**：
  - 契约（design 2.4.2）：`Props: plan: Plan; items: PlanItem[]; compact?: boolean = false; highlights?: Map<number, ItemHighlight>`；**Emits: 无**（纯展示，禁止任何点击编辑/拖拽改期入口，spec §5.1.1 规则 9）
  - 骨架（决策 D4）：原生 CSS grid（`grid-template-columns: 72px repeat(7, minmax(120px, 1fr))`，首列时段行头「上午/下午/晚上」），**不用 el-table**；外层容器 `overflow-x: auto` 窄屏兜底（R5）
  - 三时段行 × 7 列 = 21 格（`buildWeekGrid` 产出），每格纵向堆叠条目卡片；第四行为每列独立「休息」区块（有 rest 条目的列显示灰底「休息」标记，无 rest 列空白占位维持列对齐）
  - 条目卡片四类信息（spec §5.1.1 规则 5）：topic 主文案 + `start_time ~ end_time`（rest 条目不显示时间）+ `estimated_minutes`（null 不渲染该行）+ `task_id` 非空时「关联任务」el-tag
  - 状态标注（规则 6，**仅依据条目自身 status 字段**，禁止按 task_id 反查任务状态）：`planned` → 左侧 3px `--el-color-warning` 色条；`done` → 文本灰显 + 对勾 icon；`skipped` → 删除线 + 灰显
  - compact 模式：仅 topic + 时间，隐藏色条/关联标识/时长行，缩小内边距字号（diff 双栏缩略复用）；highlights 模式：附加 `is-highlight-moved/added/removed` class + 角标文案（moved 左栏「移出」/ 右栏「移入」、added「新增」、removed「移除」）
  - **compact 状态视觉关闭**：done / skipped 的透明度与删除线在 compact 下同样关闭，但 moved/added/removed 的 highlights 边框必须保留（`border-left-color: transparent` 仅作用于无高亮类卡片）
  - **高亮下标映射约束**：`markDiffHighlights` 返回 `Map<数组索引, ItemHighlight>`（design 2.4.3），而 `buildWeekGrid` 分组后丢失原始下标——渲染前必须自行建立 `const indexOf = new Map(items.map((it, i) => [it, i]))`（buildWeekGrid 保留同一对象引用），取 `highlights?.get(indexOf.get(item)!)`；**禁止**把 `item.id` 当 key 查 highlights
  - **时间渲染口径**：条目卡片 `start_time ~ end_time` 必须经 `formatHm` 截取 `HH:MM`（前置约定 8）；rest 条目不显示时间
- **涉及文件**：新增 `frontend/src/components/plan/WeekGrid.vue`
- **完成判定**：`npm run build` 通过；`grep -nE "axios|fetch\(|@/api|emit" frontend/src/components/plan/WeekGrid.vue` 零命中（纯展示零交互出口）；`grep -n "task_id" frontend/src/components/plan/WeekGrid.vue` 命中处仅为「关联任务」标识渲染（无按 task_id 的请求逻辑）；`grep -n "formatHm" frontend/src/components/plan/WeekGrid.vue` 命中（前置约定 8）；时段归属与休息区块由 8.3-W1/W2 走查覆盖
- **依赖**：组 1、3.1
- **决策锚点**：design 2.4.2 / D4 / D13；spec §5.1.1 规则 2a/3a/3b/4a/5a/6a/6b/9a、§5.1.3-3

### 4.3 UnplacedTasksCard.vue：未排入任务提示卡

- [x] **要点**：
  - 契约（design 2.4.4）：`Props: tasks: UnplacedTask[]`；无 emits
  - 渲染（裁定 #5）：el-alert（warning，不阻断）或独立 el-card「容量不足，未排入的任务」：逐条 `title` + 后端中文 `reason` + 固定说明文案「这些任务已保存在任务列表，可前往任务页手动安排」
  - **组件内不判空占位**——`tasks.length === 0` 时由父层不挂载（spec §5.1.1 规则 8b「页面无该卡片占位」）；adjust 流程响应无此字段，父层不触碰（决策 D8）
- **涉及文件**：新增 `frontend/src/components/plan/UnplacedTasksCard.vue`
- **完成判定**：`npm run build` 通过；固定说明文案与「容量不足，未排入的任务」标题 grep 命中
- **依赖**：组 1（与 4.1/4.4 并行）
- **决策锚点**：design 2.4.4 / D8；spec §5.1.1 规则 8a/8b（裁定 #5）

### 4.4 PlanEmptyState.vue：空态引导

- [x] **要点**：
  - 契约（design 2.4.4）：`Props: loading: boolean`（生成请求飞行中透传按钮）；`Emits: generate`
  - 渲染（裁定 #3）：el-empty「还没有进行中的学习计划」+ 说明文案含「为下一个完整自然周（周一开始）生成」语义 + 主按钮「生成下一周学习计划」（loading 锁）+ 次级说明「同一周期重复生成会归档旧版本」（spec §5.2.1 规则 4）
  - **文案红线**：按钮与说明必须如实写「下一周」，禁止任何暗示生成「本周」计划的措辞
- **涉及文件**：新增 `frontend/src/components/plan/PlanEmptyState.vue`
- **完成判定**：`npm run build` 通过；`grep -n "下一周" frontend/src/components/plan/PlanEmptyState.vue` 命中 ≥1（按钮）且说明文案含「下一个完整自然周」；`grep -n "归档" frontend/src/components/plan/PlanEmptyState.vue` 命中
- **依赖**：组 1（与 4.1/4.3 并行）
- **决策锚点**：design 2.4.4；spec §5.1.3-1、§5.2.1 规则 2a/4a（裁定 #3）

### 4.5 PlanDiffPreview.vue：diff 预览双栏对比（裁定 #2 落点）

- [x] **要点**：
  - 契约（design 2.4.4）：`Props: pending: PendingNewPlan`；`Emits: confirm(source: 'primary' | 'close')`——**「查看调整后的计划」主按钮与「关闭对比」次按钮共用同一 emit 出口、以 source 参数区分路径**（关闭预览等同查看完毕，裁定 #2；关闭路径父组件追加「新计划已生效」提示，spec §5.3.1 规则 6）；**无任何「放弃调整 / 取消 / 撤销」类按钮**；ESC 键与「关闭对比」同路径（`source='close'`），onMounted/onUnmounted 挂载与移除 window keydown 监听
  - 四段结构（spec §5.3.1 规则 3，自上而下）：① `adjust_reason` 显著卡片（大字号独立色块，禁止折叠默认隐藏；reason 为 null 降级显示「本次调整未提供说明」——防御）；② 双栏 WeekGrid（左「原计划」=`pending.oldItems` / 右「新计划」=`pending.items`，均 `compact + highlights`，每栏上方小标题 + 新栏版本徽章）；③ 结构化改动清单——moved 逐条「{topic}：从 {from_date} {from_time} 挪到 {to_date} {to_time}（{reason}）」（time 为 null 显示「休息时段」）、removed 逐条「{topic} 被移出计划（{reason}）」、added 逐条「新增：{topic}（{reason}）」；三类全空 → 显示「本次调整无条目变动」（spec §5.3.3-3）；④ 操作区主按钮「查看调整后的计划」（primary）+「关闭对比」（plain）
  - **数据来源铁律注释**：右栏条目一律为 `pending.items`（服务端取回），严禁用 oldItems + diff 前端重建（spec §5.3.1 规则 4-⑤）
  - **高亮下标映射约束**：分别调用 `markDiffHighlights(pending.oldItems, pending.diff, 'old')` 与 `markDiffHighlights(pending.items, pending.diff, 'new')`，并把对应 items 数组与 Map 传给左右两个 WeekGrid；WeekGrid 内部按对象引用建下标映射（见 4.2），**禁止**用 `item.id` 当 key
  - **时间渲染口径**：moved 清单的 `from_time` / `to_time` 必须经 `formatHm` 截取（前置约定 8）；时间为 null 时显示「休息时段」
- **涉及文件**：新增 `frontend/src/components/plan/PlanDiffPreview.vue`
- **完成判定**：`npm run build` 通过；`grep -nE "放弃|取消调整|撤销" frontend/src/components/plan/PlanDiffPreview.vue` 零命中；「查看调整后的计划」「关闭对比」「本次调整无条目变动」grep 命中；`grep -n "formatHm" frontend/src/components/plan/PlanDiffPreview.vue` 命中（前置约定 8）；`grep -n "Escape" frontend/src/components/plan/PlanDiffPreview.vue` 命中（ESC 同关闭路径）；`grep -n "emit('confirm', 'primary')\|emit('confirm', 'close')" frontend/src/components/plan/PlanDiffPreview.vue` 各命中；双栏高亮与清单由 8.3-W4/W5 走查覆盖
- **依赖**：组 1、3.1、4.2
- **决策锚点**：design 2.4.4 / D6 / D13；spec §5.3.1 规则 2a/3a/3b/3c/6a、§5.3.3-3（裁定 #2）

### 4.6 AdjustHistoryPanel.vue：调整记录回看（降级形态）

- [x] **要点**：
  - 契约（design 2.4.4）：`Props: plan: Plan; diff: PlanDiff | null（null=请求飞行中骨架）; loading: boolean`；`Emits: back`
  - 渲染（spec §5.4.1 规则 2，降级形态）：`plan.adjust_reason` 显著展示（计划对象自带字段）+ 三类改动清单（与 PlanDiffPreview ③ 同构样式，实现为各自局部模板块，**不抽公共子组件**——清单 markup 约 20 行，抽组件反增间接层）；diff 空结构 → 「该版本无调整记录」（spec §5.4.3-2）
  - **无双栏网格**（parent 版本条目需全量翻页取回，回看属低频能力不付此开销）；**无任何「应用/确认」类按钮**（调整早已生效，spec §5.4.1 规则 4）
- **涉及文件**：新增 `frontend/src/components/plan/AdjustHistoryPanel.vue`
- **完成判定**：`npm run build` 通过；`grep -nE "应用|确认" frontend/src/components/plan/AdjustHistoryPanel.vue` 零命中；「该版本无调整记录」「返回周视图」grep 命中；`grep -n "formatHm" frontend/src/components/plan/AdjustHistoryPanel.vue` 命中（前置约定 8，改动时间经 formatHm 截取）
- **依赖**：组 1
- **决策锚点**：design 2.4.4；spec §5.4.1 规则 2a/4a、§5.4.3-2

**里程碑验证（组 4 结束）**：
```bash
cd frontend && npm run build && \
grep -rnE "axios|fetch\(|@/api" src/components/plan/ | wc -l   # 输出 0 = 六件全部纯展示零请求
```

---

## 5. components/report/ReportCard（纯展示 + 内联纯前端导出）

**写作说明**：新增 `frontend/src/components/report/ReportCard.vue`（~260 行）——报告域唯一子组件。导出按钮内联调用 utils 纯函数（零请求，不违反分层铁律第 1 条——design 2.1.2 铁律 2 的明确豁免）。

### 5.1 ReportCard.vue：报告卡片（区间显著头部 + 七要素分区 + 导出）

- [x] **要点**：
  - 契约（design 2.4.5）：`Props: report: Report`；**Emits: 无**（导出内联调 `downloadReportMarkdown`，纯前端行为）
  - ① 卡片头部（**显著位置硬性要求**，spec §5.5.1 规则 3）：类型标识 tag（`REPORT_TYPE_LABELS` 映射日报/周报/月报）+ 统计区间「{period_start} 至 {period_end}」大字重文本 + 生成时间（`formatCreatedAtLocal`）+ 生成方式徽章（`generatedByLabel` 返回 null 则不渲染——「LLM 总结 / 规则模板」两值以外无徽章）；**禁止只在正文埋区间信息**
  - ② `summary` 非空 → 摘要引用块（置于七要素之前）
  - ③ 七要素分区（el-descriptions 或分块 grid，**有则显示、无则隐藏该分区**，spec §5.5.1 规则 6）：学习时长（`formatMinutes(total_minutes)`）；完成任务（「完成 {task_completed} 个任务，完成率 {completion_rate}%」）；学习最多的方向（`top_direction` 或「本期暂无」）；薄弱知识点（weak_points 逐个 el-tag danger/warning 色系「{knowledge_point} {mastery_score} 分」；空数组 → 「本期无明显薄弱知识点」不留白）；阶段进步（progress 三差值，正负号保留显式拼接 +/-，`avg_mastery_diff` 为 null 省略该行）；建议（advice 有序列表）
  - ④ 操作区：「导出 Markdown」按钮（plain）→ `downloadReportMarkdown(report)`；外层 try/catch 兜底 → ElMessage「浏览器已拦截下载，请允许下载后重试」（spec §5.6.3-3）
  - **零数据容错**：`content=null` 的卡片仅渲染 ①（+② 若有），页面不报错、不渲染「undefined/null」字样
- **涉及文件**：新增 `frontend/src/components/report/ReportCard.vue`
- **完成判定**：`npm run build` 通过；`grep -nE "axios|fetch\(|@/api" frontend/src/components/report/ReportCard.vue` 零命中；`grep -nE "\"rules\"|'rules'" frontend/src/components/report/ReportCard.vue` 零命中（报告域铁律）；「至」「本期暂无」「本期无明显薄弱知识点」「导出 Markdown」grep 命中；区间显著性与色块渲染由 8.3-W8 走查覆盖
- **依赖**：组 1、3.2
- **决策锚点**：design 2.4.5 / D11；spec §5.5.1 规则 3a/4a/5a/5b/6a/7a、§5.6.1 规则 3a、§5.6.3-2/3

**里程碑验证（组 5 结束）**：
```bash
cd frontend && npm run build && \
grep -rnE "axios|fetch\(|@/api" src/components/report/ | wc -l   # 输出 0
```

---

## 6. views/PlanView.vue：会话态状态机编排（本批核心）

**写作说明**：`PlanView.vue` 由 14 行 PagePlaceholder 骨架替换为 ~300 行实体。状态机唯一来源：design 2.1.3-A/B/C；状态字段表：design 2.4.1。**不复用 `useDashboardBlock`**（决策 D2：会话态混合加载是多阶段状态机，非单块 reload）。四个子任务严格串行（同文件）：6.1 骨架 → 6.2 生成 → 6.3 调整取数（核心红线）→ 6.4 切换与回看。

### 6.1 状态机骨架 + loadCurrent（首屏 / 刷新 / 重试共用入口）

- [x] **要点**：
  - 页面状态字段九项逐字落地（design 2.4.1 表）：`phase: 'loading'|'empty'|'ready'`、`viewMode: 'week'|'diff'|'history'`、`sessionPlan: SessionPlan|null`、`unplacedTasks: UnplacedTask[]`、`pendingNew: PendingNewPlan|null`、`historyDiff: PlanDiff|null`、`fetchError: boolean`、`generating / adjusting / fetchingItems: boolean`（`adjustBusy = adjusting || fetchingItems`，决策 D14）、`degraded: boolean`
  - `loadCurrent(): Promise<void>`（design 2.2.2-(8) 签名）：`onMounted` 唯一调用入口——`fetchCurrentPlan()` 成功非 null → `sessionPlan={...current, origin:'current'}` + `phase='ready'`；返回 null → `phase='empty'`（**正常空态非错误，不走 catch**，spec §5.1.3-1）；失败 → catch 静默（拦截器已弹错）+ `phase='empty'` 兜底（空态含生成按钮保持可用，spec §5.1.3-2——**首屏失败是空态兜底，不是错误卡片**，决策 D15 两形态区分）
  - `loadCurrent` 同时清空 `unplacedTasks` 与 `pendingNew`（决策 D8）；**首屏仅 1 次请求，空态不追加请求**（spec §4.1-1）
  - `isNextWeek` 计算属性（决策 D3）：`plan.start_date > todayLocalStr()` 日期推导（非 origin 字段——覆盖 adjust 后跨会话周期真值）；模板拼装：信息头 / WeekGrid / UnplacedTasksCard（`length>0` 才挂载）/ PlanEmptyState / 工具栏「重新调整计划」按钮（页面存在可展示计划时可用）
- **涉及文件**：修改 `frontend/src/views/PlanView.vue`（骨架 → 实体）
- **完成判定**：`npm run build` 通过；`grep -n "PagePlaceholder" frontend/src/views/PlanView.vue` 零命中（骨架已退出）；`grep -n "loadCurrent" frontend/src/views/PlanView.vue` 命中且 `onMounted` 中唯一调用；首屏请求数与空态由 8.3-W1 走查覆盖
- **依赖**：组 2、组 3、组 4
- **决策锚点**：design 2.1.3-A/C / 2.4.1 / D2 / D3 / D8 / D15；spec §5.1.1 规则 1-①④（验收 1b/1c）、§5.1.3-1/2、§4.1-1、§4.2-2

### 6.2 handleGenerate：生成动作（会话态直接渲染，不重查 current）

- [x] **要点**：
  - `handleGenerate(): Promise<void>`：`generating` 锁（飞行期重复点击不发起第二次请求，spec §4.2-1）→ `generatePlan()` 成功 → `sessionPlan={plan, items, origin:'generate'}` + `unplacedTasks=res.unplaced_tasks` + `phase='ready'` + `viewMode='week'` + `ElMessage.success`——**不重查 current**（下周计划不满足 current 条件，spec §5.1.1 规则 1-②）；`res.generated_by === 'rules'` → `degraded=true` + `ElMessage.warning('LLM 规划暂不可用，已按规则引擎生成计划')`（计划域字面量判定，合法）；`'llm'` → 无额外提示
  - 失败 → catch 静默 + 解除 loading + 维持原状态（空态或原周视图）；400/1007 冲突由拦截器弹后端 message（spec §5.2.3-1/2）
  - **禁止**成功后自动跳转或全屏遮罩（spec §5.2.1 规则 5）；停留 /plans 直接看到新周视图
- **涉及文件**：修改 `frontend/src/views/PlanView.vue`
- **完成判定**：`npm run build` 通过；`grep -n "fetchCurrentPlan" frontend/src/views/PlanView.vue` 命中处仅在 `loadCurrent` 与取数判定函数内（handleGenerate 函数体内零命中——不重查 current 的静态佐证）；「LLM 规划暂不可用，已按规则引擎生成计划」grep 命中；生成链路交互由 8.3-W2/W3 走查覆盖
- **依赖**：6.1
- **决策锚点**：design 2.1.3-A 生成分支 / 2.2.2-(2) / D8；spec §5.2.1 规则 1a/3a/3b/5a、§5.2.3-1/2/3、§5.1.1 规则 1-②（验收 1a）、§4.2-1

### 6.3 handleAdjust + resolveNewVersionItems：调整动作与两段式服务端取数（红线任务）

- [x] **要点**：
  - `handleAdjust(): Promise<void>`：`adjustBusy` 锁全程（adjust 请求 + 后续取数两阶段，决策 D14——取数是 adjust 流程组成部分，中间态不放行）；发起前从 `sessionPlan.items` 拷贝 `oldItems` 快照（双栏左栏数据源）
  - `adjusted=false` 分支：`ElMessage.info(res.adjust_reason)`（此场景它是提示文案），页面停留原周视图，**不进入取数、不进预览**（spec §5.3.1 规则 5）
  - `resolveNewVersionItems(targetPlanId: number): Promise<PlanItem[]>`（design 2.2.2-(8)，spec §5.3.1 规则 4 逐条落地）：① 先 `fetchCurrentPlan()`——**仅当** `data != null` 且 `data.plan.id === targetPlanId` 时采用 `data.items`；② 否则循环 `fetchLearningPlanItems(page, 100)`，`page * page_size < total` 续页取全，`MAX_PAGES = 50` 硬上限（R3 防脏数据死循环，达上限按已取数据过滤 + `console.warn`）；③ 客户端 `items.filter(plan_id === targetPlanId)`；④ 过滤结果为空或任一请求失败 → `throw PlanFetchError`（内部错误类，仅用于驱动错误态分支）
  - 取数成功 → `pendingNew = {plan, items, diff, oldItems, adjustReason}` → `viewMode='diff'`（**取数在进入 diff 预览之前完成**，预览渲染零请求）
  - **取数失败错误态（决策 D15，本任务硬性验收点）**：`fetchError=true` 渲染**独立错误卡片**（与首屏空态视觉语义区分——「有新计划但拿不到」≠「没有计划」）——文案**必须**写「**计划调整已生效，但新版本条目暂时加载失败**」，**禁止只写「加载失败」**（会让用户误以为调整未生效，spec §5.3.3-4b/4d）；「重新加载」按钮点击 → `loadCurrent()`（回 current 流程重新初始化）；**绝不**用旧 items + diff 前端重建新网格（规则 4-⑤ 红线），**绝不**渲染旧网格冒充新版本（规则 4-④）
  - adjust 请求失败（404/1005/1007 等）→ catch 静默 + 解除锁 + 维持原周视图（拦截器已按后端 message 弹错；视图层零业务码分支，spec §5.3.3-1/2/5）
  - **禁止项**：本流程全程不调用 `fetchPlanDiff`（规则 7——adjust 响应已含同构 diff）
- **涉及文件**：修改 `frontend/src/views/PlanView.vue`
- **完成判定**：`npm run build` 通过；`grep -n "计划调整已生效，但新版本条目暂时加载失败" frontend/src/views/PlanView.vue` 命中（文案写死）；`grep -n "加载失败" frontend/src/views/PlanView.vue` 命中行均为该完整句一部分（无孤立「加载失败」措辞，人工复核）；「重新加载」按钮 handler 绑定 `loadCurrent`（grep 命中同区域）；`grep -n "MAX_PAGES" frontend/src/views/PlanView.vue` 命中且值为 50；`grep -n "fetchPlanDiff" frontend/src/views/PlanView.vue` 仅命中 6.4 回看函数调用处（adjust 流程零调用）；请求序列与错误态由 8.3-W4/W6 走查覆盖
- **依赖**：6.1
- **决策锚点**：design 2.1.3-B / 2.2.2-(3)(5)(8) / 2.4.1 / D7 / D14 / D15 / R3；spec §5.3.1 规则 1a/4a/4b/4c/4d/5a/7a、§5.3.3-1/2/4（含 4d 文案验收）/5、§4.2-1、§4.2-3

### 6.4 handleConfirmNewPlan(source) + handleViewHistory：零请求切换与回看

- [x] **要点**：
  - `handleConfirmNewPlan(source: 'primary' | 'close'): void`——「查看调整后的计划」与「关闭对比」**同一处理函数**（PlanDiffPreview 的 confirm 统一出口，source 区分路径）：`sessionPlan = {plan: pendingNew.plan, items: pendingNew.items, origin:'adjust'}`（**同一 items 引用转移**，保证 diff 右栏与切换后周视图一致）→ `pendingNew=null` → `viewMode='week'`；**全程零请求**（纯前端切换）；**仅当 `source === 'close'`**（含 ESC 路径）追加轻提示「新计划已生效」（spec §5.3.1 规则 6——主按钮路径不提示）
  - `handleViewHistory(): Promise<void>`：`parent_plan_id ≠ null` 入口点击 → `fetchPlanDiff(plan.id)` → `historyDiff` → `viewMode='history'`；失败 → catch 静默停留原周视图（spec §5.4.3-1）；AdjustHistoryPanel 的 `back` → `viewMode='week'` 回切（`historyDiff` 保留不重发，**零请求**，spec §5.4.1 规则 3）
- **涉及文件**：修改 `frontend/src/views/PlanView.vue`
- **完成判定**：`npm run build` 通过；`grep -n "新计划已生效" frontend/src/views/PlanView.vue` 命中；`handleConfirmNewPlan` 函数体内 `grep` 无任何 api 调用（零请求静态佐证，人工复核）；零请求切换与回看由 8.3-W5/W12 走查覆盖
- **依赖**：6.3、4.5、4.6
- **决策锚点**：design 2.1.3-A/B / 2.2.2-(8)；spec §5.3.1 规则 2b/2c/6a、§5.4.1 规则 3a、§5.4.3-1（裁定 #2）

**里程碑验证（组 6 结束）**：
```bash
cd frontend && npm run build && \
grep -n "计划调整已生效，但新版本条目暂时加载失败" src/views/PlanView.vue && \
grep -c "fetchCurrentPlan\|generatePlan\|adjustPlan\|fetchPlanDiff\|fetchLearningPlanItems" src/views/PlanView.vue   # ≥5 = 编排收口在视图层
```

---

## 7. views/ReportsView.vue：三 tab 编排（按需加载 + 会话缓存）

**写作说明**：`ReportsView.vue` 由 14 行骨架替换为 ~260 行实体。状态机唯一来源：design 2.1.3-D。**不复用 `useDashboardBlock`**（reload 语义与「未加载才请求」缓存语义冲突，design 1.2.2）。两个子任务串行：7.1 列表状态机 → 7.2 生成动作。

### 7.1 三 tab 状态机与按需加载

- [x] **要点**：
  - `el-tabs` + 三个 `el-tab-pane`（日报/周报/月报），**默认激活周报 tab**；`tabState: reactive<Record<ReportType, TabState>>`，`TabState = {items, total, page, pageSize, loaded, loading}`
  - `onMounted` 仅加载 weekly（首屏仅 1 次请求，spec §4.1-2 / §5.5.1 规则 1a）；切换 handler：目标 tab `loaded === false` 才 `loadTabList(type, 1)`；**已加载直接渲染会话内缓存，零请求**（规则 1b）；翻页始终真实请求并覆盖缓存页（page_size 固定 10）
  - 空态：某 tab `loaded && total === 0` → el-empty + 「生成报告」引导，**不渲染分页器**（规则 8a）；列表失败 → catch 静默（拦截器弹错）+ 该 tab 空态（含生成入口，spec §5.5.3-1）
  - 列表按后端 created_at 倒序直传渲染，**前端不重排**；`el-pagination` total 对齐响应 total
  - report_type 非法防御（spec §5.5.3-2）：`ReportType` 字面量联合类型 TS 层面结构性排除，按钮绑定固定三字面量，无用户输入路径，不额外判空
- **涉及文件**：修改 `frontend/src/views/ReportsView.vue`（骨架 → 实体）
- **完成判定**：`npm run build` 通过；`grep -n "PagePlaceholder" frontend/src/views/ReportsView.vue` 零命中；`grep -n "loaded" frontend/src/views/ReportsView.vue` 命中（缓存标记在位）；tab 缓存与分页请求序列由 8.3-W8 走查覆盖
- **依赖**：组 2.2、5.1
- **决策锚点**：design 2.1.3-D / 2.4.5 / D9；spec §5.5.1 规则 1a/1b/2a/2b/8a、§5.5.3-1/2、§4.1-2

### 7.2 handleGenerateReport：生成报告动作

- [x] **要点**：
  - `generatingReport` 锁（spec §4.2-1）；`generateReport({report_type: 当前激活 tab 类型})`——请求体**仅 `{report_type}`**，不传 period_end（spec §5.6.1 规则 1）
  - 成功 → `ElMessage.success` + `loadTabList(type, 1)` **重载列表**（决策 D9：选重载不选头部插入——保证 total/分页一致性，新报告置顶由后端倒序保证）；失败 → catch 静默 + 解除锁 + 列表维持原状（spec §5.6.3-1）
  - 工具栏「生成报告」按钮 +「生成说明」tooltip（同周期重复生成会追加新报告行——后端 append 语义如实告知）
- **涉及文件**：修改 `frontend/src/views/ReportsView.vue`
- **完成判定**：`npm run build` 通过；`grep -n "period_end" frontend/src/views/ReportsView.vue` 零命中；生成与置顶由 8.3-W9 走查覆盖
- **依赖**：7.1
- **决策锚点**：design 2.2.2-(7) / 2.4.5 / D9；spec §5.6.1 规则 1a/1b/2a、§5.6.3-1、§4.2-1

**里程碑验证（组 7 结束）**：
```bash
cd frontend && npm run build && \
grep -rnE "axios|fetch\(" src/views/PlanView.vue src/views/ReportsView.vue | wc -l   # 输出 0 = 视图层零裸请求
```

---

## 8. 收尾走查（沙箱门禁 + 静态检查 + 设计一致性 + 本机走查交接）

**写作说明**：本组是交付收口。**沙箱门禁与手工走查严格分离**：8.1 全部命令在沙箱可执行（构建 + grep + git diff）；8.3 的 W1–W13 为交互类验收，沙箱无后端联调环境（R1），移交本机浏览器逐步执行。**最终判据写死：「`npm run build` 通过 + 本机走查清单全部通过」**——两者缺一不可交付。

### 8.1 沙箱门禁与静态检查（vue-tsc + grep 套件 + 冻结项 diff）

- [x] **要点**（全部沙箱内执行，逐项记录结果）：
  1. **构建门禁**：`cd frontend && npm run build` → exit 0（vue-tsc 类型检查含其中，无 any 相关告警，spec §4.4-2 / §4.5-3）
  2. **分层静态核查**：`grep -rnE "axios|fetch\(" frontend/src/views/PlanView.vue frontend/src/views/ReportsView.vue frontend/src/components/plan/ frontend/src/components/report/` → 零命中（spec §4.4-1）；`grep -rn "@/api" frontend/src/components/plan/ frontend/src/components/report/` → 零命中（子组件零请求铁律）
  3. **报告域字面量静态检查（铁律，决策 D11）**：`grep -rnE "\"rules\"|'rules'" frontend/src/types/report.ts frontend/src/api/report.ts frontend/src/utils/report.ts frontend/src/components/report/ frontend/src/views/ReportsView.vue` → **零命中**；反证计划域合法：`grep -c "'rules'" frontend/src/types/plan.ts` ≥ 1（`generated_by: 'llm' | 'rules'` 在位）
  4. **错误卡文案静态核查**：`grep -n "计划调整已生效，但新版本条目暂时加载失败" frontend/src/views/PlanView.vue` → 命中；`grep -n "加载失败" frontend/src/views/PlanView.vue` → 命中行均为完整句一部分（无孤立「加载失败」）；「重新加载」按钮与 `loadCurrent` 绑定同区域命中
  5. **导出实现核查**：`grep -n "toISOString" frontend/src/utils/report.ts frontend/src/utils/plan.ts` → 零命中；`grep -n "revokeObjectURL" frontend/src/utils/report.ts` → 命中；`grep -n "file-saver\|FileSaver" frontend/src/ -r` → 零命中
  6. **api 封装边界核查**：`grep -c "^export" frontend/src/api/plan.ts` = 5、`grep -c "^export" frontend/src/api/report.ts` = 2；人工核对无 `GET /plans` 列表 / `GET /plans/{id}` 详情 / `GET /reports/{id}` 封装
  7. **冻结项 diff 审查**：`git status --short backend/ frontend/package.json frontend/src/api/request.ts frontend/src/router/index.ts frontend/src/types/index.ts frontend/src/stores/ frontend/src/components/PagePlaceholder.vue` → **输出为空**（`git status` 同时覆盖「被修改」与「未跟踪新增」两种越界，`git diff` 看不到未跟踪文件）；后端测试不受影响（本批零触碰，无需重跑亦可声明 206 passed 基线不变）
- **涉及文件**：无代码改动（检查性任务）
- **完成判定**：上述 7 项命令全部按预期输出，逐项记录
- **依赖**：组 1–7
- **决策锚点**：design 2.6（D1/D11/D12）/ 2.9 / 2.10；spec §4.4-1/4.4-2、§4.5-1/4.5-2/4.5-3、§5.3.3-4d

### 8.2 代码走查与设计一致性核对

- [x] **要点**：
  - **决策 D1–D15 逐项复核**：D1 域类型文件、D2 状态机未复用 useDashboardBlock、D3 isNextWeek 日期推导、D4 CSS grid（无 el-table 课表）、D5 字典序时段、D6 业务键高亮降级、D7 取数编排在视图层 + MAX_PAGES=50、D8 unplaced 生命周期、D9 生成后重载、D10 无 toISOString、D11 报告域字面量、D12 零 Pinia（`grep -rn "defineStore" frontend/src/` 无新增命中）、D13 WeekGrid 双形态 props、D14 adjustBusy 全程锁、D15 首屏空态 vs 取数错误卡两形态
  - **裁定 #1–#6 落实核对**：#1 会话态混合加载三来源与刷新回 current、#2 无放弃/取消/撤销按钮且关闭=确认、#3 空态与按钮「下一周」文案、#4 三时段映射与休息区块、#5 unplaced 独立卡、#6 文件名与 Markdown 结构
  - **文件清单对齐 design 2.9**：16 项（2 修改 + 14 新增 + 本文档）逐一核对存在性；无清单外新增文件（尤其无 `stores/plan.ts`、无 ECharts 相关、无历史版本双栏浏览组件）
  - **文案与规范**：用户可见文案全中文抽查；组件 PascalCase / 函数 camelCase / 常量 UPPER_SNAKE_CASE；`<script setup lang="ts">` 全覆盖；主题变量 `--el-color-*` 无硬编码色值抽查
- **涉及文件**：组 1–7 全部新增/改动文件（走查，无代码改动）
- **完成判定**：D1–D15 与裁定 #1–#6 逐项核对通过并记录；文件清单 16 项齐全
- **依赖**：8.1
- **决策锚点**：design 2.6 / 2.9 / 2.10；spec 附录 A、§4.4-3/4.4-4

### 8.3 本机走查清单交接（W1–W13，沙箱无法覆盖的交互类验收）

> **实施记录（2026-10-24）**：W1–W12 已由浏览器自动化（本机 Chrome + puppeteer-core）验证通过；W13（LLM 降级）为可选，未执行。详细证据见 `docs/WALKTHROUGH_PLAN_REPORT_FRONTEND.md` 的「自动化验证记录」。

- [x] **要点**（沿 design 2.8-R1 的 7 条扩充为 13 条；前置：本机后端已启动、demo 账号可登录、`cd frontend && npm run dev`；逐条在浏览器 + DevTools 网络面板执行，操作 → 预期如实记录）：
  1. **W1 首屏请求序列与网格结构**（验收 §4.1-1、§5.1.1-1c/2a/3a/3b/4a/5a/6a/6b）：有当前计划的账号打开 /plans → 网络面板**仅 1 个** `GET /plans/current` 即完成首屏；可见 7 列（周一~周日）× 3 行（上午/下午/晚上）网格，列头日期与计划周期一致；抽查 19:00 条目在「晚上」行、14:00 条目在「下午」行；周五休息条目（若有）在独立休息区块、不占三时段行；planned 条目左侧醒目色条、done 条目灰显对勾；条目卡片四类信息齐全
  2. **W2 生成链路**（验收 §5.1.1-1a/7b/8a/8b、§5.2.1-1a/2a/4a/5a）：空态账号（或工具栏入口）点「生成下一周学习计划」→ 按钮 loading 且仅 1 次 `POST /plans/generate` → 周视图立即渲染下周完整网格（不显示空态）、信息头含「下周计划」标注；unplaced_tasks 非空时下方提示卡含标题与原因、空数组时无卡片占位；全程停留 /plans 无跳转
  3. **W3 刷新回 current**（验收 §5.1.1-1b）：W2 之后刷新页面 → 重新出现且仅 1 次 `GET /plans/current`；若本周另有 active 计划则显示本周计划，否则显示空态（会话态不持久，预期行为）
  4. **W4 adjust 全请求序列与 diff 预览**（验收 §5.3.1-1a/2a/3a/3b/3c/4a/4b/4c、§4.2-3）：点「重新调整计划」→ 按钮全程锁定；网络面板依序出现 `POST /plans/{id}/adjust` → `GET /plans/current`（可选）→（必要时）1..N 次 `GET /learning-plan-items?page=N&page_size=100`；**全程无** `GET /plans/{id}/diff`、无任何确认/提交类请求；diff 预览顶部 adjust_reason 全文显著可见；双栏对比中 moved 左栏标「移出」/右栏标「移入」、added 在右栏标「新增」、removed 在左栏标「移除」；底部清单含挪动描述（含「休息时段」降级，若涉及）；**右栏与后续周视图为新版本条目，不出现本周计划内容**
  5. **W5 零请求切换（两条路径）**（验收 §5.3.1-2b/2c/6a）：diff 预览点「查看调整后的计划」→ 网络面板**零新请求**，页面切为新版本周视图；再次调整走「关闭对比」路径 → 同样零请求 + 出现「新计划已生效」轻提示；预览与切换后网格内容一致（同一份条目）
  6. **W6 取数失败错误态**（验收 §5.3.1-4d、§5.3.3-4d）：调整成功后、learning-plan-items 阶段用 DevTools 设 offline（或拦截该请求置失败）→ 页面出现**独立错误卡**，文案含「**计划调整已生效，但新版本条目暂时加载失败**」（**不得只写「加载失败」**）；不出现旧网格冒充新版本；点「重新加载」→ 发出 1 次 `GET /plans/current`（loadCurrent 流程），页面恢复到当前生效计划或空态
  7. **W7 按钮锁防重**（验收 §4.2-1、§5.2.3-3、§5.6.1-1b）：「生成下一周学习计划」「重新调整计划」「生成报告」三按钮分别在请求飞行期间（可用 DevTools 降速模拟）重复点击 → 均不发起第二次请求
  8. **W8 tab 缓存与分页**（验收 §4.1-2、§5.5.1-1a/1b/2a/2b/3a/8a）：打开 /reports → 仅 1 次 `GET /reports?report_type=weekly&page=1`；依次切 日报 → 周报 → 月报 → 周报 → 每类型至多首次各 1 次请求，回到周报**零请求**渲染缓存；点分页器第 2 页 → 1 次 `page=2` 请求并渲染该页；任意卡片头部肉眼即见「{period_start} 至 {period_end}」区间（无需展开正文）；空 tab 显示空态 + 生成引导、无分页器
  9. **W9 报告生成置顶**（验收 §5.6.1-1a/2a）：周报 tab 点「生成报告」→ 请求体仅 `{"report_type":"weekly"}`（无 period_end）；成功后列表自动重载 page=1，第一张卡片为刚生成的报告（无需手动刷新）
  10. **W10 导出文件名与内容**（验收 §5.6.1-3a/4a/5a/5b/6a）：点某卡片「导出 Markdown」→ 网络面板**零新请求**；下载文件名形如「学习周报_2026-10-12_2026-10-18.md」；文本编辑器打开：首行为含区间的一级标题、引言含区间重申与生成时间、七个分区（有数据时）齐全、weak_points 为空的报告该节显示「本期无明显薄弱知识点」且文件完整、结尾「生成方式」标注、**全文无「undefined/null」字样**
  11. **W11 断网重试与鉴权回退**（验收 §4.2-2、§4.3-1、§5.1.3-2）：断网点「生成下一周学习计划」→ 弹「网络异常，请稍后重试」，页面不白屏、保持可用的空态/原视图；恢复网络重试成功；token 过期后访问 /plans → 自动跳 /login（既有行为不回退）
  12. **W12 调整记录回看**（验收 §5.4.1-1a/1b/2a/3a/4a、§5.4.3-2）：对 parent_plan_id 非空的计划，信息头出现「查看调整记录」→ 点击发出 1 次 `GET /plans/{id}/diff` → 回看视图可见 adjust_reason 与三类改动清单、**无双栏网格、无任何应用/确认按钮**；点「返回周视图」→ 零请求回到原周视图且数据不变；首版计划（parent_plan_id=null）无该入口；diff 空结构时显示「该版本无调整记录」
  13. **W13 降级提示（LLM 故障演练，可选环境）**（验收 §5.2.1-3a/3b、§5.5.1-7a）：改错后端 `.env` 的 LLM_BASE_URL 重启 → 生成计划成功但信息头显示「规则降级」徽章 + 页面出现降级提示；生成报告成功但卡片显示「规则模板」徽章（数字仍为真实统计）；恢复正常配置后徽章回到「LLM 规划 / LLM 总结」且无降级提示
- **涉及文件**：无新增（操作验证；走查记录建议存 `docs/` 或临时目录）
- **完成判定（本批最终判据，写死）**：**`npm run build` 通过（8.1-1）+ 本机走查清单 W1–W13 全部通过**——两者缺一不得交付
- **依赖**：8.2
- **决策锚点**：design 2.8-R1（7 条扩充为 13 条）；spec §4.1/§4.2/§4.3、§5.1–§5.6 全部交互类验收条件

**里程碑验证（组 8 结束——全批收口）**：
```bash
cd frontend && npm run build                                              # 门禁：exit 0
git status --short backend/ | wc -l                                        # 输出 0 = 后端零改动
git status --short frontend/package.json frontend/src/api/request.ts frontend/src/router/index.ts frontend/src/types/index.ts frontend/src/stores/   # 输出为空（git status 才能发现未跟踪的新增文件）
git status --short frontend/src/ | wc -l                                   # 输出 15（2 修改 + 13 新增）
grep -rnE "\"rules\"|'rules'" frontend/src/types/report.ts frontend/src/api/report.ts frontend/src/utils/report.ts frontend/src/components/report/ frontend/src/views/ReportsView.vue | wc -l   # 输出 0 = 报告域无 rules
# + 8.3 本机走查 W1–W13 全绿（人工执行记录）
```

---

## 附：覆盖率自检（spec 验收条件 → 任务映射表，70 条全覆盖、缺 0）

**口径说明**：N = 70 = spec 全文「验收条件」条目数（10 条 §4 DFX 内嵌式 + 60 条 §5 字母编号式，grep 实测）。沙箱可静态判定项标注【静态】，交互类标注【W#】移交 8.3 本机走查。

### §4 DFX（10 条）

| spec 验收条件 | 覆盖任务 | 判定点 |
|---|---|---|
| §4.1-1 首屏仅 1 次 plans 请求 | 6.1（loadCurrent 唯一入口） | 【W1】 |
| §4.1-2 未加载 tab 仅 1 次请求 | 7.1（loaded 缓存判重） | 【W8】 |
| §4.2-1 三按钮飞行期锁定 | 6.2 / 6.3（adjustBusy 全程）/ 7.2 | 【W7】+ 8.1 静态（loading 绑定） |
| §4.2-2 失败不白屏可重试 | 6.1 / 6.2 / 7.1（catch 静默回滚） | 【W11】 |
| §4.3-1 鉴权链路不回退 | 组 0 冻结（request.ts 零改动） | 8.1 diff 为空 +【W11】 |
| §4.4-1 无 axios/裸 fetch | 2.1 / 2.2（封装收口） | 8.1-2【静态】 |
| §4.4-2 vue-tsc 通过无 any | 1.1 / 1.2（类型具名） | 8.1-1【静态】 |
| §4.5-1 后端零改动 | 组 0 冻结 | 8.1-7【静态】 |
| §4.5-2 零新增依赖 | 3.2（原生 Blob） | 8.1-7（package.json diff 空）+【W10】 |
| §4.5-3 npm run build exit 0 | 全组 | 8.1-1【静态】 |

### §5.1 计划周视图（15 条）+ §5.1.3 异常

| spec 验收条件 | 覆盖任务 | 判定点 |
|---|---|---|
| §5.1.1-1a 生成下周立即渲染 | 6.2 | 【W2】 |
| §5.1.1-1b 刷新回 current | 6.1 | 【W3】 |
| §5.1.1-1c 周期与计划一致 | 4.1 + 3.1（buildWeekColumns） | 【W1】 |
| §5.1.1-2a 7 列 × 3 行网格 | 4.2 | 【W1】+ 8.2（D4 复核） |
| §5.1.1-3a/3b 时段归属（19:00→晚 / 14:00→午） | 3.1（slotOfItem 左闭右开） | 【W1】 |
| §5.1.1-4a 休息条目独立区块 | 3.1（rests 分区）+ 4.2 | 【W1/W2】 |
| §5.1.1-5a 卡片四类信息 | 4.2 | 【W1】 |
| §5.1.1-6a/6b planned 色条 / done 完成样式 | 4.2 | 【W1】 |
| §5.1.1-7a 信息头徽章（周期/v3/LLM 规划） | 4.1 | 【W1】+ 8.1（文案 grep） |
| §5.1.1-7b 「下周计划」标注 | 4.1 + 6.1（isNextWeek 推导） | 【W2】 |
| §5.1.1-8a/8b unplaced 提示卡 / 空数组无占位 | 4.3 + 6.1（父层不挂载） | 【W2】 |
| §5.1.1-9a 无编辑/拖拽入口 | 4.2（零 emits） | 8.1-2【静态】+ 8.2 |
| §5.1.3-1 空态非错误（无报错弹窗） | 6.1 + 4.4 | 【W1/W2】 |
| §5.1.3-2 current 失败空态兜底 | 6.1（D15 空态非错误卡） | 【W11】 |
| §5.1.3-3 越界条目剔除 + 告警 | 3.1（buildWeekGrid 防御） | 8.2（console.warn 复核） |

### §5.2 计划生成（6 条）+ §5.2.3 异常

| spec 验收条件 | 覆盖任务 | 判定点 |
|---|---|---|
| §5.2.1-1a 空态生成渲染下周网格 | 6.2 + 4.4 | 【W2】 |
| §5.2.1-2a 文案含「下一周」 | 4.4 | 4.4 完成判定【静态 grep】 |
| §5.2.1-3a rules 降级徽章 + 提示 | 6.2 + 4.1 | 【W13】 |
| §5.2.1-3b llm 无降级提示 | 6.2 + 4.1 | 【W2/W13】 |
| §5.2.1-4a 归档说明文案 | 4.4 | 4.4 完成判定【静态 grep】 |
| §5.2.1-5a 生成成功不跳转 | 6.2 | 【W2】 |
| §5.2.3-1/2/3 失败/冲突/重复点击 | 6.2（catch 静默 + 锁） | 【W7/W11】 |

### §5.3 动态调整与 diff 预览（14+1 条）+ §5.3.3 异常

| spec 验收条件 | 覆盖任务 | 判定点 |
|---|---|---|
| §5.3.1-1a 发出 POST /plans/{id}/adjust | 6.3（id 取 sessionPlan.plan.id） | 【W4】 |
| §5.3.1-2a 未点击前仅 diff 预览 | 6.3（pendingNew + viewMode）+ 4.5 | 【W4】 |
| §5.3.1-2b 点击切换零请求 | 6.4（handleConfirmNewPlan） | 【W5】+ 6.4 静态佐证 |
| §5.3.1-2c 无确认/提交类请求 | 6.3 / 6.4 | 【W4/W5】 |
| §5.3.1-3a adjust_reason 显著展示 | 4.5 段① | 【W4】 |
| §5.3.1-3b moved 双栏标记 + 清单 | 4.5 段②③ + 3.1（markDiffHighlights） | 【W4】 |
| §5.3.1-3c removed 清单 | 4.5 段③ | 【W4】 |
| §5.3.1-4a 调整下周展示新版本条目 | 6.3（resolveNewVersionItems） | 【W4】 |
| §5.3.1-4b id 不命中不用 current items | 6.3（命中判定严格相等） | 【W4】+ 8.2 |
| §5.3.1-4c 多页过滤不缺不重 | 6.3（翻页取全 + MAX_PAGES=50） | 【W4】+ 8.2 |
| §5.3.1-4d 取数失败明确错误态 | 6.3（fetchError 错误卡） | 【W6】 |
| §5.3.1-5a adjusted=false 停留原视图 | 6.3（info 分支） | 【W4 构造或人工】 |
| §5.3.1-6a 关闭预览 = 新版本 + 提示 | 6.4 + 4.5（confirm 统一出口） | 【W5】 |
| §5.3.1-7a 全程不调 GET diff | 6.3（fetchPlanDiff 仅回看） | 6.3 完成判定【静态 grep】+【W4】 |
| §5.3.3-4d 错误卡文案含「调整已生效」语义 | 6.3（文案写死） | 8.1-4【静态 grep】+【W6】 |
| §5.3.3-1/2/5 adjust 失败/越权/并发归档 | 6.3（catch 静默维持原视图） | 【W11】 |
| §5.3.3-3 空 diff 显示「无条目变动」 | 4.5 段③ | 4.5 完成判定【静态 grep】 |

### §5.4 调整记录回看（5 条）+ §5.4.3 异常

| spec 验收条件 | 覆盖任务 | 判定点 |
|---|---|---|
| §5.4.1-1a/1b 入口按 parent_plan_id 显隐 | 4.1 | 【W12】 |
| §5.4.1-2a 理由 + 清单、无双栏 | 4.6 | 【W12】 |
| §5.4.1-3a 返回零请求 | 6.4（viewMode 回切） | 【W12】 |
| §5.4.1-4a 无应用/确认按钮 | 4.6 | 4.6 完成判定【静态 grep】 |
| §5.4.3-1 diff 失败停留原视图 | 6.4（catch 静默） | 【W12】 |
| §5.4.3-2 空结构提示 | 4.6 | 4.6 完成判定【静态 grep】 |

### §5.5 报告列表与查看（11 条）+ §5.5.3 异常

| spec 验收条件 | 覆盖任务 | 判定点 |
|---|---|---|
| §5.5.1-1a 首屏仅 weekly | 7.1 | 【W8】 |
| §5.5.1-1b tab 至多首次各 1 次、回切零请求 | 7.1（loaded 缓存） | 【W8】 |
| §5.5.1-2a monthly 请求 + 倒序渲染 | 7.1（前端不重排） | 【W8】 |
| §5.5.1-2b 分页第 2 页真实请求 | 7.1 | 【W8】 |
| §5.5.1-3a 区间头部显著 | 5.1 ① | 【W8】 |
| §5.5.1-4a 七要素分区数字一致 | 5.1 ③ | 【W8】 |
| §5.5.1-5a/5b 薄弱点色块 / 空态文案 | 5.1 ③ | 【W8】+ 5.1 静态 grep |
| §5.5.1-6a content=null 容错 | 5.1 + 1.2（全可选类型） | 【W8】+ 8.2 |
| §5.5.1-7a 「规则模板」徽章 | 3.2（generatedByLabel 仅 'llm'/'template'）+ 5.1 | 【W13】+ 8.1-3【静态】 |
| §5.5.1-8a 空 tab 无分页器 | 7.1 | 【W8】 |
| §5.5.3-1 列表失败空态可重试 | 7.1 | 【W11】 |
| §5.5.3-2 report_type 非法防御 | 1.2（字面量联合 TS 结构性排除）+ 7.1 | 8.1-1【静态】 |

### §5.6 报告生成与导出（8 条）+ §5.6.3 异常

| spec 验收条件 | 覆盖任务 | 判定点 |
|---|---|---|
| §5.6.1-1a 生成后重载 page=1 置顶 | 7.2（D9 重载路径） | 【W9】 |
| §5.6.1-1b 生成按钮飞行锁定 | 7.2（generatingReport） | 【W7】 |
| §5.6.1-2a 免手动刷新见新报告 | 7.2 | 【W9】 |
| §5.6.1-3a 导出零请求 | 5.1 ④（内联纯函数） | 【W10】 |
| §5.6.1-4a 文件名格式 | 3.2（buildReportFilename） | 【W10】 |
| §5.6.1-5a 结构完整无 undefined | 3.2（buildReportMarkdown 空态文案） | 【W10】 |
| §5.6.1-5b weak_points 空导出完整 | 3.2 | 【W10】 |
| §5.6.1-6a 依赖无变化 + URL 释放 | 3.2（revokeObjectURL） | 8.1-5/8.1-7【静态】 |
| §5.6.3-1 生成失败维持原状 | 7.2 | 【W11】 |
| §5.6.3-2 content=null 导出容错 | 3.2 | 【W10】 |
| §5.6.3-3 拦截下载提示 | 5.1 ④（try/catch + ElMessage） | 【W10 环境允许时】 |

### §6 数据约束与附录 A 裁定（无独立验收编号，逐节落点）

| spec 条目 | 覆盖任务 |
|---|---|
| §6.1 Plan / §6.2 PlanItem / §6.3 UnplacedTask / §6.4 PlanGenerateOut / §6.5 PlanDiffOut·PlanAdjustOut | 1.1 |
| §6.6 Report / §6.7 ReportContent（含 generated_by 'llm'\|'template' 勘误口径） | 1.2 |
| 裁定 #1 会话态混合加载 + 调整后服务端取数 | 6.1 / 6.2 / 6.3 |
| 裁定 #2 展示层两阶段、无放弃类按钮 | 4.5 / 6.4 |
| 裁定 #3 生成文案「下一周」 | 4.4 |
| 裁定 #4 三时段映射 + 休息区块 | 3.1 / 4.2 |
| 裁定 #5 unplaced 独立提示卡 | 4.3 |
| 裁定 #6 导出命名与结构 | 3.2 |
| 附录 B #1/#2 api 模块新建 / #3 不封装列表与详情 / #4 diff 端点仅回看消费 | 2.1 / 2.2 / 6.3 / 6.4 |

### 孤儿任务声明

**无孤儿任务**：全部 22 个子任务均可回溯至 spec 章节 / 验收条件或 spec 授权的工程验证要求——其中纯工程验证类任务 8.1（构建门禁 + 静态检查）来源 spec §4.4-1/4.4-2/§4.5-1/4.5-2/4.5-3 与 §5.3.3-4d；8.2（一致性核对）来源 spec 附录 A 与 §4.4-3/4.4-4；8.3（本机走查）来源 spec §4.5-3 授权（「沙箱无后端联调环境，交互走查留本机执行」）与 design 2.8-R1。除此之外无「无 spec 来源」的任务。

> **沙箱可完成 vs 留本机总结**：组 1–7 与 8.1/8.2 全部沙箱内可完成（`npm run build` 为门禁 + grep/git diff 静态检查）；**留本机项**为 8.3 的 W1–W13 共 13 条（请求序列、零请求切换、按钮锁、tab 缓存、导出文件名与内容、取数失败错误态、断网重试、回看、降级演练）。**本批最终判据：`npm run build` 通过 + 本机走查清单 W1–W13 全部通过。**