<script setup lang="ts">
/**
 * 目标卡片（P4，design 2.5.2）。
 *
 * 布局：左侧固定宽进度位 + 右侧内容区（名称 / 类型 / 状态 / 起止日期 /
 * 剩余天数），底部操作按钮。进度区由 calcGoalProgress 输出驱动三态渲染：
 * - 起止齐全：el-progress 环（format 显示剩余天数；已过期 100% + 危险色）；
 * - 仅截止日期：环退化为大号数字占位；
 * - 未设截止日期：灰字提示（杜绝除零 / NaN）。
 *
 * 「AI 拆解」「知识树」按钮只负责 emit，由父页面打开 RoadmapDrawer 统一处理。
 */
import { computed } from 'vue'

import type { Goal, GoalStatus } from '@/types'
import { calcGoalProgress } from '@/utils/goal'

const props = defineProps<{ goal: Goal }>()

const emit = defineEmits<{
  (e: 'edit', goal: Goal): void
  (e: 'breakdown', goal: Goal): void
  (e: 'view-roadmap', goal: Goal): void
  (e: 'delete', goal: Goal): void
}>()

/** 状态标签映射（design 2.5.2）。 */
const STATUS_META: Record<GoalStatus, { label: string; type: 'success' | 'info' | 'warning' }> = {
  active: { label: '进行中', type: 'success' },
  completed: { label: '已完成', type: 'info' },
  archived: { label: '已归档', type: 'warning' },
}

/** 进度三态计算结果。 */
const progress = computed(() => calcGoalProgress(props.goal.start_date, props.goal.end_date))

/** 状态标签元信息。 */
const statusMeta = computed(() => STATUS_META[props.goal.status] ?? STATUS_META.active)

/** 起止日期展示文本（缺失一侧时降级为单边表述）。 */
const dateRangeText = computed(() => {
  const s = props.goal.start_date
  const e = props.goal.end_date
  if (s && e) return `${s} ~ ${e}`
  if (s) return `${s} 起`
  if (e) return `截止 ${e}`
  return ''
})

/** 环中心的 format 函数（剩余天数 / 已过期）。 */
function ringFormat(_percentage: number): string {
  return progress.value.expired ? '已过期' : `${progress.value.remainingDays} 天`
}
</script>

<template>
  <el-card shadow="hover" class="goal-card">
    <div class="goal-card-body">
      <!-- 进度位三态 -->
      <div class="progress-zone">
        <el-progress
          v-if="progress.showRing"
          type="circle"
          :percentage="progress.percent"
          :width="84"
          :status="progress.expired ? 'exception' : undefined"
          :format="ringFormat"
        />
        <div v-else-if="progress.showRemainingText" class="days-placeholder">
          <template v-if="progress.expired">
            <span class="expired-text">已过期</span>
          </template>
          <template v-else>
            <div class="days-num">{{ progress.remainingDays }}</div>
            <div class="days-unit">天</div>
          </template>
        </div>
        <div v-else class="no-deadline">未设置截止日期</div>
      </div>

      <!-- 内容区 -->
      <div class="content-zone">
        <div class="title-row">
          <span class="goal-title" :title="goal.title">{{ goal.title }}</span>
          <el-tag v-if="goal.goal_type" size="small" disable-transitions>{{ goal.goal_type }}</el-tag>
        </div>
        <div class="meta-row">
          <el-tag size="small" :type="statusMeta.type" disable-transitions>{{ statusMeta.label }}</el-tag>
          <span v-if="dateRangeText" class="date-range">{{ dateRangeText }}</span>
        </div>
        <div
          v-if="progress.showRing"
          class="remaining-line"
          :class="{ 'remaining-expired': progress.expired }"
        >
          {{ progress.expired ? '已过期' : `剩余 ${progress.remainingDays} 天` }}
        </div>
      </div>
    </div>

    <!-- 操作按钮区 -->
    <div class="actions">
      <el-button size="small" link @click="emit('edit', goal)">编辑</el-button>
      <el-button size="small" link type="primary" @click="emit('breakdown', goal)">AI 拆解</el-button>
      <el-button size="small" link @click="emit('view-roadmap', goal)">知识树</el-button>
      <el-button size="small" link type="danger" @click="emit('delete', goal)">删除</el-button>
    </div>
  </el-card>
</template>

<style scoped>
.goal-card {
  height: 100%;
}
.goal-card-body {
  display: flex;
  gap: 16px;
  align-items: center;
}
.progress-zone {
  flex: 0 0 96px;
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 84px;
}
.days-placeholder {
  text-align: center;
  color: #303133;
}
.days-num {
  font-size: 28px;
  font-weight: 600;
  line-height: 1.1;
}
.days-unit {
  font-size: 13px;
  color: #909399;
}
.expired-text {
  font-size: 15px;
  font-weight: 600;
  color: #f56c6c;
}
.no-deadline {
  font-size: 12px;
  color: #909399;
  text-align: center;
  line-height: 1.6;
}
.content-zone {
  flex: 1;
  min-width: 0;
}
.title-row {
  display: flex;
  align-items: center;
  gap: 8px;
}
.goal-title {
  font-size: 15px;
  font-weight: 600;
  color: #303133;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.meta-row {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 8px;
  flex-wrap: wrap;
}
.date-range {
  font-size: 12px;
  color: #909399;
}
.remaining-line {
  margin-top: 8px;
  font-size: 12px;
  color: #606266;
}
.remaining-expired {
  color: #f56c6c;
}
.actions {
  display: flex;
  justify-content: flex-end;
  gap: 4px;
  margin-top: 8px;
  padding-top: 8px;
  border-top: 1px solid #ebeef5;
}
</style>