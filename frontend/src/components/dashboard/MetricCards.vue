<script setup lang="ts">
/**
 * 学习总览：一条账本式指标带。
 * 四个数用衬线大字横向排开，细线分隔，不再用四张相同的圆角卡片。
 */
import { computed } from 'vue'

import type { OverviewData } from '@/types'

const props = defineProps<{
  data: OverviewData | null
  loading: boolean
  error: boolean
  reload: () => void
}>()

const display = computed(() => {
  const d = props.data
  if (d == null) return null
  const total = d.total_minutes
  const hours = Math.floor(total / 60)
  const rest = total % 60
  return {
    minutesValue: total >= 60 ? String(hours) : String(total),
    minutesUnit: total >= 60 ? '小时' : '分钟',
    minutesSub:
      total >= 60 && rest > 0
        ? `另 ${rest} 分钟 · 共 ${d.total_record_count} 条记录`
        : `共 ${d.total_record_count} 条记录`,
    completionValue: String(d.task_completion_rate),
    completionSub: `${d.overdue_task_count} 个任务逾期`,
    overdue: d.overdue_task_count > 0,
    masteryValue: String(d.avg_mastery),
    masterySub: '满分 100',
    streakValue: String(d.streak_days),
    streakSub: `平均单次 ${d.avg_session_minutes} 分钟`,
  }
})
</script>

<template>
  <div v-if="error" class="block-error" @click="reload">数据加载失败，点击重试</div>

  <div v-else class="ledger" :aria-busy="loading">
    <div class="ledger__item">
      <div class="ledger__value">
        {{ display?.minutesValue ?? '--' }}<span v-if="display" class="unit">{{ display.minutesUnit }}</span>
      </div>
      <div class="ledger__label">总学习时长</div>
      <div class="ledger__sub">{{ display?.minutesSub ?? '正在读取' }}</div>
    </div>

    <div class="ledger__item" :class="{ 'is-alert': display?.overdue }">
      <div class="ledger__value">
        {{ display?.completionValue ?? '--' }}<span v-if="display" class="unit">%</span>
      </div>
      <div class="ledger__label">任务完成率</div>
      <div class="ledger__sub">{{ display?.completionSub ?? '正在读取' }}</div>
    </div>

    <div class="ledger__item">
      <div class="ledger__value">
        {{ display?.masteryValue ?? '--' }}<span v-if="display" class="unit">分</span>
      </div>
      <div class="ledger__label">平均掌握度</div>
      <div class="ledger__sub">{{ display?.masterySub ?? '正在读取' }}</div>
    </div>

    <div class="ledger__item">
      <div class="ledger__value">
        {{ display?.streakValue ?? '--' }}<span v-if="display" class="unit">天</span>
      </div>
      <div class="ledger__label">连续学习</div>
      <div class="ledger__sub">{{ display?.streakSub ?? '正在读取' }}</div>
    </div>
  </div>
</template>
