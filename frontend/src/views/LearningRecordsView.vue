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
import PageHeader from '@/components/common/PageHeader.vue'
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
  <div class="page records-view">
    <PageHeader
      folio="卷四 · 留痕"
      title="学习记录"
      lead="每天记下学了什么、多久、掌握了多少；这些痕迹会变成趋势和建议。"
    >
      <template #actions>
        <el-button type="primary" @click="onCreate">记录学习</el-button>
      </template>
    </PageHeader>

    <RecordStatsCards :stats="stats" />

    <div class="filter-bar">
      <el-date-picker
        v-model="filterDateRange"
        type="daterange"
        value-format="YYYY-MM-DD"
        range-separator="至"
        start-placeholder="开始日期"
        end-placeholder="结束日期"
        clearable
        class="filter-item filter-item--date"
      />
      <el-select v-model="filterCourseId" class="filter-item" placeholder="全部课程" clearable>
        <el-option v-for="c in courses" :key="c.id" :label="c.name" :value="c.id" />
      </el-select>
      <el-input
        v-model="filterKnowledgePoint"
        class="filter-item filter-item--wide"
        placeholder="知识点（回车筛选）"
        clearable
        @keyup.enter="onKnowledgeSearch"
        @clear="onKnowledgeSearch"
      />
      <el-button @click="onResetFilters">重置</el-button>
      <span class="filter-bar__spacer" />
      <span class="filter-bar__hint">共 {{ total }} 条记录</span>
    </div>

    <div v-loading="listLoading" class="records-body">
      <div v-if="!listLoading && records.length === 0" class="empty-note">
        <span class="seal seal--ghost" aria-hidden="true">记</span>
        <div class="empty-note__title">还没有学习记录</div>
        <div>从今天开始记一笔，哪怕只有二十分钟。</div>
        <div class="empty-note__actions">
          <el-button type="primary" @click="onCreate">记录学习</el-button>
        </div>
      </div>

      <template v-else>
        <section v-for="group in dateGroups" :key="group.date" class="record-day">
          <header class="record-day__head">
            <h2 class="record-day__title">{{ group.title }}</h2>
            <span v-if="group.title !== group.date" class="record-day__date">
              {{ group.date }}
            </span>
            <span class="record-day__count">{{ group.records.length }} 条</span>
          </header>

          <article v-for="rec in group.records" :key="rec.id" class="record-row">
            <div class="record-row__time">
              <span class="record-duration">{{ formatMinutes(rec.duration_minutes) }}</span>
              <span class="record-duration-label">时长</span>
            </div>

            <div class="record-row__main">
              <div class="record-row__head">
                <h3 class="record-content">{{ rec.content }}</h3>
                <div class="record-actions">
                  <el-button link size="small" @click="onEdit(rec)">编辑</el-button>
                  <el-button link size="small" type="danger" @click="onDelete(rec)">删除</el-button>
                </div>
              </div>

              <div class="record-meta">
                <span v-if="rec.course_id != null" class="meta-item">
                  {{ courseNameMap.get(rec.course_id) ?? `课程 #${rec.course_id}` }}
                </span>
                <span v-if="rec.task_id != null" class="meta-item">任务 #{{ rec.task_id }}</span>
                <span
                  v-if="rec.mastery_level != null"
                  class="mastery-chip"
                  :class="`is-${masterySegment(rec.mastery_level)?.tagType ?? 'info'}`"
                >
                  <span class="mastery-chip__dot" aria-hidden="true" />
                  自评 {{ rec.mastery_level }} · {{ masterySegment(rec.mastery_level)?.label }}
                </span>
                <span v-else class="meta-item">未自评</span>
              </div>

              <div
                v-if="normalizeKnowledgePoints(rec.knowledge_points).length > 0"
                class="record-kps"
              >
                <span
                  v-for="k in normalizeKnowledgePoints(rec.knowledge_points)"
                  :key="k"
                  class="kp"
                >
                  {{ k }}
                </span>
              </div>

              <div v-if="rec.achievement" class="record-note">
                <span class="note-label">成果</span>
                <span class="note-text">{{ rec.achievement }}</span>
              </div>
              <div v-if="rec.problems" class="record-note is-problem">
                <span class="note-label">问题</span>
                <span class="note-text">{{ rec.problems }}</span>
              </div>
            </div>
          </article>
        </section>

        <div class="pager-row">
          <el-pagination
            layout="total, prev, pager, next"
            :total="total"
            :page-size="pageSize"
            :current-page="page"
            @current-change="onPageChange"
          />
        </div>
      </template>
    </div>

    <RecordFormDialog
      v-model:visible="formVisible"
      :editing="editingRecord"
      :courses="courses"
      :preset="preset"
      :knowledge-options="knowledgeOptions"
      @saved="onSaved"
    />
  </div>
</template>

<style scoped>
.records-body {
  min-height: 240px;
}

.record-day {
  margin-bottom: 28px;
}

.record-day:last-of-type {
  margin-bottom: 0;
}

.record-day__head {
  display: flex;
  align-items: baseline;
  gap: 12px;
  padding-bottom: 8px;
  margin-bottom: 2px;
  border-bottom: 1px solid var(--line);
}

.record-day__title {
  display: flex;
  align-items: center;
  gap: 8px;
  font-family: var(--font-display);
  font-size: 19px;
  font-weight: 600;
  color: var(--ink);
}

.record-day__title::before {
  content: '';
  width: 6px;
  height: 6px;
  background: var(--vermilion);
  border-radius: 1px;
}

.record-day__date {
  font-family: var(--font-mono);
  font-size: 10px;
  color: var(--ink-4);
}

.record-day__count {
  margin-left: auto;
  font-family: var(--font-mono);
  font-size: 10px;
  color: var(--ink-4);
}

.record-row {
  display: flex;
  gap: 18px;
  padding: 16px 0;
  border-bottom: 1px solid var(--line-soft);
}

.record-row:last-child {
  border-bottom: none;
}

.record-row__time {
  flex: 0 0 92px;
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 3px;
  padding-right: 16px;
  border-right: 1px solid var(--line-soft);
  text-align: right;
}

.record-duration {
  font-family: var(--font-mono);
  font-size: 11px;
  line-height: 1.5;
  color: var(--ink-2);
}

.record-duration-label {
  font-family: var(--font-mono);
  font-size: 9px;
  letter-spacing: 0.1em;
  color: var(--ink-4);
}

.record-row__main {
  flex: 1 1 auto;
  min-width: 0;
}

.record-row__head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
}

.record-content {
  font-size: 15px;
  font-weight: 600;
  line-height: 1.55;
  color: var(--ink);
  word-break: break-word;
}

.record-actions {
  flex: 0 0 auto;
  display: flex;
  gap: 2px;
}

.record-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  align-items: center;
  margin-top: 7px;
  font-size: 11px;
  color: var(--ink-3);
}

.meta-item {
  font-family: var(--font-mono);
  font-size: 10px;
  color: var(--ink-4);
}

.mastery-chip {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  font-family: var(--font-mono);
  font-size: 9px;
  color: var(--ink-3);
}

.mastery-chip__dot {
  width: 5px;
  height: 5px;
  border-radius: 1px;
  background: var(--dust);
}

.mastery-chip.is-danger .mastery-chip__dot {
  background: var(--vermilion);
}

.mastery-chip.is-warning .mastery-chip__dot {
  background: var(--ochre);
}

.mastery-chip.is-success .mastery-chip__dot {
  background: var(--jade);
}

.record-kps {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  margin-top: 8px;
}

.kp {
  padding: 0 6px;
  font-size: 10px;
  line-height: 18px;
  color: var(--ink-3);
  background: var(--paper-3);
  border: 1px solid var(--line-soft);
  border-radius: var(--radius);
}

.record-note {
  display: flex;
  gap: 10px;
  margin-top: 9px;
  padding-top: 8px;
  border-top: 1px dashed var(--line);
  font-size: 12px;
  line-height: 1.7;
  color: var(--ink-2);
  word-break: break-word;
}

.note-label {
  flex: 0 0 26px;
  font-family: var(--font-mono);
  font-size: 9px;
  letter-spacing: 0.08em;
  color: var(--jade);
  padding-top: 2px;
}

.record-note.is-problem .note-label {
  color: var(--ochre);
}

.note-text {
  flex: 1 1 auto;
  min-width: 0;
}

.pager-row {
  display: flex;
  justify-content: flex-end;
  padding-top: 16px;
}

@media (max-width: 720px) {
  .record-row {
    flex-direction: column;
    gap: 8px;
  }

  .record-row__time {
    flex-direction: row;
    align-items: baseline;
    justify-content: flex-start;
    gap: 6px;
    padding-right: 0;
    border-right: none;
    text-align: left;
  }
}
</style>