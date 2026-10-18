<script setup lang="ts">
/**
 * 学习任务管理页面（P5，design 2.5.1 页面编排）。
 *
 * - 顶部 TaskStatsCards（数值全部来自后端 stats 接口）；
 * - 工具栏：6 项筛选 + 视图切换（list/board，默认 list）+ 新建按钮；
 * - 列表视图：el-table + 行内状态切换（受控模式，仅合法目标）
 *   + 逾期行标红 + 分页；
 * - 看板视图：TaskBoard（原生 HTML5 拖拽 + 失败回滚）；
 * - 数据流：任何写操作成功后刷新 stats + 当前视图（spec 5.6.1 规则 1）。
 */
import { computed, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'

import { fetchCourses } from '@/api/course'
import {

  deleteTask,
  fetchStats,
  fetchTasks,
  transitionTaskStatus,
} from '@/api/task'
import TaskBoard from '@/components/task/TaskBoard.vue'
import TaskFormDialog from '@/components/task/TaskFormDialog.vue'
import TaskStatsCards from '@/components/task/TaskStatsCards.vue'
import type {
  Course,
  Task,
  TaskListQuery,
  TaskPriority,
  TaskStats,
  TaskStatus,
} from '@/types'
import {
  TASK_STATUS_LABELS,
  formatDeadline,
  isTaskOverdue,
  nextStatusOptions,
  priorityTagType,
} from '@/utils/task'

const router = useRouter()

// ---------------------------------------------------------------------------
// 页面状态
// ---------------------------------------------------------------------------
const stats = ref<TaskStats | null>(null)
const viewMode = ref<'list' | 'board'>('list')

/** 筛选状态（'' = 全部；与后端 query 参数一一对应）。 */
const filterStatus = ref<TaskStatus | ''>('')
const filterPriority = ref<TaskPriority | ''>('')
const filterCourseId = ref<number | ''>('')
const filterKnowledgePoint = ref('')
const filterOverdue = ref<'' | 'true' | 'false'>('')
const filterKeyword = ref('')

/** 列表分页状态。 */
const tasks = ref<Task[]>([])
const total = ref(0)
const page = ref(1)
const pageSize = ref(10)
const listLoading = ref(false)

/** 课程下拉数据源（onMounted 拉一次）。 */
const courses = ref<Course[]>([])

/** 弹窗状态（editingTask 为 null = 新建）。 */
const formVisible = ref(false)
const editingTask = ref<Task | null>(null)

/** 看板组件引用。 */
const boardRef = ref<InstanceType<typeof TaskBoard> | null>(null)

/** 已加载任务的知识点聚合（供弹窗下拉候选）。 */
const knowledgeOptions = computed<string[]>(() => {
  const set = new Set<string>()
  for (const t of tasks.value) {
    for (const k of t.knowledge_points) set.add(k)
  }
  return [...set].sort()
})

/** 课程 id → 名称映射。 */
const courseNameMap = computed<Map<number, string>>(() => {
  const m = new Map<number, string>()
  for (const c of courses.value) m.set(c.id, c.name)
  return m
})

// ---------------------------------------------------------------------------
// 数据加载
// ---------------------------------------------------------------------------
/** 加载任务列表（按当前筛选与分页）。 */
async function loadTasks(): Promise<void> {
  listLoading.value = true
  try {
    const params: TaskListQuery = { page: page.value, page_size: pageSize.value }
    if (filterStatus.value) params.status = filterStatus.value
    if (filterPriority.value) params.priority = filterPriority.value
    if (typeof filterCourseId.value === 'number') params.course_id = filterCourseId.value
    if (filterKnowledgePoint.value.trim()) params.knowledge_point = filterKnowledgePoint.value.trim()
    if (filterOverdue.value) params.overdue = filterOverdue.value === 'true'
    if (filterKeyword.value.trim()) params.keyword = filterKeyword.value.trim()
    const data = await fetchTasks(params)
    tasks.value = data.items
    total.value = data.total
  } catch {
    // 错误提示已由 request.ts 拦截器统一展示
  } finally {
    listLoading.value = false
  }
}

/** 刷新统计（失败置 null，卡片显示 '--' 不阻塞页面）。 */
async function loadStats(): Promise<void> {
  try {
    stats.value = await fetchStats()
  } catch {
    stats.value = null
  }
}

onMounted(() => {
  void loadStats()
  void loadTasks()
  // 课程下拉：加载失败时退化为空选项，不阻断任务功能（spec 5.6.3 场景 1）
  fetchCourses({ page: 1, page_size: 100 })
    .then((data) => {
      courses.value = data.items
    })
    .catch(() => {})
})

// 筛选变化：回到第 1 页重新加载（P4 GoalsView 的 watch 模式）。
watch([filterStatus, filterPriority, filterCourseId, filterKnowledgePoint, filterOverdue], () => {
  page.value = 1
  void loadTasks()
})

/** keyword 回车搜索。 */
function onKeywordSearch(): void {
  page.value = 1
  void loadTasks()
}

/** 重置筛选。 */
function onResetFilters(): void {
  filterStatus.value = ''
  filterPriority.value = ''
  filterCourseId.value = ''
  filterKnowledgePoint.value = ''
  filterOverdue.value = ''
  filterKeyword.value = ''
  page.value = 1
  void loadTasks()
}

// ---------------------------------------------------------------------------
// 分页
// ---------------------------------------------------------------------------
function onPageChange(p: number): void {
  page.value = p
  void loadTasks()
}

function onSizeChange(s: number): void {
  pageSize.value = s
  page.value = 1
  void loadTasks()
}

// ---------------------------------------------------------------------------
// 新建 / 编辑 / 删除
// ---------------------------------------------------------------------------
function onCreate(): void {
  editingTask.value = null
  formVisible.value = true
}

function onEdit(task: Task): void {
  editingTask.value = task
  formVisible.value = true
}

/** 弹窗保存回调：刷新 stats + 当前视图（列表原位替换或重拉）。 */
function onSaved(saved: Task): void {
  void loadStats()
  if (viewMode.value === 'board') {
    void boardRef.value?.reload()
  } else {
    const idx = tasks.value.findIndex((t) => t.id === saved.id)
    if (idx >= 0) {
      tasks.value[idx] = saved
    } else {
      void loadTasks()
    }
  }
}

/** 删除二次确认（spec 5.1.1 规则 3）。 */
async function onDelete(task: Task): Promise<void> {
  try {
    await ElMessageBox.confirm(
      `确定删除任务「${task.title}」吗？删除后不可恢复。`,
      '删除任务',
      { type: 'warning', confirmButtonText: '删除', cancelButtonText: '取消' },
    )
  } catch {
    return
  }
  try {
    await deleteTask(task.id)
    ElMessage.success('删除成功')
    void loadStats()
    if (viewMode.value === 'board') {
      void boardRef.value?.reload()
    } else {
      // 当前页仅剩这一条且不在第 1 页：先回退一页再加载。
      if (tasks.value.length === 1 && page.value > 1) {
        page.value -= 1
      }
      void loadTasks()
    }
  } catch {
    // 错误提示已由拦截器统一展示
  }
}

// ---------------------------------------------------------------------------
// 行内状态切换（受控模式：成功才写本地，失败自动回显原值）
// ---------------------------------------------------------------------------
async function onStatusChange(row: Task, target: TaskStatus): Promise<void> {
  try {
    const updated = await transitionTaskStatus(row.id, target)
    row.status = updated.status
    row.completed_at = updated.completed_at
    row.updated_at = updated.updated_at
    void loadStats()
    if (updated.status === 'done') {
      void handleTaskDone(updated)
    }
  } catch {
    // 失败不写 row.status，select 自动回显原值；1007 message 由拦截器弹出
  }
}

// ---------------------------------------------------------------------------
// 看板事件
// ---------------------------------------------------------------------------
/** 看板流转成功：仅刷 stats（列位已由看板乐观更新保持，不整板重拉）。 */
function onBoardChanged(): void {
  void loadStats()
}

/** 看板卡片点击编辑。 */
function onBoardEdit(task: Task): void {
  onEdit(task)
}

// ---------------------------------------------------------------------------
// 完成任务快捷入口（P6 预留，裁定⑯）
// ---------------------------------------------------------------------------
/**
 * 任务经 PATCH 成功流转为 done 后调用（含 review→done）。
 * 取消留在当前页，状态保持已流转的 done；确认则携带 query 跳转 P6 占位页。
 */
async function handleTaskDone(task: Task): Promise<void> {
  try {
    await ElMessageBox.confirm(
      `「${task.title}」已完成！是否立即记录本次学习情况？`,
      '记录学习情况',
      { confirmButtonText: '记录学习情况', cancelButtonText: '暂不记录', type: 'success' },
    )
  } catch {
    return
  }
  void router.push({
    path: '/learning-records',
    query: {
      task_id: String(task.id),
      task_title: task.title,
      knowledge_points: task.knowledge_points.join(','),
      ...(task.course_id != null ? { course_id: String(task.course_id) } : {}),
    },
  })
}

// ---------------------------------------------------------------------------
// 列表辅助
// ---------------------------------------------------------------------------
/** 逾期行整行标红（口径同后端）。 */
function rowClassName({ row }: { row: Task }): string {
  return isTaskOverdue(row) ? 'overdue-row' : ''
}

/** 课程列显示名（未挂显示 '—'）。 */
function courseName(courseId: number | null): string {
  if (courseId == null) return '—'
  return courseNameMap.value.get(courseId) ?? '—'
}

const statusOptions: { value: TaskStatus | ''; label: string }[] = [
  { value: '', label: '全部状态' },
  ...(['todo', 'in_progress', 'done', 'review'] as TaskStatus[]).map((s) => ({
    value: s,
    label: TASK_STATUS_LABELS[s],
  })),
]

const priorityOptions: { value: TaskPriority | ''; label: string }[] = [
  { value: '', label: '全部优先级' },
  { value: 'high', label: '高' },
  { value: 'medium', label: '中' },
  { value: 'low', label: '低' },
]

const overdueOptions: { value: '' | 'true' | 'false'; label: string }[] = [
  { value: '', label: '全部' },
  { value: 'true', label: '仅逾期' },
  { value: 'false', label: '未逾期' },
]
</script>

<template>
  <el-space direction="vertical" alignment="stretch" :size="16" style="width: 100%">
    <el-card shadow="never">
      <TaskStatsCards :stats="stats" />
    </el-card>

    <el-card shadow="never">
      <div class="toolbar">
        <div class="filters">
          <el-select v-model="filterStatus" class="filter-item" placeholder="全部状态">
            <el-option v-for="o in statusOptions" :key="o.value" :label="o.label" :value="o.value" />
          </el-select>
          <el-select v-model="filterPriority" class="filter-item" placeholder="全部优先级">
            <el-option v-for="o in priorityOptions" :key="o.value" :label="o.label" :value="o.value" />
          </el-select>
          <el-select v-model="filterCourseId" class="filter-item" placeholder="全部课程" clearable>
            <el-option v-for="c in courses" :key="c.id" :label="c.name" :value="c.id" />
          </el-select>
          <el-input
            v-model="filterKnowledgePoint"
            class="filter-item"
            placeholder="知识点"
            clearable
          />
          <el-select v-model="filterOverdue" class="filter-item" placeholder="逾期筛选">
            <el-option v-for="o in overdueOptions" :key="o.value" :label="o.label" :value="o.value" />
          </el-select>
          <el-input
            v-model="filterKeyword"
            class="filter-item keyword"
            placeholder="关键词（回车搜索）"
            clearable
            @keyup.enter="onKeywordSearch"
            @clear="onKeywordSearch"
          />
          <el-button @click="onResetFilters">重置</el-button>
        </div>
        <div class="toolbar-right">
          <el-radio-group v-model="viewMode">
            <el-radio-button value="list">列表</el-radio-button>
            <el-radio-button value="board">看板</el-radio-button>
          </el-radio-group>
          <el-button type="primary" @click="onCreate">新建任务</el-button>
        </div>
      </div>
    </el-card>

    <el-card v-if="viewMode === 'list'" shadow="never" v-loading="listLoading">
      <el-empty
        v-if="!listLoading && tasks.length === 0"
        description="还没有学习任务"
      >
        <el-button type="primary" @click="onCreate">新建任务</el-button>
      </el-empty>
      <template v-else>
        <el-table :data="tasks" :row-class-name="rowClassName">
          <el-table-column prop="title" label="名称" min-width="180" show-overflow-tooltip />
          <el-table-column label="知识点" min-width="160">
            <template #default="{ row }">
              <template v-if="row.knowledge_points.length > 0">
                <el-tag
                  v-for="k in row.knowledge_points.slice(0, 3)"
                  :key="k"
                  size="small"
                  type="info"
                  effect="plain"
                  style="margin-right: 4px"
                >
                  {{ k }}
                </el-tag>
                <el-tag v-if="row.knowledge_points.length > 3" size="small" type="info" effect="plain">
                  +{{ row.knowledge_points.length - 3 }}
                </el-tag>
              </template>
              <span v-else>—</span>
            </template>
          </el-table-column>
          <el-table-column label="优先级" width="90">
            <template #default="{ row }">
              <el-tag :type="priorityTagType(row.priority)" size="small">
                {{ row.priority === 'high' ? '高' : row.priority === 'medium' ? '中' : '低' }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column label="所属课程" min-width="110">
            <template #default="{ row }">
              {{ courseName(row.course_id) }}
            </template>
          </el-table-column>
          <el-table-column label="截止时间" min-width="150">
            <template #default="{ row }">
              <span :class="{ 'overdue-text': isTaskOverdue(row) }">
                {{ formatDeadline(row.deadline) }}
                <template v-if="isTaskOverdue(row)">（已逾期）</template>
              </span>
            </template>
          </el-table-column>
          <el-table-column label="预计耗时" width="95">
            <template #default="{ row }">
              {{ row.estimated_minutes != null ? `${row.estimated_minutes} 分钟` : '—' }}
            </template>
          </el-table-column>
          <el-table-column label="实际耗时" width="95">
            <template #default="{ row }">
              {{ row.actual_minutes != null ? `${row.actual_minutes} 分钟` : '—' }}
            </template>
          </el-table-column>
          <el-table-column label="状态" width="150">
            <template #default="{ row }">
              <el-select
                :model-value="row.status"
                size="small"
                @change="(v: TaskStatus) => onStatusChange(row, v)"
              >
                <el-option
                  v-for="opt in nextStatusOptions(row.status)"
                  :key="opt.value"
                  :label="opt.label"
                  :value="opt.value"
                />
              </el-select>
            </template>
          </el-table-column>
          <el-table-column label="操作" width="120" fixed="right">
            <template #default="{ row }">
              <el-button link type="primary" size="small" @click="onEdit(row)">编辑</el-button>
              <el-button link type="danger" size="small" @click="onDelete(row)">删除</el-button>
            </template>
          </el-table-column>
        </el-table>
        <div v-if="total > 0" class="pager-row">
          <el-pagination
            :current-page="page"
            :page-size="pageSize"
            :total="total"
            :page-sizes="[10, 20, 50, 100]"
            layout="total, sizes, prev, pager, next"
            @current-change="onPageChange"
            @size-change="onSizeChange"
          />
        </div>
      </template>
    </el-card>

    <el-card v-else shadow="never">
      <TaskBoard
        ref="boardRef"
        @changed="onBoardChanged"
        @task-done="handleTaskDone"
        @edit="onBoardEdit"
      />
    </el-card>
  </el-space>

  <TaskFormDialog
    v-model:visible="formVisible"
    :task="editingTask"
    :courses="courses"
    :knowledge-options="knowledgeOptions"
    @saved="onSaved"
  />
</template>

<style scoped>
.toolbar {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
}
.filters {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  flex: 1 1 auto;
}
.filter-item {
  width: 130px;
}
.filter-item.keyword {
  width: 180px;
}
.toolbar-right {
  display: flex;
  align-items: center;
  gap: 8px;
}
.pager-row {
  display: flex;
  justify-content: flex-end;
  margin-top: 12px;
}
.overdue-text {
  color: var(--el-color-danger);
}
:deep(.overdue-row) {
  --el-table-tr-bg-color: var(--el-color-danger-light-9);
}
</style>