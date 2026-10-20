<script setup lang="ts">
import { computed } from 'vue'
import type { EChartsCoreOption } from 'echarts/core'

import EChartContainer from '@/components/dashboard/EChartContainer.vue'
import type { MasteryData } from '@/types'

const props = defineProps<{
  data: MasteryData | null
  loading: boolean
  error: boolean
  reload: () => void
}>()

const MASTERY_COLORS = {
  danger: '#F56C6C',
  warning: '#E6A23C',
  success: '#67C238',
} as const

function masteryColor(score: number): string {
  if (score < 50) return MASTERY_COLORS.danger
  if (score <= 70) return MASTERY_COLORS.warning
  return MASTERY_COLORS.success
}

const chartOption = computed<EChartsCoreOption>(() => {
  const items = props.data?.items ?? []
  return {
    tooltip: { trigger: 'axis' },
    grid: { left: 88, right: 32, top: 16, bottom: 24 },
    xAxis: { type: 'value', max: 100 },
    yAxis: {
      type: 'category',
      inverse: true,
      data: items.map((item) => item.knowledge_point),
    },
    series: [
      {
        name: '掌握度',
        type: 'bar',
        barMaxWidth: 18,
        itemStyle: {
          color: (params: { dataIndex: number }) =>
            masteryColor(items[params.dataIndex]?.mastery_score ?? 0),
        },
        data: items.map((item) => item.mastery_score),
      },
    ],
  }
})
</script>

<template>
  <el-skeleton v-if="loading" class="chart-skeleton" :rows="5" animated />

  <div v-else-if="error" class="block-error" @click="reload">数据加载失败，点击重试</div>

  <el-empty v-else-if="data != null && data.items.length === 0" description="暂无知识点掌握度数据" />

  <div v-else class="chart-wrap">
    <EChartContainer :option="chartOption" />
  </div>
</template>

<style scoped>
.chart-skeleton {
  height: 300px;
  padding-top: 16px;
}
.chart-wrap {
  height: 300px;
}
.block-error {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 300px;
  color: var(--el-color-danger);
  font-size: 14px;
  cursor: pointer;
}
.block-error:hover {
  text-decoration: underline;
}
</style>