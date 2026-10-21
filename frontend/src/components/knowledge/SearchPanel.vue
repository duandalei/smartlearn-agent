<script setup lang="ts">
/**
 * 知识库检索测试面板（P8，design.md 2.6.2-D）。
 *
 * 输入区：el-input（回车触发）+ top_k（1~20 默认 5）+ 搜索按钮
 * （loading 态）。结果区逐条卡片 = 片段正文 + 来源（次要文字）+
 * score 徽标（保留 2 位小数，**每条结果必须展示相似度分数——硬性
 * 要求**：分数是用户判断命中可信度的唯一量化依据）。
 *
 * 离线模式常驻警示（硬性要求，禁止一次性 toast）：检索响应
 * mode === 'offline' 时结果区上方渲染 el-alert type="warning"
 * （:closable="false"）常驻于当次结果之上；主文案逐字为
 * 「当前为离线检索模式」（spec 验收锚点）。
 *
 * 决策理由（design.md 2.6.2-D / 2.7-D）：2-gram 哈希兜底本质是
 * **词面匹配**而非**语义匹配**——离线时能召回与查询关键词重合的
 * 分块，但「换个说法问同一个问题」（同义改写、上下位词替换）会
 * 失效，因为兜底向量只编码 token 字面重合度，不具备语义泛化能力。
 * 这一能力差异从「结果正常返回」的外观上完全无法感知；若不显式
 * 告知，用户会把词面匹配的召回当作语义检索结果采信，形成错误的
 * 能力预期。因此降级必须对用户透明且**持续**可见（mode 透出 →
 * 常驻警示条 → 逐条分数展示三件套）。警示条由每次检索响应的 mode
 * 实时驱动（不依赖任何持久化状态），恢复 online 随该次响应消失。
 */
import { computed, ref } from 'vue'

import { searchKnowledge } from '@/api/knowledge'
import type { KnowledgeSearchHit } from '@/types'

const query = ref('')
const topK = ref(5)
const loading = ref(false)
/** 最近一次检索响应（null = 尚未检索过）。 */
const searched = ref<{ mode: 'online' | 'offline'; results: KnowledgeSearchHit[] } | null>(null)

/** 是否展示离线常驻警示条（仅当次结果为离线模式）。 */
const offline = computed(() => searched.value?.mode === 'offline')

async function doSearch(): Promise<void> {
  const q = query.value.trim()
  if (!q || loading.value) return
  loading.value = true
  try {
    const data = await searchKnowledge({ query: q, top_k: topK.value })
    searched.value = { mode: data.mode, results: data.results }
  } catch {
    // 错误提示由拦截器统一弹出；保留上一次成功结果不闪空。
  } finally {
    loading.value = false
  }
}

/** 分数展示（保留 2 位小数）。 */
function fmtScore(score: number): string {
  return score.toFixed(2)
}
</script>

<template>
  <div class="search-panel">
    <div class="search-bar">
      <el-input
        v-model="query"
        placeholder="输入问题检索知识库，如：Transformer 的注意力机制"
        maxlength="500"
        clearable
        @keyup.enter="doSearch"
      />
      <el-input-number v-model="topK" :min="1" :max="20" :step="1" controls-position="right" />
      <el-button type="primary" :loading="loading" @click="doSearch">搜索</el-button>
    </div>

    <el-alert
      v-if="offline"
      type="warning"
      :closable="false"
      show-icon
      class="offline-alert"
      title="当前为离线检索模式"
    >
      <p class="offline-desc">
        Embedding 服务不可用，当前为本地词面（关键词）匹配模式，语义理解能力受限：
        换一种问法可能无法命中，建议使用与原文一致的关键词；请结合每条结果的相似度分数自行判断可信度。
      </p>
    </el-alert>

    <div v-if="searched" class="result-area">
      <template v-if="searched.results.length">
        <div v-for="(hit, idx) in searched.results" :key="idx" class="hit-card">
          <div class="hit-head">
            <span class="hit-source">{{ hit.source_title }}</span>
            <span class="hit-score">相似度 {{ fmtScore(hit.score) }}</span>
          </div>
          <p class="hit-content">{{ hit.content }}</p>
        </div>
      </template>
      <el-empty v-else description="未命中相关内容" :image-size="80" />
    </div>
    <div v-else class="search-hint">输入问题并点击搜索，将同时在个人库与公共库中检索最相关的片段。</div>
  </div>
</template>

<style scoped>
.search-bar {
  display: flex;
  gap: 12px;
  align-items: center;
}
.search-bar .el-input {
  flex: 1 1 auto;
}
.search-bar .el-input-number {
  width: 100px;
  flex: 0 0 auto;
}
.offline-alert {
  margin-top: 12px;
}
.offline-desc {
  margin: 4px 0 0;
  font-size: 13px;
  line-height: 1.6;
}
.result-area {
  margin-top: 12px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.hit-card {
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 6px;
  padding: 12px 14px;
}
.hit-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
  margin-bottom: 8px;
}
.hit-source {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.hit-score {
  flex: 0 0 auto;
  font-size: 12px;
  color: var(--el-color-primary);
  background: var(--el-color-primary-light-9);
  border-radius: 10px;
  padding: 2px 10px;
}
.hit-content {
  margin: 0;
  font-size: 13px;
  line-height: 1.7;
  white-space: pre-wrap;
  word-break: break-word;
}
.search-hint {
  margin-top: 16px;
  font-size: 13px;
  color: var(--el-text-color-secondary);
}
</style>