/**
 * Axios 统一封装与拦截器（PROJECT_CONTEXT 7.3）。
 *
 * - 实例：baseURL 取自 VITE_API_BASE_URL，timeout 30s。
 * - 本地单用户，不注入 Token，也不跳登录页。
 * - 响应拦截器：
 *     code === 0 -> 直接返回 data（业务层无需解包）；
 *     code !== 0 -> ElMessage.error + reject；
 *     网络错误   -> 统一提示「网络异常，请稍后重试」。
 *
 * 所有业务接口函数返回 Promise<T>，T 定义在 src/types。
 */
import axios, { type AxiosInstance, type AxiosResponse } from 'axios'
import { ElMessage } from 'element-plus'

import type { ApiResponse } from '@/types'

/** 业务码：成功 */
const CODE_SUCCESS = 0

const request: AxiosInstance = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || '/api/v1',
  timeout: 30000,
  // 不设置全局 Content-Type：Axios 会按 data 类型自动选择
  // （普通对象 → application/json；FormData → 交给浏览器附加 multipart boundary）。
  // 若在此固定 application/json，文件上传的 multipart 头会被覆盖，
  // 后端解析不到 file 字段，返回 422 / 1001「参数校验失败」。
})

// ---------------------------------------------------------------------------
// 响应拦截器：统一解包 + 错误提示
// ---------------------------------------------------------------------------
// 说明：本拦截器在成功后把 `{code, message, data}` 解包为 `data` 返回，
// 返回值类型不再等于 axios 声明的 `AxiosResponse`，因此显式做一次类型断言，
// 业务层拿到的即为解包后的 `data`（见各 api/*.ts 的 `Promise<T>` 返回类型）。
type RawFulfilled = (response: AxiosResponse) => AxiosResponse

const unwrapResponse = ((response: AxiosResponse<ApiResponse>) => {
  const res = response.data

  // 非标准结构（如文件流）直接返回原始数据
  if (res == null || typeof res.code !== 'number') {
    return response.data
  }

  if (res.code === CODE_SUCCESS) {
    // 成功：直接把 data 交给业务层
    return res.data
  }

  ElMessage.error(res.message || '请求失败')
  return Promise.reject(new Error(res.message || '请求失败'))
}) as unknown as RawFulfilled

request.interceptors.response.use(
  unwrapResponse,
  (error: unknown) => {
    // 统一处理 HTTP / 网络错误
    if (axios.isAxiosError(error)) {
      const status = error.response?.status
      if (status === 401) {
        ElMessage.error('请求未授权')
      } else if (status === 403) {
        ElMessage.error('无权限访问该资源')
      } else if (error.response) {
        const msg =
          (error.response.data as ApiResponse | undefined)?.message ||
          `请求异常（HTTP ${status}）`
        ElMessage.error(msg)
      } else {
        ElMessage.error('网络异常，请稍后重试')
      }
    } else {
      ElMessage.error('网络异常，请稍后重试')
    }
    return Promise.reject(error)
  },
)

export default request
