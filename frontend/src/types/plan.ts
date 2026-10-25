/**
 * 计划域类型单一来源（design 2.3.2 全量；spec §6.1–§6.5）。
 *
 * 与 types/index.ts 并存零耦合（对齐 types/agent.ts 先例：域类型独立文件，
 * 仅计划域 import，不被其他模块反向依赖）。传输字段全程保留 snake_case
 * （PROJECT_CONTEXT §8.3——JSON 字段不做大小写转换）。
 *
 * 分两层：
 * - 传输层：逐字对齐后端 schemas/plan.py 出参（PlanOut / PlanItemOut /
 *   UnplacedTaskOut / PlanGenerateOut / PlanDiffOut / PlanAdjustOut）；
 * - 视图层：SessionPlan 会话态渲染数据源 + 周网格渲染结构 + PendingNewPlan
 *   diff 预览持有（design 2.3.2 说明 2）。
 */

// ---------------------------------------------------------------------------
// 传输层（spec §6.1–§6.5，对齐后端 schemas/plan.py）
// ---------------------------------------------------------------------------

/** 学习计划版本（对齐后端 PlanOut；spec §6.1）。 */
export interface Plan {
  id: number
  user_id: number // 出参存在但前端无消费，保留定义防字段漂移（design 2.3.2 说明 1）
  goal_id: number | null
  title: string
  version: number
  status: 'active' | 'archived'
  parent_plan_id: number | null
  source: 'agent' | 'manual'
  adjust_reason: string | null
  start_date: string // 'YYYY-MM-DD'
  end_date: string // 'YYYY-MM-DD'，恒为完整自然周（周一 ~ 周日）
  created_at: string
}

/** 学习计划条目（对齐后端 PlanItemOut；spec §6.2）。 */
export interface PlanItem {
  id: number
  plan_id: number
  plan_date: string // 'YYYY-MM-DD'
  start_time: string | null // 'HH:MM' 或 null（休息条目）
  end_time: string | null
  topic: string
  task_id: number | null
  estimated_minutes: number | null
  priority: 'low' | 'medium' | 'high' | null
  status: 'planned' | 'done' | 'skipped'
  created_at: string
}

/** 容量不足未排入的候选任务（对齐后端 UnplacedTaskOut；spec §6.3）。 */
export interface UnplacedTask {
  task_id: number | null
  title: string
  reason: string
}

/**
 * GET /plans/current 出参（data 为 null = 空态，非错误；spec §6.4-2 同构）。
 *
 * GET /plans/upcoming 复用同构出参：{plan, items} 或 null。
 */
export interface PlanCurrent {
  plan: Plan
  items: PlanItem[]
}

/** 计划生成目标周期（POST /plans/generate 的 target 字段）。 */
export type PlanGenerateTarget = 'next_week' | 'current_week'

/**
 * POST /plans/generate 出参（对齐后端 PlanGenerateOut；spec §6.4）。
 *
 * generated_by 为计划域字面量 'llm' | 'rules'（后端 Literal 锁定）；
 * 'rules' = LLM 失败降级规则引擎，触发「规则降级」徽章与提示（spec §5.2.1 规则 3）。
 */
export interface PlanGenerateResult {
  plan: Plan
  items: PlanItem[]
  unplaced_tasks: UnplacedTask[]
  generated_by: 'llm' | 'rules'
}

/** diff 被移动条目（from → to 五要素；spec §6.5-2）。 */
export interface DiffEntryMoved {
  topic: string
  task_id: number | null
  from_date: string
  from_time: string | null
  to_date: string
  to_time: string | null
  reason: string
}

/** diff 新增条目（调整路径通常为空；spec §6.5-3）。 */
export interface DiffEntryAdded {
  topic: string
  task_id: number | null
  plan_date: string
  start_time: string | null
  reason: string
}

/** diff 被移出条目（任务保留在任务列表；spec §6.5-4）。 */
export interface DiffEntryRemoved {
  topic: string
  task_id: number | null
  from_date: string
  reason: string
}

/**
 * 版本对比结构化改动清单（对齐后端 PlanDiffOut；spec §6.5）。
 *
 * 红线：diff 仅作对比展示与清单，严禁作为新版本条目的数据来源
 * （spec §5.3.1 规则 4-⑤——新版本条目一律服务端取回）。
 */
export interface PlanDiff {
  base_plan_id: number | null
  moved: DiffEntryMoved[]
  added: DiffEntryAdded[]
  removed: DiffEntryRemoved[]
}

/** POST /plans/{id}/adjust 出参（对齐后端 PlanAdjustOut；spec §6.5-5~7）。 */
export interface PlanAdjustResult {
  plan: Plan // 仅元信息，不含条目
  adjust_reason: string | null // adjusted=false 时为提示文案
  diff: PlanDiff
  adjusted: boolean
}

// ---------------------------------------------------------------------------
// 视图层（会话态与网格渲染结构，design 2.3.2 说明 2）
// ---------------------------------------------------------------------------

/** 条目时段归属（start_time 判定；rest = 休息条目进独立区块，spec §5.1.1 规则 3/4）。 */
export type WeekSlot = 'morning' | 'afternoon' | 'evening' | 'rest'

/** 周视图列头元信息（buildWeekColumns 产物：date + 「周一 10-26」式 label）。 */
export interface WeekColumnMeta {
  date: string // 'YYYY-MM-DD'
  label: string
}

/** 周视图单列渲染结构（三时段行 + 休息条目独立区块）。 */
export interface WeekGridColumn {
  date: string
  label: string
  slots: Record<'morning' | 'afternoon' | 'evening', PlanItem[]>
  rests: PlanItem[]
}

/** diff 高亮类别（markDiffHighlights 产物值；双栏渲染标记用）。 */
export type ItemHighlight = 'moved' | 'added' | 'removed'

/**
 * 会话态渲染数据源（design D2：周视图唯一数据来源）。
 *
 * origin 记录来源（current 本周基线 / upcoming 下周基线 / generate 生成 /
 * adjust 调整后切换）；计划数据本身不持久化，页面重进仍从接口读取。
 */
export interface SessionPlan {
  plan: Plan
  items: PlanItem[]
  origin: 'current' | 'upcoming' | 'generate' | 'adjust'
}

/**
 * diff 预览持有（design 2.3.2 说明 2）：adjust 响应 + 服务端取回的新版本条目
 * + 旧条目快照。「查看调整后的计划」确认后 items 引用转移给 SessionPlan，
 * 保证 diff 右栏与切换后周视图一致性（零请求切换，spec 裁定 #2）。
 */
export interface PendingNewPlan {
  plan: Plan
  items: PlanItem[]
  diff: PlanDiff
  oldItems: PlanItem[]
  adjustReason: string | null
}