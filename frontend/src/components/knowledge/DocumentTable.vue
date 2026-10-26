<script setup lang="ts">
/**
 * 知识库文档列表（P8，design.md 2.6.2-B）。
 *
 * - 列：标题、类型、大小（formatFileSize）、分块数、状态（四色
 *   tag）、失败原因（failed 行直显 error_msg）、上传时间、操作列。
 * - 操作：查看分块（indexed 行）、重新索引（全部行，处理中禁用）、
 *   删除（全部行；公共库能力已移除）。
 * - 删除带 ElMessageBox.confirm；删除/重索引完成后 emit 'refresh'
 *   （视图刷新列表——重索引后存在 parsing 状态会自动启动轮询）。
 * - 分页 el-pagination 对齐后端 page/page_size/total；排序依赖后端
 *   id desc（新上传置顶），前端不排序。
 * - 错误提示由 request.ts 拦截器统一弹出（如越权删除 1005）。
 */
import { ElMessage, ElMessageBox } from 'element-plus'

import { deleteKnowledgeItem, reindexKnowledgeItem } from '@/api/knowledge'
import type { KnowledgeItem } from '@/types'
import { KB_STATUS_META, formatDateTime, formatFileSize, isKbProcessing } from '@/utils/knowledge'

const props = defineProps<{
  /** 文档列表数据（视图持有，props 进不持副本）。 */
  items: KnowledgeItem[]
  /** 表格加载态。 */
  loading: boolean
  /** 当前页码（1 起）。 */
  page: number
  /** 每页条数。 */
  pageSize: number
  /** 总条数。 */
  total: number
}>()

const emit = defineEmits<{
  /** 查看分块（indexed 行，视图打开 ChunkDrawer）。 */
  (e: 'view-chunks', item: KnowledgeItem): void
  /** 列表数据已变化（删除/重索引成功后，视图刷新）。 */
  (e: 'refresh'): void
  /** 翻页（视图按新页码拉取）。 */
  (e: 'page-change', page: number): void
}>()

/** 删除确认并发防抖（ElMessageBox 期间禁止二次点击）。 */
const deletingIds = new Set<number>()

/** 删除个人库文档（确认框 → API → 通知视图刷新）。 */
async function handleDelete(item: KnowledgeItem): Promise<void> {
  try {
    await ElMessageBox.confirm(
      `确定删除文档「${item.title}」？分块与向量将一并清理。`,
      '删除确认',
      { type: 'warning', confirmButtonText: '删除', cancelButtonText: '取消' },
    )
  } catch {
    return
  }
  if (deletingIds.has(item.id)) return
  deletingIds.add(item.id)
  try {
    await deleteKnowledgeItem(item.id)
    ElMessage.success('已删除')
    emit('refresh')
  } catch {
    // 错误提示由拦截器统一弹出（如 1005 文档不可见）。
  } finally {
    deletingIds.delete(item.id)
  }
}

/** 触发重新索引（toast + 通知视图刷新启动轮询）。 */
async function handleReindex(item: KnowledgeItem): Promise<void> {
  try {
    await reindexKnowledgeItem(item.id)
    ElMessage.success('已触发重新索引')
    emit('refresh')
  } catch {
    // 错误提示由拦截器统一弹出（如 1007 文档正在处理中）。
  }
}
</script>

<template>
  <div v-loading="props.loading" class="doc-list">
    <div v-if="props.items.length === 0" class="empty-note">
      <span class="seal seal--ghost" aria-hidden="true">藏</span>
      <div class="empty-note__title">还没有文档</div>
      <div>把 PDF、Word 或笔记拖进左侧上传区。</div>
    </div>

    <article v-for="item in props.items" :key="item.id" class="doc-row">
      <div class="doc-type" :class="`is-${item.source_type}`">
        {{ item.source_type.toUpperCase() }}
      </div>

      <div class="doc-main">
        <div class="doc-title" :title="item.title">{{ item.title }}</div>
        <div class="doc-meta">
          <span>{{ formatFileSize(item.file_size) }}</span>
          <span class="doc-dot">·</span>
          <span>{{ item.chunk_count }} 块</span>
          <span class="doc-dot">·</span>
          <span>{{ formatDateTime(item.created_at) }}</span>
        </div>
        <div v-if="item.status === 'failed'" class="doc-error">
          {{ item.error_msg ?? '解析失败，可尝试重新索引' }}
        </div>
      </div>

      <div class="doc-status">
        <el-tag
          :type="KB_STATUS_META[item.status as keyof typeof KB_STATUS_META].tag"
          size="small"
        >
          <span v-if="isKbProcessing(item.status)" class="status-loading" />
          {{ KB_STATUS_META[item.status as keyof typeof KB_STATUS_META].label }}
        </el-tag>
      </div>

      <div class="doc-actions">
        <el-button
          v-if="item.status === 'indexed'"
          link
          type="primary"
          size="small"
          @click="emit('view-chunks', item)"
        >
          查看分块
        </el-button>
        <el-button
          link
          size="small"
          :disabled="isKbProcessing(item.status)"
          @click="handleReindex(item)"
        >
          重新索引
        </el-button>
        <el-button link type="danger" size="small" @click="handleDelete(item)">
          删除
        </el-button>
      </div>
    </article>

    <div v-if="props.total > 0" class="table-footer">
      <el-pagination
        layout="total, prev, pager, next"
        :total="props.total"
        :page-size="props.pageSize"
        :current-page="props.page"
        @current-change="(p: number) => emit('page-change', p)"
      />
    </div>
  </div>
</template>

<style scoped>
.doc-list {
  min-height: 120px;
}

.doc-row {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  padding: 13px 18px;
  border-bottom: 1px solid var(--line-soft);
  transition: background-color 0.16s var(--ease);
}

.doc-row:hover {
  background: var(--paper-3);
}

.doc-row:last-of-type {
  border-bottom: none;
}

.doc-type {
  flex: 0 0 32px;
  height: 32px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-family: var(--font-mono);
  font-size: 9px;
  letter-spacing: 0.02em;
  color: var(--ink-3);
  background: var(--paper-3);
  border: 1px solid var(--line);
  border-radius: var(--radius);
}

.doc-type.is-pdf {
  color: #8f3325;
  background: var(--vermilion-wash);
  border-color: #e4b6ac;
}

.doc-type.is-md {
  color: #33513e;
  background: var(--jade-wash);
  border-color: #b3c9b9;
}

.doc-type.is-pptx {
  color: #7a5318;
  background: var(--ochre-wash);
  border-color: #ddc79b;
}

.doc-main {
  flex: 1 1 auto;
  min-width: 0;
}

.doc-title {
  font-size: 13.5px;
  font-weight: 600;
  line-height: 1.5;
  color: var(--ink);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.doc-meta {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
  margin-top: 4px;
  font-family: var(--font-mono);
  font-size: 9px;
  color: var(--ink-4);
}

.doc-dot {
  color: var(--line-strong);
}

.doc-error {
  margin-top: 5px;
  font-size: 11px;
  line-height: 1.6;
  color: var(--vermilion);
}

.doc-status {
  flex: 0 0 auto;
  padding-top: 6px;
}

.doc-actions {
  flex: 0 0 auto;
  display: flex;
  align-items: center;
  gap: 2px;
  max-width: 190px;
  flex-wrap: wrap;
  padding-top: 4px;
}

.table-footer {
  display: flex;
  justify-content: flex-end;
  padding: 12px 16px;
  border-top: 1px solid var(--line);
}

.status-loading {
  display: inline-block;
  width: 9px;
  height: 9px;
  margin-right: 4px;
  border: 2px solid currentColor;
  border-top-color: transparent;
  border-radius: 50%;
  animation: kb-spin 0.8s linear infinite;
  vertical-align: -1px;
}

@keyframes kb-spin {
  to {
    transform: rotate(360deg);
  }
}

@media (max-width: 720px) {
  .doc-row {
    flex-wrap: wrap;
  }

  .doc-main {
    flex-basis: calc(100% - 44px);
  }

  .doc-status {
    margin-left: 44px;
    padding-top: 6px;
  }

  .doc-actions {
    flex: 1 1 auto;
    max-width: none;
    justify-content: flex-end;
    padding: 8px 0 0 8px;
  }
}
</style>