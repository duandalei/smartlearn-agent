<script setup lang="ts">
import { computed } from 'vue'
import type { EChartsCoreOption } from 'echarts/core'

import EChartContainer from '@/components/dashboard/EChartContainer.vue'
import type { TrendData } from '@/types'
import {
  CHART_COLORS,
  CHART_FONT,
  CHART_MONO,
  CHART_TOOLTIP,
} from '@/utils/chartTheme'

const props = defineProps<{
  data: TrendData | null
  loading: boolean
  error: boolean
  reload: () => void
  days: number
  onDaysChange: (days: number) => void
}>()

const chartOption = computed<EChartsCoreOption>(() => {
  const items = props.data?.items ?? []
  return {
    animationDuration: 320,
    textStyle: { fontFamily: CHART_FONT },
    tooltip: {
      trigger: 'axis',
      ...CHART_TOOLTIP,
      valueFormatter: (value: unknown) => `${String(value)} 分钟`,
      axisPointer: {
        type: 'line',
        lineStyle: {
          color: CHART_COLORS.vermilion,
          width: 1,
          type: 'dashed',
        },
      },
    },
    grid: { left: 46, right: 18, top: 24, bottom: 30 },
    xAxis: {
      type: 'category',
      boundaryGap: false,
      data: items.map((item) => item.date),
      axisLine: { lineStyle: { color: CHART_COLORS.line } },
      axisTick: { show: false },
      axisLabel: {
        color: CHART_COLORS.inkSoft,
        fontSize: 10,
        fontFamily: CHART_MONO,
        margin: 12,
        formatter: (value: string) => value.slice(5),
      },
    },
    yAxis: {
      type: 'value',
      splitNumber: 4,
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
    series: [
      {
        name: '学习时长',
        type: 'line',
        smooth: 0.3,
        showSymbol: items.length <= 14,
        symbol: 'circle',
        symbolSize: 6,
        data: items.map((item) => item.minutes),
        lineStyle: { width: 2, color: CHART_COLORS.ink },
        itemStyle: {
          color: CHART_COLORS.vermilion,
          borderColor: CHART_COLORS.paper,
          borderWidth: 2,
        },
        areaStyle: { color: 'rgba(28, 42, 36, 0.045)' },
        emphasis: { focus: 'series', scale: 1.4 },
      },
    ],
  }
})

function handleDaysChange(value: string | number | boolean | undefined): void {
  props.onDaysChange(Number(value))
}
</script>

<template>
  <section class="panel trend-card">
    <div class="panel__head">
      <div>
        <div class="panel__title">学习时间趋势</div>
        <div class="panel__sub">每天实际投入的分钟数</div>
      </div>
      <el-radio-group
        :model-value="days"
        size="small"
        aria-label="选择趋势时间范围"
        @update:model-value="handleDaysChange"
      >
        <el-radio-button :value="7">7 天</el-radio-button>
        <el-radio-button :value="30">30 天</el-radio-button>
        <el-radio-button :value="90">90 天</el-radio-button>
      </el-radio-group>
    </div>

    <div class="panel__body">
      <el-skeleton v-if="loading" class="chart-skeleton" :rows="4" animated />

      <div v-else-if="error" class="block-error chart-error" @click="reload">
        数据加载失败，点击重试
      </div>

      <div v-else-if="(data?.items.length ?? 0) === 0" class="empty-note">
        <div class="empty-note__title">还没有可以画出的趋势</div>
        <div>记录第一次学习后，这里会留下一条墨线。</div>
      </div>

      <div v-else class="chart-wrap">
        <EChartContainer :option="chartOption" />
      </div>
    </div>
  </section>
</template>

<style scoped>
.trend-card {
  height: 100%;
}

.chart-skeleton {
  height: 300px;
  padding-top: 8px;
}

.chart-wrap {
  height: 300px;
}

.chart-error {
  height: 300px;
}
</style>
