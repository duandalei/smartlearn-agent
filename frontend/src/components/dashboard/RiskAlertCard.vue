<script setup lang="ts">
import { Warning } from '@element-plus/icons-vue'

import type { RiskAlert } from '@/types'

defineProps<{
  alert: RiskAlert | null
  loading: boolean
  error: boolean
  reload: () => void
}>()
</script>

<template>
  <el-card shadow="never" class="risk-card">
    <template #header>
      <div class="card-header">
        <span class="card-title">学习风险提醒</span>
        <el-icon v-if="alert != null" class="risk-header-icon"><Warning /></el-icon>
      </div>
    </template>

    <el-skeleton v-if="loading" :rows="3" animated />

    <div v-else-if="error" class="block-error" @click="reload">数据加载失败，点击重试</div>

    <el-alert v-else-if="alert != null" type="warning" :closable="false" class="risk-alert">
      <template #title>{{ alert.title }}</template>
      <div class="risk-message">{{ alert.message }}</div>
      <div class="risk-suggestion">{{ alert.suggestion }}</div>
    </el-alert>

    <el-empty v-else description="暂无学习风险提醒" />
  </el-card>
</template>

<style scoped>
.risk-card {
  height: 100%;
}
.card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.card-title {
  font-size: 15px;
  font-weight: 600;
}
.risk-header-icon {
  color: var(--el-color-warning);
  font-size: 18px;
}
.risk-alert {
  margin-top: 4px;
}
.risk-message {
  font-size: 13px;
  line-height: 1.6;
}
.risk-suggestion {
  margin-top: 6px;
  font-size: 13px;
  line-height: 1.6;
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