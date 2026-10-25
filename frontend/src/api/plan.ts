/**
 * 学习计划接口封装（P13 批次 1；design 2.2.1 / 2.2.2-(1)~(5)）。
 *
 * - GET  /plans/current           当前生效计划及条目（data=null 为空态，非 404）
 * - GET  /plans/upcoming          最近一条尚未开始的生效计划及条目（同构空态）
 * - POST /plans/generate          生成计划（target 可选：next_week / current_week）
 * - POST /plans/{id}/adjust       动态调整（零字段体 {}，后端即时生效）
 * - GET  /plans/{id}/diff         调整记录回看（首版返回空结构，非错误）
 * - GET  /learning-plan-items     条目分页（无 plan_id 参数，客户端过滤用）
 *
 * 单请求粒度铁律（决策 D7）：翻页循环与 current 命中判定属视图编排（组 6），
 * 不在本层。明确不封装：GET /plans 列表、GET /plans/{id} 详情（design 2.2.1，
 * spec 附录 B #3）。
 *
 * 错误提示由 request.ts 拦截器统一处理，业务层无需重复弹错。
 */
import request from '@/api/request'
import type { PageResult } from '@/types'
import type {
  PlanAdjustResult,
  PlanCurrent,
  PlanDiff,
  PlanGenerateResult,
  PlanGenerateTarget,
  PlanItem,
} from '@/types/plan'

/**
 * 查询当前生效计划（start_date <= 今天 <= end_date 且 active）。
 *
 * 空态语义：无匹配返回 null（HTTP 200 + data=null，非 404，非错误）——
 * 调用方不得以 catch 处理空态（spec §5.1.1 规则 1-①）。
 *
 * @returns {plan, items} 或 null。
 */
export function fetchCurrentPlan(): Promise<PlanCurrent | null> {
  return request.get('/plans/current') as unknown as Promise<PlanCurrent | null>
}

/**
 * 查询最近一条尚未开始的生效计划（start_date > 今天，active）及条目。
 *
 * 用于回读「已生成但还没开始」的下周计划；空态返回 null（HTTP 200 +
 * data=null，非 404），调用方不得以 catch 处理空态。
 *
 * @returns {plan, items} 或 null。
 */
export function fetchUpcomingPlan(): Promise<PlanCurrent | null> {
  return request.get('/plans/upcoming') as unknown as Promise<PlanCurrent | null>
}

/**
 * 生成学习计划（LLM 失败自动降级规则引擎，降级不是错误，
 * 由响应 generated_by 字段区分，spec §5.2.1 规则 3）。
 *
 * target 缺省 next_week（保持原「下一个完整自然周」语义）；current_week
 * 生成本周剩余时间（周期仍为本周一~本周日，只排今天及以后）。
 *
 * 后置条件（spec §5.2.1 规则 1）：视图层以响应 {plan, items, unplaced_tasks,
 * generated_by} 直接渲染会话态，不得重查 current。同周期重生成会归档旧版
 * （规则 4，真实副作用；视图层必须先二次确认并以 loading 锁防重复提交）。
 *
 * @param target 目标周期，默认 next_week。
 * @returns 生成结果（含未排入任务清单）。
 */
export function generatePlan(
  target: PlanGenerateTarget = 'next_week',
): Promise<PlanGenerateResult> {
  return request.post('/plans/generate', { target }) as unknown as Promise<PlanGenerateResult>
}

/**
 * 动态调整指定计划（纯确定性零 LLM；planId = 当前展示计划的 id）。
 *
 * 后端即时生效（新版本落库、旧版归档）：视图层收到响应后必须继续完成
 * 新版本条目取数（spec §5.3.1 规则 4），不得停在中间态；响应 plan 仅元信息
 * 不含条目（spec §6.5-5）。adjusted=false 时 diff 为空结构，仅提示
 * adjust_reason（规则 5）。
 *
 * @param planId 当前展示计划的 id。
 * @returns 调整结果（含同构 diff——本流程禁止再调 fetchPlanDiff，规则 7）。
 */
export function adjustPlan(planId: number): Promise<PlanAdjustResult> {
  return request.post(`/plans/${planId}/adjust`, {}) as unknown as Promise<PlanAdjustResult>
}

/**
 * 查询版本对比（调整记录回看专用，spec §5.4）。
 *
 * 首版或父版本丢失返回空结构（base_plan_id=null、三个空数组，HTTP 200），
 * 不是错误。禁止在 adjust 即时流程调用（adjust 响应已含同构 diff）。
 *
 * @param planId 计划 id（前置：plan.parent_plan_id 非空）。
 * @returns 结构化改动清单。
 */
export function fetchPlanDiff(planId: number): Promise<PlanDiff> {
  return request.get(`/plans/${planId}/diff`) as unknown as Promise<PlanDiff>
}

/**
 * 分页查询当前用户全部计划条目（新版本条目取数的兜底路径，design 2.2.2-(5)）。
 *
 * 端点仅接受分页参数（无 plan_id 过滤），返回 id 升序全量条目；调用方翻页
 * 取全后按 plan_id 客户端过滤。仅由视图编排的兜底分支调用，不作为常规数据源。
 * 任何一页失败即整个取数流程失败（spec §5.3.3 场景 4）。
 *
 * @param page 页码（从 1 起）。
 * @param pageSize 页大小（调用方固定传 100，最小化翻页次数）。
 * @returns 分页结果。
 */
export function fetchLearningPlanItems(
  page: number,
  pageSize: number,
): Promise<PageResult<PlanItem>> {
  return request.get('/learning-plan-items', {
    params: { page, page_size: pageSize },
  }) as unknown as Promise<PageResult<PlanItem>>
}