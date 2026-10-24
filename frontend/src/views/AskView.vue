<script setup lang="ts">
/**
 * AI 学习问答页（P9，design.md 2.6.1 / 2.6.6；路由 /ask）。
 *
 * 对话式界面：流式逐字渲染（fetch + ReadableStream 解析 SSE，禁
 * EventSource）；三档检索范围切换；回答下方参考来源折叠卡（点击
 * 跳 /knowledge-base 定位对应分块）；无据回答差异化警示样式（双
 * 信号 intent × is_grounded 由 done 事件服务端权威下发）。
 *
 * 历史回放（D6）：onMounted 拉第 1 页历史（created_at 倒序），
 * reverse 后按时间正序还原对话流——**intent 落库是回放样式一致性
 * 的前提**（chat 与 knowledge 无据字段同构，不落库则无法区分），
 * 历史接口失败仅弹错、保留空对话区可正常提问（spec 5.5.3 场景 2）。
 */
import { nextTick, onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'

import AskComposer from '@/components/ask/AskComposer.vue'
import MessageBubble from '@/components/ask/MessageBubble.vue'
import { getChatHistory, streamChatQa } from '@/api/chat'
import type { AskMessage, ChatHistoryItem, QaSourceItem } from '@/types'

const router = useRouter()

/** 历史每页条数。 */
const HISTORY_PAGE_SIZE = 10

const messages = ref<AskMessage[]>([])
const streaming = ref(false)

/** 历史分页状态（「加载更早的问答」）。 */
const historyTotal = ref(0)
const historyPage = ref(1)
const historyLoading = ref(false)
/** 是否还有更早的历史可加载。 */
const hasEarlier = ref(false)

/** 对话流滚动容器。 */
const scroller = ref<HTMLElement | null>(null)

/** 滚动跟随最新消息。 */
async function scrollToBottom(): Promise<void> {
  await nextTick()
  if (scroller.value) {
    scroller.value.scrollTop = scroller.value.scrollHeight
  }
}

/** 占位助手消息（流式渲染目标，push 后持有同一引用原地更新）。 */
function placeholderAssistant(): AskMessage {
  return {
    role: 'assistant',
    content: '',
    sources: [],
    is_grounded: null,
    intent: null,
    mode: null,
    streaming: true,
    error: null,
  }
}

/** 提交提问：SSE 四回调分发响应式更新。 */
async function onAsk(question: string): Promise<void> {
  if (streaming.value) return
  streaming.value = true
  messages.value.push({
    role: 'user',
    content: question,
    sources: [],
    is_grounded: null,
    intent: null,
    mode: null,
    streaming: false,
    error: null,
  })
  // 必须包一层 reactive：下面各回调直接改的是这个局部变量，
  // 若是原始对象则绕过 Vue 的响应式代理，逐片 delta 不会触发重渲染，
  // 界面要等到 finally 里 streaming=false 才整体刷新一次（表现为「不流式」）。
  const assistant = reactive<AskMessage>(placeholderAssistant())
  messages.value.push(assistant)
  void scrollToBottom()

  try {
    await streamChatQa(
      { question },
      {
        // sources 即时写入（卡片先于回答完成出现，spec 5.4.1 规则 1）。
        onSources: (event) => {
          assistant.sources = event.data
          void scrollToBottom()
        },
        // delta 逐字追加（流式渲染）。
        onDelta: (text) => {
          assistant.content += text
          void scrollToBottom()
        },
        // done 定值双信号（服务端权威，阈值判定在前端不可见）；
        // history_id=null 时本页无「已保存」状态可显示（自然满足）。
        onDone: (data) => {
          assistant.is_grounded = data.is_grounded
          assistant.intent = data.intent
          assistant.mode = data.mode
        },
        // error：保留已生成内容不清空（spec 4.2 规则 5）。
        onError: (data) => {
          assistant.error = data.message
        },
      },
    )
  } finally {
    assistant.streaming = false
    streaming.value = false
    void scrollToBottom()
  }
}

/** 历史条目 → 一对消息（用户气泡 + 助手气泡，双信号样式回放）。 */
function historyToMessages(item: ChatHistoryItem): AskMessage[] {
  return [
    {
      role: 'user',
      content: item.question,
      sources: [],
      is_grounded: null,
      intent: null,
      mode: null,
      streaming: false,
      error: null,
    },
    {
      role: 'assistant',
      content: item.answer,
      sources: item.sources,
      is_grounded: item.is_grounded,
      intent: item.intent,
      mode: item.mode,
      streaming: false,
      error: null,
    },
  ]
}

/** 同步「加载更早」可见性（total 与已加载问答条数比较）。 */
function syncEarlierFlag(): void {
  const loaded = messages.value.filter((m) => m.role === 'user').length
  hasEarlier.value = historyTotal.value > loaded
}

/** 加载历史（倒序页 reverse 后正序还原；「加载更早」prepend 头部）。 */
async function loadHistory(): Promise<void> {
  historyLoading.value = true
  try {
    const data = await getChatHistory(historyPage.value, HISTORY_PAGE_SIZE)
    historyTotal.value = data.total
    // 倒序页 → reverse 后正序；prepend 保证时间正序拼接。
    const restored = data.items.flatMap(historyToMessages)
    messages.value = [...restored.reverse(), ...messages.value]
    syncEarlierFlag()
  } catch {
    // 错误提示由 request.ts 拦截器统一弹出；保留空对话区可正常提问。
  } finally {
    historyLoading.value = false
  }
}

/** 加载更早的问答（page+1 追加更早条目，保持正序拼接）。 */
async function loadEarlier(): Promise<void> {
  if (historyLoading.value) return
  historyPage.value += 1
  await loadHistory()
}

/** 来源卡跳转：/knowledge-base 定位对应文档分块（D2 闭环）。 */
function onNavigate(source: QaSourceItem): void {
  if (source.item_id == null) return
  void router.push({
    path: '/knowledge-base',
    query: {
      item_id: String(source.item_id),
      ...(source.chunk_index != null ? { chunk_index: String(source.chunk_index) } : {}),
    },
  })
}

onMounted(() => {
  void loadHistory()
})
</script>

<template>
  <div class="ask-page">
    <div class="ask-header">
      <h2 class="page-title">AI 学习问答</h2>
      <span class="page-sub">基于你的知识库回答并引用来源；无相关内容时明确告知，不会编造</span>
    </div>

    <el-card shadow="never" class="chat-card" :body-style="{ padding: '0' }">
      <div ref="scroller" class="chat-scroll">
        <div v-if="hasEarlier" class="earlier-row">
          <el-button
            size="small"
            :loading="historyLoading"
            @click="loadEarlier"
          >
            加载更早的问答
          </el-button>
        </div>

        <el-empty
          v-if="!messages.length && !historyLoading"
          description="暂无问答记录，开始提问吧"
          :image-size="90"
          class="chat-empty"
        />

        <div class="message-list">
          <MessageBubble
            v-for="(message, idx) in messages"
            :key="idx"
            :message="message"
            @navigate="onNavigate"
          />
        </div>
      </div>

      <div class="composer-area">
        <AskComposer :disabled="streaming" @ask="onAsk" />
      </div>
    </el-card>
  </div>
</template>

<style scoped>
.ask-page {
  height: 100%;
  min-height: 0;
  display: flex;
  flex-direction: column;
  gap: 12px;
  /* 页面自身不滚动：滚动只发生在 .chat-scroll 内部，
     否则会出现 el-main 与消息区两条竖向滚动条。 */
  overflow: hidden;
}
.ask-header {
  display: flex;
  align-items: baseline;
  gap: 12px;
}
.page-title {
  margin: 0;
  font-size: 20px;
}
.page-sub {
  font-size: 13px;
  color: var(--el-text-color-secondary);
}
.chat-card {
  flex: 1 1 auto;
  min-height: 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}
/* el-card 的 body 需要成为纵向 flex 容器，消息区才能靠 flex 分配剩余高度；
   用 height:100% + overflow 会导致消息区与输入区总高超出卡片、产生第二条滚动条。 */
.chat-card :deep(.el-card__body) {
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 0;
  overflow: hidden;
}
.chat-scroll {
  flex: 1 1 auto;
  min-height: 0;
  overflow-y: auto;
  padding: 16px;
}
.earlier-row {
  display: flex;
  justify-content: center;
  margin-bottom: 12px;
}
.chat-empty {
  margin-top: 60px;
}
.message-list {
  display: flex;
  flex-direction: column;
  gap: 16px;
}
.composer-area {
  flex: 0 0 auto;
  border-top: 1px solid var(--el-border-color-lighter);
  padding: 12px 16px;
  background: #ffffff;
}
</style>