<script setup lang="ts">
/**
 * RAG 知识库页面：上传 + 文档列表 + 语义检索。
 * 轮询与视图状态逻辑保持不变，仅重排视觉层级。
 */
import { onMounted, onUnmounted, ref } from 'vue'
import { useRoute } from 'vue-router'

import PageHeader from '@/components/common/PageHeader.vue'
import ChunkDrawer from '@/components/knowledge/ChunkDrawer.vue'
import DocumentTable from '@/components/knowledge/DocumentTable.vue'
import SearchPanel from '@/components/knowledge/SearchPanel.vue'
import UploadPanel from '@/components/knowledge/UploadPanel.vue'
import { getKnowledgeItem, listKnowledgeItems } from '@/api/knowledge'
import type { KnowledgeItem } from '@/types'
import { isKbProcessing } from '@/utils/knowledge'

const route = useRoute()

/** 轮询间隔（spec 5.6.1 规则 7：3 秒条件轮询）。 */
const POLL_INTERVAL = 3000

/** 每页条数。 */
const PAGE_SIZE = 10

const items = ref<KnowledgeItem[]>([])
const total = ref(0)
const page = ref(1)
const loading = ref(false)

/** 轮询定时器句柄（undefined = 未在轮询）。 */
let pollTimer: number | undefined

/** 分块抽屉状态（视图持有目标文档）。 */
const drawerVisible = ref(false)
const activeItem = ref<KnowledgeItem | null>(null)

/** 跳转定位的分块高亮序号（P9 来源卡承接，null = 无高亮）。 */
const highlightChunkIndex = ref<number | null>(null)

/**
 * 处理来源卡跳转 query（?item_id=&chunk_index=）。
 * 详情调用使定位不受分页影响；失败即止，错误由拦截器统一提示。
 */
async function consumeLocateQuery(): Promise<void> {
  const rawItemId = Array.isArray(route.query.item_id)
    ? route.query.item_id[0]
    : route.query.item_id
  const rawChunk = Array.isArray(route.query.chunk_index)
    ? route.query.chunk_index[0]
    : route.query.chunk_index
  const itemId = Number(rawItemId)
  if (!rawItemId || !Number.isInteger(itemId) || itemId <= 0) return
  try {
    const item = await getKnowledgeItem(itemId)
    activeItem.value = item
    highlightChunkIndex.value =
      rawChunk != null && Number.isInteger(Number(rawChunk)) && Number(rawChunk) >= 0
        ? Number(rawChunk)
        : null
    drawerVisible.value = true
  } catch {
    // 文档不存在 / 不可见：提示由拦截器统一弹出，页面保持正常可用。
  }
}

function shouldPoll(list: KnowledgeItem[]): boolean {
  return list.some((item) => isKbProcessing(item.status))
}

function syncPoller(list: KnowledgeItem[]): void {
  if (shouldPoll(list) && pollTimer === undefined) {
    pollTimer = window.setInterval(() => void refreshItems(true), POLL_INTERVAL)
  } else if (!shouldPoll(list) && pollTimer !== undefined) {
    window.clearInterval(pollTimer)
    pollTimer = undefined
  }
}

async function refreshItems(silent = false): Promise<void> {
  if (!silent) loading.value = true
  try {
    const data = await listKnowledgeItems(page.value, PAGE_SIZE)
    items.value = data.items
    total.value = data.total
    syncPoller(data.items)
  } catch {
    // 错误提示由 request.ts 拦截器统一弹出；轮询模式下静默等下一周期。
  } finally {
    if (!silent) loading.value = false
  }
}

function onUploaded(): void {
  void refreshItems()
}

function onRefresh(): void {
  void refreshItems()
}

function onPageChange(next: number): void {
  page.value = next
  void refreshItems()
}

function onViewChunks(item: KnowledgeItem): void {
  activeItem.value = item
  highlightChunkIndex.value = null
  drawerVisible.value = true
}

onMounted(() => {
  void refreshItems()
  void consumeLocateQuery()
})

onUnmounted(() => {
  if (pollTimer !== undefined) {
    window.clearInterval(pollTimer)
    pollTimer = undefined
  }
})
</script>

<template>
  <div class="page kb-page">
    <PageHeader
      folio="卷六 · 藏书"
      title="知识库"
      lead="把你自己的资料放进来；AI 助手会先检索这里，再回答你的问题。"
    />

    <div class="kb-top">
      <section class="panel">
        <div class="panel__head">
          <div class="panel__title">上传文档</div>
          <span class="panel__sub">仅自己可见</span>
        </div>
        <div class="panel__body">
          <UploadPanel :items="items" @uploaded="onUploaded" />
        </div>
      </section>

      <section class="panel">
        <div class="panel__head">
          <div>
            <div class="panel__title">文档列表</div>
            <div class="panel__sub">个人库 · 共 {{ total }} 份</div>
          </div>
          <span class="panel__sub">解析完成后自动进入索引</span>
        </div>
        <div class="panel__body kb-docs">
          <DocumentTable
            :items="items"
            :loading="loading"
            :page="page"
            :page-size="PAGE_SIZE"
            :total="total"
            @view-chunks="onViewChunks"
            @refresh="onRefresh"
            @page-change="onPageChange"
          />
        </div>
      </section>
    </div>

    <section class="panel">
      <div class="panel__head">
        <div>
          <div class="panel__title">语义检索</div>
          <div class="panel__sub">在你的资料里找最相关的片段，并显示相似度</div>
        </div>
        <span class="seal seal--sm seal--ghost" aria-hidden="true">检</span>
      </div>
      <div class="panel__body">
        <SearchPanel />
      </div>
    </section>

    <ChunkDrawer
      v-model="drawerVisible"
      :item="activeItem"
      :highlight-chunk-index="highlightChunkIndex"
    />
  </div>
</template>

<style scoped>
.kb-top {
  display: grid;
  grid-template-columns: minmax(280px, 0.85fr) minmax(0, 1.6fr);
  gap: 20px;
  align-items: start;
}

.kb-docs {
  padding: 0;
}

@media (max-width: 1100px) {
  .kb-top {
    grid-template-columns: minmax(0, 1fr);
  }
}
</style>
