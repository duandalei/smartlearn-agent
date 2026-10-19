<script setup lang="ts">
/**
 * 学习记录页面（P6，design 2.5.1 页面编排）。
 *
 * - 顶部 RecordStatsCards（三值全部来自后端 stats 接口）；
 * - 工具栏：日期范围 / 课程 / 知识点三筛选 + 新建按钮；
 * - 列表：groupRecordsByDate 按天分组（今天/昨天/日期标题，今天在前），
 *   组内 id 降序（列表接口排序天然满足）；
 * - P5 跳转预填消费：onMounted 读 route.query（task_id / course_id /
 *   task_title / knowledge_points），有任一可识别参数即打开新建弹窗；
 *   提交成功后 router.replace 清理 query → 刷新列表与 stats。
 */
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'

import { fetchCourses } from '@/api/course'
import { deleteRecord, fetchRecordStats, fetchRecords } from '@/api/record'
import RecordFormDialog from '@/components/record/RecordFormDialog.vue'
import type { RecordPreset } from '@/components/record/RecordFormDialog.vue'
import RecordStatsCards from '@/components/record/RecordStatsCards.vue'
import type { Course, LearningRecord, RecordListQuery, RecordStats } from '@/types'
import { normalizeKnowledgePoints } from '@/utils/knowledge'
import { formatMinutes, groupRecordsByDate, masterySegment } from '@/utils/record'

const route = useRoute()
const router = useRouter()

// ---------------------------------------------------------------------------
// 页面状态
// ---------------------------------------------------------------------------
const stats = ref<RecordStats | null>(null)

/** 筛选状态（'' / null = 全部；与后端 query 参数一一对应）。 */
const filterDateRange = ref<[string, string] | null>(null)
const filterCourseId = ref<number | ''>('')
const filterKnowledgePoint = ref('')

/** 列表分页状态。 */
const records = ref<LearningRecord[]>([])
const total = ref(0)
const page = ref(1)
const pageSize = ref(10)
const listLoading = ref(false)

/** 课程下拉数据源（onMounted 拉一次）。 */
const courses = ref<Course[]>([])

/** 弹窗状态（editingRecord 为 null = 新建）。 */
const formVisible = ref(false)
const editingRecord = ref<LearningRecord | null>(null)
const preset = ref<RecordPreset | null>(null)

/** 已加载记录的知识点聚合（供弹窗下拉候选）。 */
const knowledgeOptions = computed<string[]>(() => {
  const set = new Set<string>()
  for (const r of records.value) {
    for (const k of normalizeKnowledgePoints(r.knowledge_points)) set.add(k)
  }
  return [...set].sort()
})

/** 课程 id → 名称映射。 */
const courseNameMap = computed<Map<number, string>>(() => {
  const m = new Map<number, string>()
  for (const c of courses.value) m.set(c.id, c.name)
  return m
})

/** 按天分组（组间日期降序 = 今天在前；组内保持接口顺序 = id 降序）。 */
const dateGroups = computed(() => groupRecordsByDate(records.value))

// ---------------------------------------------------------------------------
// 数据加载
// ---------------------------------------------------------------------------
/** 加载记录列表（按当前筛选与分页）。 */
async function loadRecords(): Promise<void> {
  listLoading.value = true
  try {
    const params: RecordListQuery = { page: page.value, page_size: pageSize.value }
    if (filterDateRange.value && filterDateRange.value.length === 2) {
      params.start_date = filterDateRange.value[0]
      params.end_date = filterDateRange.value[1]
    }
    if (typeof filterCourseId.value === 'number') params.course_id = filterCourseId.value
    if (filterKnowledgePoint.value.trim()) {
      params.knowledge_point = filterKnowledgePoint.value.trim()
    }
    const data = await fetchRecords(params)
    records.value = data.items
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
    stats.value = await fetchRecordStats()
  } catch {
    stats.value = null
  }
}

onMounted(() => {
  void loadStats()
  void loadRecords()
  // 课程下拉：加载失败时退化为空选项，不阻断记录功能
  fetchCourses({ page: 1, page_size: 100 })
    .then((data) => {
      courses.value = data.items
    })
    .catch(() => {
      courses.value = []
    })
  consumeQueryPreset()
})

// ---------------------------------------------------------------------------
// 筛选联动（变化回第 1 页重载；知识点回车触发避免逐字请求）
// ---------------------------------------------------------------------------
watch([filterDateRange, filterCourseId], () => {
  page.value = 1
  void loadRecords()
})

/** 知识点筛选：回车 / 清空触发。 */
function onKnowledgeSearch(): void {
  page.value = 1
  void loadRecords()
}

/** 重置全部筛选。 */
function onResetFilters(): void {
  filterDateRange.value = null
  filterCourseId.value = ''
  filterKnowledgePoint.value = ''
  page.value = 1
  void loadRecords()
}

/** 分页翻页。 */
function onPageChange(p: number): void {
  page.value = p
  void loadRecords()
}

// ---------------------------------------------------------------------------
// 弹窗编排（新建 / 编辑 / 删除）
// ---------------------------------------------------------------------------
/** 打开新建弹窗（清空编辑态与预填）。 */
function onCreate(): void {
  editingRecord.value = null
  preset.value = null
  formVisible.value = true
}

/** 打开编辑弹窗（回填原值；mastery_level 为 null 时弹窗自动勾选跳过自评）。 */
function onEdit(rec: LearningRecord): void {
  editingRecord.value = rec
  formVisible.value = true
}

/** 弹窗保存成功：清理预填 query → 新建回第 1 页 → 刷新列表与统计。 */
function onSaved(): void {
  const wasCreate = editingRecord.value == null
  if (Object.keys(route.query).length > 0) {
    void router.replace({ query: {} })
  }
  if (wasCreate) page.value = 1
  void loadRecords()
  void loadStats()
}

/** 删除记录（二次确认；当前页删空时回退一页）。 */
async function onDelete(rec: LearningRecord): Promise<void> {
  try {
    await ElMessageBox.confirm(
      '删除后该记录的时长将不再计入任务与统计，确定删除？',
      '删除学习记录',
      { confirmButtonText: '删除', cancelButtonText: '取消', type: 'warning' },
    )
  } catch {
    return
  }
  try {
    await deleteRecord(rec.id)
    ElMessage.success('学习记录已删除')
    if (records.value.length === 1 && page.value > 1) {
      page.value -= 1
    }
    void loadRecords()
    void loadStats()
  } catch {
    // 错误提示已由 request.ts 拦截器统一展示
  }
}

// ---------------------------------------------------------------------------
// P5 跳转预填消费（tasks 8.3：query → 新建弹窗预填）
// ---------------------------------------------------------------------------
/** 读取 route.query，有任一可识别参数即构造预填并打开新建弹窗。 */
function consumeQueryPreset(): void {
  const q = route.query
  const taskId = Number.parseInt(String(q.task_id ?? ''), 10)
  const courseId = Number.parseInt(String(q.course_id ?? ''), 10)
  const taskTitle = typeof q.task_title === 'string' ? q.task_title : ''
  const knowledgePoints =
    typeof q.knowledge_points === 'string'
      ? normalizeKnowledgePoints(q.knowledge_points.split(','))
      : []

  const hasTaskId = Number.isInteger(taskId) && taskId > 0
  const hasCourseId = Number.isInteger(courseId) && courseId > 0
  if (!hasTaskId && !hasCourseId && !taskTitle && knowledgePoints.length === 0) {
    return
  }

  preset.value = {
    ...(taskTitle ? { content: taskTitle, task_title: taskTitle } : {}),
    ...(knowledgePoints.length > 0 ? { knowledge_points: knowledgePoints } : {}),
    course_id: hasCourseId ? courseId : null,
    task_id: hasTaskId ? taskId : null,
  }
  formVisible.value = true
}
</script>

<template>
  <el-space direction="vertical" alignment="stretch" :size="16" style="width: 100%">
    <el-card shadow="never">
      <RecordStatsCards :stats="stats" />
    </el-card>

    <el-card shadow="never">
      <div class="toolbar">
        <div class="filters">
          <el-date-picker
            v-model="filterDateRange"
            type="daterange"
            value-format="YYYY-MM-DD"
            range-separator="至"
            start-placeholder="开始日期"
            end-placeholder="结束日期"
            clearable
            class="filter-item date-range"
          />
          <el-select
            v-model="filterCourseId"
            class="filter-item"
            placeholder="全部课程"
            clearable
          >
            <el-option v-for="c in courses" :key="c.id" :label="c.name" :value="c.id" />
          </el-select>
          <el-input
            v-model="filterKnowledgePoint"
            class="filter-item"
            placeholder="知识点（回车筛选）"
            clearable
            @keyup.enter="onKnowledgeSearch"
            @clear="onKnowledgeSearch"
          />
          <el-button @click="onResetFilters">重置</el-button>
        </div>
        <div class="toolbar-right">
          <el-button type="primary" @click="onCreate">记录学习</el-button>
        </div>
      </div>
    </el-card>

    <el-card shadow="never" v-loading="listLoading">
      <el-empty
        v-if="!listLoading && records.length === 0"
        description="还没有学习记录，去记录第一条学习吧"
      >
        <el-button type="primary" @click="onCreate">记录学习</el-button>
      </el-empty>
      <template v-else>
        <div v-for="group in dateGroups" :key="group.date" class="date-group">
          <div class="group-title">
            {{ group.title }}
            <span class="group-count">{{ group.records.length }} 条</span>
          </div>
          <div v-for="rec in group.records" :key="rec.id" class="record-card">
            <div class="record-head">
              <span class="record-content">{{ rec.content }}</span>
              <span class="record-actions">
                <el-button link type="primary" size="small" @click="onEdit(rec)">编辑</el-button>
                <el-button link type="danger" size="small" @click="onDelete(rec)">删除</el-button>
              </span>
            </div>
            <div class="record-meta">
              <span class="meta-item">{{ formatMinutes(rec.duration_minutes) }}</span>
              <span v-if="rec.course_id != null" class="meta-item">
                {{ courseNameMap.get(rec.course_id) ?? `课程 #${rec.course_id}` }}
              </span>
              <span v-if="rec.task_id != null" class="meta-item">任务 #{{ rec.task_id }}</span>
              <el-tag
                v-if="rec.mastery_level != null"
                :type="masterySegment(rec.mastery_level)?.tagType ?? 'info'"
                size="small"
                effect="plain"
              >
                自评 {{ rec.mastery_level }} · {{ masterySegment(rec.mastery_level)?.label }}
              </el-tag>
              <span v-else class="meta-item">未自评</span>
            </div>
            <div v-if="normalizeKnowledgePoints(rec.knowledge_points).length > 0" class="record-kps">
              <el-tag
                v-for="k in normalizeKnowledgePoints(rec.knowledge_points)"
                :key="k"
                size="small"
                type="info"
                effect="plain"
              >
                {{ k }}
              </el-tag>
            </div>
            <div v-if="rec.achievement" class="record-note">
              <span class="note-label">成果</span>{{ rec.achievement }}
            </div>
            <div v-if="rec.problems" class="record-note problems">
              <span class="note-label">问题</span>{{ rec.problems }}
            </div>
          </div>
        </div>
        <div class="pagination-row">
          <el-pagination
            layout="total, prev, pager, next"
            :total="total"
            :page-size="pageSize"
            :current-page="page"
            @current-change="onPageChange"
          />
        </div>
      </template>
    </el-card>

    <RecordFormDialog
      v-model:visible="formVisible"
      :editing="editingRecord"
      :courses="courses"
      :preset="preset"
      :knowledge-options="knowledgeOptions"
      @saved="onSaved"
    />
  </el-space>
</template>

<style scoped>
.toolbar {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
  justify-content: space-between;
}
.filters {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
}
.filter-item {
  width: 160px;
}
.filter-item.date-range {
  width: 260px;
}
.toolbar-right {
  display: flex;
  align-items: center;
}
.date-group {
  margin-bottom: 20px;
}
.date-group:last-of-type {
  margin-bottom: 0;
}
.group-title {
  margin-bottom: 8px;
  font-size: 14px;
  font-weight: 600;
  color: var(--el-text-color-primary);
}
.group-count {
  margin-left: 8px;
  font-size: 12px;
  font-weight: 400;
  color: var(--el-text-color-secondary);
}
.record-card {
  padding: 12px;
  margin-bottom: 8px;
  border-radius: 6px;
  background: var(--el-fill-color-light);
}
.record-card:last-child {
  margin-bottom: 0;
}
.record-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 8px;
}
.record-content {
  font-size: 14px;
  font-weight: 500;
  color: var(--el-text-color-primary);
  word-break: break-all;
}
.record-actions {
  flex-shrink: 0;
}
.record-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  align-items: center;
  margin-top: 8px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
.record-kps {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  margin-top: 8px;
}
.record-note {
  margin-top: 8px;
  padding: 8px;
  font-size: 12px;
  color: var(--el-text-color-regular);
  background: var(--el-fill-color);
  border-radius: 4px;
  word-break: break-all;
}
.record-note .note-label {
  margin-right: 8px;
  font-weight: 600;
  color: var(--el-color-success);
}
.record-note.problems .note-label {
  color: var(--el-color-warning);
}
.pagination-row {
  display: flex;
  justify-content: flex-end;
  margin-top: 16px;
}
</style>