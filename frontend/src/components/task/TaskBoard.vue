<script setup lang="ts">
/**
 * 任务看板（P5，design 2.5.5 / 2.1.3-E）。
 *
 * - 数据自治：挂载时 fetchBoard；defineExpose({ reload }) 供页面刷新。
 * - 四列按 BOARD_COLUMNS 固定顺序（todo/in_progress/done/review，裁定⑫）。
 * - 拖拽：原生 HTML5 四阶段（禁 vuedraggable）——
 *     dragstart（记录拖拽态，effectAllowed='move'，setData 兼容 Firefox）
 *     dragover.prevent（目标列高亮，可感知反馈）
 *     drop（同列短路不发请求，裁定⑮；否则乐观更新）
 *     dragend（无论成败必清理拖拽态与列高亮）
 * - 乐观更新与回滚：落地前暂存快照 → 本地立即移列 →
 *   PATCH /status → 成功用返回对象替换 + emit('changed')（+ done 时
 *   emit('task-done')）；失败按快照回滚原列（错误提示由 request.ts
 *   拦截器统一弹出，本组件 catch 只回滚不重复弹错）。
 * - PATCH 进行中卡片入 pendingIds 置 drag-disabled，防重复快速拖拽。
 */
import { onMounted, reactive, ref } from 'vue'

import { fetchBoard, transitionTaskStatus } from '@/api/task'
import type { Task, TaskBoardData, TaskStatus } from '@/types'
import { normalizeKnowledgePoints } from '@/utils/knowledge'
import {
  BOARD_COLUMNS,
  TASK_STATUS_LABELS,
  formatDeadline,
  isTaskOverdue,
  priorityTagType,
} from '@/utils/task'

const emit = defineEmits<{
  (e: 'changed'): void
  (e: 'task-done', task: Task): void
  (e: 'edit', task: Task): void
}>()

/** 看板数据（固定四键）。 */
const board = reactive<TaskBoardData>({
  todo: [],
  in_progress: [],
  done: [],
  review: [],
})

const loading = ref(false)

/** 拖拽态。 */
const draggingId = ref<number | null>(null)
const draggingFrom = ref<TaskStatus | null>(null)
const dragOverCol = ref<TaskStatus | null>(null)

/** PATCH 进行中的任务 id（防重复拖拽）。 */
const pendingIds = reactive(new Set<number>())

/** 拉取看板数据。 */
async function reload(): Promise<void> {
  loading.value = true
  try {
    const data = await fetchBoard()
    board.todo = data.todo
    board.in_progress = data.in_progress
    board.done = data.done
    board.review = data.review
  } catch {
    // 错误提示已由 request.ts 拦截器统一展示
  } finally {
    loading.value = false
  }
}

onMounted(reload)

/** dragstart：记录拖拽态（setData 兼容 Firefox 必调）。 */
function onDragStart(e: DragEvent, task: Task, from: TaskStatus): void {
  draggingId.value = task.id
  draggingFrom.value = from
  if (e.dataTransfer) {
    e.dataTransfer.effectAllowed = 'move'
    e.dataTransfer.setData('text/plain', String(task.id))
  }
}

/** drop：同列短路（裁定⑮）；异列执行乐观更新 + 失败回滚。 */
async function onDrop(target: TaskStatus): Promise<void> {
  const id = draggingId.value
  const from = draggingFrom.value
  clearDragState()
  if (id == null || from == null) return
  if (target === from) return // 同列落地：无操作、不发请求

  const sourceList = board[from]
  const idx = sourceList.findIndex((t) => t.id === id)
  if (idx < 0) return
  const task = sourceList[idx]

  // 快照（乐观更新失败时按原索引回滚原列原位）
  const snapshot = { task, fromStatus: from, idx }

  // 本地立即移列（乐观更新）
  sourceList.splice(idx, 1)
  board[target].unshift(task)

  pendingIds.add(id)
  try {
    const updated = await transitionTaskStatus(id, target)
    // 成功：用后端返回对象替换本地行（completed_at 等以服务端为准）
    const list = board[target]
    const i = list.findIndex((t) => t.id === id)
    if (i >= 0) list[i] = updated
    emit('changed')
    if (target === 'done') emit('task-done', updated)
  } catch {
    // 失败：按快照回滚原列原索引位置（错误提示已由拦截器弹出，此处不重复弹错）
    const list = board[target]
    const i = list.findIndex((t) => t.id === id)
    if (i >= 0) list.splice(i, 1)
    board[snapshot.fromStatus].splice(snapshot.idx, 0, snapshot.task)
  } finally {
    pendingIds.delete(id)
  }
}

/** dragend：无论成败必清理拖拽态与列高亮。 */
function onDragEnd(): void {
  clearDragState()
}

function clearDragState(): void {
  draggingId.value = null
  draggingFrom.value = null
  dragOverCol.value = null
}

defineExpose({ reload })
</script>

<template>
  <div v-loading="loading" class="board">
    <div
      v-for="col in BOARD_COLUMNS"
      :key="col"
      class="board-column"
      :class="{
        'drop-target': dragOverCol === col && draggingFrom !== null && draggingFrom !== col,
      }"
      @dragover.prevent="dragOverCol = col"
      @dragleave="dragOverCol === col && (dragOverCol = null)"
      @drop.prevent="onDrop(col)"
    >
      <div class="column-header">
        <span>{{ TASK_STATUS_LABELS[col] }}</span>
        <el-badge :value="board[col].length" type="info" class="column-count" />
      </div>
      <div class="card-list">
        <div
          v-for="t in board[col]"
          :key="t.id"
          class="task-card"
          draggable="true"
          :class="{ dragging: t.id === draggingId, 'drag-disabled': pendingIds.has(t.id) }"
          @dragstart="(e: DragEvent) => onDragStart(e, t, col)"
          @dragend="onDragEnd"
          @click="emit('edit', t)"
        >
          <div class="card-title" :title="t.title">{{ t.title }}</div>
          <div class="card-meta">
            <el-tag :type="priorityTagType(t.priority)" size="small" effect="light">
              {{ t.priority === 'high' ? '高' : t.priority === 'medium' ? '中' : '低' }}
            </el-tag>
            <span
              class="card-deadline"
              :class="{ 'overdue-text': isTaskOverdue(t) }"
            >
              {{ formatDeadline(t.deadline) }}
              <template v-if="isTaskOverdue(t)">（已逾期）</template>
            </span>
          </div>
          <div v-if="normalizeKnowledgePoints(t.knowledge_points).length > 0" class="card-kps">
            <el-tag
              v-for="k in normalizeKnowledgePoints(t.knowledge_points).slice(0, 3)"
              :key="k"
              size="small"
              type="info"
              effect="plain"
            >
              {{ k }}
            </el-tag>
            <el-tag
              v-if="normalizeKnowledgePoints(t.knowledge_points).length > 3"
              size="small"
              type="info"
              effect="plain"
            >
              +{{ normalizeKnowledgePoints(t.knowledge_points).length - 3 }}
            </el-tag>
          </div>
        </div>
        <div v-if="board[col].length === 0" class="column-empty">暂无任务</div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.board {
  display: flex;
  gap: 12px;
  width: 100%;
  align-items: stretch;
  min-height: 320px;
}
.board-column {
  flex: 1 1 0;
  min-width: 220px;
  background: var(--el-fill-color-lighter);
  border-radius: 8px;
  padding: 10px;
  display: flex;
  flex-direction: column;
  transition: background-color 0.15s, border-color 0.15s;
  border: 1px dashed transparent;
}
.board-column.drop-target {
  background: var(--el-color-primary-light-9);
  border-color: var(--el-color-primary-light-5);
}
.column-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  font-weight: 600;
  font-size: 14px;
  margin-bottom: 10px;
  color: var(--el-text-color-primary);
}
.column-count :deep(.el-badge__content) {
  position: static;
  transform: none;
}
.card-list {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.task-card {
  background: var(--el-bg-color);
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 6px;
  padding: 10px;
  cursor: grab;
  user-select: none;
  transition: opacity 0.15s, box-shadow 0.15s;
}
.task-card:hover {
  box-shadow: var(--el-box-shadow-light);
}
.task-card.dragging {
  opacity: 0.45;
}
.task-card.drag-disabled {
  cursor: not-allowed;
  opacity: 0.7;
}
.card-title {
  font-size: 14px;
  font-weight: 500;
  margin-bottom: 6px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: var(--el-text-color-primary);
}
.card-meta {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}
.card-deadline {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
.card-deadline.overdue-text {
  color: var(--el-color-danger);
}
.card-kps {
  display: flex;
  gap: 4px;
  flex-wrap: wrap;
  margin-top: 6px;
}
.column-empty {
  text-align: center;
  font-size: 12px;
  color: var(--el-text-color-placeholder);
  padding: 16px 0;
}
</style>