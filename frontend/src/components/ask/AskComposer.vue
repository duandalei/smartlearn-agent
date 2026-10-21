<script setup lang="ts">
/**
 * 问答输入区（P9，design.md 2.6.3 / spec 5.2.1）。
 *
 * el-input（maxlength 500、回车提交、提交前 trim 判空——空问题
 * 点击给输入提示不发请求）+ 三档 el-radio-group（button 形态紧凑
 * 且不可输入非法值）+ 提交按钮（streaming 期间禁用，同一时刻至多
 * 一个活跃流，防并发流串扰）。
 *
 * 档位即时生效：scope 随每次提问请求体提交，切换后下一次提问
 * 立即按新档检索、无需刷新（spec 5.2.1 规则 4）。
 */
import { ref } from 'vue'
import { ElMessage } from 'element-plus'

import type { QaScope } from '@/types'

const props = defineProps<{
  /** 检索范围三档（v-model，由 AskView 持有）。 */
  modelValue: QaScope
  /** 流式进行中（禁用提交防并发流）。 */
  disabled: boolean
}>()

const emit = defineEmits<{
  (e: 'update:modelValue', value: QaScope): void
  (e: 'ask', question: string): void
}>()

const question = ref('')

function onScopeChange(value: QaScope): void {
  emit('update:modelValue', value)
}

function submit(): void {
  const q = question.value.trim()
  if (!q) {
    ElMessage.warning('请输入问题')
    return
  }
  if (props.disabled) return
  emit('ask', q)
  question.value = ''
}
</script>

<template>
  <div class="composer">
    <div class="scope-row">
      <span class="scope-label">检索范围</span>
      <el-radio-group
        :model-value="props.modelValue"
        size="small"
        :disabled="props.disabled"
        @update:model-value="onScopeChange"
      >
        <el-radio-button value="all">两者结合</el-radio-button>
        <el-radio-button value="personal">仅个人库</el-radio-button>
        <el-radio-button value="public">仅公共库</el-radio-button>
      </el-radio-group>
    </div>
    <div class="input-row">
      <el-input
        v-model="question"
        placeholder="输入学习问题，如：什么是 Transformer？回答将引用你的知识库来源"
        maxlength="500"
        :disabled="props.disabled"
        @keyup.enter="submit"
      />
      <el-button
        type="primary"
        :loading="props.disabled"
        @click="submit"
      >
        提问
      </el-button>
    </div>
  </div>
</template>

<style scoped>
.composer {
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.scope-row {
  display: flex;
  align-items: center;
  gap: 10px;
}
.scope-label {
  font-size: 13px;
  color: var(--el-text-color-secondary);
}
.input-row {
  display: flex;
  gap: 12px;
}
.input-row .el-input {
  flex: 1 1 auto;
}
</style>