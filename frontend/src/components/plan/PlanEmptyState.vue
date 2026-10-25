<script setup lang="ts">
/**
 * 计划空态引导（P13；P22 扩展本周兜底；design 2.4.4；spec §5.1.3-1）。
 *
 * 本周仍有剩余天数（周一~周六）时优先引导「生成本周计划」；周日
 * 本周已结束，只提供「生成下周计划」。文案必须如实写清周期，禁止
 * 暗示生成已过去的时间段。
 */
import type { PlanGenerateTarget } from '@/types/plan'

defineProps<{
  loading: boolean
  canGenerateCurrent: boolean
  currentRemaining: { start: string; end: string }
  nextWindow: { start: string; end: string }
}>()

const emit = defineEmits<{
  (e: 'generate', target: PlanGenerateTarget): void
}>()
</script>

<template>
  <div class="plan-empty">
    <el-empty description="还没有学习计划">
      <p class="desc">
        {{ canGenerateCurrent ? '可以生成本周剩余时间，或提前规划下一周' : '本周已结束，可以提前规划下一周' }}
      </p>
      <div class="actions">
        <el-button
          v-if="canGenerateCurrent"
          type="primary"
          :loading="loading"
          :disabled="loading"
          @click="emit('generate', 'current_week')"
        >
          生成本周计划（{{ currentRemaining.start }} ~ {{ currentRemaining.end }}）
        </el-button>
        <el-button
          :type="canGenerateCurrent ? 'default' : 'primary'"
          :loading="loading"
          :disabled="loading"
          @click="emit('generate', 'next_week')"
        >
          生成下周计划（{{ nextWindow.start }} ~ {{ nextWindow.end }}）
        </el-button>
      </div>
      <p v-if="!canGenerateCurrent" class="sub-desc">下周计划生成后，周一自动生效</p>
      <p class="sub-desc">同一周期重复生成会归档旧版本</p>
    </el-empty>
  </div>
</template>

<style scoped>
.plan-empty {
  padding: 40px 0;
}
.desc {
  margin: 0 0 16px;
  font-size: 13px;
  color: var(--el-text-color-secondary);
}
.actions {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 12px;
  flex-wrap: wrap;
}
.sub-desc {
  margin: 12px 0 0;
  font-size: 12px;
  color: var(--el-text-color-placeholder);
}
</style>
