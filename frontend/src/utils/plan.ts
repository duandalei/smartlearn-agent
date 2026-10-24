/**
 * 计划周视图纯函数与常量（P13 批次 1；design 2.2.2-(9) / 2.4.3 / D4 / D5 / D6）。
 *
 * 全部为无副作用纯函数 + 只读常量；只 import types。日期处理用原生 Date
 * 组件拼接（不做 UTC 转换，决策 D10——对齐 utils/record.ts 时区教训）。
 *
 * 红线：diff 只用于高亮与改动清单，严禁作为新版本条目的数据来源
 * （spec §5.3.1 规则 4-⑤）。
 */
import type {
  ItemHighlight,
  Plan,
  PlanDiff,
  PlanItem,
  WeekColumnMeta,
  WeekGridColumn,
  WeekSlot,
} from '@/types/plan'

/** 三时段行渲染序标签（design 2.2.2-(9)）。 */
export const WEEK_SLOTS = ['上午', '下午', '晚上'] as const

/** 时段行标签类型（由 WEEK_SLOTS 推导，禁手写重复——对齐 utils/record.ts 惯例）。 */
export type WeekSlotLabel = (typeof WEEK_SLOTS)[number]

/**
 * 三时段窗口边界（决策 D5 / spec 裁定 #4，左闭右开；'HH:MM' 字符串字典序
 * 比较——ISO 短格式字典序 = 时间序，零解析成本）。常量集中本文件单点维护
 * （R8：后端窗口若变更只需改这里）。
 */
const SLOT_WINDOWS = {
  morning: { start: '09:00', end: '14:00' },
  afternoon: { start: '14:00', end: '19:00' },
  evening: { start: '19:00', end: '23:00' },
} as const

/** 列头星期标签（自然周周一 ~ 周日，与 buildWeekColumns 逐列顺序一致）。 */
const WEEKDAY_LABELS = ['周一', '周二', '周三', '周四', '周五', '周六', '周日'] as const

/** 个位数补零。 */
function pad2(n: number): string {
  return String(n).padStart(2, '0')
}

/** Date → 本地 'YYYY-MM-DD'（原生组件拼接，不做 UTC 转换，决策 D10）。 */
function localDateStr(d: Date): string {
  return `${d.getFullYear()}-${pad2(d.getMonth() + 1)}-${pad2(d.getDate())}`
}

/**
 * 由 plan.start_date 推导 7 列列头（design 2.2.2-(9)）。
 *
 * @param plan 计划（start_date 恒为周一，spec §6.1-8）。
 * @returns 7 列 {date: 'YYYY-MM-DD', label: '周一 10-26'}，逐列 +1 天。
 */
export function buildWeekColumns(plan: Plan): WeekColumnMeta[] {
  const [year, month, day] = plan.start_date.split('-').map(Number)
  const columns: WeekColumnMeta[] = []
  for (let i = 0; i < 7; i++) {
    const d = new Date(year, month - 1, day + i) // 本地构造，跨年/跨月由 Date 归一化
    columns.push({
      date: localDateStr(d),
      label: `${WEEKDAY_LABELS[i]} ${pad2(d.getMonth() + 1)}-${pad2(d.getDate())}`,
    })
  }
  return columns
}

/** 后端 time 字段序列化为 'HH:MM:SS'；展示统一截取 'HH:MM'。null 返回空串。 */
export function formatHm(t: string | null): string {
  return t ? t.slice(0, 5) : ''
}

/**
 * 条目时段归属判定（决策 D5；spec §5.1.1 规则 3）。
 *
 * start_time=null → 'rest'；'HH:MM' 字典序左闭右开三分支；早于 09:00 就近归
 * morning、不早于 23:00 归 evening——越界为后端不排的脏数据，就近归类并
 * console.warn 防御（不报错、不崩布局）。
 *
 * @param item 计划条目。
 * @returns 时段归属（rest = 休息条目，进独立区块不占三时段行，规则 4）。
 */
export function slotOfItem(item: PlanItem): WeekSlot {
  const t = item.start_time
  if (t == null) return 'rest'
  if (t < SLOT_WINDOWS.morning.start) {
    console.warn(`[slotOfItem] 条目 ${item.id} start_time=${t} 早于 ${SLOT_WINDOWS.morning.start}，就近归入上午`)
    return 'morning'
  }
  if (t < SLOT_WINDOWS.morning.end) return 'morning'
  if (t < SLOT_WINDOWS.afternoon.end) return 'afternoon'
  if (t < SLOT_WINDOWS.evening.end) return 'evening'
  console.warn(`[slotOfItem] 条目 ${item.id} start_time=${t} 不早于 ${SLOT_WINDOWS.evening.end}，就近归入晚上`)
  return 'evening'
}

/**
 * 构建周视图网格（design 2.2.2-(9)；spec §5.1.1 规则 2/3/4）。
 *
 * 每列 {date, label, slots:{morning,afternoon,evening}, rests:[]}；plan_date
 * 越界（不在 start~end）的条目剔除并 console.warn（spec §5.1.3-3 容错）；
 * 同时段内保持传入顺序（后端已按 plan_date + start_time 升序，前端不重排）。
 *
 * @param plan 计划。
 * @param items 该计划的全部条目（调用方保证同属 plan.id）。
 * @returns 7 列网格渲染结构。
 */
export function buildWeekGrid(plan: Plan, items: PlanItem[]): WeekGridColumn[] {
  const columns: WeekGridColumn[] = buildWeekColumns(plan).map((meta) => ({
    ...meta,
    slots: { morning: [], afternoon: [], evening: [] },
    rests: [],
  }))
  const indexByDate = new Map(columns.map((col, i) => [col.date, i]))
  for (const item of items) {
    const colIndex = indexByDate.get(item.plan_date)
    if (colIndex === undefined) {
      console.warn(`[buildWeekGrid] 条目 ${item.id} plan_date=${item.plan_date} 越界（计划周期 ${plan.start_date} ~ ${plan.end_date}），已剔除`)
      continue
    }
    const slot = slotOfItem(item)
    if (slot === 'rest') columns[colIndex].rests.push(item)
    else columns[colIndex].slots[slot].push(item)
  }
  return columns
}

/**
 * diff 高亮匹配（决策 D6；design 2.4.3）。
 *
 * diff 条目与网格条目分属两个数据集（diff 无 item id），用业务键对齐：
 * - moved：旧栏 (task_id, from_date, from_time) / 新栏 (task_id, to_date, to_time)；
 * - added：新栏 (task_id, plan_date, start_time)；
 * - removed：旧栏 (task_id, from_date)；
 * task_id 为 null 时降级 topic + 位置键（added/removed 降级不含时间位）。
 * 时间字段 null 与字符串宽松相等比较（rest 条目为 null）。
 *
 * 防御性降级（R4）：匹配不上一律不渲染高亮、不报错；多条 diff 命中同一条目
 * 按 moved > added > removed 优先级取一（互斥语义）。
 *
 * @param items 该侧栏目的条目数组（旧栏=oldItems 快照 / 新栏=服务端取回条目）。
 * @param diff 结构化改动清单。
 * @param side 'old' 左栏 / 'new' 右栏。
 * @returns Map<条目数组索引, 高亮类别>。
 */
export function markDiffHighlights(
  items: PlanItem[],
  diff: PlanDiff,
  side: 'old' | 'new',
): Map<number, ItemHighlight> {
  const highlights = new Map<number, ItemHighlight>()
  const findIndex = (pred: (item: PlanItem) => boolean): number => items.findIndex(pred)

  if (side === 'old') {
    for (const entry of diff.removed) {
      const idx = findIndex((it) =>
        entry.task_id != null
          ? it.task_id === entry.task_id && it.plan_date === entry.from_date
          : it.topic === entry.topic && it.plan_date === entry.from_date,
      )
      if (idx >= 0 && !highlights.has(idx)) highlights.set(idx, 'removed')
    }
  } else {
    for (const entry of diff.added) {
      const idx = findIndex((it) =>
        entry.task_id != null
          ? it.task_id === entry.task_id &&
            it.plan_date === entry.plan_date &&
            it.start_time == entry.start_time
          : it.topic === entry.topic && it.plan_date === entry.plan_date,
      )
      if (idx >= 0 && !highlights.has(idx)) highlights.set(idx, 'added')
    }
  }

  // moved 优先级最高（moved > added > removed），最后写入并允许覆盖
  for (const entry of diff.moved) {
    const date = side === 'old' ? entry.from_date : entry.to_date
    const time = side === 'old' ? entry.from_time : entry.to_time
    const idx = findIndex((it) =>
      entry.task_id != null
        ? it.task_id === entry.task_id && it.plan_date === date && it.start_time == time
        : it.topic === entry.topic && it.plan_date === date && it.start_time == time,
    )
    if (idx >= 0) highlights.set(idx, 'moved')
  }

  return highlights
}