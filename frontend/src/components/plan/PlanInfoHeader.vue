<script setup lang="ts">
/**
 * 计划信息头：卷标 + 计划标题 + 周期与方法标记。
 * 纯展示组件，零请求。
 */
import { computed } from 'vue'

import type { Plan } from '@/types/plan'

const props = defineProps<{
  plan: Plan | null
  weekKind: 'current' | 'next' | 'future'
  degraded: boolean
}>()

const emit = defineEmits<{
  (e: 'view-history'): void
}>()

const WEEK_KIND_LABEL = {
  current: '本周',
  next: '下周',
  future: '未来',
} as const

const weekKindLabel = computed(() => WEEK_KIND_LABEL[props.weekKind])

/** 通用计划名（去掉日期后缀后与页面标题重复时，改用「本周计划」）。 */
const GENERIC_TITLES = new Set([
  '学习计划',
  '本周学习计划',
  '下周学习计划',
  '未来学习计划',
  '计划',
])

/**
 * 展示标题：去掉 AI 标题里重复的日期括号，避免窄屏把日期从中间折断；
 * 去掉后若只剩通用词，则用周归属作为标题。
 */
const displayTitle = computed(() => {
  const raw = props.plan?.title?.trim() ?? ''
  const stripped = raw
    .replace(
      /[（(]\s*\d{4}[-/]\d{1,2}[-/]\d{1,2}\s*[~～—–-]\s*\d{4}[-/]\d{1,2}[-/]\d{1,2}\s*[）)]\s*$/,
      '',
    )
    .trim()
  if (!stripped || GENERIC_TITLES.has(stripped)) {
    return `${weekKindLabel.value}计划`
  }
  return stripped
})
</script>

<template>
  <div v-if="props.plan" class="plan-header">
    <div class="plan-header__main">
      <div class="plan-kicker">
        <span class="plan-kicker__mark" aria-hidden="true" />
        {{ weekKindLabel }} · 第 {{ props.plan.version }} 版
      </div>
      <h2 class="plan-title" :title="props.plan.title">{{ displayTitle }}</h2>
      <div class="plan-meta">
        <span class="plan-period">{{ props.plan.start_date }} — {{ props.plan.end_date }}</span>
        <el-tag v-if="props.degraded" size="small" type="warning" effect="plain">
          规则降级
        </el-tag>
        <el-tag v-else size="small" effect="plain">LLM 规划</el-tag>
        <el-button
          v-if="props.plan.parent_plan_id != null"
          link
          type="primary"
          size="small"
          @click="emit('view-history')"
        >
          查看调整记录
        </el-button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.plan-header {
  padding: 0 0 16px;
  border-bottom: 1px solid var(--line);
}

.plan-kicker {
  display: flex;
  align-items: center;
  gap: 8px;
  font-family: var(--font-mono);
  font-size: 10px;
  letter-spacing: 0.1em;
  color: var(--vermilion);
}

.plan-kicker__mark {
  width: 14px;
  height: 1px;
  background: var(--vermilion);
}

.plan-title {
  margin-top: 8px;
  font-family: var(--font-display);
  font-size: 26px;
  font-weight: 600;
  line-height: 1.3;
  color: var(--ink);
}

.plan-meta {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
  margin-top: 10px;
}

.plan-period {
  font-family: var(--font-mono);
  font-size: 11px;
  color: var(--ink-3);
}

@media (max-width: 720px) {
  .plan-title {
    font-size: 22px;
  }
}
</style>
