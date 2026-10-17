<script setup lang="ts">
/**
 * 学习中心（Dashboard）页面 —— 骨架占位。
 *
 * 后续接入：统计卡片、趋势图、掌握度、AI 建议、本周计划摘要卡片。
 * 当前仅提供「后端连通性自检」按钮，用于验证 Axios 封装与统一错误提示。
 */
import { ref } from 'vue'
import { ElMessage } from 'element-plus'

import PagePlaceholder from '@/components/PagePlaceholder.vue'
import { healthCheck } from '@/api/health'

const checking = ref(false)

/** 触发一次后端健康检查，验证请求链路与拦截器。 */
async function handleCheckBackend(): Promise<void> {
  checking.value = true
  try {
    const data = await healthCheck()
    ElMessage.success(`后端连通正常：${data.status}`)
  } catch {
    // 错误提示已由响应拦截器统一处理，此处无需重复提示
  } finally {
    checking.value = false
  }
}
</script>

<template>
  <el-space direction="vertical" alignment="stretch" :size="16" style="width: 100%">
    <el-card shadow="never">
      <el-space>
        <el-button type="primary" :loading="checking" @click="handleCheckBackend">
          检测后端连通性
        </el-button>
        <span style="color: #909399; font-size: 13px">
          调用 GET /health，验证请求封装与统一错误提示是否生效
        </span>
      </el-space>
    </el-card>

    <PagePlaceholder
      title="学习中心"
      description="统计卡片 / 学习趋势 / 知识掌握度 / AI 建议 / 本周计划摘要 —— 待实现"
    />
  </el-space>
</template>