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
  <el-space direction="vertical" alignment="stretch" :size="16" style="width: 100%">
    <el-card shadow="never">
      <div class="toolbar">
        <el-radio-group v-model="statusFilter">
          <el-radio-button v-for="f in STATUS_FILTERS" :key="f.value" :label="f.value">
            {{ f.label }}
          </el-radio-button>
        </el-radio-group>
        <el-button type="primary" @click="onCreate">新建目标</el-button>
      </div>
    </el-card>

    <el-card shadow="never" v-loading="listLoading">
      <el-empty
        v-if="!listLoading && goals.length === 0"
        description="还没有学习目标"
      >
        <el-button type="primary" @click="onCreate">新建目标</el-button>
      </el-empty>
      <template v-else>
        <el-row :gutter="16">
          <el-col
            v-for="g in goals"
            :key="g.id"
            :xs="24"
            :sm="12"
            :lg="8"
            class="card-col"
          >
            <GoalCard
              :goal="g"
              @edit="onEdit"
              @breakdown="onBreakdown"
              @view-roadmap="onViewRoadmap"
              @delete="onDelete"
            />
          </el-col>
        </el-row>
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
    </el-card>
  </el-space>

  <GoalFormDialog v-model:visible="formVisible" :goal="editingGoal" @saved="onSaved" />
  <RoadmapDrawer
    v-model:visible="drawerVisible"
    :goal="drawerGoal"
    :initial-action="drawerAction"
    @breakdown-success="onBreakdownSuccess"
  />
</template>

<style scoped>
.toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
}
.card-col {
  margin-bottom: 16px;
}
.pager-row {
  display: flex;
  justify-content: flex-end;
  margin-top: 8px;
}
</style>