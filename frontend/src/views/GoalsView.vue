<script setup lang="ts">
/**
 * 学习目标页面（P4，design 2.5.1 页面编排）。
 *
 * - 筛选区：状态单选（全部 / 进行中 / 已完成 / 已归档）+「新建目标」；
 * - 卡片列表区：响应式 el-row/el-col 渲染 GoalCard + 分页 + 空态；
 * - 弹窗与抽屉：GoalFormDialog（新建/编辑）、RoadmapDrawer（知识树/
 *   AI 拆解）；拆解成功原位更新卡片 roadmap 数据（不整页刷新）。
 */
import { onMounted, ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'

import { deleteGoal, fetchGoals } from '@/api/goal'
import PageHeader from '@/components/common/PageHeader.vue'
import GoalCard from '@/components/goal/GoalCard.vue'
import GoalFormDialog from '@/components/goal/GoalFormDialog.vue'
import RoadmapDrawer from '@/components/goal/RoadmapDrawer.vue'
import type { Goal, GoalListQuery, GoalRoadmap, GoalStatus } from '@/types'

/** 状态筛选项（'' = 全部）。 */
const STATUS_FILTERS: { value: GoalStatus | ''; label: string }[] = [
  { value: '', label: '全部' },
  { value: 'active', label: '进行中' },
  { value: 'completed', label: '已完成' },
  { value: 'archived', label: '已归档' },
]

/** 列表状态。 */
const goals = ref<Goal[]>([])
const total = ref(0)
const page = ref(1)
const pageSize = ref(10)
const statusFilter = ref<GoalStatus | ''>('')
const listLoading = ref(false)

/** 弹窗状态（goal 为 null = 新建）。 */
const formVisible = ref(false)
const editingGoal = ref<Goal | null>(null)

/** 抽屉状态。 */
const drawerVisible = ref(false)
const drawerGoal = ref<Goal | null>(null)
const drawerAction = ref<'view' | 'breakdown'>('view')

/**
 * 加载目标列表（按当前筛选与分页）。
 */
async function loadGoals(): Promise<void> {
  listLoading.value = true
  try {
    const params: GoalListQuery = { page: page.value, page_size: pageSize.value }
    if (statusFilter.value) params.status = statusFilter.value
    const data = await fetchGoals(params)
    goals.value = data.items
    total.value = data.total
  } catch {
    // 错误提示已由 request.ts 拦截器统一展示
  } finally {
    listLoading.value = false
  }
}

// 状态筛选变化：回到第 1 页重新加载。
watch(statusFilter, () => {
  page.value = 1
  void loadGoals()
})

onMounted(loadGoals)

/** 分页页码变化。 */
function onPageChange(p: number): void {
  page.value = p
  void loadGoals()
}

/** 每页条数变化：回到第 1 页。 */
function onSizeChange(s: number): void {
  pageSize.value = s
  page.value = 1
  void loadGoals()
}

/** 新建目标。 */
function onCreate(): void {
  editingGoal.value = null
  formVisible.value = true
}

/** 编辑目标。 */
function onEdit(goal: Goal): void {
  editingGoal.value = goal
  formVisible.value = true
}

/**
 * 弹窗保存回调：编辑则原位替换，新建则刷新列表
 * （新建影响 total 与页码，刷新最稳）。
 */
function onSaved(saved: Goal): void {
  const idx = goals.value.findIndex((g) => g.id === saved.id)
  if (idx >= 0) {
    goals.value[idx] = saved
  } else {
    void loadGoals()
  }
}

/** 删除目标（二次确认；知识树一并删除、掌握度由后端保留）。 */
async function onDelete(goal: Goal): Promise<void> {
  try {
    await ElMessageBox.confirm(
      '该目标下的知识树将一并删除，且删除后不可恢复。确定删除该目标吗？',
      '删除目标',
      { type: 'warning', confirmButtonText: '删除', cancelButtonText: '取消' },
    )
  } catch {
    return
  }
  try {
    await deleteGoal(goal.id)
    ElMessage.success('删除成功')
    // 当前页仅剩这一条且不在第 1 页：先回退一页再加载。
    if (goals.value.length === 1 && page.value > 1) {
      page.value -= 1
    }
    void loadGoals()
  } catch {
    // 错误提示已由拦截器统一展示
  }
}

/** 查看知识树（打开抽屉）。 */
function onViewRoadmap(goal: Goal): void {
  drawerGoal.value = goal
  drawerAction.value = 'view'
  drawerVisible.value = true
}

/** AI 拆解（打开抽屉并声明动作，二次确认由抽屉统一处理）。 */
function onBreakdown(goal: Goal): void {
  drawerGoal.value = goal
  drawerAction.value = 'breakdown'
  drawerVisible.value = true
}

/** 拆解成功：原位更新卡片 roadmap / roadmap_updated_at（不整页刷新）。 */
function onBreakdownSuccess(data: GoalRoadmap): void {
  const g = drawerGoal.value
  if (g) {
    g.roadmap = data.roadmap
    g.roadmap_updated_at = data.roadmap_updated_at
  }
}
</script>

<template>
  <div class="page goals-view">
    <PageHeader
      folio="卷二 · 方向"
      title="学习目标"
      lead="先写清楚要去的地方，再让 AI 把它拆成可以每天执行的知识点。"
    >
      <template #actions>
        <el-button type="primary" @click="onCreate">新建目标</el-button>
      </template>
    </PageHeader>

    <div class="filter-bar">
      <el-radio-group v-model="statusFilter" aria-label="按状态筛选目标">
        <el-radio-button v-for="f in STATUS_FILTERS" :key="f.value" :value="f.value">
          {{ f.label }}
        </el-radio-button>
      </el-radio-group>
      <span class="filter-bar__spacer" />
      <span class="filter-bar__hint">共 {{ total }} 个目标</span>
    </div>

    <div v-loading="listLoading" class="goals-body">
      <div v-if="!listLoading && goals.length === 0" class="empty-note">
        <span class="seal seal--ghost" aria-hidden="true">目</span>
        <div class="empty-note__title">还没有写下学习目标</div>
        <div>先写一个想去的地方，再让 AI 把它拆成知识点。</div>
        <div class="empty-note__actions">
          <el-button type="primary" @click="onCreate">新建目标</el-button>
        </div>
      </div>

      <template v-else>
        <div class="goal-grid">
          <GoalCard
            v-for="g in goals"
            :key="g.id"
            :goal="g"
            @edit="onEdit"
            @breakdown="onBreakdown"
            @view-roadmap="onViewRoadmap"
            @delete="onDelete"
          />
        </div>

        <div v-if="total > 0" class="pager-row">
          <el-pagination
            :current-page="page"
            :page-size="pageSize"
            :total="total"
            :page-sizes="[10, 20, 50]"
            layout="total, sizes, prev, pager, next"
            @current-change="onPageChange"
            @size-change="onSizeChange"
          />
        </div>
      </template>
    </div>
  </div>

  <GoalFormDialog v-model:visible="formVisible" :goal="editingGoal" @saved="onSaved" />
  <RoadmapDrawer
    v-model:visible="drawerVisible"
    :goal="drawerGoal"
    :initial-action="drawerAction"
    @breakdown-success="onBreakdownSuccess"
  />
</template>

<style scoped>
.goals-body {
  min-height: 240px;
}

.goal-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
  gap: 16px;
}

.pager-row {
  display: flex;
  justify-content: flex-end;
  padding-top: 12px;
}

@media (max-width: 720px) {
  .goal-grid {
    grid-template-columns: minmax(0, 1fr);
  }
}
</style>