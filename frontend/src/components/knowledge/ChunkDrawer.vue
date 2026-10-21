<script setup lang="ts">
/**
 * 知识库分块查看抽屉（P8，design.md 2.6.2-C）。
 *
 * el-drawer 打开时调 listKnowledgeChunks(itemId)，按 chunk_index 序
 * 渲染卡片列表：块号 + heading_path（次要文字）+ content 正文；后端
 * 全量返回无需分页。加载失败提示由 request.ts 拦截器统一弹出。
 */
import { ref, watch } from 'vue'

import { listKnowledgeChunks } from '@/api/knowledge'
import type { KnowledgeChunk, KnowledgeItem } from '@/types'

const props = defineProps<{
  /** 抽屉可见性（v-model）。 */
  modelValue: boolean
  /** 目标文档（null 时抽屉不可用）。 */
  item: KnowledgeItem | null
}>()

const emit = defineEmits<{
  (e: 'update:modelValue', value: boolean): void
}>()

const chunks = ref<KnowledgeChunk[]>([])
const loading = ref(false)

/** 拉取全量分块（打开时触发）。 */
async function loadChunks(): Promise<void> {
  if (props.item == null) return
  loading.value = true
  chunks.value = []
  try {
    chunks.value = await listKnowledgeChunks(props.item.id)
  } catch {
    // 错误提示由拦截器统一弹出；抽屉保持空态。
  } finally {
    loading.value = false
  }
}

watch(
  () => props.modelValue,
  (visible) => {
    if (visible) void loadChunks()
  },
)

function close(): void {
  emit('update:modelValue', false)
}
</script>

<template>
  <el-drawer
    :model-value="props.modelValue"
    :title="props.item ? `分块预览：${props.item.title}` : '分块预览'"
    size="480px"
    @update:model-value="close"
  >
    <div v-loading="loading" class="chunk-list">
      <div v-for="chunk in chunks" :key="chunk.id" class="chunk-card">
        <div class="chunk-head">
          <el-tag size="small" type="info" effect="plain">#{{ chunk.chunk_index }}</el-tag>
          <span v-if="chunk.heading_path" class="chunk-path">{{ chunk.heading_path }}</span>
        </div>
        <p class="chunk-content">{{ chunk.content }}</p>
      </div>
      <el-empty
        v-if="!loading && chunks.length === 0"
        description="暂无分块"
        :image-size="80"
      />
    </div>
  </el-drawer>
</template>

<style scoped>
.chunk-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.chunk-card {
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 6px;
  padding: 12px;
  background: var(--el-fill-color-blank);
}
.chunk-head {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
}
.chunk-path {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
.chunk-content {
  margin: 0;
  font-size: 13px;
  line-height: 1.7;
  white-space: pre-wrap;
  word-break: break-word;
}
</style>