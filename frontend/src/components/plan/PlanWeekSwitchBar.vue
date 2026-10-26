<script setup lang="ts">
/**
 * 周切换条（P22；零请求纯展示）。
 *
 * 让「已生成但还没开始」的下周计划在页面上始终可见、可一键切换；
 * 本周无计划时也提供本周兜底生成入口。是否渲染由父组件决定
 * （viewing === 'upcoming' || upcomingPlan != null）。
 */
import { computed } from 'vue'

import type { Plan, PlanGenerateTarget } from '@/types/plan'

const props = defineProps<{
  viewing: 'current' | 'upcoming'
  currentPlan: Plan | null
  upcomingPlan: Plan | null
  canGenerateCurrent: boolean
  currentRemaining: { start: string; end: string }
  nextWindow: { start: string; end: string }
  busy: boolean
}>()

const emit = defineEmits<{
  (e: 'switch-week', target: 'current' | 'upcoming'): void
  (e: 'generate', target: PlanGenerateTarget): void
}>()

/** 未来计划是否恰好是下一周（用于「下周 / 未来」文案分流）。 */
const isNextUpcoming = computed(
  () => props.upcomingPlan?.start_date === props.nextWindow.start,
)

const upcomingLabel = computed(() => {
  const plan = props.upcomingPlan
  if (!plan) return ''
  return `${isNextUpcoming.value ? '下周' : '未来'}计划已生成（${plan.start_date} ~ ${plan.end_date}）`
})
</script>

<template>
  <div class="week-switch-bar">
    <template v-if="viewing === 'current' && upcomingPlan">
      <span class="switch-text">{{ upcomingLabel }}</span>
      <el-button link type="primary" :disabled="busy" @click="emit('switch-week', 'upcoming')">
        {{ isNextUpcoming ? '查看下周计划' : '查看未来计划' }}
      </el-button>
    </template>

    <template v-else-if="viewing === 'upcoming' && currentPlan">
      <span class="switch-text">
        正在查看{{ isNextUpcoming ? '下周' : '未来' }}计划（未开始）
      </span>
      <el-button link type="primary" :disabled="busy" @click="emit('switch-week', 'current')">
        返回本周计划
      </el-button>
    </template>

    <template v-else-if="viewing === 'upcoming' && !currentPlan && canGenerateCurrent">
      <span class="switch-text">本周暂无计划</span>
      <el-button
        link
        type="primary"
        :disabled="busy"
        @click="emit('generate', 'current_week')"
      >
        生成本周计划（{{ currentRemaining.start }} ~ {{ currentRemaining.end }}）
      </el-button>
    </template>

    <template v-else-if="viewing === 'upcoming' && !currentPlan && !canGenerateCurrent">
      <span class="switch-text">本周已结束</span>
    </template>
  </div>
</template>

<style scoped>
.week-switch-bar {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
  padding: 10px 0;
  border-top: 1px solid var(--line);
  border-bottom: 1px solid var(--line);
  background: transparent;
  font-size: 12px;
  color: var(--ink-3);
}
.switch-text {
  line-height: 1.5;
}
.switch-text::before {
  content: '';
  display: inline-block;
  width: 5px;
  height: 5px;
  margin-right: 8px;
  vertical-align: 1px;
  background: var(--ochre);
}
</style>
