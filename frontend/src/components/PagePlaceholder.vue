<script setup lang="ts">
/**
 * 通用占位页组件。
 *
 * 骨架阶段用于所有未实现业务逻辑的页面，展示标题与说明，
 * 保证路由跳转可见且不报错。后续各页面实现后逐个替换。
 */
import { computed } from 'vue'
import { useRoute } from 'vue-router'

interface Props {
  /** 页面标题 */
  title?: string
  /** 页面说明 */
  description?: string
}

const props = withDefaults(defineProps<Props>(), {
  title: '',
  description: '该功能模块将在后续阶段实现。',
})

const route = useRoute()
const pageTitle = computed(() => props.title || (route.meta.title as string) || '页面')
</script>

<template>
  <el-card class="placeholder-card" shadow="never">
    <template #header>
      <span class="placeholder-title">{{ pageTitle }}</span>
    </template>
    <el-empty :description="description" />
  </el-card>
</template>

<style scoped>
.placeholder-card {
  min-height: 320px;
}
.placeholder-title {
  font-size: 16px;
  font-weight: 600;
}
</style>