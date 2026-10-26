<script setup lang="ts">
import type { RiskAlert } from '@/types'

defineProps<{
  alert: RiskAlert | null
  loading: boolean
  error: boolean
  reload: () => void
}>()
</script>

<template>
  <section class="panel risk-card">
    <div class="panel__head">
      <div>
        <div class="panel__title">学习风险</div>
        <div class="panel__sub">最近七天的节奏信号</div>
      </div>
      <span class="seal seal--sm seal--ghost" aria-hidden="true">警</span>
    </div>

    <div class="panel__body risk-body">
      <el-skeleton v-if="loading" :rows="3" animated />

      <div v-else-if="error" class="block-error" @click="reload">
        数据加载失败，点击重试
      </div>

      <div v-else-if="alert != null" class="risk-note">
        <div class="risk-note__label">需要留意</div>
        <div class="risk-note__title">{{ alert.title }}</div>
        <p class="risk-note__message">{{ alert.message }}</p>
        <div class="risk-note__suggestion">
          <span class="risk-note__tag">建议</span>
          <span>{{ alert.suggestion }}</span>
        </div>
      </div>

      <div v-else class="risk-clear">
        <span class="risk-clear__dot" aria-hidden="true" />
        <div>
          <div class="risk-clear__title">没有明显风险信号</div>
          <div class="risk-clear__sub">最近的学习节奏保持得不错。</div>
        </div>
      </div>
    </div>
  </section>
</template>

<style scoped>
.risk-card {
  height: 100%;
  display: flex;
  flex-direction: column;
}

.risk-body {
  flex: 1 1 auto;
}

.risk-note {
  padding: 16px;
  background: var(--ochre-wash);
  border: 1px solid #ddc79b;
  border-radius: var(--radius);
}

.risk-note__label {
  font-family: var(--font-mono);
  font-size: 9px;
  letter-spacing: 0.14em;
  color: #8a6425;
}

.risk-note__title {
  margin-top: 6px;
  font-family: var(--font-display);
  font-size: 18px;
  font-weight: 600;
  line-height: 1.45;
  color: #4d3a16;
}

.risk-note__message {
  margin-top: 8px;
  font-size: 13px;
  line-height: 1.7;
  color: #5f4a22;
}

.risk-note__suggestion {
  display: flex;
  gap: 8px;
  margin-top: 12px;
  padding-top: 10px;
  border-top: 1px dashed #d8bf8d;
  font-size: 12px;
  line-height: 1.7;
  color: #5f4a22;
}

.risk-note__tag {
  flex: 0 0 auto;
  font-weight: 600;
  color: #7a5318;
}

.risk-clear {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  padding: 14px 16px;
  background: var(--jade-wash);
  border: 1px solid #b3c9b9;
  border-radius: var(--radius);
}

.risk-clear__dot {
  width: 7px;
  height: 7px;
  margin-top: 6px;
  flex: 0 0 7px;
  border-radius: 50%;
  background: var(--jade);
}

.risk-clear__title {
  font-size: 14px;
  font-weight: 600;
  color: #33513e;
}

.risk-clear__sub {
  margin-top: 3px;
  font-size: 12px;
  line-height: 1.6;
  color: #4a6a54;
}
</style>
