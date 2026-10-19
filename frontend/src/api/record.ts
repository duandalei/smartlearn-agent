/**
 * 学习记录接口封装（P6）。
 *
 * - GET    /records              列表（分页 + 4 条件组合筛选）
 * - GET    /records/timeline     学习时间线（按天聚合补零）
 * - GET    /records/stats        学习统计（北京自然周/日口径）
 * - GET    /records/{id}         记录详情
 * - POST   /records              新建记录（触发掌握度重放 + 任务时长回填）
 * - PUT    /records/{id}         编辑记录（部分更新，提交即生效含显式 null）
 * - DELETE /records/{id}         删除记录（data 为被删快照）
 *
 * 错误提示由 request.ts 拦截器统一处理，业务层无需重复弹错。
 */
import request from '@/api/request'
import type {
  LearningRecord,
  PageResult,
  RecordCreatePayload,
  RecordListQuery,
  RecordStats,
  RecordUpdatePayload,
  TimelineData,
} from '@/types'

/**
 * 分页查询学习记录列表（start_date / end_date 闭区间，与课程、知识点 AND 组合）。
 *
 * @param params 分页与筛选参数（均可省略）。
 * @returns 分页结果（items 为 LearningRecord 数组，按日期 + id 降序）。
 */
export function fetchRecords(params: RecordListQuery): Promise<PageResult<LearningRecord>> {
  return request.get('/records', { params }) as unknown as Promise<PageResult<LearningRecord>>
}

/**
 * 查询记录详情。
 *
 * @param id 记录 id。
 * @returns 记录对象。
 */
export function fetchRecordDetail(id: number): Promise<LearningRecord> {
  return request.get(`/records/${id}`) as unknown as Promise<LearningRecord>
}

/**
 * 新建学习记录（后端同事务完成掌握度重放与任务时长回填）。
 *
 * @param payload 创建入参（content / duration_minutes / study_date 必填）。
 * @returns 新建的记录（含 id / created_at 全量字段）。
 */
export function createRecord(payload: RecordCreatePayload): Promise<LearningRecord> {
  return request.post('/records', payload) as unknown as Promise<LearningRecord>
}

/**
 * 编辑学习记录（字段级部分更新，显式 null 生效：mastery_level 置空退出
 * 聚合、task_id / course_id 置空解除关联）。
 *
 * @param id 记录 id。
 * @param payload 更新入参（仅提交要修改的字段）。
 * @returns 更新后的记录。
 */
export function updateRecord(id: number, payload: RecordUpdatePayload): Promise<LearningRecord> {
  return request.put(`/records/${id}`, payload) as unknown as Promise<LearningRecord>
}

/**
 * 删除学习记录（关联任务 actual_minutes 由后端重算，删空置 NULL）。
 *
 * @param id 记录 id。
 * @returns 被删除的记录快照。
 */
export function deleteRecord(id: number): Promise<LearningRecord> {
  return request.delete(`/records/${id}`) as unknown as Promise<LearningRecord>
}

/**
 * 查询学习时间线（恰 days 条、date 升序、无记录天补 0）。
 *
 * @param days 天数（1~365，默认 30）。
 * @returns TimelineData（items 末条恒为北京今天）。
 */
export function fetchRecordTimeline(days = 30): Promise<TimelineData> {
  return request.get('/records/timeline', {
    params: { days },
  }) as unknown as Promise<TimelineData>
}

/**
 * 查询学习统计（weekly_minutes / streak_days / total_count 全部后端计算）。
 *
 * @returns RecordStats。
 */
export function fetchRecordStats(): Promise<RecordStats> {
  return request.get('/records/stats') as unknown as Promise<RecordStats>
}