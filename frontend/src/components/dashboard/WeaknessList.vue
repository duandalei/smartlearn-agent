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

  <el-empty v-else-if="data == null || data.items.length === 0" description="暂无薄弱知识点" />

  <div v-else class="weakness-list">
    <div v-for="item in data.items" :key="item.knowledge_point" class="weakness-item">
      <div class="weakness-main">
        <span class="weakness-name">{{ item.knowledge_point }}</span>
        <span class="weakness-score">{{ item.mastery_score }} 分</span>
        <el-tag size="small" type="info">近 30 天 {{ item.recent_count }} 次</el-tag>
      </div>
      <div class="weakness-advice">{{ item.advice }}</div>
    </div>
  </div>
</template>

<style scoped>
.weakness-item {
  padding: 8px 0;
  border-bottom: 1px dashed var(--el-border-color-lighter);
}
.weakness-item:last-child {
  border-bottom: none;
}
.weakness-main {
  display: flex;
  align-items: center;
  gap: 8px;
}
.weakness-name {
  font-size: 14px;
  font-weight: 500;
  color: var(--el-text-color-primary);
}
.weakness-score {
  font-size: 13px;
  color: var(--el-color-danger);
}
.weakness-advice {
  margin-top: 4px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
.block-error {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 96px;
  color: var(--el-color-danger);
  font-size: 14px;
  cursor: pointer;
}
.block-error:hover {
  text-decoration: underline;
}
</style>