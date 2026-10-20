<script setup lang="ts">
import { computed } from 'vue'
import type { EChartsCoreOption } from 'echarts/core'

import EChartContainer from '@/components/dashboard/EChartContainer.vue'
import type { TrendData } from '@/types'

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
    tooltip: { trigger: 'axis' },
    grid: { left: 56, right: 20, top: 40, bottom: 32 },
    xAxis: {
      type: 'category',
      boundaryGap: false,
      data: items.map((item) => item.date),
    },
    yAxis: {
      type: 'value',
      name: '分钟',
      nameLocation: 'end',
      nameGap: 12,
      nameTextStyle: { color: '#909399', fontSize: 12 },
    },
    series: [
      {
        name: '学习时长',
        type: 'line',
        smooth: true,
        showSymbol: items.length <= 7,
        data: items.map((item) => item.minutes),
      },
    ],
  }
})

function handleDaysChange(value: string | number | boolean | undefined): void {
  props.onDaysChange(Number(value))
}
</script>

<template>
  <el-card shadow="never" class="trend-card">
    <template #header>
      <div class="card-header">
        <span class="card-title">学习时间趋势</span>
        <el-radio-group :model-value="days" size="small" @update:model-value="handleDaysChange">
          <el-radio-button :value="7">近 7 天</el-radio-button>
          <el-radio-button :value="30">近 30 天</el-radio-button>
          <el-radio-button :value="90">近 90 天</el-radio-button>
        </el-radio-group>
      </div>
    </template>

    <el-skeleton v-if="loading" class="chart-skeleton" :rows="4" animated />

    <div v-else-if="error" class="block-error" @click="reload">数据加载失败，点击重试</div>

    <div v-else class="chart-wrap">
      <EChartContainer :option="chartOption" />
    </div>
  </el-card>
</template>

<style scoped>
.trend-card {
  height: 100%;
}
.card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.card-title {
  font-size: 15px;
  font-weight: 600;
}
.chart-skeleton {
  height: 320px;
  padding-top: 24px;
}
.chart-wrap {
  height: 320px;
}
.block-error {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 320px;
  color: var(--el-color-danger);
  font-size: 14px;
  cursor: pointer;
}
.block-error:hover {
  text-decoration: underline;
}
</style>