<script setup lang="ts">
/**
 * 计划空态引导（P13；design 2.4.4；spec §5.1.3-1、§5.2.1 规则 2/4，裁定 #3）。
 *
 * 文案红线：按钮与说明如实写「下一周」，禁止任何暗示生成「本周」计划的措辞。
 */
defineProps<{
  loading: boolean
}>()

const emit = defineEmits<{
  (e: 'generate'): void
}>()
</script>

<template>
  <div class="plan-empty">
    <el-empty description="还没有进行中的学习计划">
      <p class="desc">为下一个完整自然周（周一开始）生成学习计划</p>
      <el-button type="primary" :loading="loading" @click="emit('generate')">
        生成下一周学习计划
      </el-button>
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
.sub-desc {
  margin: 12px 0 0;
  font-size: 12px;
  color: var(--el-text-color-placeholder);
}
</style>