<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
import * as echarts from 'echarts/core'
import type { EChartsCoreOption } from 'echarts/core'
import { BarChart, LineChart } from 'echarts/charts'
import {
  GridComponent,
  LegendComponent,
  TooltipComponent,
} from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'

echarts.use([
  LineChart,
  BarChart,
  GridComponent,
  TooltipComponent,
  LegendComponent,
  CanvasRenderer,
])

const props = defineProps<{
  option: EChartsCoreOption
}>()

const chartEl = ref<HTMLDivElement>()
let chart: echarts.EChartsType | null = null

function handleResize(): void {
  chart?.resize()
}

onMounted(() => {
  if (chartEl.value == null) return
  chart = echarts.init(chartEl.value)
  chart.setOption(props.option)
  window.addEventListener('resize', handleResize)
})

watch(
  () => props.option,
  (option) => {
    chart?.setOption(option, { notMerge: true })
  },
)

onBeforeUnmount(() => {
  window.removeEventListener('resize', handleResize)
  chart?.dispose()
  chart = null
})
</script>

<template>
  <div ref="chartEl" class="echart-container"></div>
</template>

<style scoped>
.echart-container {
  width: 100%;
  height: 100%;
}
</style>