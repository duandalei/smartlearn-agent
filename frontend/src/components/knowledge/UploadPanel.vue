<script setup lang="ts">
/**
 * 知识库拖拽上传区（P8，design.md 2.6.2-A）。
 *
 * - el-upload drag + multiple；`:before-upload` 本地预校验（扩展名
 *   白名单 + 大小 ≤20MB）：不合格 ElMessage.error 具体原因并 return
 *   false 快速失败——预校验是体验优化，后端 2000/1001 仍是权威校验源。
 * - `:http-request` 调 uploadKnowledge 自定义上传，onUploadProgress
 *   驱动每文件独立进度条；上传完成（拿到 item_id）emit 'uploaded'
 *   事件 → 视图立即刷新列表并启动轮询。
 * - 上传区下方逐文件显示「文件名 → 进度 → 状态 + 失败原因」：上传
 *   中显示 HTTP 进度，受理后状态经 items prop（列表轮询数据）按
 *   title 对齐回显（仅展示本轮会话内文件，design.md 2.6.2-A）。
 */
import { ref } from 'vue'
import { ElMessage } from 'element-plus'
import type { UploadRequestOptions } from 'element-plus'

import { uploadKnowledge } from '@/api/knowledge'
import type { KnowledgeItem } from '@/types'
import { KB_STATUS_META } from '@/utils/knowledge'

const props = defineProps<{
  /** 列表轮询数据（受理后按 title 对齐回显各文件处理状态）。 */
  items: KnowledgeItem[]
}>()

const emit = defineEmits<{
  /** 任一文件受理成功（视图刷新列表并启动轮询）。 */
  (e: 'uploaded'): void
}>()

/** 扩展名白名单（与后端 _ALLOWED_SUFFIXES 同口径）。 */
const ALLOWED_SUFFIXES = ['pdf', 'docx', 'pptx', 'md', 'txt']

/** 单文件大小上限（与后端 MAX_UPLOAD_BYTES 同口径）。 */
const MAX_UPLOAD_BYTES = 20 * 1024 * 1024

/** 上传行（本轮会话内文件，含 HTTP 进度与受理状态回显）。 */
interface UploadRow {
  title: string
  percent: number
  uploading: boolean
  failed: boolean
  failReason: string
}

const uploadRows = ref<UploadRow[]>([])

/** 上传预校验：扩展名白名单 + 大小 ≤20MB（体验优化，后端为权威校验源）。 */
function beforeUpload(file: File): boolean {
  const suffix = file.name.split('.').pop()?.toLowerCase() ?? ''
  if (!ALLOWED_SUFFIXES.includes(suffix)) {
    ElMessage.error('仅支持 PDF/DOCX/PPTX/MD/TXT')
    return false
  }
  if (file.size > MAX_UPLOAD_BYTES) {
    ElMessage.error('文件过大（上限 20MB）')
    return false
  }
  return true
}

/** 自定义上传：调 uploadKnowledge 并驱动逐文件进度条。 */
async function customRequest(options: UploadRequestOptions): Promise<void> {
  const file = options.file
  const row: UploadRow = {
    title: file.name,
    percent: 0,
    uploading: true,
    failed: false,
    failReason: '',
  }
  uploadRows.value.push(row)
  try {
    await uploadKnowledge(file, (event) => {
      if (event.total != null && event.total > 0) {
        row.percent = Math.min(100, Math.round((event.loaded / event.total) * 100))
      }
    })
    row.percent = 100
    row.uploading = false
    emit('uploaded')
  } catch {
    // 失败提示已由 request.ts 拦截器统一弹出，此处仅回显行内状态。
    row.uploading = false
    row.failed = true
    row.failReason = '上传失败'
  }
}

/** 按行 title 在列表数据中对齐当前状态（受理后的轮询回显）。 */
function rowStatus(row: UploadRow): KnowledgeItem | null {
  return props.items.find((item) => item.title === row.title) ?? null
}

/** 上传行状态文案：上传中 → 受理状态（含失败原因）。 */
function rowStatusText(row: UploadRow): string {
  if (row.uploading) {
    return row.percent >= 100 ? '受理中' : '上传中'
  }
  if (row.failed) return row.failReason
  const item = rowStatus(row)
  if (item == null) return '已受理'
  if (item.status === 'failed') return item.error_msg ?? KB_STATUS_META.failed.label
  return KB_STATUS_META[item.status].label
}
</script>

<template>
  <div class="upload-panel">
    <el-upload
      drag
      multiple
      action="#"
      :auto-upload="true"
      :show-file-list="false"
      :before-upload="beforeUpload"
      :http-request="customRequest"
      accept=".pdf,.docx,.pptx,.md,.txt"
    >
      <div class="el-upload__text">
        拖拽文件到此处，或<em>点击上传</em>
      </div>
      <template #tip>
        <div class="el-upload__tip">支持 PDF / DOCX / PPTX / MD / TXT，单个文件 ≤ 20MB</div>
      </template>
    </el-upload>
    <div v-if="uploadRows.length" class="upload-rows">
      <div v-for="(row, idx) in uploadRows" :key="idx" class="upload-row">
        <span class="upload-row-name" :title="row.title">{{ row.title }}</span>
        <el-progress
          :percentage="row.percent"
          :status="row.failed ? 'exception' : row.percent >= 100 ? 'success' : undefined"
          :stroke-width="8"
          class="upload-row-progress"
        />
        <span class="upload-row-status" :class="{ 'is-failed': row.failed }">
          {{ rowStatusText(row) }}
        </span>
      </div>
    </div>
  </div>
</template>

<style scoped>
.upload-rows {
  margin-top: 12px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.upload-row {
  display: flex;
  align-items: center;
  gap: 12px;
}
.upload-row-name {
  flex: 0 0 200px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 13px;
}
.upload-row-progress {
  flex: 1 1 auto;
}
.upload-row-status {
  flex: 0 0 auto;
  font-size: 13px;
  color: var(--el-text-color-secondary);
}
.upload-row-status.is-failed {
  color: var(--el-color-danger);
}
</style>