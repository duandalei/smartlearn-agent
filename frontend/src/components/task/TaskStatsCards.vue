<script setup lang="ts">
/**
 * 任务统计：账本式指标带。
 * 数值全部来自后端 stats 接口，本地零计算。
 */
import { computed } from 'vue'

import type { TaskStats } from '@/types'

const props = defineProps<{
  stats: TaskStats | null
}>()

const display = computed(() => {
  const s = props.stats
  return {
    total: s == null ? '--' : String(s.total),
    todo: s == null ? '--' : String(s.status_counts.todo),
    inProgress: s == null ? '--' : String(s.status_counts.in_progress),
    done: s == null ? '--' : String(s.status_counts.done),
    review: s == null ? '--' : String(s.status_counts.review),
    overdue: s == null ? '--' : String(s.overdue_count),
    overdueAlert: s != null && s.overdue_count > 0,
    weeklyRate: s == null ? '--' : s.weekly_completion_rate.toFixed(1),
    todayTodo: s == null ? '--' : String(s.today_todo_count),
  }
})
</script>

<template>
  <div class="ledger task-ledger">
    <div class="ledger__item">
      <div class="ledger__value">{{ display.total }}</div>
      <div class="ledger__label">总任务</div>
    </div>
    <div class="ledger__item">
      <div class="ledger__value">{{ display.todo }}</div>
      <div class="ledger__label">待办</div>
    </div>
    <div class="ledger__item">
      <div class="ledger__value">{{ display.inProgress }}</div>
      <div class="ledger__label">进行中</div>
    </div>
    <div class="ledger__item">
      <div class="ledger__value">{{ display.done }}</div>
      <div class="ledger__label">已完成</div>
    </div>
    <div class="ledger__item">
      <div class="ledger__value">{{ display.review }}</div>
      <div class="ledger__label">待复盘</div>
    </div>
    <div class="ledger__item" :class="{ 'is-alert': display.overdueAlert }">
      <div class="ledger__value">{{ display.overdue }}</div>
      <div class="ledger__label">逾期</div>
    </div>
    <div class="ledger__item">
      <div class="ledger__value">
        {{ display.weeklyRate }}<span v-if="props.stats" class="unit">%</span>
      </div>
      <div class="ledger__label">本周完成率</div>
    </div>
    <div class="ledger__item">
      <div class="ledger__value">{{ display.todayTodo }}</div>
      <div class="ledger__label">今日待办</div>
    </div>
  </div>
</template>

<style scoped>
.task-ledger .ledger__item {
  flex: 1 1 116px;
  padding: 16px 18px 14px;
}

.task-ledger .ledger__value {
  font-size: 32px;
}

@media (max-width: 1200px) {
  .task-ledger .ledger__item {
    flex-basis: calc(25% - 1px);
  }

  .task-ledger .ledger__item:nth-child(3) {
    border-left: 1px solid var(--line);
    padding-left: 18px;
  }

  .task-ledger .ledger__item:nth-child(4n + 1) {
    border-left: none;
    padding-left: 0;
  }
}

@media (max-width: 720px) {
  .task-ledger .ledger__item {
    flex-basis: 50%;
    padding: 14px 12px 12px;
  }

  .task-ledger .ledger__item:nth-child(3) {
    border-left: 1px solid var(--line);
    padding-left: 12px;
  }

  .task-ledger .ledger__item:nth-child(odd) {
    border-left: none;
    padding-left: 0;
  }

  .task-ledger .ledger__item:nth-child(even) {
    padding-left: 12px;
  }

  .task-ledger .ledger__value {
    font-size: 27px;
  }
}
</style>
