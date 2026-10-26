<script setup lang="ts">
/**
 * 计划空态引导：本周仍有剩余天数时优先生成本周，否则只提供下周。
 * 文案必须如实写清周期，禁止暗示生成已过去的时间段。
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
  <div class="panel plan-empty">
    <div class="panel__body">
      <div class="empty-note plan-empty__inner">
        <span class="seal seal--ghost" aria-hidden="true">划</span>
        <div class="empty-note__title">还没有学习计划</div>
        <div>
          {{
            canGenerateCurrent
              ? '可以先生成本周剩余时间，或提前规划下一周。'
              : '本周已结束，可以提前规划下一周。'
          }}
        </div>
        <div class="empty-note__actions">
          <el-button
            v-if="canGenerateCurrent"
            type="primary"
            :loading="loading"
            :disabled="loading"
            @click="emit('generate', 'current_week')"
          >
            生成本周计划（{{ currentRemaining.start }} — {{ currentRemaining.end }}）
          </el-button>
          <el-button
            :type="canGenerateCurrent ? 'default' : 'primary'"
            :loading="loading"
            :disabled="loading"
            @click="emit('generate', 'next_week')"
          >
            生成下周计划（{{ nextWindow.start }} — {{ nextWindow.end }}）
          </el-button>
        </div>
        <div class="plan-empty__notes">
          <span v-if="!canGenerateCurrent">下周计划生成后，周一自动生效</span>
          <span>同一周期重复生成会归档旧版本</span>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.plan-empty__inner {
  padding: 48px 24px 40px;
}

.plan-empty__notes {
  display: flex;
  justify-content: center;
  gap: 16px;
  flex-wrap: wrap;
  margin-top: 4px;
  font-family: var(--font-mono);
  font-size: 10px;
  color: var(--ink-4);
}
</style>
