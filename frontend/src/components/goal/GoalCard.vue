<script setup lang="ts">
/**
 * 目标卡片：以大号剩余天数作为视觉锚点，底部一条时间进度细线。
 * 不再使用圆形进度环和 el-card 外壳。
 */
import { computed } from 'vue'

import type { Goal, GoalStatus } from '@/types'
import { calcGoalProgress } from '@/utils/goal'

const props = defineProps<{ goal: Goal }>()

const emit = defineEmits<{
  (e: 'edit', goal: Goal): void
  (e: 'breakdown', goal: Goal): void
  (e: 'view-roadmap', goal: Goal): void
  (e: 'delete', goal: Goal): void
}>()

const STATUS_META: Record<
  GoalStatus,
  { label: string; type: 'success' | 'info' | 'warning'; dot: string }
> = {
  active: { label: '进行中', type: 'success', dot: 'is-active' },
  completed: { label: '已完成', type: 'info', dot: 'is-completed' },
  archived: { label: '已归档', type: 'warning', dot: 'is-archived' },
}

const progress = computed(() => calcGoalProgress(props.goal.start_date, props.goal.end_date))
const statusMeta = computed(() => STATUS_META[props.goal.status] ?? STATUS_META.active)

const dateRangeText = computed(() => {
  const s = props.goal.start_date
  const e = props.goal.end_date
  if (s && e) return `${s} — ${e}`
  if (s) return `${s} 起`
  if (e) return `截止 ${e}`
  return ''
})
</script>

<template>
  <article class="goal-card" :class="{ 'is-expired': progress.expired }">
    <div class="goal-card__head">
      <div class="goal-title-row">
        <span class="goal-status-dot" :class="statusMeta.dot" aria-hidden="true" />
        <h3 class="goal-title" :title="goal.title">{{ goal.title }}</h3>
      </div>
      <el-tag v-if="goal.goal_type" size="small" effect="plain">{{ goal.goal_type }}</el-tag>
    </div>

    <div class="goal-card__body">
      <div class="goal-days">
        <template v-if="!goal.end_date">
          <span class="goal-days__value is-muted">--</span>
          <span class="goal-days__unit">未设截止</span>
        </template>
        <template v-else-if="progress.expired">
          <span class="goal-days__value is-expired">已过期</span>
        </template>
        <template v-else>
          <span class="goal-days__value">{{ progress.remainingDays }}</span>
          <span class="goal-days__unit">天后截止</span>
        </template>
      </div>

      <div
        v-if="progress.showRing"
        class="goal-meter"
        role="img"
        :aria-label="`时间进度 ${progress.percent}%`"
      >
        <div class="goal-meter__fill" :style="{ width: `${progress.percent}%` }" />
      </div>

      <div class="goal-meta">
        <el-tag size="small" :type="statusMeta.type" effect="plain">
          {{ statusMeta.label }}
        </el-tag>
        <span v-if="dateRangeText" class="goal-dates">{{ dateRangeText }}</span>
        <span v-if="progress.showRing" class="goal-percent">时间已过 {{ progress.percent }}%</span>
      </div>
    </div>

    <div class="goal-actions">
      <el-button link size="small" @click="emit('edit', goal)">编辑</el-button>
      <el-button link size="small" type="primary" @click="emit('breakdown', goal)">
        {{ goal.roadmap ? '重新拆解' : 'AI 拆解' }}
      </el-button>
      <el-button link size="small" @click="emit('view-roadmap', goal)">知识树</el-button>
      <span class="goal-actions__spacer" />
      <el-button link size="small" type="danger" @click="emit('delete', goal)">删除</el-button>
    </div>
  </article>
</template>

<style scoped>
.goal-card {
  display: flex;
  flex-direction: column;
  height: 100%;
  padding: 18px 20px 12px;
  background: var(--paper-2);
  border: 1px solid var(--line);
  border-radius: var(--radius);
  transition: border-color 0.16s var(--ease), box-shadow 0.16s var(--ease),
    transform 0.16s var(--ease);
}

.goal-card:hover {
  border-color: var(--line-strong);
  box-shadow: var(--shadow-lift);
  transform: translateY(-1px);
}

.goal-card__head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  min-height: 50px;
}

.goal-title-row {
  display: flex;
  align-items: flex-start;
  gap: 9px;
  min-width: 0;
}

.goal-status-dot {
  width: 6px;
  height: 6px;
  flex: 0 0 6px;
  margin-top: 9px;
  border-radius: 1px;
  background: var(--jade);
}

.goal-status-dot.is-completed {
  background: var(--dust);
}

.goal-status-dot.is-archived {
  background: var(--ochre);
}

.goal-title {
  font-family: var(--font-display);
  font-size: 17px;
  font-weight: 600;
  line-height: 1.45;
  color: var(--ink);
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.goal-card__body {
  flex: 1 1 auto;
  margin-top: 18px;
}

.goal-days {
  display: flex;
  align-items: baseline;
  gap: 8px;
  min-height: 38px;
}

.goal-days__value {
  font-family: var(--font-display);
  font-variant-numeric: lining-nums tabular-nums;
  font-size: 36px;
  font-weight: 600;
  line-height: 1;
  color: var(--ink);
}

.goal-days__value.is-muted {
  font-size: 26px;
  color: var(--ink-4);
}

.goal-days__value.is-expired {
  font-size: 20px;
  letter-spacing: 0.04em;
  color: var(--vermilion);
}

.goal-days__unit {
  font-size: 12px;
  color: var(--ink-3);
}

.goal-meter {
  height: 3px;
  margin-top: 14px;
  background: var(--paper-4);
  overflow: hidden;
}

.goal-meter__fill {
  height: 100%;
  background: var(--ink);
  transition: width 0.3s var(--ease);
}

.is-expired .goal-meter__fill {
  background: var(--vermilion);
}

.goal-meta {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
  margin-top: 12px;
}

.goal-dates {
  font-family: var(--font-mono);
  font-size: 10px;
  color: var(--ink-4);
}

.goal-percent {
  margin-left: auto;
  font-family: var(--font-mono);
  font-size: 10px;
  color: var(--ink-4);
  white-space: nowrap;
}

.goal-actions {
  display: flex;
  align-items: center;
  gap: 2px;
  margin-top: 16px;
  padding-top: 10px;
  border-top: 1px solid var(--line-soft);
}

.goal-actions__spacer {
  flex: 1 1 auto;
}

@media (prefers-reduced-motion: reduce) {
  .goal-card:hover {
    transform: none;
  }
}
</style>
