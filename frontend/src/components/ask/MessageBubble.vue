<script setup lang="ts">
/**
 * 问答消息气泡（P9，design.md 2.6.5 / spec 5.3.1 R3 口径）。
 *
 * 用户/助手双形态；助手气泡按 **intent × is_grounded 双信号联合
 * 权威驱动**（裁定①两条规则逐字）：
 * - `intent === 'knowledge' && is_grounded === false` → 无据警示
 *   变体（灰底 + warning 边框 + 顶部常驻警示条「未引用知识库 ·
 *   基于通用知识回答」，不可关闭）——检索了但没找到；
 * - `intent === 'chat'` → 正常回答，**不显示任何警示**（正常聊天，
 *   根本没检索）；
 * - 有据 → 常规白底 + 底部来源卡片组。
 *
 * 仅 is_grounded 不足以区分「没检索（chat）」与「检索无果
 * （knowledge 无据）」两种 false 场景——intent 是必要第二信号
 * （阈值判定在服务端，前端不可见，裁决 #8）。信号来源：实时流取
 * done.data（服务端权威），历史还原取 ChatHistoryItem 同源字段。
 *
 * 流中断（无 done，双信号为 null）→ 常规样式 + 错误提示（权威信号
 * 缺失宁可不标注）。mode === 'offline' → 气泡内常驻离线警示条
 * （文案与 SearchPanel 逐字一致），与无据警示并存时先 mode 后
 * is_grounded 上下排布。
 */
import { computed } from 'vue'

import SourceCard from '@/components/ask/SourceCard.vue'
import type { AskMessage, QaSourceItem } from '@/types'

const props = defineProps<{
  /** 单条消息（用户消息仅用 role/content）。 */
  message: AskMessage
}>()

const emit = defineEmits<{
  (e: 'navigate', source: QaSourceItem): void
}>()

/** 无据警示变体：仅 intent=knowledge 且 is_grounded=false（裁定①）。 */
const isUngrounded = computed(
  () =>
    props.message.role === 'assistant' &&
    props.message.intent === 'knowledge' &&
    props.message.is_grounded === false,
)

/** 常规聊天（chat 恒不警示）。 */
const isChat = computed(
  () => props.message.role === 'assistant' && props.message.intent === 'chat',
)

/** 离线检索警示（mode 权威信号，与 SearchPanel 文案逐字一致）。 */
const isOffline = computed(() => props.message.mode === 'offline')

/** 气泡形态 class（三种变体肉眼可辨，D3 验收）。 */
const bubbleClass = computed(() => ({
  user: props.message.role === 'user',
  assistant: props.message.role === 'assistant',
  ungrounded: isUngrounded.value,
  chat: isChat.value,
}))
</script>

<template>
  <div class="bubble-row" :class="{ mine: props.message.role === 'user' }">
    <div class="bubble" :class="bubbleClass">
      <!-- 助手气泡顶部：离线警示（先 mode 后 is_grounded） -->
      <el-alert
        v-if="isOffline && props.message.role === 'assistant'"
        type="warning"
        :closable="false"
        show-icon
        class="inline-alert"
        title="当前为离线检索模式"
      />
      <el-alert
        v-if="isUngrounded"
        type="warning"
        :closable="false"
        show-icon
        class="inline-alert"
        title="未引用知识库 · 基于通用知识回答"
      />

      <div class="content">
        {{ props.message.content }}<span v-if="props.message.streaming" class="cursor" />
      </div>

      <!-- 流中断（无 done）：错误提示，已生成内容保留 -->
      <el-alert
        v-if="props.message.error"
        type="error"
        :closable="false"
        show-icon
        class="inline-alert"
        :title="props.message.error"
      />

      <!-- 参考来源折叠卡组（有据专属；先于回答完成渲染） -->
      <div v-if="props.message.sources.length" class="sources">
        <div class="sources-title">参考来源（点击可跳转知识库原文）</div>
        <SourceCard
          v-for="(source, idx) in props.message.sources"
          :key="idx"
          :source="source"
          :index="idx + 1"
          @navigate="(s) => emit('navigate', s)"
        />
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
  white-space: pre-wrap;
  word-break: break-word;
}
/* 用户气泡：主色底右对齐 */
.bubble.user {
  background: var(--el-color-primary);
  color: #ffffff;
  border-bottom-right-radius: 2px;
}
/* 助手气泡常规（有据）：白底 */
.bubble.assistant {
  background: #ffffff;
  border: 1px solid var(--el-border-color-lighter);
  border-bottom-left-radius: 2px;
}
/* 无据警示变体：灰底 + warning 边框（与常规肉眼可辨） */
.bubble.assistant.ungrounded {
  background: var(--el-fill-color-light);
  border: 1px solid var(--el-color-warning-light-5);
}
/* chat 气泡：常规白底（无来源卡组，恒不警示） */
.bubble.assistant.chat {
  background: #ffffff;
}
.inline-alert {
  margin-bottom: 10px;
}
.content {
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
.sources {
  margin-top: 12px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.sources-title {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
</style>