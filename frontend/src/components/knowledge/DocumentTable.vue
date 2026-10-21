<script setup lang="ts">
/**
 * 知识库文档列表（P8，design.md 2.6.2-B）。
 *
 * - 列：标题（公共文档加「公共」tag）、类型、大小（formatFileSize）、
 *   分块数、状态（四色 tag）、失败原因（failed 行直显 error_msg）、
 *   上传时间、操作列。
 * - 操作：查看分块（indexed 行）、重新索引（全部行，处理中禁用）、
 *   删除（仅个人库行渲染；公共行不渲染删除按钮）。
 * - 删除带 ElMessageBox.confirm；删除/重索引完成后 emit 'refresh'
 *   （视图刷新列表——重索引后存在 parsing 状态会自动启动轮询）。
 * - 分页 el-pagination 对齐后端 page/page_size/total；排序依赖后端
 *   id desc（新上传置顶），前端不排序。
 * - 错误提示由 request.ts 拦截器统一弹出（如公共文档误删 1004）。
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

/** 类型 tag 颜色（五格式固定映射，纯展示）。 */
const TYPE_TAG: Record<string, string> = {
  pdf: 'danger',
  docx: 'primary',
  pptx: 'warning',
  md: 'success',
  txt: 'info',
}

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
    // 错误提示由拦截器统一弹出（如 1004 公共文档不可删除）。
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
  <el-table :data="props.items" v-loading="props.loading" stripe>
    <el-table-column label="标题" min-width="220" show-overflow-tooltip>
      <template #default="{ row }">
        <el-tag v-if="row.scope === 'public'" size="small" class="scope-tag">公共</el-tag>
        <span>{{ row.title }}</span>
      </template>
    </el-table-column>
    <el-table-column label="类型" width="80">
      <template #default="{ row }">
        <el-tag :type="TYPE_TAG[row.source_type] ?? 'info'" size="small" effect="plain">
          {{ row.source_type.toUpperCase() }}
        </el-tag>
      </template>
    </el-table-column>
    <el-table-column label="大小" width="90">
      <template #default="{ row }">{{ formatFileSize(row.file_size) }}</template>
    </el-table-column>
    <el-table-column label="分块数" width="80" align="center">
      <template #default="{ row }">{{ row.chunk_count }}</template>
    </el-table-column>
    <el-table-column label="状态" width="100">
      <template #default="{ row }">
        <el-tag :type="KB_STATUS_META[row.status as keyof typeof KB_STATUS_META].tag" size="small">
          <span v-if="isKbProcessing(row.status)" class="status-loading" />
          {{ KB_STATUS_META[row.status as keyof typeof KB_STATUS_META].label }}
        </el-tag>
      </template>
    </el-table-column>
    <el-table-column label="失败原因" min-width="180" show-overflow-tooltip>
      <template #default="{ row }">
        <span v-if="row.status === 'failed'" class="error-msg">{{ row.error_msg ?? '—' }}</span>
        <span v-else>—</span>
      </template>
    </el-table-column>
    <el-table-column label="上传时间" width="150">
      <template #default="{ row }">{{ formatDateTime(row.created_at) }}</template>
    </el-table-column>
    <el-table-column label="操作" width="210" fixed="right">
      <template #default="{ row }">
        <el-button
          v-if="row.status === 'indexed'"
          link
          type="primary"
          size="small"
          @click="emit('view-chunks', row)"
        >
          查看分块
        </el-button>
        <el-button
          link
          type="warning"
          size="small"
          :disabled="isKbProcessing(row.status)"
          @click="handleReindex(row)"
        >
          重新索引
        </el-button>
        <el-button
          v-if="row.scope === 'personal'"
          link
          type="danger"
          size="small"
          @click="handleDelete(row)"
        >
          删除
        </el-button>
      </template>
    </el-table-column>
    <template #empty>
      <el-empty description="暂无文档，拖拽上传试试" :image-size="80" />
    </template>
  </el-table>
  <div class="table-footer">
    <el-pagination
      layout="total, prev, pager, next"
      :total="props.total"
      :page-size="props.pageSize"
      :current-page="props.page"
      @current-change="(p: number) => emit('page-change', p)"
    />
  </div>
</template>

<style scoped>
.scope-tag {
  margin-right: 6px;
}
.error-msg {
  color: var(--el-color-danger);
  font-size: 13px;
}
.table-footer {
  margin-top: 12px;
  display: flex;
  justify-content: flex-end;
}
.status-loading {
  display: inline-block;
  width: 10px;
  height: 10px;
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
</style>