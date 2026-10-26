<script setup lang="ts">
import type { AdviceData, AdviceType } from '@/types'

defineProps<{
  data: AdviceData | null
  loading: boolean
  error: boolean
  reload: () => void
}>()

/** 建议类型对应的一个色点（不只靠颜色区分，标题本身也说明问题）。 */
const ADVICE_MARK: Record<AdviceType, string> = {
  overdue: 'is-vermilion',
  weakness: 'is-ochre',
  streak: 'is-jade',
}
</script>

<template>
  <section class="panel advice-card">
    <div class="panel__head">
      <div>
        <div class="panel__title">今日建议</div>
        <div class="panel__sub">根据最近的记录生成</div>
      </div>
      <span class="seal seal--sm seal--ghost" aria-hidden="true">议</span>
    </div>

    <div class="panel__body advice-body">
      <el-skeleton v-if="loading" :rows="4" animated />

      <div v-else-if="error" class="block-error" @click="reload">
        数据加载失败，点击重试
      </div>

      <div v-else-if="data == null || data.items.length === 0" class="empty-note advice-empty">
        <span class="seal seal--ghost" aria-hidden="true">静</span>
        <div class="empty-note__title">今天没有需要特别提醒的事</div>
        <div>记一笔学习，或去问问 AI 助手下一步做什么。</div>
      </div>

      <div v-else class="advice-list">
        <article
          v-for="(item, index) in data.items"
          :key="item.type"
          class="advice-item"
        >
          <div class="advice-index" aria-hidden="true">{{ String(index + 1).padStart(2, '0') }}</div>
          <div class="advice-main">
            <div class="advice-title-row">
              <span class="advice-mark" :class="ADVICE_MARK[item.type]" aria-hidden="true" />
              <div class="advice-title">{{ item.title }}</div>
            </div>
            <p class="advice-content">{{ item.content }}</p>
          </div>
        </article>
      </div>
    </div>
  </section>
</template>

<style scoped>
.advice-card {
  height: 100%;
  display: flex;
  flex-direction: column;
}

.advice-body {
  flex: 1 1 auto;
}

.advice-list {
  display: flex;
  flex-direction: column;
}

.advice-item {
  display: flex;
  gap: 14px;
  padding: 14px 0;
  border-bottom: 1px solid var(--line-soft);
}

.advice-item:first-child {
  padding-top: 0;
}

.advice-item:last-child {
  padding-bottom: 0;
  border-bottom: none;
}

.advice-index {
  flex: 0 0 24px;
  font-family: var(--font-display);
  font-variant-numeric: lining-nums tabular-nums;
  font-size: 15px;
  font-weight: 600;
  line-height: 1.6;
  color: var(--vermilion);
}

.advice-main {
  min-width: 0;
}

.advice-title-row {
  display: flex;
  align-items: center;
  gap: 8px;
}

.advice-mark {
  width: 5px;
  height: 5px;
  flex: 0 0 5px;
  border-radius: 1px;
  background: var(--vermilion);
}

.advice-mark.is-ochre {
  background: var(--ochre);
}

.advice-mark.is-jade {
  background: var(--jade);
}

.advice-title {
  font-size: 14px;
  font-weight: 600;
  line-height: 1.5;
  color: var(--ink);
}

.advice-content {
  margin-top: 4px;
  font-size: 13px;
  line-height: 1.7;
  color: var(--ink-3);
}

.advice-empty {
  gap: 10px;
  padding: 28px 8px;
}
</style>
