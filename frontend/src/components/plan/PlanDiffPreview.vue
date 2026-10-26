<script setup lang="ts">
/**
 * 调整结果预览：左旧右新双栏对比 + 结构化改动清单。
 * 右栏条目一律来自服务端 pending.items，禁止前端重建。
 */
import { computed, onMounted, onUnmounted } from 'vue'

import type { PendingNewPlan } from '@/types/plan'
import { formatHm, markDiffHighlights } from '@/utils/plan'
import WeekGrid from '@/components/plan/WeekGrid.vue'

const props = defineProps<{
  pending: PendingNewPlan
}>()

const emit = defineEmits<{
  (e: 'confirm', source: 'primary' | 'close'): void
}>()

function onKeydown(e: KeyboardEvent): void {
  if (e.key === 'Escape') emit('confirm', 'close')
}
onMounted(() => window.addEventListener('keydown', onKeydown))
onUnmounted(() => window.removeEventListener('keydown', onKeydown))

const oldHighlights = computed(() =>
  markDiffHighlights(props.pending.oldItems, props.pending.diff, 'old'),
)
const newHighlights = computed(() =>
  markDiffHighlights(props.pending.items, props.pending.diff, 'new'),
)

const isDiffEmpty = computed(() => {
  const d = props.pending.diff
  return d.moved.length === 0 && d.added.length === 0 && d.removed.length === 0
})

function hmOrRest(t: string | null): string {
  return t == null ? '休息时段' : formatHm(t)
}
</script>

<template>
  <div class="diff-preview">
    <div class="head-row">
      <div>
        <div class="panel-kicker">计划调整预览</div>
        <h2 class="panel-title">调整后的计划</h2>
      </div>
      <span class="head-version">v{{ pending.plan.version }}</span>
    </div>

    <div class="reason-card">
      <div class="reason-title">调整说明</div>
      <div class="reason-text">{{ pending.adjustReason ?? '本次调整未提供说明' }}</div>
    </div>

    <div class="dual-pane">
      <section class="pane">
        <div class="pane-title">
          <span>原计划</span>
          <span class="pane-version">v{{ pending.plan.version - 1 }}</span>
        </div>
        <WeekGrid
          :plan="pending.plan"
          :items="pending.oldItems"
          compact
          :highlights="oldHighlights"
          highlight-side="old"
        />
      </section>
      <section class="pane">
        <div class="pane-title">
          <span>新计划</span>
          <span class="pane-version is-new">v{{ pending.plan.version }}</span>
        </div>
        <WeekGrid
          :plan="pending.plan"
          :items="pending.items"
          compact
          :highlights="newHighlights"
          highlight-side="new"
        />
      </section>
    </div>

    <div class="change-section">
      <div class="section-head">
        <div class="section-title">条目变动</div>
        <span class="section-note">只列出被移动、移除和新增的条目</span>
      </div>

      <ul v-if="!isDiffEmpty" class="change-list">
        <li v-for="(m, i) in pending.diff.moved" :key="`m${i}`" class="change-item">
          <span class="change-tag is-moved">移动</span>
          <span class="change-text">
            {{ m.topic }}：从 {{ m.from_date }} {{ hmOrRest(m.from_time) }} 挪到
            {{ m.to_date }} {{ hmOrRest(m.to_time) }}（{{ m.reason }}）
          </span>
        </li>
        <li v-for="(r, i) in pending.diff.removed" :key="`r${i}`" class="change-item">
          <span class="change-tag is-removed">移除</span>
          <span class="change-text">{{ r.topic }} 被移出计划（{{ r.reason }}）</span>
        </li>
        <li v-for="(a, i) in pending.diff.added" :key="`a${i}`" class="change-item">
          <span class="change-tag is-added">新增</span>
          <span class="change-text">新增：{{ a.topic }}（{{ a.reason }}）</span>
        </li>
      </ul>
      <div v-else class="change-empty">本次调整没有条目变动</div>
    </div>

    <div class="actions">
      <span class="actions-hint">按 Esc 关闭对比</span>
      <span class="spacer" />
      <el-button plain @click="emit('confirm', 'close')">关闭对比</el-button>
      <el-button type="primary" @click="emit('confirm', 'primary')">
        查看调整后的计划
      </el-button>
    </div>
  </div>
</template>

<style scoped>
.diff-preview {
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

.head-version {
  font-family: var(--font-mono);
  font-size: 11px;
  color: var(--ink-3);
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

.dual-pane {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
  gap: 16px;
}

.pane {
  min-width: 0;
}

.pane-title {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  padding-bottom: 8px;
  font-family: var(--font-display);
  font-size: 14px;
  font-weight: 600;
  color: var(--ink-3);
}

.pane-version {
  font-family: var(--font-mono);
  font-size: 10px;
  color: var(--ink-4);
}

.pane-version.is-new {
  color: var(--vermilion);
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

.change-empty {
  padding: 18px 0;
  font-size: 13px;
  color: var(--ink-3);
}

.actions {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  padding-top: 4px;
}

.actions-hint {
  font-family: var(--font-mono);
  font-size: 10px;
  color: var(--ink-4);
}

@media (max-width: 1100px) {
  .dual-pane {
    grid-template-columns: minmax(0, 1fr);
  }
}
</style>
