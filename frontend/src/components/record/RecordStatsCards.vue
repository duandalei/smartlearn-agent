<script setup lang="ts">
/**
 * 学习记录统计卡片（P6）。
 *
 * 纯展示组件：三值全部来自后端 stats 接口（weekly_minutes /
 * streak_days / total_count，北京周/日口径），本地零计算；stats 为
 * null（加载失败）时数值显示 '--' 不阻塞页面（P5 TaskStatsCards 模式）。
 */
import { computed } from 'vue'

import { formatMinutes } from '@/utils/record'
import type { RecordStats } from '@/types'

const props = defineProps<{
  stats: RecordStats | null
}>()

/** 卡片数值：stats 为 null 时统一显示 '--'。 */
const display = computed(() => {
  const s = props.stats
  return {
    weekly: s == null ? '--' : formatMinutes(s.weekly_minutes),
    streak: s == null ? '--' : `${s.streak_days} 天`,
    total: s == null ? '--' : `${s.total_count} 条`,
  }
})
</script>

<template>
  <el-row :gutter="12" class="stats-row">
    <el-col :xs="24" :sm="8">
      <div class="stat-card">
        <div class="stat-value">{{ display.weekly }}</div>
        <div class="stat-label">本周学习时长</div>
      </div>
    </el-col>
    <el-col :xs="24" :sm="8">
      <div class="stat-card">
        <div class="stat-value">{{ display.streak }}</div>
        <div class="stat-label">连续学习天数</div>
      </div>
    </el-col>
    <el-col :xs="24" :sm="8">
      <div class="stat-card">
        <div class="stat-value">{{ display.total }}</div>
        <div class="stat-label">记录条数</div>
      </div>
    </el-col>
  </el-row>
</template>

<style scoped>
.stats-row {
  width: 100%;
}
.stats-row .el-col {
  margin-bottom: 8px;
}
.stat-card {
  background: var(--el-fill-color-light);
  border-radius: 6px;
  padding: 12px 8px;
  text-align: center;
}
.stat-value {
  font-size: 22px;
  font-weight: 600;
  line-height: 1.4;
  color: var(--el-text-color-primary);
}
.stat-label {
  margin-top: 4px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
</style>