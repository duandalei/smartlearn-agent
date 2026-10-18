/**
 * 学习任务接口封装（P5，design 2.2.4）。
 *
 * - GET    /tasks                列表（分页 + 6 条件组合筛选）
 * - GET    /tasks/board          看板四列数据
 * - GET    /tasks/stats          统计（北京自然周/日口径）
 * - POST   /tasks                新建任务（status 固定 todo）
 * - GET    /tasks/{id}           任务详情
 * - PUT    /tasks/{id}           编辑任务（部分更新）
 * - DELETE /tasks/{id}           删除任务（data 为被删对象）
 * - PATCH  /tasks/{id}/status    状态流转（唯一合法的状态修改通道）
 *
 * 错误提示由 request.ts 拦截器统一处理，业务层无需重复弹错。
 */
import request from '@/api/request'
import type {
  PageResult,
  Task,
  TaskBoardData,
  TaskCreatePayload,
  TaskListQuery,
  TaskStats,
  TaskStatus,
  TaskStatusPayload,
  TaskUpdatePayload,
} from '@/types'

/**
 * 分页查询任务列表（6 筛选条件 AND 组合）。
 *
 * @param params 分页与筛选参数（均可省略）。
 * @returns 分页结果（items 为 Task 数组）。
 */
export function fetchTasks(params: TaskListQuery): Promise<PageResult<Task>> {
  return request.get('/tasks', { params }) as unknown as Promise<PageResult<Task>>
}

/**
 * 查询任务详情。
 *
 * @param id 任务 id。
 * @returns 任务对象。
 */
export function fetchTask(id: number): Promise<Task> {
  return request.get(`/tasks/${id}`) as unknown as Promise<Task>
}

/**
 * 新建任务（后端固定 status=todo、source=manual）。
 *
 * @param payload 创建入参（title 必填，不含 status / scheduled_date）。
 * @returns 新建的任务。
 */
export function createTask(payload: TaskCreatePayload): Promise<Task> {
  return request.post('/tasks', payload) as unknown as Promise<Task>
}

/**
 * 编辑任务（字段级部分更新，仅提交要修改的字段）。
 *
 * @param id 任务 id。
 * @param payload 更新入参。
 * @returns 更新后的任务。
 */
export function updateTask(id: number, payload: TaskUpdatePayload): Promise<Task> {
  return request.put(`/tasks/${id}`, payload) as unknown as Promise<Task>
}

/**
 * 删除任务（关联学习记录的 task_id 由后端 FK 置空）。
 *
 * @param id 任务 id。
 * @returns 被删除的任务。
 */
export function deleteTask(id: number): Promise<Task> {
  return request.delete(`/tasks/${id}`) as unknown as Promise<Task>
}

/**
 * 状态流转（合法性由后端 TRANSITIONS 状态机单点判定，非法流转 1007/400）。
 *
 * @param id 任务 id。
 * @param status 目标状态。
 * @returns 流转后的任务（含 completed_at 首次语义）。
 */
export function transitionTaskStatus(id: number, status: TaskStatus): Promise<Task> {
  const payload: TaskStatusPayload = { status }
  return request.patch(`/tasks/${id}/status`, payload) as unknown as Promise<Task>
}

/**
 * 查询看板四列数据（固定键 todo/in_progress/done/review，列内优先级降序）。
 *
 * @returns TaskBoardData（四键齐全，空列为空数组）。
 */
export function fetchBoard(): Promise<TaskBoardData> {
  return request.get('/tasks/board') as unknown as Promise<TaskBoardData>
}

/**
 * 查询任务统计（数值全部来自后端，前端零计算）。
 *
 * @returns TaskStats（today_todo_count 为今日待办数）。
 */
export function fetchStats(): Promise<TaskStats> {
  return request.get('/tasks/stats') as unknown as Promise<TaskStats>
}