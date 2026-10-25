<script setup lang="ts">
/**
 * 计划信息头（P13；design 2.4.4；spec §5.1.1 规则 7、§5.2.1 规则 3、§5.4.1 规则 1）。
 *
 * 纯展示组件：标题 + 周期文本 + 版本徽章 + 生成方式徽章 + 周归属标注
 * + 「查看调整记录」入口（parent_plan_id 为空不渲染）。零请求。
 */
import type { Plan } from '@/types/plan'

const props = defineProps<{
  plan: Plan | null
  /** 周归属：本周 / 下周 / 更远未来（日期推导，不依赖视图来源）。 */
  weekKind: 'current' | 'next' | 'future'
  degraded: boolean
}>()

const emit = defineEmits<{
  (e: 'view-history'): void
}>()
</script>

<template>
  <div v-if="props.plan" class="plan-info-header">
    <div class="title-row">
      <span class="plan-title">{{ props.plan.title }}</span>
      <el-tag size="small" effect="plain" class="version-tag">v{{ props.plan.version }}</el-tag>
      <el-tag v-if="props.degraded" size="small" type="warning">规则降级</el-tag>
      <el-tag v-else size="small" type="info">LLM 规划</el-tag>
      <el-tag v-if="props.weekKind === 'current'" size="small" type="success">
        本周计划
      </el-tag>
      <el-tag v-else-if="props.weekKind === 'next'" size="small" type="primary">
        下周计划
      </el-tag>
      <el-tag v-else size="small" type="info">未来计划</el-tag>
    </div>
    <div class="meta-row">
      <span class="period">{{ props.plan.start_date }} ~ {{ props.plan.end_date }}</span>
      <el-button
        v-if="props.plan.parent_plan_id != null"
        type="primary"
        link
        @click="emit('view-history')"
      >
        查看调整记录
      </el-button>
    </div>
  </div>
</template>

<style scoped>
.plan-info-header {
  padding: 4px 0 12px;
}
.title-row {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}
.plan-title {
  font-size: 18px;
  font-weight: 600;
  color: var(--el-text-color-primary);
}
.version-tag {
  font-weight: 400;
}
.meta-row {
  margin-top: 6px;
  display: flex;
  align-items: center;
  gap: 12px;
}
.period {
  font-size: 13px;
  color: var(--el-text-color-secondary);
}
</style>