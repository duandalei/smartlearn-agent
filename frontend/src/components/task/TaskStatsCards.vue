<script setup lang="ts">
/**
 * 任务统计卡片（P5，design 2.5.2）。
 *
 * 纯展示组件：数值全部来自后端 stats 接口（spec 5.5.1 规则 6a），
 * 本地零计算；stats 为 null（加载失败）时数值显示 '--' 不阻塞页面
 * （spec 5.5.3 场景 1）。
 */
import { computed } from 'vue'

import type { TaskStats } from '@/types'

const props = defineProps<{
  stats: TaskStats | null
}>()


/** 卡片数值：stats 为 null 时统一显示 '--'。 */
const display = computed(() => {
  const s = props.stats
  return {
    total: s == null ? '--' : String(s.total),
    todo: s == null ? '--' : String(s.status_counts.todo),
    inProgress: s == null ? '--' : String(s.status_counts.in_progress),
    done: s == null ? '--' : String(s.status_counts.done),
    review: s == null ? '--' : String(s.status_counts.review),
    overdue: s == null ? '--' : String(s.overdue_count),
    weeklyRate: s == null ? '--' : `${s.weekly_completion_rate.toFixed(1)}%`,
    todayTodo: s == null ? '--' : String(s.today_todo_count),
  }
})
</script>

<template>
  <el-row :gutter="12" class="stats-row">
    <el-col :xs="12" :sm="6" :md="3">
      <div class="stat-card">
        <div class="stat-value">{{ display.total }}</div>
        <div class="stat-label">总任务数</div>
      </div>
    </el-col>
    <el-col :xs="12" :sm="6" :md="3">
      <div class="stat-card">
        <div class="stat-value">{{ display.todo }}</div>
        <div class="stat-label">待办</div>
      </div>
    </el-col>
    <el-col :xs="12" :sm="6" :md="3">
      <div class="stat-card">
        <div class="stat-value">{{ display.inProgress }}</div>
        <div class="stat-label">进行中</div>
      </div>
    </el-col>
    <el-col :xs="12" :sm="6" :md="3">
      <div class="stat-card">
        <div class="stat-value">{{ display.done }}</div>
        <div class="stat-label">已完成</div>
      </div>
    </el-col>
    <el-col :xs="12" :sm="6" :md="3">
      <div class="stat-card">
        <div class="stat-value">{{ display.review }}</div>
        <div class="stat-label">待复盘</div>
      </div>
    </el-col>
    <el-col :xs="12" :sm="6" :md="3">
      <div class="stat-card overdue">
        <div class="stat-value">{{ display.overdue }}</div>
        <div class="stat-label">逾期数</div>
      </div>
    </el-col>
    <el-col :xs="12" :sm="6" :md="3">
      <div class="stat-card">
        <div class="stat-value">{{ display.weeklyRate }}</div>
        <div class="stat-label">本周完成率</div>
      </div>
    </el-col>
    <el-col :xs="12" :sm="6" :md="3">
      <div class="stat-card">
        <div class="stat-value">{{ display.todayTodo }}</div>
        <div class="stat-label">今日待办</div>
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
.stat-card.overdue .stat-value {
  color: var(--el-color-danger);
}
.stat-label {
  margin-top: 4px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
</style>