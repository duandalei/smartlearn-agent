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
import MarkdownText from '@/components/common/MarkdownText.vue'
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
/** 源码/渲染切换：默认渲染 Markdown；需要核对原始切分时切到源码。 */
const showRaw = ref(false)

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
    size="min(480px, 92vw)"
    @update:model-value="close"
  >
    <template #header>
      <div class="drawer-head">
        <span class="drawer-title">
          {{ props.item ? `分块预览：${props.item.title}` : '分块预览' }}
        </span>
        <el-switch
          v-model="showRaw"
          size="small"
          active-text="源码"
          inactive-text="渲染"
        />
      </div>
    </template>
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
        <MarkdownText v-if="!showRaw" :content="chunk.content" class="chunk-content" />
        <div v-else class="chunk-content raw">{{ chunk.content }}</div>
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
}
.chunk-card {
  padding: 14px 0;
  border-bottom: 1px solid var(--line-soft);
}
.chunk-card:last-child {
  border-bottom: none;
}
/* 跳转定位的高亮分块：整块浅朱砂底 + 完整细边框 */
.chunk-card.highlighted {
  margin: 6px 0;
  padding: 14px 12px;
  background: var(--vermilion-wash);
  border: 1px solid #e4b6ac;
  border-radius: var(--radius);
}
.chunk-head {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
}
.chunk-path {
  font-size: 11px;
  color: var(--ink-3);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.drawer-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  width: 100%;
}
.drawer-title {
  font-family: var(--font-display);
  font-size: 19px;
  font-weight: 600;
  color: var(--ink);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.chunk-content {
  margin: 0;
  font-size: 13px;
  line-height: 1.75;
  color: var(--ink-2);
  word-break: break-word;
}
.chunk-content.raw {
  padding: 10px 12px;
  background: var(--paper-3);
  border: 1px solid var(--line);
  border-radius: var(--radius);
  font-family: var(--font-mono);
  font-size: 11px;
  line-height: 1.7;
  white-space: pre-wrap;
}
</style>