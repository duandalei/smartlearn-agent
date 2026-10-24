/**
 * 报告域类型单一来源（design 2.3.2 全量；spec §6.6 / §6.7）。
 *
 * 与 types/index.ts 并存零耦合（对齐 types/agent.ts 先例：域类型独立文件）。
 * 传输字段全程保留 snake_case（PROJECT_CONTEXT §8.3）。
 *
 * 字面量铁律（决策 D11，spec §6.7-8 勘误后口径）：ReportContent.generated_by
 * 锁定 'llm' | 'template' | null；计划域 generate 的降级标记属另一套字面量，
 * 与本文件无关，本文件任何位置不得引用之。
 */

// ---------------------------------------------------------------------------
// 传输层（spec §6.6 / §6.7，对齐后端 schemas/report.py ReportOut）
// ---------------------------------------------------------------------------

/** 报告类型三值（tab 与文案映射的唯一依据；spec §6.6-2）。 */
export type ReportType = 'daily' | 'weekly' | 'monthly'

/** 薄弱知识点单项（spec §6.7-5）。 */
export interface ReportWeakPoint {
  knowledge_point: string
  mastery_score: number // 0–100
}

/** 阶段进步三差值（对比上一等长周期，正负号语义保留；spec §6.7-6）。 */
export interface ReportProgress {
  minutes_diff: number
  task_completed_diff: number
  avg_mastery_diff: number | null // 无对比数据时 null
}

/**
 * 报告七要素结构化内容（spec §6.7）。
 *
 * 全字段可选（design 2.3.2 说明 3）：存量报告可能部分字段缺失，
 * 「有则显示、无则隐藏分区」（spec §5.5.1 规则 6）在类型上即 optional。
 */
export interface ReportContent {
  total_minutes?: number
  task_completed?: number
  completion_rate?: number // 0–100，一位小数
  top_direction?: string | null
  weak_points?: ReportWeakPoint[] // 至多 3 项；空数组 = 本期无明显薄弱点
  progress?: ReportProgress
  advice?: string[]
  generated_by?: 'llm' | 'template' | null
}

/**
 * 学习成长报告（对齐后端 ReportOut；spec §6.6）。
 *
 * content 为 null 表示无结构化内容（JSONType 读出语义，不是空对象）；
 * 卡片按零数据容错渲染（仅头部 + 摘要），页面不报错（spec §5.5.1 规则 6）。
 */
export interface Report {
  id: number
  report_type: ReportType
  period_start: string // 'YYYY-MM-DD'
  period_end: string // 'YYYY-MM-DD'
  summary: string | null
  content: ReportContent | null
  created_at: string
}

/** 报告列表查询参数（GET /reports；page 从 1 起）。 */
export interface ReportListQuery {
  report_type: ReportType
  page?: number
  page_size?: number
}

/**
 * 生成报告入参（POST /reports/generate；spec §5.6.1 规则 1 / §1.4-4）。
 *
 * 仅 {report_type}——不传统计区间末日，恒用后端缺省最近完整周期
 * （daily=昨天 / weekly=上周日 / monthly=上月末）。
 */
export interface ReportGeneratePayload {
  report_type: ReportType
}