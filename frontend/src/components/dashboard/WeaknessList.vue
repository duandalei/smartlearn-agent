<script setup lang="ts">
import type { WeaknessData } from '@/types'

defineProps<{
  data: WeaknessData | null
  loading: boolean
  error: boolean
  reload: () => void
}>()
</script>

<template>
  <el-skeleton v-if="loading" :rows="4" animated />

  <div v-else-if="error" class="block-error" @click="reload">数据加载失败，点击重试</div>

  <div v-else-if="data == null || data.items.length === 0" class="empty-note weakness-empty">
    <div class="empty-note__title">暂时没有薄弱知识点</div>
    <div>继续保持记录，或去知识库补充一些可检索的资料。</div>
  </div>

  <ol v-else class="weakness-list">
    <li
      v-for="(item, index) in data.items"
      :key="item.knowledge_point"
      class="weakness-item"
    >
      <div class="weakness-rank" aria-hidden="true">{{ String(index + 1).padStart(2, '0') }}</div>
      <div class="weakness-main">
        <div class="weakness-line">
          <span class="weakness-name">{{ item.knowledge_point }}</span>
          <span class="weakness-score">{{ item.mastery_score }} 分</span>
          <span class="weakness-count">近 30 天 {{ item.recent_count }} 次</span>
        </div>
        <p class="weakness-advice">{{ item.advice }}</p>
      </div>
    </li>
  </ol>
</template>

<style scoped>
.weakness-list {
  margin: 0;
  padding: 0;
  list-style: none;
}

.weakness-item {
  display: flex;
  gap: 14px;
  padding: 12px 0;
  border-bottom: 1px solid var(--line-soft);
}

.weakness-item:first-child {
  padding-top: 0;
}

.weakness-item:last-child {
  padding-bottom: 0;
  border-bottom: none;
}

.weakness-rank {
  flex: 0 0 24px;
  font-family: var(--font-display);
  font-variant-numeric: lining-nums tabular-nums;
  font-size: 15px;
  font-weight: 600;
  line-height: 1.6;
  color: var(--vermilion);
}

.weakness-main {
  min-width: 0;
  flex: 1 1 auto;
}

.weakness-line {
  display: flex;
  align-items: baseline;
  gap: 10px;
  flex-wrap: wrap;
}

.weakness-name {
  font-size: 14px;
  font-weight: 600;
  color: var(--ink);
}

.weakness-score {
  font-family: var(--font-mono);
  font-size: 11px;
  color: var(--vermilion);
}

.weakness-count {
  font-family: var(--font-mono);
  font-size: 10px;
  color: var(--ink-4);
}

.weakness-advice {
  margin-top: 3px;
  font-size: 12px;
  line-height: 1.65;
  color: var(--ink-3);
}

.weakness-empty {
  padding: 24px 8px;
}
</style>
