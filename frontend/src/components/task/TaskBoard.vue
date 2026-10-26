<script setup lang="ts">
/**
 * 任务看板：四列纸质任务单。
 *
 * 数据自治、HTML5 拖拽、乐观更新与回滚逻辑保持不变；
 * 视觉去掉 el-badge 和侧边色条，改用列首色点与优先级小方块。
 */
import { onMounted, reactive, ref } from 'vue'

import { fetchBoard, transitionTaskStatus } from '@/api/task'
import type { Task, TaskBoardData, TaskStatus } from '@/types'
import { normalizeKnowledgePoints } from '@/utils/knowledge'
import {
  BOARD_COLUMNS,
  PRIORITY_LABEL,
  TASK_STATUS_LABELS,
  formatDeadline,
  isTaskOverdue,
} from '@/utils/task'

const emit = defineEmits<{
  (e: 'changed'): void
  (e: 'task-done', task: Task): void
  (e: 'edit', task: Task): void
}>()

const board = reactive<TaskBoardData>({
  todo: [],
  in_progress: [],
  done: [],
  review: [],
})

const loading = ref(false)

const draggingId = ref<number | null>(null)
const draggingFrom = ref<TaskStatus | null>(null)
const dragOverCol = ref<TaskStatus | null>(null)

const pendingIds = reactive(new Set<number>())

/** 列首色点：待办/进行中/完成/复盘。 */
const COLUMN_TONE: Record<TaskStatus, string> = {
  todo: 'is-dust',
  in_progress: 'is-ochre',
  done: 'is-jade',
  review: 'is-vermilion',
}

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

function onDragStart(e: DragEvent, task: Task, from: TaskStatus): void {
  draggingId.value = task.id
  draggingFrom.value = from
  if (e.dataTransfer) {
    e.dataTransfer.effectAllowed = 'move'
    e.dataTransfer.setData('text/plain', String(task.id))
  }
}

async function onDrop(target: TaskStatus): Promise<void> {
  const id = draggingId.value
  const from = draggingFrom.value
  clearDragState()
  if (id == null || from == null) return
  if (target === from) return

  const task = board[from].find((t) => t.id === id)
  if (!task) return
  await moveTask(task, from, target)
}

async function moveTask(task: Task, from: TaskStatus, target: TaskStatus): Promise<void> {
  if (from === target || pendingIds.has(task.id)) return
  const sourceList = board[from]
  const idx = sourceList.findIndex((t) => t.id === task.id)
  if (idx < 0) return

  const snapshot = { task: sourceList[idx], fromStatus: from, idx }

  sourceList.splice(idx, 1)
  board[target].unshift(task)

  pendingIds.add(task.id)
  try {
    const updated = await transitionTaskStatus(task.id, target)
    const list = board[target]
    const i = list.findIndex((t) => t.id === task.id)
    if (i >= 0) list[i] = updated
    emit('changed')
    if (target === 'done' && from !== 'review') emit('task-done', updated)
  } catch {
    const list = board[target]
    const i = list.findIndex((t) => t.id === task.id)
    if (i >= 0) list.splice(i, 1)
    board[snapshot.fromStatus].splice(snapshot.idx, 0, snapshot.task)
  } finally {
    pendingIds.delete(task.id)
  }
}

function onMarkReviewed(task: Task): void {
  void moveTask(task, 'review', 'done')
}

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
  <div v-loading="loading" class="board-scroll">
    <div class="board">
      <section
        v-for="col in BOARD_COLUMNS"
        :key="col"
        class="board-column"
        :class="{
          'drop-target': dragOverCol === col && draggingFrom !== null && draggingFrom !== col,
        }"
        :aria-label="TASK_STATUS_LABELS[col]"
        @dragover.prevent="dragOverCol = col"
        @dragleave="dragOverCol === col && (dragOverCol = null)"
        @drop.prevent="onDrop(col)"
      >
        <header class="column-header">
          <div class="column-title-row">
            <span class="column-dot" :class="COLUMN_TONE[col]" aria-hidden="true" />
            <span class="column-title">{{ TASK_STATUS_LABELS[col] }}</span>
          </div>
          <span class="column-count">{{ board[col].length }}</span>
        </header>

        <div class="card-list">
          <article
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
              <span class="priority" :class="`is-${t.priority}`">
                <span class="priority__dot" aria-hidden="true" />
                {{ PRIORITY_LABEL[t.priority] }}
              </span>
              <span class="card-deadline" :class="{ 'is-overdue': isTaskOverdue(t) }">
                {{ formatDeadline(t.deadline) }}
                <template v-if="isTaskOverdue(t)"> · 已逾期</template>
              </span>
            </div>

            <div
              v-if="normalizeKnowledgePoints(t.knowledge_points).length > 0"
              class="card-kps"
            >
              <span
                v-for="k in normalizeKnowledgePoints(t.knowledge_points).slice(0, 3)"
                :key="k"
                class="kp"
              >
                {{ k }}
              </span>
              <span
                v-if="normalizeKnowledgePoints(t.knowledge_points).length > 3"
                class="kp kp--more"
              >
                +{{ normalizeKnowledgePoints(t.knowledge_points).length - 3 }}
              </span>
            </div>

            <div v-if="col === 'review'" class="card-footer">
              <el-button
                link
                type="success"
                size="small"
                :loading="pendingIds.has(t.id)"
                :disabled="pendingIds.has(t.id)"
                @click.stop="onMarkReviewed(t)"
              >
                标记已复盘
              </el-button>
            </div>
          </article>

          <div v-if="board[col].length === 0" class="column-empty">暂无任务</div>
        </div>
      </section>
    </div>
  </div>
</template>

<style scoped>
.board-scroll {
  width: 100%;
  overflow-x: auto;
}

.board {
  display: grid;
  grid-template-columns: repeat(4, minmax(210px, 1fr));
  gap: 12px;
  min-width: 880px;
  align-items: stretch;
}

.board-column {
  min-width: 0;
  display: flex;
  flex-direction: column;
  min-height: 360px;
  padding: 12px;
  background: var(--paper-3);
  border: 1px solid var(--line);
  border-radius: var(--radius);
  transition: background-color 0.16s var(--ease), border-color 0.16s var(--ease);
}

.board-column.drop-target {
  background: var(--vermilion-wash);
  border-color: var(--vermilion);
  border-style: dashed;
}

.column-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  padding-bottom: 10px;
  margin-bottom: 10px;
  border-bottom: 1px solid var(--line);
}

.column-title-row {
  display: flex;
  align-items: center;
  gap: 8px;
}

.column-dot {
  width: 6px;
  height: 6px;
  border-radius: 1px;
  background: var(--dust);
}

.column-dot.is-ochre {
  background: var(--ochre);
}

.column-dot.is-jade {
  background: var(--jade);
}

.column-dot.is-vermilion {
  background: var(--vermilion);
}

.column-dot.is-dust {
  background: var(--dust);
}

.column-title {
  font-family: var(--font-display);
  font-size: 15px;
  font-weight: 600;
  color: var(--ink);
}

.column-count {
  font-family: var(--font-mono);
  font-size: 10px;
  color: var(--ink-3);
}

.card-list {
  flex: 1 1 auto;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.task-card {
  padding: 11px 12px;
  background: var(--paper-2);
  border: 1px solid var(--line);
  border-radius: var(--radius);
  cursor: grab;
  user-select: none;
  transition: border-color 0.16s var(--ease), box-shadow 0.16s var(--ease),
    opacity 0.16s var(--ease);
}

.task-card:hover {
  border-color: var(--line-strong);
  box-shadow: var(--shadow-lift);
}

.task-card.dragging {
  opacity: 0.42;
}

.task-card.drag-disabled {
  cursor: not-allowed;
  opacity: 0.66;
}

.card-title {
  font-size: 13.5px;
  font-weight: 500;
  line-height: 1.5;
  color: var(--ink);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.card-meta {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
  margin-top: 6px;
}

.priority {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-family: var(--font-mono);
  font-size: 9px;
  letter-spacing: 0.04em;
  color: var(--ink-3);
}

.priority__dot {
  width: 5px;
  height: 5px;
  border-radius: 1px;
  background: var(--dust);
}

.priority.is-high .priority__dot {
  background: var(--vermilion);
}

.priority.is-medium .priority__dot {
  background: var(--ochre);
}

.priority.is-low .priority__dot {
  background: var(--dust);
}

.card-deadline {
  font-family: var(--font-mono);
  font-size: 9px;
  color: var(--ink-4);
}

.card-deadline.is-overdue {
  color: var(--vermilion);
}

.card-kps {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  margin-top: 7px;
}

.kp {
  padding: 0 5px;
  font-size: 10px;
  line-height: 17px;
  color: var(--ink-3);
  background: var(--paper-3);
  border: 1px solid var(--line-soft);
  border-radius: var(--radius);
}

.kp--more {
  color: var(--ink-4);
}

.card-footer {
  display: flex;
  justify-content: flex-end;
  margin-top: 8px;
  padding-top: 6px;
  border-top: 1px dashed var(--line);
}

.column-empty {
  padding: 18px 8px;
  text-align: center;
  font-size: 11px;
  color: var(--ink-4);
  border: 1px dashed var(--line);
  border-radius: var(--radius);
}
</style>
