<script setup lang="ts">
import { computed } from 'vue'

import { formatMinutes } from '@/utils/record'
import type { OverviewData } from '@/types'

const props = defineProps<{
  data: OverviewData | null
  loading: boolean
  error: boolean
  reload: () => void
}>()

const display = computed(() => {
  const d = props.data
  return {
    totalMinutes: d == null ? '--' : formatMinutes(d.total_minutes),
    completionRate: d == null ? '--' : `${d.task_completion_rate}%`,
    avgMastery: d == null ? '--' : `${d.avg_mastery} 分`,
    streakDays: d == null ? '--' : `${d.streak_days} 天`,
    recordCount: d == null ? '--' : `共 ${d.total_record_count} 条记录`,
    overdueCount: d == null ? '--' : `${d.overdue_task_count} 个任务逾期`,
    avgSession: d == null ? '--' : `平均单次 ${d.avg_session_minutes} 分钟`,
  }
})
</script>

<template>
  <el-row v-if="loading" :gutter="16">
    <el-col v-for="n in 4" :key="n" :xs="12" :sm="6">
      <el-skeleton class="metric-skeleton" :rows="2" animated />
    </el-col>
  </el-row>

  <div v-else-if="error" class="block-error" @click="reload">数据加载失败，点击重试</div>

  <el-row v-else :gutter="16">
    <el-col :xs="12" :sm="6">
      <div class="metric-card">
        <div class="metric-value">{{ display.totalMinutes }}</div>
        <div class="metric-label">总学习时长</div>
        <div class="metric-sub">{{ display.recordCount }}</div>
      </div>
    </el-col>
    <el-col :xs="12" :sm="6">
      <div class="metric-card">
        <div class="metric-value">{{ display.completionRate }}</div>
        <div class="metric-label">任务完成率</div>
        <div class="metric-sub">{{ display.overdueCount }}</div>
      </div>
    </el-col>
    <el-col :xs="12" :sm="6">
      <div class="metric-card">
        <div class="metric-value">{{ display.avgMastery }}</div>
        <div class="metric-label">平均掌握度</div>
        <div class="metric-sub">满分 100 分</div>
      </div>
    </el-col>
    <el-col :xs="12" :sm="6">
      <div class="metric-card">
        <div class="metric-value">{{ display.streakDays }}</div>
        <div class="metric-label">连续学习天数</div>
        <div class="metric-sub">{{ display.avgSession }}</div>
      </div>
    </el-col>
  </el-row>
</template>

<style scoped>
.metric-skeleton {
  padding: 12px;
}
.metric-card {
  background: var(--el-fill-color-light);
  border-radius: 6px;
  padding: 16px 12px;
  text-align: center;
}
.metric-value {
  font-size: 22px;
  font-weight: 600;
  line-height: 1.4;
  color: var(--el-text-color-primary);
}
.metric-label {
  margin-top: 4px;
  font-size: 13px;
  color: var(--el-text-color-regular);
}
.metric-sub {
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