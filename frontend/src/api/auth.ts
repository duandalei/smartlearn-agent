/**
 * 认证接口封装（PROJECT_CONTEXT P3）。
 *
 * - POST /auth/register：注册（成功即返回 token，自动登录）。
 * - POST /auth/login：登录。
 * - GET  /auth/me：获取当前登录用户（token 校验 / 刷新用户信息）。
 *
 * 说明：request 实例 baseURL 已含 /api/v1，失败提示由统一拦截器展示。
 */
import request from '@/api/request'
import type { AuthResult, LoginPayload, RegisterPayload, UserInfo } from '@/types'

/**
 * 用户登录。
 *
 * @param payload 用户名 + 密码。
 * @returns token 与用户信息（AuthResult）。
 */
export function login(payload: LoginPayload): Promise<AuthResult> {
  return request.post('/auth/login', payload) as unknown as Promise<AuthResult>
}

/**
 * 注册新用户（后端注册成功即自动登录，返回结构同登录）。
 *
 * @param payload 用户名 + 密码 + 确认密码。
 * @returns token 与用户信息（AuthResult）。
 */
export function register(payload: RegisterPayload): Promise<AuthResult> {
  return request.post('/auth/register', payload) as unknown as Promise<AuthResult>
}

/**
 * 获取当前登录用户信息（用于刷新页面后校验 token 有效性）。
 *
 * @returns 当前用户（UserOut）。
 */
export function fetchMe(): Promise<UserInfo> {
  return request.get('/auth/me') as unknown as Promise<UserInfo>
}