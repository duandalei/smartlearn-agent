<script setup lang="ts">
/**
 * 调整记录回看面板（只读，不含任何回退操作）。
 */
import { computed } from 'vue'

import type { Plan, PlanDiff } from '@/types/plan'
import { formatHm } from '@/utils/plan'

const props = defineProps<{
  plan: Plan
  diff: PlanDiff | null
  loading: boolean
}>()

const emit = defineEmits<{
  (e: 'back'): void
}>()

const isDiffEmpty = computed(() => {
  const d = props.diff
  if (!d) return false
  return d.moved.length === 0 && d.added.length === 0 && d.removed.length === 0
})

function hmOrRest(t: string | null): string {
  return t == null ? '休息时段' : formatHm(t)
}
</script>

<template>
  <div class="history-panel">
    <div class="head-row">
      <div>
        <div class="panel-kicker">调整记录</div>
        <h2 class="panel-title">v{{ plan.version }} 的计划版本</h2>
      </div>
      <el-button plain @click="emit('back')">返回周视图</el-button>
    </div>

    <div class="reason-card">
      <div class="reason-title">调整说明</div>
      <div class="reason-text">{{ plan.adjust_reason ?? '本次调整未提供说明' }}</div>
    </div>

    <el-skeleton v-if="loading" :rows="4" animated class="list-skeleton" />

    <template v-else-if="diff">
      <div v-if="isDiffEmpty" class="diff-empty">该版本没有条目变动</div>

      <ul v-else class="change-list">
        <li v-for="(m, i) in diff.moved" :key="`m${i}`" class="change-item">
          <span class="change-tag is-moved">移动</span>
          <span class="change-text">
            {{ m.topic }}：从 {{ m.from_date }} {{ hmOrRest(m.from_time) }} 挪到
            {{ m.to_date }} {{ hmOrRest(m.to_time) }}（{{ m.reason }}）
          </span>
        </li>
        <li v-for="(r, i) in diff.removed" :key="`r${i}`" class="change-item">
          <span class="change-tag is-removed">移除</span>
          <span class="change-text">{{ r.topic }} 被移出计划（{{ r.reason }}）</span>
        </li>
        <li v-for="(a, i) in diff.added" :key="`a${i}`" class="change-item">
          <span class="change-tag is-added">新增</span>
          <span class="change-text">新增：{{ a.topic }}（{{ a.reason }}）</span>
        </li>
      </ul>
    </template>
  </div>
</template>

<style scoped>
.history-panel {
  display: flex;
  flex-direction: column;
  gap: 18px;
}

.head-row {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 16px;
  padding-bottom: 14px;
  border-bottom: 1px solid var(--line);
}

.panel-kicker {
  display: flex;
  align-items: center;
  gap: 8px;
  font-family: var(--font-mono);
  font-size: 10px;
  letter-spacing: 0.1em;
  color: var(--vermilion);
}

.panel-kicker::before {
  content: '';
  width: 14px;
  height: 1px;
  background: var(--vermilion);
}

.panel-title {
  margin-top: 8px;
  font-family: var(--font-display);
  font-size: 24px;
  font-weight: 600;
  line-height: 1.3;
  color: var(--ink);
}

.reason-card {
  padding: 16px;
  background: var(--ochre-wash);
  border: 1px solid #ddc79b;
  border-radius: var(--radius);
}

.reason-title {
  font-family: var(--font-mono);
  font-size: 9px;
  letter-spacing: 0.14em;
  color: #8a6425;
}

.reason-text {
  margin-top: 7px;
  font-size: 14px;
  line-height: 1.75;
  color: #4d3a16;
}

.list-skeleton {
  padding: 8px 0;
}

.change-list {
  margin: 0;
  padding: 0;
  list-style: none;
}

.change-item {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  padding: 11px 0;
  border-bottom: 1px solid var(--line-soft);
  font-size: 13px;
  line-height: 1.7;
  color: var(--ink-2);
}

.change-item:last-child {
  border-bottom: none;
}

.change-tag {
  flex: 0 0 auto;
  margin-top: 1px;
  padding: 0 5px;
  font-family: var(--font-mono);
  font-size: 9px;
  line-height: 17px;
  color: var(--ink-3);
  background: var(--paper-3);
  border: 1px solid var(--line);
  border-radius: var(--radius);
}

.change-tag.is-moved {
  color: #7a5318;
  background: var(--ochre-wash);
  border-color: #ddc79b;
}

.change-tag.is-added {
  color: #33513e;
  background: var(--jade-wash);
  border-color: #b3c9b9;
}

.change-tag.is-removed {
  color: #7a2a20;
  background: var(--danger-wash);
  border-color: #d8aaa2;
}

.change-text {
  min-width: 0;
}

.diff-empty {
  padding: 20px 0;
  font-size: 13px;
  color: var(--ink-3);
}
</style>
