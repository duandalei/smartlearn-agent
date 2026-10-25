/** 模型 API 设置接口封装。 */
import request from '@/api/request'
import type {
  LlmSettingsPayload,
  LlmSettingsStatus,
  LlmTestResult,
} from '@/types/settings'

/** 读取当前配置状态（Key 为掩码）。 */
export function fetchLlmSettings(): Promise<LlmSettingsStatus> {
  return request.get('/settings/llm') as unknown as Promise<LlmSettingsStatus>
}

/** 保存配置到 backend/.env（保存后立即生效）。 */
export function saveLlmSettings(
  payload: LlmSettingsPayload,
): Promise<LlmSettingsStatus> {
  return request.put('/settings/llm', payload) as unknown as Promise<LlmSettingsStatus>
}

/** 用表单当前值测试对话 / 向量连接（不保存）。 */
export function testLlmSettings(payload: LlmSettingsPayload): Promise<LlmTestResult> {
  return request.post('/settings/llm/test', payload) as unknown as Promise<LlmTestResult>
}
