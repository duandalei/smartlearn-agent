<script setup lang="ts">
/**
 * AI Agent 对话页（P11 前端，design 2.1.3 / 2.4.3 / 2.4.4；路由 /ai-agent）。
 *
 * 视图状态编排唯一宿主：双栏布局（左会话列表 / 右对话区）+ SSE 六
 * 事件回调分发到响应式树 + 停止链路（R3 硬约束——置位先于 abort）+
 * 竞态防护（O5 短路 + loadSeq 守卫）+ 历史回放还原（buildViewMessages
 * ——用户设计重点 ②）+ 快捷问题空态（O2/O3）。
 *
 * 路由与 MainLayout 零改动（O7——router/index.ts:73-78 既有注册）。
 * 布局复刻 P9「页面不滚动、消息区内部滚动」三件套约束。
 */
import { nextTick, onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { useRouter } from 'vue-router'

import AgentComposer from '@/components/agent/AgentComposer.vue'
import ConversationList from '@/components/agent/ConversationList.vue'
import MessageItem from '@/components/agent/MessageItem.vue'
import {
  createAgentConversation,
  deleteAgentConversation,
  getAgentConversationMessages,
  getAgentConversations,
  renameAgentConversation,
  streamAgentChat,
} from '@/api/agent'
import type { QaSourceItem } from '@/types'
import type {
  AgentConversation,
  AgentMessage,
  AssistantSegment,
  AssistantViewMessage,
  ToolCallView,
  ViewMessage,
} from '@/types/agent'

// ---------------------------------------------------------------------------
// 常量表（design 2.1.2-B——锁定值 + 来源注释；渲染宿主类文案常量
// FINISH_HINTS / THINKING_TEXT / STOPPED_TEXT 定义于 MessageItem.vue
// 渲染宿主单一来源，见交付说明编排裁定）
// ---------------------------------------------------------------------------
/** 用户消息长度上限（spec §7.1 规则 1——与后端 O6 的 2000 同值同义）。 */
const MESSAGE_MAX_LEN = 2000

/** 会话列表首屏单页条数（spec 冲突裁决 #3——后端上限 100 内取 50）。 */
const CONVERSATION_PAGE_SIZE = 50

/** 快捷问题四项（O3 用户指定清单——四类演示场景）。 */
const QUICK_QUESTIONS: string[] = [
  '我最近学习怎么样',
  '我哪些知识点最薄弱',
  '我还有哪些任务没做完',
  '帮我制定下周学习计划',
]

/** 生成中列表操作拦截提示（O5 裁定——禁静默无响应）。 */
const GENERATING_BLOCK_HINT = '请先停止当前生成'

/** 列表超出首屏时底部提示（O4——不做加载更多）。 */
const LIST_TOTAL_HINT = `仅显示最近 ${CONVERSATION_PAGE_SIZE} 条会话`

/** 来源条数上限（与后端 core.py SOURCES_MAX_COUNT 同名同值——L2）。 */
const SOURCES_MAX_COUNT = 20

/** 来源单条片段截断长度（与后端 SOURCE_CONTENT_MAX_LEN 同名同值）。 */
const SOURCE_CONTENT_MAX_LEN = 240

/** 空态知识库轻提示（spec §5.2.1-6——L2 agent_absorb_ask）。 */
const KNOWLEDGE_HINT =
  '可以直接问知识库——我会自动检索你的笔记和公共资料，并在回答下方标注来源'

// ---------------------------------------------------------------------------
// 来源规范化与块级合并（L2 agent_absorb_ask，design 2.1.3-C）
// 实时 SSE（已截断）与历史回放（完整 JSON）两路径共用 normalizeSources
// 单一口径——再过一遍是幂等，保证实时/历史一致（spec §4.2 规则 2）。
// ---------------------------------------------------------------------------
/** 来源去重键（'x' 占位区分 null 与数值 0——脏防御）。 */
function sourceDedupKey(s: QaSourceItem): string {
  return `${s.item_id ?? 'x'}:${s.chunk_index ?? 'x'}`
}

/**
 * 单一口径规范化（纯函数零副作用）：六字段白名单——content/title 缺失
 * 整条丢弃、存在则强制 String()；scope 仅认 personal/public；score 强制
 * Number()（NaN 置 0）；item_id/chunk_index 可空但非空须为数（否则置
 * null 降级）；content 截 240；按 (item_id, chunk_index) 去重；≤20；
 * 全坏返回 []。
 */
function normalizeSources(raw: unknown): QaSourceItem[] {
  if (!Array.isArray(raw)) return []
  const seen = new Map<string, QaSourceItem>()
  for (const item of raw) {
    if (typeof item !== 'object' || item === null) continue
    const rec = item as Record<string, unknown>
    if (rec.content == null || rec.source_title == null) continue
    if (rec.scope !== 'personal' && rec.scope !== 'public') continue
    const score = Number(rec.score)
    const normalized: QaSourceItem = {
      source_title: String(rec.source_title),
      content: String(rec.content).slice(0, SOURCE_CONTENT_MAX_LEN),
      score: Number.isNaN(score) ? 0 : score,
      item_id: typeof rec.item_id === 'number' ? rec.item_id : null,
      chunk_index: typeof rec.chunk_index === 'number' ? rec.chunk_index : null,
      scope: rec.scope,
    }
    const key = sourceDedupKey(normalized)
    if (seen.has(key)) continue
    seen.set(key, normalized)
    if (seen.size >= SOURCES_MAX_COUNT) break
  }
  return [...seen.values()]
}

/**
 * 块级保序去重合并：首现位次保留（对齐 SourceCard 编号连续惯例，去重
 * 仅针对多次检索的重复命中——spec §6.3-6）；合并后超 20 截断。
 */
function mergeAssistantSources(
  block: AssistantViewMessage,
  incoming: QaSourceItem[],
): void {
  if (!incoming.length) return
  const seen = new Map<string, QaSourceItem>()
  for (const s of block.sources) seen.set(sourceDedupKey(s), s)
  for (const s of incoming) {
    const key = sourceDedupKey(s)
    if (seen.has(key)) continue
    seen.set(key, s)
    if (seen.size >= SOURCES_MAX_COUNT) break
  }
  block.sources = [...seen.values()]
}

// ---------------------------------------------------------------------------
// 响应式状态域（design 2.4.4-A）
// ---------------------------------------------------------------------------
const messages = ref<ViewMessage[]>([])
const streaming = ref(false)
/** 停止信号句柄（非 ref——无需模板响应）。 */
let abortController: AbortController | null = null

const conversations = ref<AgentConversation[]>([])
const conversationsLoading = ref(false)
const currentConversation = ref<AgentConversation | null>(null)
const messagesLoading = ref(false)
/** 会话消息加载序号守卫（决策 A6——旧响应晚到丢弃）。 */
let loadSeq = 0

/** 滚动跟随开关（autoFollow 滞回——决策 A5）。 */
const autoFollow = ref(true)
const scroller = ref<HTMLElement | null>(null)

/** 路由实例（L2：来源卡跳转 /knowledge-base 使用）。 */
const router = useRouter()

/** 对话流滚动跟随（P9 scrollToBottom 复刻）。 */
async function scrollToBottom(): Promise<void> {
  await nextTick()
  if (scroller.value) {
    scroller.value.scrollTop = scroller.value.scrollHeight
  }
}

/** 滚动监听：上滚 >80px 暂停跟随；回底 <40px 恢复（滞回带防抖动）。 */
function onScroll(): void {
  const el = scroller.value
  if (!el) return
  const distance = el.scrollHeight - el.scrollTop - el.clientHeight
  if (distance > 80) autoFollow.value = false
  else if (distance < 40) autoFollow.value = true
}

// ---------------------------------------------------------------------------
// 发送链路与六事件回调分发（design 2.4.4-A 写入规则表）
// ---------------------------------------------------------------------------
/** assistant 占位块（流式渲染目标——必须 reactive 包裹，P9 实测）。 */
function placeholderAssistant(): AssistantViewMessage {
  return {
    kind: 'assistant',
    segments: [],
    streaming: true,
    finish: null,
    error: null,
    stopped: false,
    sources: [],
  }
}

/** 提交消息：SSE 六回调分发响应式更新（segments 保序 append）。 */
async function onSend(message: string): Promise<void> {
  const trimmed = message.trim()
  if (streaming.value) return
  if (!trimmed || trimmed.length > MESSAGE_MAX_LEN) return

  messages.value.push({ kind: 'user', content: trimmed })
  // 必须包一层 reactive：回调直接改局部变量，原始对象绕过 Vue 响应式
  // 代理则逐片 delta 不触发重渲染（P9 AskView.vue:78-82 实测同款）。
  const assistant = reactive<AssistantViewMessage>(placeholderAssistant())
  messages.value.push(assistant)
  autoFollow.value = true
  void scrollToBottom()

  abortController = new AbortController()
  streaming.value = true

  try {
    await streamAgentChat(
      {
        message: trimmed,
        ...(currentConversation.value
          ? { conversation_id: currentConversation.value.id }
          : {}),
      },
      {
        onThinking: (data) => {
          // 新轮次信号：之前最后一个 thinking 段置 done（弱化，A11）。
          const segments = assistant.segments
          if (data.round != null) {
            for (let i = segments.length - 1; i >= 0; i -= 1) {
              const segment = segments[i]
              if (segment.kind === 'thinking') {
                segment.done = true
                break
              }
            }
            const seg: AssistantSegment = {
              kind: 'thinking',
              round: data.round,
              content: data.content ?? '',
              done: false,
            }
            segments.push(seg)
          } else if (data.content) {
            // 防御路径：仅 content 增量 → 追加到最后 thinking 段。
            for (let i = segments.length - 1; i >= 0; i -= 1) {
              const segment = segments[i]
              if (segment.kind === 'thinking') {
                segment.content += data.content
                break
              }
            }
          }
          if (autoFollow.value) void scrollToBottom()
        },
        onToolCall: (data) => {
          // 调用中卡片（result===null）——segments 保序即堆叠序（A2）。
          assistant.segments.push({
            kind: 'tool',
            call: {
              call_id: data.call_id,
              name: data.name,
              arguments: data.arguments,
              result: null,
            },
          })
          if (autoFollow.value) void scrollToBottom()
        },
        onToolResult: (data) => {
          // 按 call_id 配对写入；未命中降级为独立完成态卡片（spec
          // §5.3.1 规则 8）。sources 三态（L2）：undefined → null
          // （非检索/失败路径零行为变化）；[] → 空命中；[...] → 命中。
          const normalized =
            data.sources !== undefined ? normalizeSources(data.sources) : null
          let hit = false
          for (const segment of assistant.segments) {
            if (segment.kind === 'tool' && segment.call.call_id === data.call_id) {
              segment.call.result = {
                ok: data.ok,
                elapsed_ms: data.elapsed_ms,
                summary: data.summary,
                truncated: data.truncated,
                raw_content: null,
                sources: normalized,
              }
              hit = true
              break
            }
          }
          if (!hit) {
            assistant.segments.push({
              kind: 'tool',
              call: {
                call_id: data.call_id,
                name: data.name,
                arguments: {},
                result: {
                  ok: data.ok,
                  elapsed_ms: data.elapsed_ms,
                  summary: data.summary,
                  truncated: data.truncated,
                  raw_content: null,
                  sources: normalized,
                },
              },
            })
          }
          // 块级合并：实时路径当前 assistant 即本轮消息，直接聚合——
          // 来源区渲染在 segments 之后（spec §5.2.1-7）。
          if (normalized) mergeAssistantSources(assistant, normalized)
          if (autoFollow.value) void scrollToBottom()
        },
        onDelta: (text) => {
          // 尾段为 text → 追加；否则新 text 段（中间轮解释与最终
          // 回答分属不同段——A8）。
          const segments = assistant.segments
          const last = segments[segments.length - 1]
          if (last && last.kind === 'text') {
            last.content += text
          } else {
            segments.push({ kind: 'text', content: text })
          }
          if (autoFollow.value) void scrollToBottom()
        },
        onDone: (data) => {
          assistant.finish = {
            finish_reason: data.finish_reason,
            rounds: data.rounds,
            tool_call_count: data.tool_call_count,
            conversation_id: data.conversation_id,
          }
          // 空态直发（无 currentConversation）→ 列表刷新后绑定新会话。
          if (!currentConversation.value) void bindConversationAfterDone(data.conversation_id)
        },
        onError: (data) => {
          // 内容保留红线：只增错误行，segments 不动。
          assistant.error = data.message
        },
      },
      abortController.signal,
    )
  } finally {
    // 单一 finally 复位块（五条终结路径结构性消灭「永久转圈」）。
    assistant.streaming = false
    streaming.value = false
    abortController = null
    // 仅当用户仍在跟随（未上滚查看历史）时补滚到底；
    // 无条件滚动会把正在回看的用户拽回底部。
    if (autoFollow.value) void scrollToBottom()
    void refreshConversations()
  }
}

/**
 * 停止生成（R3 硬约束——决策 A4 锁死顺序，不得重排）：
 * ① 先置位 stopped（保留内容红线——置位先行保证标记与内容落定，
 *    即使 abort 触发的 reject 竞先也只走 agent.ts 静默分支）→
 * ② abort() → ③ agent.ts catch 首语句 aborted 判定 → ④ 静默
 * resolve → finally 复位。
 */
function onStop(): void {
  const last = messages.value[messages.value.length - 1]
  if (last && last.kind === 'assistant') last.stopped = true
  abortController?.abort()
}

/** 空态直发后绑定新会话（列表刷新回调内按 id 匹配）。 */
async function bindConversationAfterDone(conversationId: number): Promise<void> {
  try {
    await refreshConversations()
    const found = conversations.value.find((c) => c.id === conversationId)
    if (found) currentConversation.value = found
  } catch {
    // 列表刷新失败不阻塞对话（拦截器已弹错）。
  }
}

// ---------------------------------------------------------------------------
// 历史回放还原算法（design 2.4.3——用户设计重点 ②）
// ---------------------------------------------------------------------------
/**
 * agent_messages 全量 → 视图消息流。
 *
 * 两阶段配对（design 2.4.3-A）：第一阶段按 id 升序遍历，为每个
 * assistant(tool_calls) 元素建卡片骨架并注册 call_id 索引 map；
 * 第二阶段（同一遍历时序）tool 消息按 tool_call_id 回填结果——
 * 注册先于回填的时序由消息 id 升序结构性保证。
 *
 * arguments 容错解析三分支（design 2.4.3-B）：JSON.parse 成功且为
 * 对象 → 标准形态；成功但非对象 / 失败 → 原始字符串降级（联合类型
 * 第二分支，整条历史不崩）；空串 → {}（name() 括号留空）。
 * 孤儿 tool 消息（call_id 未命中）continue 跳过不渲染。
 * 历史卡 ok 判定：解析后含 error 键即失败（决策 A12——对齐后端
 * `"error" not in result` 语义）。
 */
function buildViewMessages(msgs: AgentMessage[]): ViewMessage[] {
  const result: ViewMessage[] = []
  const cardIndex = new Map<string, ToolCallView>()
  // 轮次 flush 游标（L2 修正①，design 2.1.3-C）：来源挂到「本轮最终
  // 回答」块而非拥有工具调用的块——user 分支前置 flush + 循环末尾
  // 终态 flush；不引入块级索引，纯局部变量增量。
  let pendingSources: QaSourceItem[] = []
  let lastAssistant: AssistantViewMessage | null = null
  const flushPendingSources = (): void => {
    if (pendingSources.length && lastAssistant) {
      mergeAssistantSources(lastAssistant, pendingSources)
    }
    pendingSources = []
  }

  for (const msg of msgs) {
    if (msg.role === 'user') {
      flushPendingSources()
      result.push({ kind: 'user', content: msg.content })
      continue
    }
    if (msg.role === 'assistant') {
      const block: AssistantViewMessage = {
        kind: 'assistant',
        segments: [],
        streaming: false,
        finish: null,
        error: null,
        stopped: false,
        sources: [],
      }
      if (msg.content) block.segments.push({ kind: 'text', content: msg.content })
      if (msg.tool_calls && msg.tool_calls.length) {
        for (const tc of msg.tool_calls) {
          const card: ToolCallView = {
            call_id: tc.id,
            name: tc.function.name,
            arguments: parseArgumentsSafe(tc.function.arguments),
            result: null,
          }
          block.segments.push({ kind: 'tool', call: card })
          cardIndex.set(tc.id, card)
        }
      }
      result.push(block)
      // 同轮多块（工具调用块/最终回答块）时后者覆盖前者——游标始终
      // 指向「当前轮最后一个 assistant 块」。
      lastAssistant = block
      continue
    }
    // role === 'tool'：按 tool_call_id 回填（未命中即孤儿——跳过）。
    const card = msg.tool_call_id != null ? cardIndex.get(msg.tool_call_id) : undefined
    if (!card) continue
    let parsed: unknown = null
    let parseOk = false
    try {
      parsed = JSON.parse(msg.content)
      parseOk = true
    } catch {
      parseOk = false
    }
    const isFailed =
      parseOk &&
      typeof parsed === 'object' &&
      parsed !== null &&
      'error' in parsed
    const errorText =
      parseOk &&
      typeof parsed === 'object' &&
      parsed !== null &&
      'error' in parsed &&
      typeof (parsed as { error?: unknown }).error === 'string'
        ? (parsed as { error: string }).error
        : '工具执行失败'
    card.result = {
      ok: !isFailed,
      // 历史无耗时字段 → null（折叠行省略耗时项——F8 样式一致仅缺耗时）。
      elapsed_ms: null,
      summary: isFailed ? errorText : msg.content,
      truncated: false,
      // 历史回放展开详情 = 完整结果 JSON 格式化（ToolCallCard 数据驱动切换）。
      raw_content: msg.content,
      // 检索来源默认 null（历史缺源语义）；仅检索工具成功且 results
      // 为数组时在下方追加段重建覆盖。
      sources: null,
    }
    // 检索来源重建（L2 历史路径）：卡片级可溯写入 + 块级暂存（不立
    // 即挂块，flush 时挂到本轮最终回答）；parse 失败 / error 信封 /
    // results 非数组 → 保持 null 且不并入（降级不崩，spec §5.2.3-1）。
    if (msg.tool_name === 'search_knowledge_base' && parseOk && !isFailed) {
      const results = (parsed as { results?: unknown }).results
      if (Array.isArray(results)) {
        const normalized = normalizeSources(results)
        card.result.sources = normalized
        pendingSources = pendingSources.concat(normalized)
      }
    }
  }
  // 终态 flush：覆盖最后一轮无后继 user 消息的收尾场景。
  flushPendingSources()
  return result
}

/** 来源卡跳转（L2：与 AskView.onNavigate 同构口径——item_id 缺失
 * 守卫 return；query 携带 item_id 字符串化 + chunk_index 可空省略）。
 * SourceCard canNavigate 已前置拦截，此处双保险。 */
function onSourceNavigate(source: QaSourceItem): void {
  if (source.item_id == null) return
  void router.push({
    path: '/knowledge-base',
    query: {
      item_id: String(source.item_id),
      ...(source.chunk_index != null
        ? { chunk_index: String(source.chunk_index) }
        : {}),
    },
  })
}

/** arguments 容错解析（三分支——失败降级原始字符串）。 */
function parseArgumentsSafe(raw: string): Record<string, unknown> | string {  if (!raw) return {}
  try {
    const parsed: unknown = JSON.parse(raw)
    if (typeof parsed === 'object' && parsed !== null && !Array.isArray(parsed)) {
      return parsed as Record<string, unknown>
    }
    return raw
  } catch {
    return raw
  }
}

// ---------------------------------------------------------------------------
// 会话管理编排（O5 短路 + loadSeq 守卫 + 全操作矩阵）
// ---------------------------------------------------------------------------
/** 刷新会话列表（服务端 updated_at 倒序原样覆盖）。 */
async function refreshConversations(): Promise<void> {
  conversationsLoading.value = true
  try {
    const data = await getAgentConversations(1, CONVERSATION_PAGE_SIZE)
    conversations.value = data.items
  } catch {
    // 错误提示由 request.ts 拦截器统一弹出；保留空列表态页面可用。
  } finally {
    conversationsLoading.value = false
  }
}

/** 生成中操作拦截（O5——轻提示禁静默，单一来源）。 */
function guardGenerating(): boolean {
  if (streaming.value) {
    ElMessage.info(GENERATING_BLOCK_HINT)
    return true
  }
  return false
}

/** 新建会话（显式 POST；插顶部置当前）。 */
async function onCreate(): Promise<void> {
  if (guardGenerating()) return
  try {
    const conversation = await createAgentConversation()
    conversations.value.unshift(conversation)
    currentConversation.value = conversation
    messages.value = []
  } catch {
    // 拦截器已弹错。
  }
}

/** 切换会话（loadSeq 守卫 + 全量回放）。 */
async function selectConversation(conversationId: number): Promise<void> {
  if (guardGenerating()) return
  if (conversationId === currentConversation.value?.id) return
  const conversation = conversations.value.find((c) => c.id === conversationId)
  if (!conversation) return
  currentConversation.value = conversation
  const seq = ++loadSeq
  messagesLoading.value = true
  try {
    const msgs = await getAgentConversationMessages(conversationId)
    if (seq !== loadSeq) return // 旧响应晚到丢弃（决策 A6）
    messages.value = buildViewMessages(msgs)
    autoFollow.value = true
    void scrollToBottom()
  } catch {
    // 404/1005（并发删除）由拦截器弹错；保留当前视图。
    if (seq === loadSeq) {
      conversations.value = conversations.value.filter((c) => c.id !== conversationId)
      if (currentConversation.value?.id === conversationId) currentConversation.value = null
    }
  } finally {
    if (seq === loadSeq) messagesLoading.value = false
  }
}

/** 重命名会话（成功后更新列表行与 chat-head 标题）。 */
async function onRename(conversationId: number, title: string): Promise<void> {
  if (guardGenerating()) return
  try {
    const updated = await renameAgentConversation(conversationId, title)
    const idx = conversations.value.findIndex((c) => c.id === conversationId)
    if (idx >= 0) conversations.value[idx] = updated
    if (currentConversation.value?.id === conversationId) currentConversation.value = updated
  } catch {
    // 拦截器已弹错（422 空标题/超长由前端拦截 + 后端兜底）。
  }
}

/** 删除会话（级联消息；删除当前 → 切剩余首个或空态）。 */
async function onRemove(conversationId: number): Promise<void> {
  if (guardGenerating()) return
  try {
    await deleteAgentConversation(conversationId)
    conversations.value = conversations.value.filter((c) => c.id !== conversationId)
    if (currentConversation.value?.id === conversationId) {
      currentConversation.value = conversations.value[0] ?? null
      if (currentConversation.value) {
        void selectConversation(currentConversation.value.id)
      } else {
        messages.value = []
      }
    }
  } catch {
    // 拦截器已弹错。
  }
}

/**
 * 卡片展开/收起上报。
 *
 * **刻意不做任何滚动**：用户点开卡片是为了阅读其中的参数与结果，
 * 此刻若调用 scrollToBottom 会立刻把视图拽到底部，展开的内容反而看不见。
 * 内容高度变化由浏览器滚动锚定（scroll anchoring）自然保持视口稳定。
 * 保留该回调是为了组件契约完整（ToolCallCard emit），后续不要再往里加滚动。
 */
function onCardToggle(): void {
  // 故意为空。
}

/** 快捷问题点击（O3——一步动作直接发送）。 */
function onQuickQuestion(question: string): void {
  void onSend(question)
}

// ---------------------------------------------------------------------------
// 初始化：刷新恢复最近活跃会话（spec §5.6.1 规则 8）
// ---------------------------------------------------------------------------
onMounted(() => {
  void (async () => {
    await refreshConversations()
    const first = conversations.value[0]
    if (first) {
      currentConversation.value = first
      const seq = ++loadSeq
      messagesLoading.value = true
      try {
        const msgs = await getAgentConversationMessages(first.id)
        if (seq !== loadSeq) return
        messages.value = buildViewMessages(msgs)
      } catch {
        // 拦截器已弹错；保留空对话区。
      } finally {
        if (seq === loadSeq) messagesLoading.value = false
      }
    }
  })()
})
</script>

<template>
  <div class="agent-page">
    <!-- 左栏：会话列表（O5：生成中新建入口置灰 + 轻提示拦截） -->
    <aside class="conversation-panel">
      <ConversationList
        :conversations="conversations"
        :current-id="currentConversation?.id ?? null"
        :loading="conversationsLoading"
        :generating="streaming"
        @create="onCreate"
        @select="selectConversation"
        @rename="onRename"
        @remove="onRemove"
      />
      <div v-if="conversations.length >= CONVERSATION_PAGE_SIZE" class="panel-foot">
        {{ LIST_TOTAL_HINT }}
      </div>
    </aside>

    <!-- 右栏：对话区（页面不滚动，唯一滚动容器在 chat-scroll） -->
    <section class="chat-panel">
      <header class="chat-head">
        <span class="head-title">{{ currentConversation?.title || '新会话' }}</span>
      </header>

      <div ref="scroller" class="chat-scroll" @scroll="onScroll">
        <!-- 空态：el-empty + 快捷问题（O2/O3——非空会话不显示） -->
        <div v-if="!messages.length && !messagesLoading" class="empty-state">
          <el-empty
            description="向 AI 助手提问，它会自动调用工具分析你的学习数据"
            :image-size="90"
          />
          <p class="kb-hint">{{ KNOWLEDGE_HINT }}</p>
          <div class="quick-questions">
            <el-button
              v-for="question in QUICK_QUESTIONS"
              :key="question"
              plain
              :disabled="streaming"
              @click="onQuickQuestion(question)"
            >
              {{ question }}
            </el-button>
          </div>
        </div>

        <div v-else class="message-list" v-loading="messagesLoading">
          <MessageItem
            v-for="(message, idx) in messages"
            :key="idx"
            :message="message"
            @card-toggle="onCardToggle"
            @source-navigate="onSourceNavigate"
          />
        </div>
      </div>

      <!-- 输入区（停止按钮原位常驻——O5） -->
      <div class="composer-area">
        <AgentComposer :streaming="streaming" @send="onSend" @stop="onStop" />
      </div>
    </section>
  </div>
</template>

<style scoped>
/* 双栏布局（design 2.4.4-D）：页面不滚动，滚动仅发生在 chat-scroll。 */
.agent-page {
  height: 100%;
  display: flex;
  gap: 12px;
  overflow: hidden;
}
.conversation-panel {
  flex: 0 0 264px;
  display: flex;
  flex-direction: column;
  min-height: 0;
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 8px;
  background: #ffffff;
  overflow: hidden;
}
.panel-foot {
  flex: 0 0 auto;
  padding: 8px 12px;
  border-top: 1px solid var(--el-border-color-lighter);
  font-size: 12px;
  color: var(--el-text-color-placeholder);
}
.chat-panel {
  flex: 1 1 auto;
  min-width: 0;
  display: flex;
  flex-direction: column;
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 8px;
  background: #ffffff;
  overflow: hidden;
}
.chat-head {
  flex: 0 0 auto;
  padding: 12px 16px;
  border-bottom: 1px solid var(--el-border-color-lighter);
}
.head-title {
  font-size: 15px;
  font-weight: 600;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.chat-scroll {
  flex: 1 1 auto;
  min-height: 0;
  overflow-y: auto;
  padding: 16px;
}
.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 16px;
  padding-top: 40px;
}
.kb-hint {
  margin: 0;
  font-size: 12px;
  color: var(--el-text-color-placeholder);
}
.quick-questions {
  display: flex;
  flex-direction: column;
  gap: 10px;
  width: 320px;
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