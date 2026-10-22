/**
 * Agent API（P11 前端）：SSE 流客户端 + 会话管理五函数。
 *
 * SSE 解析骨架与 P9 chat.ts **逐行同构复刻**（design 2.4.2 十六项
 * 对照表——`\n\n` 边界切块 / 残包留 buffer / TextDecoder
 * stream:true / 注释行忽略 / 脏块跳过；差异仅三处：端点
 * /agent/chat、事件数四→六（新增 default 静默分支）、signal 停止
 * 链路）。chat.ts 解析循环内联于 streamChatQa 函数体（:119-152）
 * 不可 import，同构复刻是唯一合规路径（design 实测发现 ①，裁决 #1）。
 *
 * 停止链路（R3 硬约束 / 决策 A4）：catch 块**第一条语句**判定
 * `signal?.aborted === true` → 静默 return——用户主动停止不是错误，
 * 禁止落入「网络中断，请重试」分支渲染红色错误行；该顺序为锁死
 * 顺序，不得被后续 catch 逻辑重排。视图层在 abort() 前置位
 * stopped 标记（保留内容红线）。
 *
 * 会话管理五函数走 request.ts（Axios 统一通道：token 注入 / code
 * 解包 / 错误 ElMessage / 401 清 token 跳转全部由拦截器完成——
 * 本文件零手写 401 跳转，clearTokenAndRedirect 仅用于 SSE 受理段）。
 */
import { ElMessage } from 'element-plus'

import request from './request'
import { clearTokenAndRedirect } from './request'
import { useUserStore } from '@/stores/user'
import type {
  AgentChatPayload,
  AgentConversation,
  AgentMessage,
  AgentSseEvent,
  ConversationPage,
} from '@/types/agent'

/** 业务码：Token 无效或已过期（与 request.ts 同口径）。 */
const CODE_TOKEN_INVALID = 1003

/** SSE 事件回调接口（六事件；thinking 入参放宽做前向兼容）。 */
export interface AgentStreamHandlers {
  onThinking: (data: { round?: number; content?: string }) => void
  onToolCall: (data: Extract<AgentSseEvent, { type: 'tool_call' }>['data']) => void
  onToolResult: (
    data: Extract<AgentSseEvent, { type: 'tool_result' }>['data'],
  ) => void
  onDelta: (text: string) => void
  onDone: (data: Extract<AgentSseEvent, { type: 'done' }>['data']) => void
  onError: (data: { code: number; message: string }) => void
}

/**
 * Agent SSE 流式对话：POST /agent/chat，fetch + ReadableStream。
 *
 * - 受理阶段错误（HTTP 非 200，流未开始）：统一响应体 JSON →
 *   401 / code=1003 时 clearTokenAndRedirect + 提示；422/1001、
 *   404/1005 走通用 ElMessage(message)（后端中文文案直出）；随后
 *   onError 终止。
 * - 流内六事件按 type 分发；done / error 到达后 resolve。
 * - 停止（signal aborted）：catch 首句静默 return（R3 硬约束），
 *   不合成网络中断、不触发 onError。
 *
 * @param payload 请求体（message + conversation_id?）。
 * @param handlers 六事件回调。
 * @param signal 停止信号（fetch init 透传；abort 使在途 read reject）。
 * @returns Promise<void> 流终结时 resolve（含静默停止路径）。
 */
export async function streamAgentChat(
  payload: AgentChatPayload,
  handlers: AgentStreamHandlers,
  signal?: AbortSignal,
): Promise<void> {
  const token = useUserStore().token
  const base = import.meta.env.VITE_API_BASE_URL || '/api/v1'

  let resp: Response
  try {
    resp = await fetch(`${base}/agent/chat`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      body: JSON.stringify(payload),
      signal,
    })
  } catch {
    // 建连失败：abort 恰在本窗口触发时静默（停止不是错误，R3）；
    // 其余按受理阶段口径提示。
    if (signal?.aborted === true) return
    ElMessage.error('网络异常，请稍后重试')
    handlers.onError({ code: 0, message: '网络异常，请稍后重试' })
    return
  }

  if (!resp.ok) {
    // 受理阶段错误：统一响应体 JSON（非 SSE），流未开始。
    let code = 0
    let message = `请求异常（HTTP ${resp.status}）`
    try {
      const body = (await resp.json()) as { code?: number; message?: string }
      code = body.code ?? 0
      message = body.message || message
    } catch {
      // 响应体非 JSON（如网关 HTML 错误页），保留默认 message。
    }
    if (resp.status === 401 || code === CODE_TOKEN_INVALID) {
      clearTokenAndRedirect()
    }
    ElMessage.error(message)
    handlers.onError({ code, message })
    return
  }

  const reader = resp.body?.getReader()
  if (!reader) {
    handlers.onError({ code: 0, message: '当前浏览器不支持流式响应' })
    return
  }

  const decoder = new TextDecoder('utf-8')
  // 行缓冲：半包留在 buffer，仅在 \n\n 边界切出完整事件块。
  let buffer = ''

  const dispatch = (event: AgentSseEvent): 'end' | 'continue' => {
    switch (event.type) {
      case 'thinking':
        handlers.onThinking(event.data)
        return 'continue'
      case 'tool_call':
        handlers.onToolCall(event.data)
        return 'continue'
      case 'tool_result':
        handlers.onToolResult(event.data)
        return 'continue'
      case 'delta':
        handlers.onDelta(event.data)
        return 'continue'
      case 'done':
        handlers.onDone(event.data)
        return 'end'
      case 'error':
        handlers.onError(event.data)
        return 'end'
      default:
        // 未知 type 静默忽略（前向兼容，spec §5.3.1 规则 4）。
        return 'continue'
    }
  }

  try {
    for (;;) {
      const { done, value } = await reader.read()
      if (done) break
      buffer += decoder.decode(value, { stream: true })
      // 按 \n\n 边界切分：一个事件块 = data: 行 + 空行。
      for (;;) {
        const sep = buffer.indexOf('\n\n')
        if (sep === -1) break
        const block = buffer.slice(0, sep)
        buffer = buffer.slice(sep + 2)
        const line = block.trim()
        // 忽略空行与 ':' 注释行；仅消费 data: 行。
        if (!line || line.startsWith(':')) continue
        if (!line.startsWith('data: ')) continue
        let event: AgentSseEvent
        try {
          event = JSON.parse(line.slice(6)) as AgentSseEvent
        } catch {
          // 理论不可达（\n\n 边界保证 JSON 完整）；脏块跳过不中断。
          continue
        }
        if (dispatch(event) === 'end') return
      }
    }
    // 流自然耗尽但无终结事件：停止路径前置判定（R3）——停止后流以
    // done 收尾的正常路径已在 dispatch return；此处 aborted 说明
    // 服务端在 abort 后关闭流，静默不合成网络中断。
    if (signal?.aborted === true) return
    handlers.onError({ code: 0, message: '网络中断，请重试' })
  } catch {
    // R3 硬约束（决策 A4 锁死顺序，不得重排）：catch 首语句判定
    // aborted——用户主动停止不是错误，静默 return，不合成
    // 「网络中断，请重试」、不触发 onError、不渲染红色错误行。
    if (signal?.aborted === true) return
    // reader.read() 抛错（浏览器侧网络中断）：已收到的内容保留。
    // 防御性预案（个别浏览器 read 未 reject 的差异，非主路径）：
    void reader.cancel().catch(() => {})
    handlers.onError({ code: 0, message: '网络中断，请重试' })
  } finally {
    reader.releaseLock()
  }
}

// ---------------------------------------------------------------------------
// 会话管理五函数（request.ts 统一通道；错误提示/401 处理由拦截器完成）
// ---------------------------------------------------------------------------
/**
 * 会话列表分页查询：GET /agent/conversations（updated_at 倒序）。
 *
 * @param page 页码（从 1 开始）。
 * @param pageSize 每页条数（1~100）。
 */
export function getAgentConversations(
  page: number,
  pageSize: number,
): Promise<ConversationPage> {
  return request.get('/agent/conversations', {
    params: { page, page_size: pageSize },
  }) as Promise<ConversationPage>
}

/**
 * 新建会话：POST /agent/conversations（title 可空——空时后端在首条
 * 消息落库后补 20 字截断标题）。
 */
export function createAgentConversation(
  title?: string,
): Promise<AgentConversation> {
  return request.post('/agent/conversations', {
    ...(title ? { title } : {}),
  }) as Promise<AgentConversation>
}

/**
 * 重命名会话：PATCH /agent/conversations/{id}（title 1..200）。
 */
export function renameAgentConversation(
  conversationId: number,
  title: string,
): Promise<AgentConversation> {
  return request.patch(`/agent/conversations/${conversationId}`, {
    title,
  }) as Promise<AgentConversation>
}

/** 删除会话（级联消息）：DELETE /agent/conversations/{id}。 */
export function deleteAgentConversation(
  conversationId: number,
): Promise<null> {
  return request.delete(
    `/agent/conversations/${conversationId}`,
  ) as Promise<null>
}

/**
 * 会话消息全量查询：GET /agent/conversations/{id}/messages
 * （id 升序；含 role/tool_name/tool_calls/tool_call_id 全链，足以
 * 还原历史工具卡片——design 2.4.3 回放算法输入）。
 */
export function getAgentConversationMessages(
  conversationId: number,
): Promise<AgentMessage[]> {
  return request.get(
    `/agent/conversations/${conversationId}/messages`,
  ) as Promise<AgentMessage[]>
}