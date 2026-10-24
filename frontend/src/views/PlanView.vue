<script setup lang="ts">
/**
 * 学习计划周视图（P13 批次 3；design 2.1.3-A/B/C / 2.4.1；spec §5.1–§5.4）。
 *
 * 会话态状态机编排（不复用 useDashboardBlock，决策 D2）：
 * - 首屏/刷新/重试共用 loadCurrent（仅 1 次 GET /plans/current）；
 * - 生成成功直接渲染响应会话态，不重查 current（spec §5.1.1 规则 1-②）；
 * - adjust 两段式：adjust 请求 + 服务端取数（current 命中 → 翻页兜底），
 *   取数完成才进 diff 预览（spec §5.3.1 规则 4，D7/D14）；
 * - 「查看调整后的计划」/ 关闭对比 / ESC 统一 handleConfirmNewPlan(source)，
 *   零请求切换（裁定 #2）；仅 close 路径提示「新计划已生效」；
 * - 取数失败 → 独立错误卡（D15），文案必须含「调整已生效」语义，
 *   绝不渲染旧网格冒充新版本；
 * - 回看（handleViewHistory）是 fetchPlanDiff 的唯一调用点（规则 7）。
 *
 * 不引入 Pinia（D12）；错误提示由 request.ts 拦截器统一弹出，catch 只做
 * 状态回滚（静默）。
 */
import { computed, onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'

import {
  adjustPlan,
  fetchCurrentPlan,
  fetchLearningPlanItems,
  fetchPlanDiff,
  generatePlan,
} from '@/api/plan'
import type {
  PendingNewPlan,
  PlanDiff,
  PlanItem,
  SessionPlan,
  UnplacedTask,
} from '@/types/plan'
import { todayLocalStr } from '@/utils/record'
import AdjustHistoryPanel from '@/components/plan/AdjustHistoryPanel.vue'
import PlanDiffPreview from '@/components/plan/PlanDiffPreview.vue'
import PlanEmptyState from '@/components/plan/PlanEmptyState.vue'
import PlanInfoHeader from '@/components/plan/PlanInfoHeader.vue'
import UnplacedTasksCard from '@/components/plan/UnplacedTasksCard.vue'
import WeekGrid from '@/components/plan/WeekGrid.vue'

/** 取数兜底内部错误类（仅驱动错误态分支，design 2.2.2-(8)）。 */
class PlanFetchError extends Error {}

// ---------------------------------------------------------------------------
// 页面状态字段（design 2.4.1 九项，逐项落地）
// ---------------------------------------------------------------------------

const phase = ref<'loading' | 'empty' | 'ready'>('loading')
const viewMode = ref<'week' | 'diff' | 'history'>('week')
const sessionPlan = ref<SessionPlan | null>(null)
const unplacedTasks = ref<UnplacedTask[]>([])
const pendingNew = ref<PendingNewPlan | null>(null)
const historyDiff = ref<PlanDiff | null>(null)
const fetchError = ref(false)
const generating = ref(false)
const adjusting = ref(false)
const fetchingItems = ref(false)
const degraded = ref(false)

/** 调整流程全程锁（adjust 请求 + 取数两阶段，决策 D14）。 */
const adjustBusy = computed(() => adjusting.value || fetchingItems.value)

/** 「下周计划」标注推导（决策 D3：日期推导比 origin 更稳健）。 */
const isNextWeek = computed(() =>
  sessionPlan.value ? sessionPlan.value.plan.start_date > todayLocalStr() : false,
)

// ---------------------------------------------------------------------------
// loadCurrent：首屏 / 刷新 / 错误态重试共用入口（design 2.2.2-(8)）
// ---------------------------------------------------------------------------

async function loadCurrent(): Promise<void> {
  phase.value = 'loading'
  fetchError.value = false
  viewMode.value = 'week'
  pendingNew.value = null
  unplacedTasks.value = []
  historyDiff.value = null
  degraded.value = false
  try {
    const current = await fetchCurrentPlan()
    if (current == null) {
      // 正常空态（HTTP 200 + data=null，非 404，不走 catch）
      phase.value = 'empty'
      return
    }
    sessionPlan.value = { plan: current.plan, items: current.items, origin: 'current' }
    phase.value = 'ready'
  } catch {
    // 拦截器已弹错；首屏失败落空态兜底（D15：空态 ≠ 取数错误卡，spec §5.1.3-2）
    phase.value = 'empty'
  }
}

onMounted(() => {
  void loadCurrent()
})

// ---------------------------------------------------------------------------
// handleGenerate：生成动作（会话态直接渲染，不重查 current）
// ---------------------------------------------------------------------------

async function handleGenerate(): Promise<void> {
  if (generating.value) return
  generating.value = true
  try {
    const res = await generatePlan()
    sessionPlan.value = { plan: res.plan, items: res.items, origin: 'generate' }
    unplacedTasks.value = res.unplaced_tasks
    pendingNew.value = null
    historyDiff.value = null
    fetchError.value = false
    viewMode.value = 'week'
    phase.value = 'ready'
    degraded.value = res.generated_by === 'rules'
    ElMessage.success('生成成功')
    if (degraded.value) {
      ElMessage.warning('LLM 规划暂不可用，已按规则引擎生成计划')
    }
    // 不重查 current：下周计划不满足 current 条件（spec §5.1.1 规则 1-②）
  } catch {
    // 拦截器已弹错；维持原状态（空态或原周视图）
  } finally {
    generating.value = false
  }
}

// ---------------------------------------------------------------------------
// handleAdjust + resolveNewVersionItems：两段式服务端取数（核心红线）
// ---------------------------------------------------------------------------

const PAGE_SIZE = 100
const MAX_PAGES = 50 // R3：脏数据死循环硬上限（50×100=5000 条远超真实规模）

/**
 * 新版本条目两段式取数（spec §5.3.1 规则 4；design 2.2.2-(8)）。
 *
 * ① current 命中同 id 才采用其 items（优化路径）——current 请求失败不直接
 * 放弃，console.warn 后继续兜底；② 否则翻页取全 + 客户端 plan_id 过滤；
 * ③ 过滤为空或任一请求失败 → 抛 PlanFetchError（驱动错误卡分支）。
 */
async function resolveNewVersionItems(targetPlanId: number): Promise<PlanItem[]> {
  try {
    const current = await fetchCurrentPlan()
    if (current != null && current.plan.id === targetPlanId) {
      return current.items
    }
  } catch (e) {
    console.warn('[resolveNewVersionItems] current 命中判定失败，转翻页兜底', e)
  }

  let page = 1
  const all: PlanItem[] = []
  while (true) {
    const res = await fetchLearningPlanItems(page, PAGE_SIZE)
    all.push(...res.items)
    if (page * PAGE_SIZE >= res.total) break
    page += 1
    if (page > MAX_PAGES) {
      console.warn(`[resolveNewVersionItems] 翻页超过 ${MAX_PAGES} 页硬上限，按已取数据过滤`)
      break
    }
  }
  const filtered = all.filter((it) => it.plan_id === targetPlanId)
  if (filtered.length === 0) {
    throw new PlanFetchError(`未取到计划 ${targetPlanId} 的任何条目`)
  }
  return filtered
}

async function handleAdjust(): Promise<void> {
  if (adjustBusy.value || !sessionPlan.value) return
  const planId = sessionPlan.value.plan.id
  const oldItems = [...sessionPlan.value.items] // 双栏左栏快照（adjust 发起时拷贝）

  // 阶段 1：adjust 请求（失败 → 停留原周视图，不置 fetchError，spec §5.3.3-1/2/5）
  adjusting.value = true
  let res
  try {
    res = await adjustPlan(planId)
  } catch {
    adjusting.value = false
    return
  }
  if (!res.adjusted) {
    // 无可调整：adjust_reason 此场景为提示文案（spec §5.3.1 规则 5）
    adjusting.value = false
    ElMessage.info(res.adjust_reason ?? '当前计划暂无需调整的条目')
    return
  }

  // 阶段 2：服务端取数（失败 → 独立错误卡；绝不渲染旧网格冒充新版本）
  fetchingItems.value = true
  try {
    const items = await resolveNewVersionItems(res.plan.id)
    pendingNew.value = {
      plan: res.plan,
      items,
      diff: res.diff,
      oldItems,
      adjustReason: res.adjust_reason,
    }
    fetchError.value = false
    viewMode.value = 'diff'
  } catch {
    fetchError.value = true
    pendingNew.value = null
    viewMode.value = 'week'
  } finally {
    adjusting.value = false
    fetchingItems.value = false
  }
}

// ---------------------------------------------------------------------------
// handleConfirmNewPlan(source)：零请求切换（裁定 #2 统一出口）
// ---------------------------------------------------------------------------

function handleConfirmNewPlan(source: 'primary' | 'close'): void {
  const pending = pendingNew.value
  if (!pending) return
  // 同一 items 引用转移（diff 右栏与切换后周视图一致）；全程零请求
  sessionPlan.value = { plan: pending.plan, items: pending.items, origin: 'adjust' }
  pendingNew.value = null
  viewMode.value = 'week'
  phase.value = 'ready'
  fetchError.value = false
  if (source === 'close') {
    ElMessage.info('新计划已生效')
  }
}

// ---------------------------------------------------------------------------
// handleViewHistory / 返回：回看路径（fetchPlanDiff 唯一调用点）
// ---------------------------------------------------------------------------

async function handleViewHistory(): Promise<void> {
  const plan = sessionPlan.value?.plan
  if (!plan || plan.parent_plan_id == null) return
  viewMode.value = 'history'
  historyDiff.value = null // null = 请求飞行中，AdjustHistoryPanel 显示骨架
  try {
    historyDiff.value = await fetchPlanDiff(plan.id)
  } catch {
    // 拦截器已弹错；停留原周视图（spec §5.4.3-1）
    viewMode.value = 'week'
  }
}

function handleBackFromHistory(): void {
  // historyDiff 保留不重发请求，零请求回切（spec §5.4.1 规则 3）
  viewMode.value = 'week'
}
</script>

<template>
  <div class="plan-view">
    <!-- 1. 首屏加载骨架 -->
    <el-skeleton v-if="phase === 'loading'" :rows="8" animated />

    <!-- 2. 取数失败错误卡（优先于周视图，不残留旧网格冒充新版本，D15） -->
    <el-card v-else-if="fetchError" class="fetch-error-card" shadow="never">
      <div class="error-icon">!</div>
      <div class="error-text">计划调整已生效，但新版本条目暂时加载失败</div>
      <el-button type="primary" @click="loadCurrent">重新加载</el-button>
    </el-card>

    <!-- 3. diff 预览 -->
    <PlanDiffPreview
      v-else-if="viewMode === 'diff' && pendingNew"
      :pending="pendingNew"
      @confirm="handleConfirmNewPlan"
    />

    <!-- 4. 调整记录回看 -->
    <AdjustHistoryPanel
      v-else-if="viewMode === 'history' && sessionPlan"
      :plan="sessionPlan.plan"
      :diff="historyDiff"
      :loading="historyDiff === null"
      @back="handleBackFromHistory"
    />

    <!-- 5. 空态引导（首屏失败也落此兜底，页面保持可用） -->
    <PlanEmptyState v-else-if="phase === 'empty'" :loading="generating" @generate="handleGenerate" />

    <!-- 6. 周视图 -->
    <template v-else-if="phase === 'ready' && sessionPlan && viewMode === 'week'">
      <PlanInfoHeader
        :plan="sessionPlan.plan"
        :is-next-week="isNextWeek"
        :degraded="degraded"
        @view-history="handleViewHistory"
      />
      <div class="toolbar">
        <el-button
          type="primary"
          :loading="generating"
          :disabled="adjustBusy"
          @click="handleGenerate"
        >
          生成下一周学习计划
        </el-button>
        <el-button plain :loading="adjustBusy" :disabled="generating" @click="handleAdjust">
          重新调整计划
        </el-button>
        <span class="toolbar-hint">同一周期重复生成会归档旧版本</span>
      </div>
      <WeekGrid :plan="sessionPlan.plan" :items="sessionPlan.items" />
      <UnplacedTasksCard v-if="unplacedTasks.length > 0" :tasks="unplacedTasks" />
    </template>
  </div>
</template>

<style scoped>
.plan-view {
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.toolbar {
  display: flex;
  align-items: center;
  gap: 12px;
}
.toolbar-hint {
  font-size: 12px;
  color: var(--el-text-color-placeholder);
}
.fetch-error-card {
  text-align: center;
  padding: 32px 0;
}
.error-icon {
  width: 40px;
  height: 40px;
  margin: 0 auto 12px;
  border-radius: 50%;
  background: var(--el-color-danger-light-9);
  color: var(--el-color-danger);
  font-size: 22px;
  font-weight: 600;
  line-height: 40px;
}
.error-text {
  font-size: 15px;
  color: var(--el-text-color-primary);
  margin-bottom: 16px;
}
</style>