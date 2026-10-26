<script setup lang="ts">
/**
 * 学习记录统计：账本式指标带（本周时长 / 连续天数 / 记录条数）。
 */
import { computed } from 'vue'

import type { RecordStats } from '@/types'

const props = defineProps<{
  stats: RecordStats | null
}>()

const display = computed(() => {
  const s = props.stats
  if (s == null) return null
  const total = s.weekly_minutes
  const hours = Math.floor(total / 60)
  const rest = total % 60
  return {
    weeklyValue: total >= 60 ? String(hours) : String(total),
    weeklyUnit: total >= 60 ? '小时' : '分钟',
    weeklySub:
      total >= 60 && rest > 0
        ? `另 ${rest} 分钟`
        : `本周共 ${total} 分钟`,
    streakValue: String(s.streak_days),
    totalValue: String(s.total_count),
  }
})
</script>

<template>
  <div class="ledger record-ledger">
    <div class="ledger__item">
      <div class="ledger__value">
        {{ display?.weeklyValue ?? '--' }}<span v-if="display" class="unit">{{ display.weeklyUnit }}</span>
      </div>
      <div class="ledger__label">本周学习时长</div>
      <div class="ledger__sub">{{ display?.weeklySub ?? '正在读取' }}</div>
    </div>
    <div class="ledger__item">
      <div class="ledger__value">
        {{ display?.streakValue ?? '--' }}<span v-if="display" class="unit">天</span>
      </div>
      <div class="ledger__label">连续学习天数</div>
      <div class="ledger__sub">按北京时间的自然日计算</div>
    </div>
    <div class="ledger__item">
      <div class="ledger__value">
        {{ display?.totalValue ?? '--' }}<span v-if="display" class="unit">条</span>
      </div>
      <div class="ledger__label">累计记录</div>
      <div class="ledger__sub">每条记录都会进入分析与建议</div>
    </div>
  </div>
</template>

<style scoped>
.record-ledger .ledger__item {
  flex-basis: 33.333%;
}

@media (max-width: 720px) {
  .record-ledger .ledger__item {
    flex-basis: 100%;
    border-left: none;
    padding-left: 0;
  }

  .record-ledger .ledger__item + .ledger__item {
    border-top: 1px solid var(--line);
  }
}
</style>
