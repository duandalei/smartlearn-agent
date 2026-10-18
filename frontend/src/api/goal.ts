/**
 * 学习目标接口封装（P4，PROJECT_CONTEXT 8.2）。
 *
 * - GET    /goals              列表（分页 + status 筛选）
 * - POST   /goals              新建目标
 * - PUT    /goals/{id}         编辑目标（部分更新）
 * - DELETE /goals/{id}         删除目标（data 为被删对象）
 * - GET    /goals/{id}/roadmap 知识树查询
 * - POST   /goals/{id}/breakdown AI 拆解（单独 90s 超时）
 */
import request from '@/api/request'
import type {
  Goal,
  GoalCreatePayload,
  GoalListQuery,
  GoalRoadmap,
  GoalUpdatePayload,
  PageResult,
} from '@/types'

/** 拆解请求单独超时（毫秒）：不沿用全局 30s（spec 4.1 规则 5）。 */
export const BREAKDOWN_TIMEOUT_MS = 90000

/**
 * 分页查询学习目标列表（可按状态筛选）。
 *
 * @param params 分页与筛选参数（status 可省略）。
 * @returns 分页结果（items 为 Goal 数组）。
 */
export function fetchGoals(params: GoalListQuery): Promise<PageResult<Goal>> {
  return request.get('/goals', { params }) as unknown as Promise<PageResult<Goal>>
}

/**
 * 新建学习目标。
 *
 * @param payload 创建入参（title 必填）。
 * @returns 新建的目标（Goal）。
 */
export function createGoal(payload: GoalCreatePayload): Promise<Goal> {
  return request.post('/goals', payload) as unknown as Promise<Goal>
}

/**
 * 编辑学习目标（字段级部分更新，仅提交要修改的字段）。
 *
 * @param id 目标 id。
 * @param payload 更新入参。
 * @returns 更新后的目标（Goal）。
 */
export function updateGoal(id: number, payload: GoalUpdatePayload): Promise<Goal> {
  return request.put(`/goals/${id}`, payload) as unknown as Promise<Goal>
}

/**
 * 删除学习目标（关联任务/计划的 goal_id 由后端置空，掌握度保留）。
 *
 * @param id 目标 id。
 * @returns 被删除的目标（Goal）。
 */
export function deleteGoal(id: number): Promise<Goal> {
  return request.delete(`/goals/${id}`) as unknown as Promise<Goal>
}

/**
 * 查询目标知识树（roadmap=null 表示从未拆解）。
 *
 * @param id 目标 id。
 * @returns GoalRoadmap（roadmap 可空）。
 */
export function fetchGoalRoadmap(id: number): Promise<GoalRoadmap> {
  return request.get(`/goals/${id}/roadmap`) as unknown as Promise<GoalRoadmap>
}

/**
 * AI 拆解目标为知识树（后端同步返回，实测 ~10s，上限 90s）。
 *
 * axios 请求级 timeout 优先于实例配置 → 仅本请求覆盖为 90s；
 * 后端对同一目标的并发拆解互斥（1007），失败二分类文案见
 * `utils/goal.ts` 的 breakdownErrorMessage。
 *
 * @param id 目标 id。
 * @returns GoalRoadmap（含新知识树与拆解时间）。
 */
export function breakdownGoal(id: number): Promise<GoalRoadmap> {
  return request.post(`/goals/${id}/breakdown`, undefined, {
    timeout: BREAKDOWN_TIMEOUT_MS,
  }) as unknown as Promise<GoalRoadmap>
}