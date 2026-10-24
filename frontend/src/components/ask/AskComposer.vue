<script setup lang="ts">
/**
 * 问答输入区（P9，design.md 2.6.3 / spec 5.2.1）。
 *
 * el-input（maxlength 500、回车提交、提交前 trim 判空——空问题
 * 点击给输入提示不发请求）+ 提交按钮（streaming 期间禁用，同一时刻
 * 至多一个活跃流，防并发流串扰）。
 *
 * 公共库已移除：检索范围固定为当前用户个人库，不再提供档位选择。
 */
import { ref } from 'vue'
import { ElMessage } from 'element-plus'

const props = defineProps<{
  /** 流式进行中（禁用提交防并发流）。 */
  disabled: boolean
}>()

const emit = defineEmits<{
  (e: 'ask', question: string): void
}>()

const question = ref('')

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
.input-row {
  display: flex;
  gap: 12px;
}
.input-row .el-input {
  flex: 1 1 auto;
}
</style>