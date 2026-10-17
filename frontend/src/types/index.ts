/**
 * 全局 TypeScript 类型定义（与后端 Pydantic schema 对齐）。
 *
 * 约定：字段名与后端保持 snake_case（PROJECT_CONTEXT 8.3），
 * 仅展示层按需转 camelCase。本文件随业务阶段逐步扩展。
 */

/** 统一响应体：{code, message, data}（PROJECT_CONTEXT 5.2）。 */
export interface ApiResponse<T = unknown> {
  code: number
  message: string
  data: T
}

/** 分页数据结构（PROJECT_CONTEXT 5.3）。 */
export interface PageResult<T = unknown> {
  items: T[]
  total: number
  page: number
  page_size: number
}

/** 健康检查返回的 data。 */
export interface HealthData {
  status: string
}

/** 登录用户信息（占位，待认证阶段对齐后端 schema）。 */
export interface UserInfo {
  id: number
  username: string
  email?: string | null
}