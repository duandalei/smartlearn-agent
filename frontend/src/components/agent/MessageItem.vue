<script setup lang="ts">
/**
 * Agent 消息渲染单元（P11 前端，design 2.2.2-(4) / 2.4.4-E）。
 *
 * user 分支：主色右对齐气泡（视觉规格复刻 P9 MessageBubble 模式）。
 * assistant 分支：segments 按 kind 三分支**保序渲染**（决策 A2——
 * v-for 天然保序，不排序不重排不合并段，「工作轨迹」的渲染保证）；
 * 块末固定区（非 segment）：收尾提示 → 统计小字（O8 恒显、无
 * badge）→ 错误行（el-alert error）→ 已停止标记（轻量非错误）。
 *
 * thinking 行（O6）：文字行 + 行内小 spinner；done=true 弱化保留
 * （决策 A11——不删除，保留轨迹可读性）；禁止任何 overlay（spec
 * §5.5.1 规则 3——组件内零 v-loading）。
 */
import { computed } from 'vue'
import { InfoFilled, VideoPause } from '@element-plus/icons-vue'

import ToolCallCard from '@/components/agent/ToolCallCard.vue'
import type { AgentFinishReason, ViewMessage } from '@/types/agent'

/** finish_reason 三态收尾文案（spec §7.4 规则 3——渲染宿主即单一来源；normal 静默）。 */
const FINISH_HINTS: Record<AgentFinishReason, string> = {
  normal: '',
  max_rounds: '信息较多，已为你总结',
  timeout: '处理时间较长，以下是已获取的部分',
}

/** thinking 行文案（spec §7.4 规则 4——固定常量 + 轮次后缀拼接）。 */
const THINKING_TEXT = '思考中'

/** 已停止标记文案（spec §5.3.1 规则 11——轻量标记非错误样式）。 */
const STOPPED_TEXT = '已停止生成'

const props = defineProps<{
  /** 视图消息（user 气泡 / assistant segments 块）。 */
  message: ViewMessage
}>()

const emit = defineEmits<{
  (e: 'card-toggle', callId: string, expanded: boolean): void
}>()

/** assistant 分支窄化（模板类型收窄辅助）。 */
const assistant = computed(() =>
  props.message.kind === 'assistant' ? props.message : null,
)

/** 最后一个 text 段下标（流式光标只挂最新文本段尾部）。 */
const lastTextIdx = computed((): number => {
  const block = assistant.value
  if (!block) return -1
  let idx = -1
  block.segments.forEach((segment, i) => {
    if (segment.kind === 'text') idx = i
  })
  return idx
})

/** 收尾提示文案（normal 静默；max_rounds/timeout 差异化——spec §7.4 规则 3）。 */
const finishHint = computed((): string => {
  const finish = assistant.value?.finish
  if (!finish) return ''
  return FINISH_HINTS[finish.finish_reason]
})

/** O8 统计小字：「N 轮 · M 次工具调用」（小号灰字、无 badge、恒显）。 */
const statsText = computed((): string => {
  const finish = assistant.value?.finish
  if (!finish) return ''
  return `${finish.rounds} 轮 · ${finish.tool_call_count} 次工具调用`
})

/** thinking 段文案（THINKING_TEXT 常量 + 轮次后缀）。 */
function thinkingLabel(round: number | null): string {
  return round == null ? THINKING_TEXT : `${THINKING_TEXT}（第 ${round} 轮）`
}
</script>

<template>
  <!-- 用户气泡：主色右对齐 -->
  <div v-if="props.message.kind === 'user'" class="bubble-row mine">
    <div class="bubble user">{{ props.message.content }}</div>
  </div>

  <!-- assistant 块：segments 保序渲染 + 块末固定区 -->
  <div v-else-if="assistant" class="bubble-row">
    <div class="bubble assistant">
      <template v-for="(segment, idx) in assistant.segments" :key="idx">
        <!-- thinking 轮次信号行（轻量；done 弱化保留） -->
        <div v-if="segment.kind === 'thinking'" class="thinking-row" :class="{ done: segment.done }">
          <el-icon v-if="!segment.done" class="is-loading spin" :size="12" />
          <span>{{ thinkingLabel(segment.round) }}</span>
          <span v-if="segment.content" class="thinking-content">{{ segment.content }}</span>
        </div>
        <!-- 工具调用卡片（工作轨迹） -->
        <ToolCallCard
          v-else-if="segment.kind === 'tool'"
          :call="segment.call"
          class="tool-segment"
          @toggle="(id, ex) => emit('card-toggle', id, ex)"
        />
        <!-- 文本段（中间轮解释与最终回答分属不同段） -->
        <div v-else class="content">
          {{ segment.content }}<span
            v-if="assistant.streaming && idx === lastTextIdx"
            class="cursor"
          />
        </div>
      </template>

      <!-- 块末固定区：收尾提示 → 统计小字 → 错误行 / 已停止 -->
      <div v-if="finishHint" class="finish-hint">
        <el-icon :size="14"><InfoFilled /></el-icon>
        <span>{{ finishHint }}</span>
      </div>
      <div v-if="statsText" class="stats-text">{{ statsText }}</div>
      <el-alert
        v-if="assistant.error"
        type="error"
        :closable="false"
        show-icon
        class="inline-alert"
        :title="assistant.error"
      />
      <div v-if="assistant.stopped" class="stopped-mark">
        <el-icon :size="12"><VideoPause /></el-icon>
        <span>{{ STOPPED_TEXT }}</span>
      </div>
    </div>
  </div>
</template>

<style scoped>
.bubble-row {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
}
.bubble-row.mine {
  align-items: flex-end;
}
.bubble {
  max-width: 86%;
  border-radius: 8px;
  padding: 12px 14px;
  font-size: 14px;
  line-height: 1.8;
  word-break: break-word;
}
.bubble.user {
  background: var(--el-color-primary);
  color: #ffffff;
  border-bottom-right-radius: 2px;
  white-space: pre-wrap;
}
.bubble.assistant {
  background: #ffffff;
  border: 1px solid var(--el-border-color-lighter);
  border-bottom-left-radius: 2px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}
/* thinking 轻量行：小字号浅灰单行（O6——禁遮罩禁大面积 loading） */
.thinking-row {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
.thinking-row.done {
  color: var(--el-text-color-placeholder);
}
.thinking-row .spin {
  color: var(--el-text-color-secondary);
}
.thinking-content {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  max-width: 70%;
  font-size: 12px;
  color: var(--el-text-color-placeholder);
}
/* 工具卡片段间距（堆叠 gap 6px——4 连卡片 162px 计算的分母） */
.tool-segment {
  margin: 0;
}
.tool-segment + .tool-segment {
  margin-top: 6px;
}
.content {
  white-space: pre-wrap;
  min-height: 22px;
}
.cursor {
  display: inline-block;
  width: 2px;
  height: 16px;
  margin-left: 2px;
  background: var(--el-color-primary);
  animation: blink 0.9s infinite;
  vertical-align: middle;
}
@keyframes blink {
  0%,
  100% {
    opacity: 1;
  }
  50% {
    opacity: 0;
  }
}
/* 收尾提示：轻量信息条（非弹窗非错误红） */
.finish-hint {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
/* O8 统计小字：小号灰字、无 badge 无底色（弱化——不像调试信息） */
.stats-text {
  font-size: 12px;
  color: var(--el-text-color-placeholder);
}
.inline-alert {
  margin: 0;
}
/* 已停止标记：轻量非错误样式 */
.stopped-mark {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
</style>