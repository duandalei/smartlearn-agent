<script setup lang="ts">
import { computed } from 'vue'
import type { EChartsCoreOption } from 'echarts/core'

import EChartContainer from '@/components/dashboard/EChartContainer.vue'
import type { MasteryData } from '@/types'
import {
  CHART_COLORS,
  CHART_FONT,
  CHART_MONO,
  CHART_TOOLTIP,
} from '@/utils/chartTheme'

const props = defineProps<{
  data: MasteryData | null
  loading: boolean
  error: boolean
  reload: () => void
}>()

function masteryColor(score: number): string {
  if (score < 40) return CHART_COLORS.vermilion
  if (score < 70) return CHART_COLORS.ochre
  return CHART_COLORS.jade
}

/** 知识点多时按行高撑开画布，避免横条挤在一起。 */
const chartHeight = computed(() =>
  Math.max(280, (props.data?.items.length ?? 0) * 26 + 40),
)

const chartOption = computed<EChartsCoreOption>(() => {
  const items = props.data?.items ?? []
  return {
    animationDuration: 320,
    textStyle: { fontFamily: CHART_FONT },
    tooltip: {
      trigger: 'axis',
      ...CHART_TOOLTIP,
      valueFormatter: (value: unknown) => `${String(value)} 分`,
      axisPointer: { type: 'shadow', shadowStyle: { color: 'rgba(28,42,36,0.04)' } },
    },
    grid: { left: 104, right: 34, top: 8, bottom: 22 },
    xAxis: {
      type: 'value',
      max: 100,
      axisLine: { show: false },
      axisTick: { show: false },
      axisLabel: {
        color: CHART_COLORS.inkSoft,
        fontSize: 10,
        fontFamily: CHART_MONO,
      },
      splitLine: {
        lineStyle: { color: CHART_COLORS.grid, type: 'dashed' },
      },
    },
    yAxis: {
      type: 'category',
      inverse: true,
      data: items.map((item) => item.knowledge_point),
      axisLine: { show: false },
      axisTick: { show: false },
      axisLabel: {
        color: CHART_COLORS.ink,
        fontSize: 12,
        width: 96,
        overflow: 'truncate',
        margin: 14,
      },
    },
    series: [
      {
        name: '掌握度',
        type: 'bar',
        barMaxWidth: 10,
        barCategoryGap: '42%',
        showBackground: true,
        backgroundStyle: { color: '#f2efe8' },
        itemStyle: {
          color: (params: { dataIndex: number }) =>
            masteryColor(items[params.dataIndex]?.mastery_score ?? 0),
        },
        label: {
          show: true,
          position: 'right',
          color: CHART_COLORS.inkSoft,
          fontSize: 10,
          fontFamily: CHART_MONO,
          formatter: '{c}',
        },
        markLine: {
          silent: true,
          symbol: 'none',
          label: {
            formatter: '60',
            color: CHART_COLORS.inkFaint,
            fontSize: 9,
            fontFamily: CHART_MONO,
            position: 'end',
          },
          lineStyle: {
            color: CHART_COLORS.line,
            width: 1,
            type: 'dashed',
          },
          data: [{ xAxis: 60 }],
        },
        data: items.map((item) => item.mastery_score),
      },
    ],
  }
})
</script>

<template>
  <el-skeleton
    v-if="loading"
    class="chart-skeleton"
    :style="{ height: `${chartHeight}px` }"
    :rows="5"
    animated
  />

  <div
    v-else-if="error"
    class="block-error chart-error"
    :style="{ height: `${chartHeight}px` }"
    @click="reload"
  >
    数据加载失败，点击重试
  </div>

  <div v-else-if="data != null && data.items.length === 0" class="empty-note">
    <div class="empty-note__title">还没有知识点掌握度</div>
    <div>在学习记录里自评掌握程度，这里会按知识点排出高低。</div>
  </div>

  <div v-else class="chart-wrap" :style="{ height: `${chartHeight}px` }">
    <EChartContainer :option="chartOption" />
  </div>
</template>

<style scoped>
.chart-skeleton {
  padding-top: 8px;
}

.chart-wrap,
.chart-error {
  width: 100%;
}
</style>
