/**
 * 课程只读接口封装（P2 上线接口的 P5 消费，design 2.2.4）。
 *
 * - GET /courses 分页查询（任务表单课程下拉数据源）。
 */
import request from '@/api/request'
import type { Course, PageResult } from '@/types'

/**
 * 分页查询课程列表。
 *
 * @param params 分页参数（任务页调用时传 page_size=100 拉全量）。
 * @returns 分页结果（items 为 Course 数组）。
 */
export function fetchCourses(params: { page?: number; page_size?: number }): Promise<PageResult<Course>> {
  return request.get('/courses', { params }) as unknown as Promise<PageResult<Course>>
}