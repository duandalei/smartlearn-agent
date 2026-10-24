<script setup lang="ts">
/**
 * RAG 知识库页面（P8，design.md 2.6.1/2.6.3；D2 裁决：文件名与
 * 路由 /knowledge-base 均不变）。
 *
 * 页面骨架 = 上传卡片 + 文档列表卡片 + 检索测试卡片三区块；视图
 * 持有列表数据与轮询定时器，子组件 props 进 / emit 出不持有副本。
 *
 * 轮询逻辑（design.md 2.6.3）：POLL_INTERVAL = 3000；shouldPoll
 * 判存在 pending/parsing——存在非终态才保证定时器在跑，全部终态
 * 自动停止；触发点 = 上传成功回调 + 重新索引成功回调 + 页面初次
 * 加载；onUnmounted 清理定时器（路由切走不泄漏）；轮询请求失败
 * 静默重试（错误 toast 由 request.ts 拦截器统一弹出一次）。
 */
import { onMounted, onUnmounted, ref } from 'vue'
import { useRoute } from 'vue-router'

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
 * 处理来源卡跳转 query（?item_id=&chunk_index=，P9 spec 5.4.3）。
 *
 * 详情调用使定位不受分页影响（文档可能不在当前页列表中）；不可见
 * 或已删除统一 404（错误提示由拦截器统一弹出，不白屏）；历史快照
 * 过期场景按 item_id 尽力定位、失败即止。仅挂载时消费一次，避免
 * 站内刷新重复弹错。
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

/** 是否存在非终态文档（pending/parsing）——轮询启动/停止判定。 */
function shouldPoll(list: KnowledgeItem[]): boolean {
  return list.some((item) => isKbProcessing(item.status))
}

/** 同步轮询定时器状态：存在非终态保证在跑，全部终态自动停止。 */
function syncPoller(list: KnowledgeItem[]): void {
  if (shouldPoll(list) && pollTimer === undefined) {
    pollTimer = window.setInterval(() => void refreshItems(true), POLL_INTERVAL)
  } else if (!shouldPoll(list) && pollTimer !== undefined) {
    window.clearInterval(pollTimer)
    pollTimer = undefined
  }
}

/**
 * 拉取列表并同步轮询状态。
 *
 * @param silent 轮询静默模式（不切 loading，失败静默重试）。
 */
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

/** 上传受理成功 → 立即刷新（pending 状态自动触发轮询）。 */
function onUploaded(): void {
  void refreshItems()
}

/** 删除/重索引完成 → 刷新（重索引后 parsing 状态自动触发轮询）。 */
function onRefresh(): void {
  void refreshItems()
}

/** 翻页 → 按新页码拉取。 */
function onPageChange(next: number): void {
  page.value = next
  void refreshItems()
}

/** 查看分块（indexed 行）：清除跳转高亮（人工浏览场景）。 */
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
  <div class="kb-page">
    <h2 class="page-title">个人学习知识库</h2>
    <el-row :gutter="16">
      <el-col :xs="24" :lg="8">
        <el-card shadow="never" class="kb-card">
          <template #header><span>上传文档</span></template>
          <UploadPanel :items="items" @uploaded="onUploaded" />
        </el-card>
      </el-col>
      <el-col :xs="24" :lg="16">
        <el-card shadow="never" class="kb-card">
          <template #header><span>文档列表（个人库）</span></template>
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
        </el-card>
      </el-col>
    </el-row>
    <el-card shadow="never" class="kb-card">
      <template #header><span>语义检索</span></template>
      <SearchPanel />
    </el-card>
    <ChunkDrawer
      v-model="drawerVisible"
      :item="activeItem"
      :highlight-chunk-index="highlightChunkIndex"
    />
  </div>
</template>

<style scoped>
.kb-page {
  display: flex;
  flex-direction: column;
  gap: 16px;
}
.page-title {
  margin: 0;
  font-size: 20px;
}
.kb-card {
  margin-bottom: 0;
}
</style>