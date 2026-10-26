<script setup lang="ts">
/**
 * 设置页：模型 API 配置（本地单用户）。
 *
 * - 读取 GET /settings/llm（Key 只返回掩码）
 * - 保存 PUT /settings/llm：写 backend/.env 并热加载，无需重启
 * - 测试 POST /settings/llm/test：对话（含 tools）与向量连接
 */
import { onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'

import PageHeader from '@/components/common/PageHeader.vue'
import { fetchLlmSettings, saveLlmSettings, testLlmSettings } from '@/api/settings'
import type { LlmSettingsStatus, LlmTestResult } from '@/types/settings'

const loading = ref(false)
const saving = ref(false)
const testing = ref(false)
const status = ref<LlmSettingsStatus | null>(null)
const testResult = ref<LlmTestResult | null>(null)

const form = reactive({
  llm_base_url: '',
  llm_api_key: '',
  llm_model: '',
  embedding_base_url: '',
  embedding_api_key: '',
  embedding_model: '',
})

/** 常用配置示例（以服务商最新文档为准）。 */
const examples = [
  {
    provider: 'DeepSeek',
    baseUrl: 'https://api.deepseek.com',
    model: 'deepseek-chat',
    embedding: '通常不提供 Embedding',
  },
  {
    provider: '硅基流动',
    baseUrl: 'https://api.siliconflow.cn/v1',
    model: 'Qwen/Qwen2.5-7B-Instruct',
    embedding: '支持，如 BAAI/bge-m3',
  },
  {
    provider: 'OpenAI',
    baseUrl: 'https://api.openai.com/v1',
    model: 'gpt-4o-mini',
    embedding: '支持，如 text-embedding-3-small',
  },
  {
    provider: 'Moonshot',
    baseUrl: 'https://api.moonshot.cn/v1',
    model: 'moonshot-v1-8k',
    embedding: '以官方文档为准',
  },
  {
    provider: '智谱',
    baseUrl: 'https://open.bigmodel.cn/api/paas/v4',
    model: 'glm-4-flash',
    embedding: '以官方兼容文档为准',
  },
]

/** 读取当前配置（Key 不回显明文）。 */
async function load(): Promise<void> {
  loading.value = true
  try {
    const data = await fetchLlmSettings()
    status.value = data
    form.llm_base_url = data.llm.base_url
    form.llm_model = data.llm.model
    form.embedding_base_url = data.embedding.base_url
    form.embedding_model = data.embedding.model
    form.llm_api_key = ''
    form.embedding_api_key = ''
  } finally {
    loading.value = false
  }
}

onMounted(load)

/** 保存到 .env（Key 留空则沿用已保存值）。 */
async function onSave(): Promise<void> {
  saving.value = true
  try {
    const data = await saveLlmSettings({ ...form })
    status.value = data
    form.llm_api_key = ''
    form.embedding_api_key = ''
    testResult.value = null
    ElMessage.success('配置已保存，立即生效')
  } finally {
    saving.value = false
  }
}

/** 用当前表单值测试连接（不保存）。 */
async function onTest(): Promise<void> {
  testing.value = true
  testResult.value = null
  try {
    testResult.value = await testLlmSettings({ ...form })
  } finally {
    testing.value = false
  }
}

/** API Key 输入框占位符。 */
function keyPlaceholder(hasKey: boolean, masked: string): string {
  return hasKey ? `已保存：${masked}，留空不修改` : '请输入 API Key'
}
</script>

<template>
  <div class="page settings-view">
    <PageHeader
      folio="卷九 · 设置"
      title="设置"
      lead="配置模型 API；保存后立即生效，不需要重启后端。"
    />

    <section v-loading="loading" class="panel">
      <div class="panel__head">
        <div>
          <div class="panel__title">模型 API</div>
          <div class="panel__sub">任意 OpenAI 兼容接口</div>
        </div>
        <el-tag v-if="status?.configured" type="success" effect="plain">已配置</el-tag>
        <el-tag v-else type="warning" effect="plain">未配置</el-tag>
      </div>

      <div class="panel__body">
        <el-alert
          type="info"
          :closable="false"
          show-icon
          title="支持任意 OpenAI 兼容接口，不限于 DeepSeek / 硅基流动"
          description="对话模型必须支持 tool calling；向量模型必须支持 /v1/embeddings。两者可以是不同服务商。"
          class="settings-alert"
        />

        <el-form label-position="top" class="settings-form">
          <div class="form-section">
            <div class="form-section__title">对话模型<span>必填</span></div>
            <el-row :gutter="20">
              <el-col :xs="24" :md="12">
                <el-form-item label="Base URL">
                  <el-input
                    v-model="form.llm_base_url"
                    placeholder="如 https://api.deepseek.com 或 https://api.siliconflow.cn/v1"
                    clearable
                  />
                </el-form-item>
              </el-col>
              <el-col :xs="24" :md="12">
                <el-form-item label="模型名">
                  <el-input
                    v-model="form.llm_model"
                    placeholder="如 deepseek-chat、Qwen/Qwen2.5-7B-Instruct"
                    clearable
                  />
                </el-form-item>
              </el-col>
              <el-col :xs="24">
                <el-form-item label="API Key">
                  <el-input
                    v-model="form.llm_api_key"
                    type="password"
                    show-password
                    autocomplete="new-password"
                    :placeholder="
                      keyPlaceholder(!!status?.llm.has_api_key, status?.llm.api_key_masked || '')
                    "
                  />
                </el-form-item>
              </el-col>
            </el-row>
          </div>

          <div class="form-section">
            <div class="form-section__title">
              向量模型<span>可选，留空回退对话配置</span>
            </div>
            <el-row :gutter="20">
              <el-col :xs="24" :md="12">
                <el-form-item label="Base URL">
                  <el-input
                    v-model="form.embedding_base_url"
                    placeholder="留空沿用对话 Base URL"
                    clearable
                  />
                </el-form-item>
              </el-col>
              <el-col :xs="24" :md="12">
                <el-form-item label="模型名">
                  <el-input
                    v-model="form.embedding_model"
                    placeholder="留空沿用对话模型；建议 BAAI/bge-m3"
                    clearable
                  />
                </el-form-item>
              </el-col>
              <el-col :xs="24">
                <el-form-item label="API Key">
                  <el-input
                    v-model="form.embedding_api_key"
                    type="password"
                    show-password
                    autocomplete="new-password"
                    :placeholder="
                      status?.embedding.has_api_key
                        ? `已保存：${status?.embedding.api_key_masked || ''}，留空不修改`
                        : '留空沿用对话 API Key'
                    "
                  />
                </el-form-item>
              </el-col>
            </el-row>
          </div>

          <div class="form-actions">
            <el-button type="primary" :loading="saving" @click="onSave">保存配置</el-button>
            <el-button :loading="testing" @click="onTest">测试连接</el-button>
            <span class="form-actions__hint">Key 留空表示沿用已保存值</span>
          </div>
        </el-form>

        <div v-if="testResult" class="test-result">
          <el-alert
            :type="testResult.chat.ok ? 'success' : 'error'"
            :closable="false"
            show-icon
            :title="`对话模型：${testResult.chat.ok ? '连接成功' : '连接失败'}`"
            :description="testResult.chat.message || testResult.chat.error || ''"
          />
          <el-alert
            :type="testResult.embedding.ok ? 'success' : 'error'"
            :closable="false"
            show-icon
            :title="`向量模型：${testResult.embedding.ok ? '连接成功' : '连接失败'}`"
            :description="testResult.embedding.message || testResult.embedding.error || ''"
          />
        </div>
      </div>
    </section>

    <section class="panel">
      <div class="panel__head">
        <div>
          <div class="panel__title">支持范围与注意事项</div>
          <div class="panel__sub">配置前先读一遍</div>
        </div>
      </div>
      <div class="panel__body">
        <ul class="tips">
          <li>对话模型必须支持 <strong>tool calling</strong>，否则 AI 助手无法调用工具。</li>
          <li>向量模型必须支持 <strong>/v1/embeddings</strong>；留空时逐项回退对话配置。</li>
          <li>更换向量模型后需要重建知识库索引（不同模型维度可能不同）。</li>
          <li>RAG 相似度阈值 0.55 是按 bge-m3 调的，换模型后可能需要调整。</li>
          <li>保存后立即生效；手动修改 <code>backend/.env</code> 则需重启后端。</li>
        </ul>

        <el-collapse>
          <el-collapse-item title="常用配置示例（以服务商最新文档为准）" name="examples">
            <el-table :data="examples" size="small">
              <el-table-column prop="provider" label="服务商" width="120" />
              <el-table-column prop="baseUrl" label="Base URL" min-width="240" />
              <el-table-column prop="model" label="对话模型示例" min-width="180" />
              <el-table-column prop="embedding" label="向量说明" min-width="180" />
            </el-table>
          </el-collapse-item>
        </el-collapse>
      </div>
    </section>
  </div>
</template>

<style scoped>
.settings-form {
  max-width: 960px;
}

.settings-alert {
  margin-bottom: 22px;
}

.test-result {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin-top: 20px;
  padding-top: 16px;
  border-top: 1px solid var(--line);
}

.tips {
  margin: 0 0 16px;
  padding-left: 18px;
  color: var(--ink-2);
  font-size: 13px;
  line-height: 1.9;
}

.tips li::marker {
  color: var(--vermilion);
}

.tips code {
  padding: 1px 5px;
  background: var(--paper-3);
  border: 1px solid var(--line-soft);
  border-radius: var(--radius);
  font-family: var(--font-mono);
  font-size: 11px;
}
</style>
