/**
 * 本地用户接口封装。
 *
 * - GET /auth/me：获取当前本地用户（无登录，无需 Token）。
 *
 * 说明：request 实例 baseURL 已含 /api/v1，失败提示由统一拦截器展示。
 */
import request from '@/api/request'
import type { UserInfo } from '@/types'

/**
 * 获取当前本地用户信息。
 *
 * @returns 当前用户（UserOut）。
 */
export function fetchMe(): Promise<UserInfo> {
  return request.get('/auth/me') as unknown as Promise<UserInfo>
}
