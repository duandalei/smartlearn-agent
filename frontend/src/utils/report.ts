/**
 * 报告文案映射 / Markdown 拼装与下载（P13 批次 1；design 2.2.2-(10) / 2.4.6）。
 *
 * 全部为无副作用纯函数 + 只读常量；唯一副作用点是 downloadReportMarkdown
 * （DOM a 元素 + URL 释放，单列函数隔离）。只 import types 与 utils/record.ts
 * 复用项。时间处理用原生 Date 组件拼接（不做 UTC 转换，决策 D10）。
 *
 * 字面量铁律（决策 D11，spec §6.7-8 勘误后口径）：报告域降级标记为
 * 'template'，映射「规则模板」徽章；本文件任何位置不得引用计划域降级字面量。
 */
import type { Report, ReportType } from '@/types/report'
import { formatMinutes } from '@/utils/record'

/** 报告类型 → 中文标签（日报 / 周报 / 月报；tab 与导出文件名共用）。 */
export const REPORT_TYPE_LABELS: Record<ReportType, string> = {
  daily: '日报',
  weekly: '周报',
  monthly: '月报',
}

/**
 * 生成方式 → 徽章文案（决策 D11；spec §5.5.1 规则 7）。
 *
 * 只映射 'llm'→「LLM 总结」、'template'→「规则模板」；其他值或缺失返回
 * null（不显示徽章——运行期防御，未知值不当作合法字面量处理）。
 *
 * @param v content.generated_by 原始值。
 * @returns 徽章文案或 null。
 */
export function generatedByLabel(v: string | null | undefined): string | null {
  if (v === 'llm') return 'LLM 总结'
  if (v === 'template') return '规则模板'
  return null
}

/**
 * 导出文件名（裁定 #6；spec §5.6.1 规则 4）。
 *
 * 独立导出便于走查复核与单测。示例：学习周报_2026-10-12_2026-10-18.md
 *
 * @param report 报告对象。
 * @returns `学习{类型中文名}_{period_start}_{period_end}.md`。
 */
export function buildReportFilename(report: Report): string {
  return `学习${REPORT_TYPE_LABELS[report.report_type]}_${report.period_start}_${report.period_end}.md`
}

/**
 * created_at ISO 时间戳 → 本地 'YYYY-MM-DD HH:mm'（决策 D10）。
 *
 * 原生 Date 组件拼接（UTC 转换会致东八区日期错位，对齐 utils/record.ts
 * 时区教训，决策 D10）。
 *
 * @param iso ISO 时间戳字符串。
 * @returns 本地可读格式。
 */
export function formatCreatedAtLocal(iso: string): string {
  const d = new Date(iso)
  const pad = (n: number): string => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`
}

/** 差值带符号格式化（正负号语义保留，spec §6.7-6；0 输出 '0'）。 */
export function signed(n: number): string {
  return n > 0 ? `+${n}` : `${n}`
}

/**
 * 拼装报告 Markdown（固定结构，spec §5.6.1 规则 5；design 2.4.6 管线）。
 *
 * 结构：一级标题含区间 → 引言块（区间重申 + 生成时间）→ ## 摘要（空则整节
 * 省略）→ 七要素七节（每节空值落空态文案）→ 结尾分隔线 + 生成方式标注
 * （generated_by 缺省时结尾整块省略）。
 *
 * 边界与防御（design 2.4.6）：content=null 时仅含标题/引言/摘要（若有），
 * 不报错（spec §5.6.3-2）；字段缺失一律落空态文案，禁止拼出「undefined/null」
 * 字样（spec §5.6.1-5a）。
 *
 * @param report 报告对象。
 * @returns UTF-8 Markdown 纯文本。
 */
export function buildReportMarkdown(report: Report): string {
  const typeLabel = REPORT_TYPE_LABELS[report.report_type]
  const lines: string[] = []

  lines.push(`# 学习${typeLabel}（${report.period_start} 至 ${report.period_end}）`)
  lines.push('')
  lines.push(`> 统计区间：${report.period_start} 至 ${report.period_end}；生成时间：${formatCreatedAtLocal(report.created_at)}`)

  if (report.summary) {
    lines.push('', '## 摘要', '', report.summary)
  }

  const content = report.content
  if (content) {
    lines.push('', '## 学习时长', '')
    if (typeof content.total_minutes === 'number') {
      lines.push(`${formatMinutes(content.total_minutes)}（共 ${content.total_minutes} 分钟）`)
    } else {
      lines.push('本期暂无数据')
    }

    lines.push('', '## 任务完成', '')
    if (typeof content.task_completed === 'number' && typeof content.completion_rate === 'number') {
      lines.push(`完成 ${content.task_completed} 个任务，完成率 ${content.completion_rate}%`)
    } else if (typeof content.task_completed === 'number') {
      lines.push(`完成 ${content.task_completed} 个任务`)
    } else {
      lines.push('本期暂无数据')
    }

    lines.push('', '## 学习最多的方向', '', content.top_direction ?? '本期暂无')

    lines.push('', '## 薄弱知识点', '')
    const weakPoints = content.weak_points
    if (weakPoints && weakPoints.length > 0) {
      for (const wp of weakPoints) {
        lines.push(`- ${wp.knowledge_point}（${wp.mastery_score} 分）`)
      }
    } else {
      lines.push('本期无明显薄弱知识点')
    }

    lines.push('', '## 阶段进步', '')
    const progress = content.progress
    if (progress) {
      lines.push(`- 学习时长：较上一周期 ${signed(progress.minutes_diff)} 分钟`)
      lines.push(`- 完成任务：较上一周期 ${signed(progress.task_completed_diff)} 个`)
      if (progress.avg_mastery_diff != null) {
        lines.push(`- 平均掌握度：较上一周期 ${signed(progress.avg_mastery_diff)} 分`)
      }
    } else {
      lines.push('本期暂无对比数据')
    }

    lines.push('', '## 建议', '')
    const advice = content.advice
    if (advice && advice.length > 0) {
      advice.forEach((text, i) => lines.push(`${i + 1}. ${text}`))
    } else {
      lines.push('本期暂无建议')
    }
  }

  const genLabel = generatedByLabel(content?.generated_by)
  if (genLabel) {
    lines.push('', '---', '', `生成方式：${genLabel}`)
  }

  return lines.join('\n') + '\n'
}

/**
 * 下载报告 Markdown（纯前端行为，零请求零依赖；spec §5.6.1 规则 3/6）。
 *
 * Blob → createObjectURL → 临时 <a download> click → remove → revokeObjectURL
 * （同一宏任务内完成释放，禁止 URL 滞留）。浏览器拦截下载由调用方 try/catch
 * 兜底提示（spec §5.6.3-3）。
 *
 * @param report 报告对象。
 */
export function downloadReportMarkdown(report: Report): void {
  const md = buildReportMarkdown(report)
  const blob = new Blob([md], { type: 'text/markdown;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = buildReportFilename(report)
  document.body.appendChild(a)
  a.click()
  a.remove()
  URL.revokeObjectURL(url)
}