/**
 * 成长报告接口封装（P13 批次 1；design 2.2.1 / 2.2.2-(6)(7)）。
 *
 * - GET  /reports           报告分页列表（report_type 过滤，created_at 倒序直传）
 * - POST /reports/generate  生成报告（请求体仅 {report_type}）
 *
 * 明确不封装：GET /reports/{id} 详情（列表出参已含全部字段，无详情页场景，
 * design 2.2.1）。
 *
 * 错误提示由 request.ts 拦截器统一处理，业务层无需重复弹错。
 */
import request from '@/api/request'
import type { PageResult } from '@/types'
import type { Report, ReportGeneratePayload, ReportListQuery } from '@/types/report'

/**
 * 分页查询报告列表（后端按 created_at 倒序 + id 倒序 tie-break 直传，
 * 前端不重排；生成成功后重载 page=1 新报告必然置顶，决策 D9）。
 *
 * @param query 查询参数（report_type 必填三值之一；page 从 1 起）。
 * @returns 分页结果。
 */
export function fetchReports(query: ReportListQuery): Promise<PageResult<Report>> {
  return request.get('/reports', { params: query }) as unknown as Promise<PageResult<Report>>
}

/**
 * 生成报告（spec §5.6.1 规则 1）。
 *
 * 请求体仅 {report_type}——不传统计区间末日，恒用后端缺省最近完整周期
 * （daily=昨天 / weekly=上周日 / monthly=上月末，spec §1.4-4）。同周期重复
 * 生成追加新行（审计轨迹）；成功后视图层重置该 tab 至 page=1 重载列表。
 *
 * @param payload 生成入参（仅 report_type）。
 * @returns 新建的报告对象（content 含七要素与生成方式标记）。
 */
export function generateReport(payload: ReportGeneratePayload): Promise<Report> {
  return request.post('/reports/generate', payload) as unknown as Promise<Report>
}