<script setup lang="ts">
/**
 * Agent 输入区（P11 前端，design 2.2.2-(6)）。
 *
 * el-input textarea（maxlength 2000 硬限 + show-word-limit 计数 +
 * Enter 发送 / Shift+Enter 换行）；**发送⇄停止原位切换**（O5——
 * 同一按钮，生成中变「停止生成」danger 态，位置固定于 composer
 * 区不随内容滚动移动，生成期间始终可见可点）；生成中 textarea
 * 保持可输入（预输入下一问，spec §5.3.1 规则 12），仅发送动作被
 * 停止替代。
 *
 * MESSAGE_MAX_LEN 与 AgentView.vue 同值常量（O6 裁定——与后端
 * O6 的 2000 同值同义，前端独立常量各自定义互相指认，对齐后端
 * A8「schema 与 core 各自定义」模式）。
 */
import { ref } from 'vue'
import { ElMessage } from 'element-plus'

/** 用户消息长度上限（spec §7.1 规则 1——与 AgentView 同值指认）。 */
const MESSAGE_MAX_LEN = 2000

const props = defineProps<{
  /** 流式生成中（true 时发送按钮原位切换为停止）。 */
  streaming: boolean
}>()

const emit = defineEmits<{
  (e: 'send', message: string): void
  (e: 'stop'): void
}>()

const draft = ref('')

/** 提交（Enter 触发；Shift+Enter 组合自然换行——exact 修饰符）。 */
function submit(): void {
  const message = draft.value.trim()
  if (props.streaming) return
  if (!message) {
    ElMessage.warning('请输入消息')
    return
  }
  emit('send', message)
  draft.value = ''
}

/** 停止生成（O5：按钮原位切换的第二形态）。 */
function stop(): void {
  if (!props.streaming) return
  emit('stop')
}
</script>

<template>
  <div class="composer">
    <el-input
      v-model="draft"
      type="textarea"
      :autosize="{ minRows: 2, maxRows: 5 }"
      :maxlength="MESSAGE_MAX_LEN"
      show-word-limit
      placeholder="问点什么，或让我分析最近的学习记录。"
      @keydown.enter.exact.prevent="submit"
    />
    <div class="action-row">
      <span class="composer-hint">Enter 发送 · Shift+Enter 换行</span>
      <span class="spacer" />
      <el-button
        v-if="!props.streaming"
        type="primary"
        :disabled="!draft.trim()"
        @click="submit"
      >
        发送
      </el-button>
      <el-button v-else type="danger" class="stop-btn" @click="stop">
        停止生成
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

.action-row {
  display: flex;
  align-items: center;
  gap: 10px;
}

.composer-hint {
  font-family: var(--font-mono);
  font-size: 9px;
  letter-spacing: 0.04em;
  color: var(--ink-4);
}
</style>