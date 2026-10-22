/**
 * Agent 前端类型单一来源（design 2.3.2 全量；spec §7 数据约束）。
 *
 * 与 types/index.ts 并存零耦合（裁决 #2：agent 类型独立文件，仅
 * agent 域 import，不被其他模块反向依赖）。传输字段全程保留
 * snake_case（PROJECT_CONTEXT §8.3——JSON 字段不做大小写转换，
 * 与后端共用同一套字面量）。
 *
 * 分两层：
 * - 传输层：SSE 六事件可辨识联合 + 会话/消息/分页（逐字对齐
 *   SPEC_AGENT_CHAT §6.2 / §6.5）；
 * - 视图层：ViewMessage segments 顺序化建模（决策 A2——保序是
 *   「工作轨迹」语义的结构保证）+ ToolCallView 统一形态（决策
 *   A3——实时/历史差异全收敛为可空字段，组件无模式分支）。
 */

// ---------------------------------------------------------------------------
// 传输层：SSE 六事件契约（spec §7.2 七条载荷约束）
// ---------------------------------------------------------------------------
/** done 事件 finish_reason 三值（与后端 core.py 字面量同套）。 */
export type AgentFinishReason = 'normal' | 'max_rounds' | 'timeout'

/** thinking 事件载荷（round 轮次信号；content 推理增量，可选）。 */
export interface AgentThinkingData {
  round: number
  content?: string
}

/** tool_call 事件载荷（arguments 已是解析后对象）。 */
export interface AgentToolCallData {
  call_id: string
  name: string
  arguments: Record<string, unknown>
}

/** tool_result 事件载荷（耗时 + ≤500 字摘要 + 截断标记）。 */
export interface AgentToolResultData {
  call_id: string
  name: string
  ok: boolean
  elapsed_ms: number
  summary: string
  truncated: boolean
}

/** done 事件载荷（五字段；finish_reason 真实反映结束原因）。 */
export interface AgentDoneData {
  conversation_id: number
  message_id: number | null
  rounds: number
  tool_call_count: number
  finish_reason: AgentFinishReason
}

/** error 事件载荷（本阶段 code 仅 3000；message 中文可读）。 */
export interface AgentErrorData {
  code: number
  message: string
}

/** SSE 六事件可辨识联合（写法对齐 types/index.ts QaSseEvent）。 */
export type AgentSseEvent =
  | { type: 'thinking'; data: AgentThinkingData }
  | { type: 'tool_call'; data: AgentToolCallData }
  | { type: 'tool_result'; data: AgentToolResultData }
  | { type: 'delta'; data: string }
  | { type: 'done'; data: AgentDoneData }
  | { type: 'error'; data: AgentErrorData }

// ---------------------------------------------------------------------------
// 传输层：会话 / 消息 / 分页（spec §7.3）
// ---------------------------------------------------------------------------
/** Agent 会话对象（GET/POST/PATCH 响应）。 */
export interface AgentConversation {
  id: number
  title: string | null
  created_at: string
  updated_at: string
}

/** 会话列表分页响应（updated_at 倒序）。 */
export interface ConversationPage {
  items: AgentConversation[]
  total: number
  page: number
  page_size: number
}

/** OpenAI 原始格式 tool_call（历史消息落库形态；arguments 为 JSON 字符串）。 */
export interface AgentToolCall {
  id: string
  type: string
  function: {
    name: string
    arguments: string
  }
}

/** agent_messages role 枚举（system 不落库不回放）。 */
export type AgentMessageRole = 'user' | 'assistant' | 'tool'

/** Agent 消息对象（GET /conversations/{id}/messages 全量元素）。 */
export interface AgentMessage {
  id: number
  conversation_id: number
  role: AgentMessageRole
  content: string
  tool_name: string | null
  tool_calls: AgentToolCall[] | null
  tool_call_id: string | null
  created_at: string
}

/** Agent 对话请求体（POST /agent/chat）。 */
export interface AgentChatPayload {
  message: string
  conversation_id?: number
}

// ---------------------------------------------------------------------------
// 视图层：ViewMessage segments 顺序化建模（design 2.3.2-B，决策 A2/A3/A8）
// ---------------------------------------------------------------------------
/**
 * 工具调用视图统一形态（决策 A3）。
 *
 * - `result === null` → 调用中态；
 * - `arguments` 联合第二分支 string = 历史容错降级（JSON.parse 失败
 *   时原始字符串，整条历史不崩——用户重点 ②）；
 * - 实时/历史差异全部收敛为可空字段：`elapsed_ms: null` → 历史省略
 *   耗时；`raw_content: null` → 实时展开显示 summary 全文。
 */
export interface ToolCallView {
  call_id: string
  name: string
  arguments: Record<string, unknown> | string
  result: ToolResultView | null
}

/** 工具结果视图（elapsed_ms/raw_content 可空即实时/历史差异点）。 */
export interface ToolResultView {
  ok: boolean
  elapsed_ms: number | null
  summary: string
  truncated: boolean
  /** 历史回放展开详情（完整结果 JSON 字符串）；实时为 null。 */
  raw_content: string | null
}

/** thinking 轮次信号段（done=true 即该轮弱化——决策 A11）。 */
export interface ThinkingSegment {
  kind: 'thinking'
  round: number | null
  content: string
  done: boolean
}

/** 工具调用卡片段（segments 保序即堆叠序）。 */
export interface ToolSegment {
  kind: 'tool'
  call: ToolCallView
}

/** 文本段（中间轮解释与最终回答分属不同 text 段——决策 A8）。 */
export interface TextSegment {
  kind: 'text'
  content: string
}

/** assistant 块内部段联合（v-for 天然保序渲染——工作轨迹）。 */
export type AssistantSegment = ThinkingSegment | ToolSegment | TextSegment

/** done 定值信息（块级字段，非流内段——决策 A2）。 */
export interface FinishInfo {
  finish_reason: AgentFinishReason
  rounds: number
  tool_call_count: number
  conversation_id: number
}

/** 用户消息视图。 */
export interface UserViewMessage {
  kind: 'user'
  content: string
}

/** assistant 块视图（块级字段：流式光标 / done / 错误行 / 已停止标记）。 */
export interface AssistantViewMessage {
  kind: 'assistant'
  segments: AssistantSegment[]
  streaming: boolean
  finish: FinishInfo | null
  error: string | null
  stopped: boolean
}

/** 视图消息联合。 */
export type ViewMessage = UserViewMessage | AssistantViewMessage