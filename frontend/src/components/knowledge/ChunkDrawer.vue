<script setup lang="ts">
/**
 * 知识库分块查看抽屉（P8，design.md 2.6.2-C；P9 增加跳转高亮）。
 *
 * el-drawer 打开时调 listKnowledgeChunks(itemId)，按 chunk_index 序
 * 渲染卡片列表：块号 + heading_path（次要文字）+ content 正文；后端
 * 全量返回无需分页。加载失败提示由 request.ts 拦截器统一弹出。
 *
 * P9 跳转承接：可选 prop highlight_chunk_index（问答来源卡定位），
 * 对应分块卡片加高亮样式 + scrollIntoView 定位（spec 5.4.1 规则 3）。
 */
import { nextTick, ref, watch } from 'vue'

import { listKnowledgeChunks } from '@/api/knowledge'
import type { KnowledgeChunk, KnowledgeItem } from '@/types'

const props = defineProps<{
  /** 抽屉可见性（v-model）。 */
  modelValue: boolean
  /** 目标文档（null 时抽屉不可用）。 */
  item: KnowledgeItem | null
  /** 跳转定位的分块序号（null = 无高亮，P9 来源卡承接）。 */
  highlightChunkIndex?: number | null
}>()

const emit = defineEmits<{
  (e: 'update:modelValue', value: boolean): void
}>()

const chunks = ref<KnowledgeChunk[]>([])
const loading = ref(false)

/** 高亮分块卡片的 DOM 引用（scrollIntoView 定位）。 */
let highlightEl: HTMLElement | null = null

/** 函数式 ref：仅高亮分块采集 DOM（条件绑定）。 */
function setHighlightRef(el: unknown): void {
  highlightEl = (el as HTMLElement | null) ?? null
}

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
    if (visible) {
      highlightEl = null
      void loadChunks().then(async () => {
        // 分块渲染完成后定位高亮分块（跳转承接场景）。
        if (props.highlightChunkIndex != null) {
          await nextTick()
          highlightEl?.scrollIntoView({ block: 'center', behavior: 'smooth' })
        }
      })
    }
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
      <div
        v-for="chunk in chunks"
        :key="chunk.id"
        :ref="chunk.chunk_index === props.highlightChunkIndex ? setHighlightRef : undefined"
        class="chunk-card"
        :class="{ highlighted: chunk.chunk_index === props.highlightChunkIndex }"
      >
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
/* 跳转定位的高亮分块（P9 来源卡承接） */
.chunk-card.highlighted {
  border-color: var(--el-color-primary);
  background: var(--el-color-primary-light-9);
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