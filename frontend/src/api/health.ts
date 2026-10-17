/**
 * 健康检查接口封装。
 *
 * `/health` 不带 /api/v1 前缀（PROJECT_CONTEXT 5.1），因此这里基于
 * VITE_API_BASE_URL 推导出后端根地址后再拼接，仍复用统一 request 实例，
 * 以便共享响应解包与错误提示逻辑。
 */
import request from '@/api/request'
import type { HealthData } from '@/types'

/** 后端服务根地址（由 API 基地址推导，去除 /api/v1 后缀）。 */
const API_ORIGIN: string = (() => {
  const base = import.meta.env.VITE_API_BASE_URL || window.location.origin
  try {
    return new URL(base, window.location.origin).origin
  } catch {
    return window.location.origin
  }
})()

/**
 * 调用后端健康检查接口。
 *
 * @returns 健康检查数据（含 status 字段）。
 */
export function healthCheck(): Promise<HealthData> {
  return request.get(`${API_ORIGIN}/health`) as unknown as Promise<HealthData>
}