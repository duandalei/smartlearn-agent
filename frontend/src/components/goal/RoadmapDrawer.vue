<script setup lang="ts">
/**
 * 知识树抽屉（P4，design 2.5.4）。
 *
 * 拆解状态机：空（尚未拆解）→ loading（AI 拆解中，按钮 loading 且
 * disabled 防重复提交）→ success（ECharts 树图 + 叶子数摘要）/
 * failed（ElAlert 持续提示，文案经 breakdownErrorMessage 二分类）。
 *
 * - initialAction='view'：打开即拉取知识树渲染；
 * - initialAction='breakdown'：已有树时先 ElMessageBox 二次确认
 *   （取消停留当前视图不发请求），确认后调 breakdownGoal（90s 超时
 *   已在 api 层覆盖）；
 * - 成功后 emit('breakdown-success')，由父页面原位更新卡片数据。
 */
import * as echarts from 'echarts/core'
import { TreeChart } from 'echarts/charts'
import { CanvasRenderer } from 'echarts/renderers'
import { TooltipComponent } from 'echarts/components'
import type { EChartsOption } from 'echarts'
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import { ElMessageBox } from 'element-plus'

import { breakdownGoal, fetchGoalRoadmap } from '@/api/goal'
import type { Goal, GoalRoadmap, RoadmapNode } from '@/types'
import { breakdownErrorMessage, countLeaves, toEChartsTree } from '@/utils/goal'
import {
  CHART_COLORS,
  CHART_FONT,
  CHART_TOOLTIP,
} from '@/utils/chartTheme'

echarts.use([TreeChart, CanvasRenderer, TooltipComponent])

const props = defineProps<{
  visible: boolean
  goal: Goal | null
  initialAction: 'view' | 'breakdown'
}>()

const emit = defineEmits<{
  (e: 'update:visible', v: boolean): void
  (e: 'breakdown-success', data: GoalRoadmap): void
  (e: 'breakdown-failed'): void
}>()

/** 本地知识树（打开时先取 goal 快照，拉取/拆解后刷新）。 */
const roadmap = ref<RoadmapNode | null>(null)
/** 拆解时间（ISO 字符串）。 */
const roadmapUpdatedAt = ref<string | null>(null)
/** 拆解中（loading 态：主按钮 loading + 蒙层文案）。 */
const breaking = ref(false)
/** 查看拉取中（短暂 v-loading，无文案）。 */
const viewLoading = ref(false)
/** 失败态持续提示文案（空串 = 非失败态）。 */
const failedMessage = ref('')

/** ECharts 容器与实例。 */
const chartRef = ref<HTMLDivElement>()
let chart: echarts.EChartsType | null = null

/** 叶子知识点数（摘要用）。 */
const leafCount = computed(() => (roadmap.value ? countLeaves(roadmap.value) : 0))

/** 拆解时间的友好展示（本地时区）。 */
const updatedAtText = computed(() => {
  const iso = roadmapUpdatedAt.value
  if (!iso) return ''
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return ''
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`
})

/** 构造 ECharts option（design 2.5.5；折叠策略见 toEChartsTree 注释）。 */
function buildOption(tree: RoadmapNode): EChartsOption {
  return {
    animationDuration: 320,
    textStyle: { fontFamily: CHART_FONT },
    tooltip: { trigger: 'item', ...CHART_TOOLTIP },
    series: [
      {
        type: 'tree',
        data: [toEChartsTree(tree)],
        orient: 'LR',
        roam: true,
        expandAndCollapse: true,
        // 与 data 内 collapsed（depth > 1）策略对齐的兜底；collapsed 优先生效
        initialTreeDepth: 1,
        symbolSize: 7,
        itemStyle: {
          color: CHART_COLORS.ink,
          borderColor: CHART_COLORS.paper,
          borderWidth: 1,
        },
        label: {
          position: 'left',
          fontSize: 12,
          color: CHART_COLORS.ink,
          fontFamily: CHART_FONT,
        },
        leaves: {
          label: {
            position: 'right',
            color: CHART_COLORS.jade,
            fontSize: 12,
            fontFamily: CHART_FONT,
          },
          itemStyle: { color: CHART_COLORS.jade },
        },
        lineStyle: { color: CHART_COLORS.lineStrong, width: 1 },
        emphasis: { focus: 'descendant' },
      },
    ],
  }
}

/** 初始化 / 刷新图表（容器存在且有树时）。 */
function renderChart(): void {
  const tree = roadmap.value
  if (!tree || !chartRef.value) return
  if (!chart) {
    chart = echarts.init(chartRef.value)
  }
  chart.setOption(buildOption(tree), true)
}

/** 拉取最新知识树（view 动作 / 二次确认取消后的兜底展示）。 */
async function loadRoadmap(): Promise<void> {
  const g = props.goal
  if (!g) return
  viewLoading.value = true
  try {
    const data = await fetchGoalRoadmap(g.id)
    roadmap.value = data.roadmap
    roadmapUpdatedAt.value = data.roadmap_updated_at
  } catch {
    // 错误提示已由拦截器统一展示；保留本地快照
  } finally {
    viewLoading.value = false
  }
}

/** 触发拆解动作（已有树时先二次确认，取消停留当前视图不发请求）。 */
async function startBreakdownAction(): Promise<void> {
  const g = props.goal
  if (!g || breaking.value) return
  if (roadmap.value) {
    try {
      await ElMessageBox.confirm('该目标已有知识树，重新拆解将覆盖，确定吗？', '重新拆解', {
        type: 'warning',
        confirmButtonText: '重新拆解',
        cancelButtonText: '取消',
      })
    } catch {
      // 取消：停留当前视图（展示已有树），不发请求
      return
    }
  }
  await runBreakdown()
}

/** 执行拆解请求（90s 超时已在 api 层覆盖）。 */
async function runBreakdown(): Promise<void> {
  const g = props.goal
  if (!g) return
  breaking.value = true
  failedMessage.value = ''
  try {
    const data = await breakdownGoal(g.id)
    roadmap.value = data.roadmap
    roadmapUpdatedAt.value = data.roadmap_updated_at
    emit('breakdown-success', data)
  } catch (error) {
    failedMessage.value = breakdownErrorMessage(error)
    emit('breakdown-failed')
  } finally {
    breaking.value = false
  }
}

/** 打开抽屉：复位状态 + 本地快照 + 按 initialAction 分派。 */
function initOnOpen(): void {
  const g = props.goal
  roadmap.value = g?.roadmap ?? null
  roadmapUpdatedAt.value = g?.roadmap_updated_at ?? null
  failedMessage.value = ''
  if (props.initialAction === 'breakdown') {
    void startBreakdownAction()
  } else {
    void loadRoadmap()
  }
}

watch(
  () => props.visible,
  (v) => {
    if (v) {
      initOnOpen()
      // 抽屉首次打开后 DOM 才挂载，本地快照有树时先渲染一次
      nextTick(renderChart)
    }
  },
)

// 树数据变化（拉取返回 / 拆解成功）后重渲染。
watch(roadmap, () => {
  nextTick(renderChart)
})

/** 抽屉打开动画结束后修正尺寸（动画期间初始化会取到 0 / 过渡宽度）。 */
function onDrawerOpened(): void {
  chart?.resize()
}

function onWindowResize(): void {
  chart?.resize()
}

onMounted(() => {
  window.addEventListener('resize', onWindowResize)
})

onUnmounted(() => {
  window.removeEventListener('resize', onWindowResize)
  chart?.dispose()
  chart = null
})
</script>

<template>
  <el-drawer
    :model-value="visible"
    size="min(1080px, 94vw)"
    @update:model-value="(v: boolean) => emit('update:visible', v)"
    @opened="onDrawerOpened"
  >
    <template #header>
      <div class="drawer-header">
        <div class="drawer-title">
          <span class="title-text">{{ goal?.title ?? '知识树' }}</span>
          <span v-if="updatedAtText" class="updated-at">拆解于 {{ updatedAtText }}</span>
        </div>
        <el-button
          type="primary"
          size="small"
          :loading="breaking"
          :disabled="breaking"
          @click="startBreakdownAction"
        >
          {{ roadmap ? '重新拆解' : 'AI 拆解' }}
        </el-button>
      </div>
    </template>

    <div
      class="drawer-body"
      v-loading="viewLoading || breaking"
      :element-loading-text="breaking ? 'AI 正在拆解知识树，请稍候…' : ''"
    >
      <!-- 失败态：持续提示（拦截器已有短暂 toast，此处不重复 ElMessage） -->
      <div v-if="failedMessage" class="failed-zone">
        <el-alert type="error" :title="failedMessage" :closable="false" show-icon />
        <el-button type="primary" class="retry-btn" @click="startBreakdownAction">重新拆解</el-button>
      </div>

      <!-- 空态：从未拆解 -->
      <div v-else-if="!roadmap" class="empty-zone">
        <el-empty description="尚未拆解">
          <div class="empty-hint">
            把目标拆解为「领域 → 技能 → 知识点」知识树，
            <br />
            叶子知识点将进入掌握度体系
          </div>
          <el-button type="primary" size="large" class="empty-btn" @click="startBreakdownAction">
            AI 拆解
          </el-button>
        </el-empty>
      </div>

      <!-- 成功态：ECharts 树图 + 摘要 -->
      <template v-else>
        <div ref="chartRef" class="chart-container" />
        <div class="chart-summary">共 {{ leafCount }} 个知识点（绿色叶子已进入掌握度体系）</div>
      </template>
    </div>
  </el-drawer>
</template>

<style scoped>
.drawer-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding-right: 32px;
}
.drawer-title {
  display: flex;
  align-items: baseline;
  gap: 10px;
  min-width: 0;
}
.title-text {
  font-family: var(--font-display);
  font-size: 19px;
  font-weight: 600;
  color: var(--ink);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.updated-at {
  font-family: var(--font-mono);
  font-size: 9px;
  color: var(--ink-4);
  white-space: nowrap;
}
.drawer-body {
  height: 100%;
  display: flex;
  flex-direction: column;
}
.failed-zone {
  padding: 24px 16px;
}
.retry-btn {
  margin-top: 16px;
}
.empty-zone {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
}
.empty-hint {
  font-size: 12px;
  line-height: 1.9;
  color: var(--ink-3);
  margin-bottom: 16px;
}
.empty-btn {
  margin-top: 4px;
}
.chart-container {
  flex: 1;
  min-height: 0;
}
.chart-summary {
  flex: 0 0 auto;
  padding: 10px 4px 2px;
  font-family: var(--font-mono);
  font-size: 10px;
  color: var(--ink-3);
  text-align: center;
  border-top: 1px solid var(--line);
}
</style>