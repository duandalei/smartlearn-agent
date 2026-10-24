<script setup lang="ts">
/**
 * 未排入任务提示卡（P13；design 2.4.4；spec §5.1.1 规则 8，裁定 #5）。
 *
 * 纯展示组件（el-alert warning，不阻断）：逐条 title + 后端中文 reason。
 * 组件内不判空占位——tasks.length === 0 时由父层不挂载（规则 8b
 * 「页面无该卡片占位」）；adjust 流程响应无此字段，父层不触碰（决策 D8）。
 */
import type { UnplacedTask } from '@/types/plan'

defineProps<{
  tasks: UnplacedTask[]
}>()
</script>

<template>
  <el-alert type="warning" :closable="false" class="unplaced-card">
    <template #title>容量不足，未排入的任务</template>
    <ul class="task-list">
      <li v-for="(t, i) in tasks" :key="t.task_id ?? i">
        <span class="task-title">{{ t.title }}</span>
        <span class="task-reason">{{ t.reason }}</span>
      </li>
    </ul>
    <p class="hint">这些任务已保存在任务列表，可前往任务页手动安排</p>
  </el-alert>
</template>

<style scoped>
.unplaced-card {
  margin-top: 12px;
}
.task-list {
  margin: 8px 0 0;
  padding-left: 18px;
}
.task-list li {
  line-height: 1.8;
}
.task-title {
  color: var(--el-text-color-primary);
  margin-right: 8px;
}
.task-reason {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
.hint {
  margin: 8px 0 0;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
</style>