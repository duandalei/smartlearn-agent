<script setup lang="ts">
import type { Component } from 'vue'
import { Aim, Clock, Trophy } from '@element-plus/icons-vue'

import type { AdviceData, AdviceType } from '@/types'

defineProps<{
  data: AdviceData | null
  loading: boolean
  error: boolean
  reload: () => void
}>()

const ADVICE_ICONS: Record<AdviceType, Component> = {
  overdue: Clock,
  weakness: Aim,
  streak: Trophy,
}
</script>

<template>
  <el-card shadow="never" class="advice-card">
    <template #header>
      <span class="card-title">AI 今日建议</span>
    </template>

    <el-skeleton v-if="loading" :rows="4" animated />

    <div v-else-if="error" class="block-error" @click="reload">数据加载失败，点击重试</div>

    <el-empty v-else-if="data == null || data.items.length === 0" description="暂无学习建议" />

    <div v-else class="advice-list">
      <div v-for="item in data.items" :key="item.type" class="advice-item">
        <el-icon class="advice-icon"><component :is="ADVICE_ICONS[item.type]" /></el-icon>
        <div class="advice-body">
          <div class="advice-title">{{ item.title }}</div>
          <div class="advice-content">{{ item.content }}</div>
        </div>
      </div>
    </div>
  </el-card>
</template>

<style scoped>
.advice-card {
  height: 100%;
}
.card-title {
  font-size: 15px;
  font-weight: 600;
}
.advice-item {
  display: flex;
  gap: 10px;
  padding: 10px 0;
  border-bottom: 1px dashed var(--el-border-color-lighter);
}
.advice-item:last-child {
  border-bottom: none;
}
.advice-icon {
  flex-shrink: 0;
  font-size: 18px;
  margin-top: 2px;
  color: var(--el-color-primary);
}
.advice-title {
  font-size: 14px;
  font-weight: 500;
  color: var(--el-text-color-primary);
}
.advice-content {
  margin-top: 4px;
  font-size: 13px;
  line-height: 1.6;
  color: var(--el-text-color-regular);
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