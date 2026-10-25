/** 模型 API 设置相关类型（与后端 schemas/settings.py 对齐）。 */

/** 对话配置状态。 */
export interface LlmChatSettings {
  base_url: string
  model: string
  has_api_key: boolean
  api_key_masked: string
  configured: boolean
}

/** 向量配置状态。 */
export interface LlmEmbeddingSettings {
  base_url: string
  model: string
  has_api_key: boolean
  api_key_masked: string
  effective_base_url: string
  effective_model: string
  configured: boolean
  fallback_to_llm: boolean
  missing: string[]
}

/** GET /settings/llm 返回结构。 */
export interface LlmSettingsStatus {
  configured: boolean
  source: 'env' | 'none'
  missing: string[]
  llm: LlmChatSettings
  embedding: LlmEmbeddingSettings
}

/** 保存 / 测试连接入参（Key 留空表示沿用旧值）。 */
export interface LlmSettingsPayload {
  llm_base_url: string
  llm_api_key: string
  llm_model: string
  embedding_base_url: string
  embedding_api_key: string
  embedding_model: string
}

/** 单组连接测试结果。 */
export interface LlmTestGroup {
  ok: boolean
  model?: string
  message?: string
  error?: string
  dimension?: number
}

/** POST /settings/llm/test 返回结构。 */
export interface LlmTestResult {
  chat: LlmTestGroup
  embedding: LlmTestGroup
}
