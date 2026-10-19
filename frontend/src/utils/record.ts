/**
 * 学习记录页纯函数与常量（P6）。
 *
 * 全部为无副作用纯函数 + 只读常量；日期处理用原生 Date（禁
 * toISOString / 第三方日期库，规避 UTC 偏移导致日期错位）。
 */
import type { LearningRecord, RecordDateGroup } from '@/types'

/** 个位数补零。 */
function pad2(n: number): string {
  return String(n).padStart(2, '0')
}

/**
 * 本地今天 'YYYY-MM-DD'。
 *
 * 用本地年月日拼接而非 toISOString()（后者先转 UTC，东八区 0~8 点
 * 会得到昨天），平移 TaskFormDialog 的时区教训为公共工具。
 */
export function todayLocalStr(now: Date = new Date()): string {
  return `${now.getFullYear()}-${pad2(now.getMonth() + 1)}-${pad2(now.getDate())}`
}

/** 分钟数 → 「X 小时 Y 分钟」（0 或负数 → '0 分钟'；整小时省略分钟段）。 */
export function formatMinutes(total: number): string {
  if (total <= 0) return '0 分钟'
  const hours = Math.floor(total / 60)
  const minutes = total % 60
  if (hours === 0) return `${minutes} 分钟`
  if (minutes === 0) return `${hours} 小时`
  return `${hours} 小时 ${minutes} 分钟`
}

/** 学习日期 → 分组标题：今天 / 昨天 / 原样 'YYYY-MM-DD'。 */
export function dateGroupTitle(studyDate: string, now: Date = new Date()): string {
  if (studyDate === todayLocalStr(now)) return '今天'
  const yesterday = new Date(now.getFullYear(), now.getMonth(), now.getDate() - 1)
  if (studyDate === todayLocalStr(yesterday)) return '昨天'
  return studyDate
}

/**
 * 记录按 study_date 分组（组间日期降序 = 今天在前；组内保持传入顺序，
 * 列表接口已按 study_date desc + id desc 排序，即组内新记录在前）。
 */
export function groupRecordsByDate(
  records: LearningRecord[],
  now: Date = new Date(),
): RecordDateGroup[] {
  const map = new Map<string, LearningRecord[]>()
  for (const rec of records) {
    const list = map.get(rec.study_date)
    if (list) list.push(rec)
    else map.set(rec.study_date, [rec])
  }
  return [...map.entries()]
    .sort((a, b) => (a[0] < b[0] ? 1 : -1))
    .map(([date, recs]) => ({ date, title: dateGroupTitle(date, now), records: recs }))
}

/** 自评掌握分段（左闭右开：[0,40) 薄弱 / [40,70) 一般 / [70,100] 熟练）。 */
export const MASTERY_SEGMENTS = [
  { label: '薄弱', min: 0, max: 40, tagType: 'danger' },
  { label: '一般', min: 40, max: 70, tagType: 'warning' },
  { label: '熟练', min: 70, max: 101, tagType: 'success' },
] as const

/** 分段类型（由 MASTERY_SEGMENTS 推导，禁手写重复）。 */
export type MasterySegment = (typeof MASTERY_SEGMENTS)[number]

/**
 * 判定自评分数所属分段（末段 max=101 保证 100 落在「熟练」）。
 *
 * @param level 自评分数 0-100；null（跳过自评）返回 null。
 */
export function masterySegment(level: number | null): MasterySegment | null {
  if (level == null) return null
  return MASTERY_SEGMENTS.find((seg) => level >= seg.min && level < seg.max) ?? null
}