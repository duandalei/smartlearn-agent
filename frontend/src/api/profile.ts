/**
 * 用户学习档案接口封装（PROJECT_CONTEXT P3）。
 *
 * - GET /profile：查询当前用户学习档案（不存在时后端惰性补建默认档案）。
 * - PUT /profile：字段级部分更新（仅提交要修改的字段）。
 */
import request from '@/api/request'
import type { UserProfile, UserProfileUpdatePayload } from '@/types'

/**
 * 查询当前用户学习档案。
 *
 * @returns 学习档案（UserProfile）。
 */
export function fetchProfile(): Promise<UserProfile> {
  return request.get('/profile') as unknown as Promise<UserProfile>
}

/**
 * 更新当前用户学习档案（部分更新语义）。
 *
 * @param payload 仅包含要修改的字段（非 null 即生效，未提交保持原值）。
 * @returns 更新后的完整档案（UserProfile）。
 */
export function updateProfile(payload: UserProfileUpdatePayload): Promise<UserProfile> {
  return request.put('/profile', payload) as unknown as Promise<UserProfile>
}