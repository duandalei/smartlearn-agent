<script setup lang="ts">
/**
 * 调整记录回看面板（P13；design 2.4.4；spec §5.4.1 规则 2/4、§5.4.3-2）。
 *
 * 降级形态：plan.adjust_reason 显著展示 + 三类改动清单（与 PlanDiffPreview ③
 * 同构样式，各自局部模板块不抽公共子组件）。无双栏网格（parent 版本条目需
 * 全量翻页取回，回看属低频能力不付此开销）；无任何操作类按钮（调整早已生效）。
 *
 * 时间显示：diff 时间位经 formatHm 截取 'HH:MM'；null → 「休息时段」。
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

/** 空结构判定：三类清单全空 → 「该版本无调整记录」（spec §5.4.3-2）。 */
const isDiffEmpty = computed(() => {
  const d = props.diff
  if (!d) return false
  return d.moved.length === 0 && d.added.length === 0 && d.removed.length === 0
})

/** 时间位展示：null → 「休息时段」；否则 formatHm 截取 'HH:MM'。 */
function hmOrRest(t: string | null): string {
  return t == null ? '休息时段' : formatHm(t)
}
</script>

<template>
  <div class="history-panel">
    <div class="head-row">
      <div class="panel-title">调整记录 · v{{ plan.version }}</div>
      <el-button plain @click="emit('back')">返回周视图</el-button>
    </div>

    <div class="reason-card">
      <div class="reason-title">调整说明</div>
      <div class="reason-text">{{ plan.adjust_reason ?? '本次调整未提供说明' }}</div>
    </div>

    <el-skeleton v-if="loading" :rows="4" animated class="list-skeleton" />
    <template v-else-if="diff">
      <div v-if="isDiffEmpty" class="diff-empty">该版本无调整记录</div>
      <div v-else class="change-list">
        <div v-for="(m, i) in diff.moved" :key="`m${i}`" class="change-item">
          {{ m.topic }}：从 {{ m.from_date }} {{ hmOrRest(m.from_time) }} 挪到
          {{ m.to_date }} {{ hmOrRest(m.to_time) }}（{{ m.reason }}）
        </div>
        <div v-for="(r, i) in diff.removed" :key="`r${i}`" class="change-item">
          {{ r.topic }} 被移出计划（{{ r.reason }}）
        </div>
        <div v-for="(a, i) in diff.added" :key="`a${i}`" class="change-item">
          新增：{{ a.topic }}（{{ a.reason }}）
        </div>
      </div>
    </template>
  </div>
</template>

<style scoped>
.history-panel {
  display: flex;
  flex-direction: column;
  gap: 16px;
}
.head-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.panel-title {
  font-size: 16px;
  font-weight: 600;
  color: var(--el-text-color-primary);
}
.reason-card {
  background: var(--el-color-warning-light-9);
  border-left: 4px solid var(--el-color-warning);
  border-radius: 4px;
  padding: 12px 16px;
}
.reason-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--el-text-color-primary);
  margin-bottom: 6px;
}
.reason-text {
  font-size: 15px;
  line-height: 1.7;
  color: var(--el-text-color-primary);
}
.list-skeleton {
  padding: 12px 0;
}
.change-list {
  background: var(--el-fill-color-light);
  border-radius: 6px;
  padding: 12px 16px;
}
.change-item {
  font-size: 13px;
  line-height: 2;
  color: var(--el-text-color-primary);
}
.diff-empty {
  font-size: 13px;
  color: var(--el-text-color-secondary);
  padding: 12px 0;
}
</style>