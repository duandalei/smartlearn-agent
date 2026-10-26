<script setup lang="ts">
/**
 * 未排入任务提示：容量不足时逐条说明原因，不阻断页面。
 */
import type { UnplacedTask } from '@/types/plan'

defineProps<{
  tasks: UnplacedTask[]
}>()
</script>

<template>
  <section class="unplaced">
    <div class="unplaced__head">
      <span class="unplaced__mark" aria-hidden="true" />
      <span class="unplaced__title">容量不足，未排入的任务</span>
    </div>
    <ul class="task-list">
      <li v-for="(t, i) in tasks" :key="t.task_id ?? i">
        <span class="task-title">{{ t.title }}</span>
        <span class="task-reason">{{ t.reason }}</span>
      </li>
    </ul>
    <p class="hint">这些任务已保存在任务列表，可前往任务页手动安排。</p>
  </section>
</template>

<style scoped>
.unplaced {
  padding: 16px;
  background: var(--ochre-wash);
  border: 1px solid #ddc79b;
  border-radius: var(--radius);
}

.unplaced__head {
  display: flex;
  align-items: center;
  gap: 8px;
}

.unplaced__mark {
  width: 5px;
  height: 5px;
  background: var(--ochre);
  border-radius: 1px;
}

.unplaced__title {
  font-size: 14px;
  font-weight: 600;
  color: #4d3a16;
}

.task-list {
  margin: 10px 0 0;
  padding: 0 0 0 13px;
}

.task-list li {
  font-size: 12px;
  line-height: 1.8;
  color: #5f4a22;
}

.task-title {
  margin-right: 8px;
  color: #4d3a16;
}

.task-reason {
  color: #7a5a2c;
}

.hint {
  margin: 8px 0 0;
  font-size: 11px;
  line-height: 1.6;
  color: #7a5a2c;
}
</style>
