/**
 * AI 学习问答 API（P9）：SSE 流式客户端 + 历史问答。
 *
 * SSE 走 fetch + ReadableStream 属 PROJECT_CONTEXT §7.3 认可的
 * 流式例外（**禁用 EventSource**——它不支持 POST body）；历史接口
 * 为常规 Axios 请求（走 request.ts 统一解包）。
 *
 * 跨 chunk 残包处理核心（design.md 2.6.2）：**行缓冲算法**——
 * `buffer += decoder.decode(value, { stream: true })`，循环按
 * `\n\n` 边界切出完整事件块（SSE 事件以空行分隔），剩余半包留在
 * buffer 等待下一 chunk；一条 data: 行的 JSON 被网络分包切断的
 * 场景由「只在 \n\n 边界切分」结构性消除——不能假设每次 read()
 * 都是一条完整事件。
 */
import { ElMessage } from 'element-plus'

import request from './request'
import { clearTokenAndRedirect } from './request'
import { useUserStore } from '@/stores/user'
import type { ChatHistoryResult, ChatQaPayload, QaSseEvent } from '@/types'

/** SSE 事件回调接口（视图层把回调绑到响应式更新）。 */
export interface StreamChatHandlers {
  onSources: (sources: QaSseEvent & { type: 'sources' }) => void
  onDelta: (text: string) => void
  onDone: (data: Extract<QaSseEvent, { type: 'done' }>['data']) => void
  onError: (data: { code: number; message: string }) => void
}

/** 业务码：Token 无效或已过期（与 request.ts 同口径）。 */
const CODE_TOKEN_INVALID = 1003

/**
 * SSE 流式问答：POST /chat/qa，fetch + ReadableStream 逐块解析。
 *
 * - 受理阶段错误（HTTP 非 200，流未开始）：解析统一响应体 →
 *   401 / code=1003 时 clearTokenAndRedirect（复用 request.ts 的
 *   单一实现）+ 错误提示；其他业务码仅提示；随后 reject 终止。
 * - 流内事件按 type 分发四回调；done / error 到达后 resolve
 *   （流终结）。
 * - 浏览器侧网络中断（reader.read() 抛错）：本地合成错误
 *   「网络中断，请重试」经 onError 通知（已收到的 delta 保留，
 *   由视图层决定呈现）。
 *
 * @param payload 请求体（question）。
 * @param handlers 四事件回调。
 * @returns Promise<void> 流终结时 resolve。
 */
export async function streamChatQa(
  payload: ChatQaPayload,
  handlers: StreamChatHandlers,
): Promise<void> {
  const token = useUserStore().token
  const base = import.meta.env.VITE_API_BASE_URL || '/api/v1'

  let resp: Response
  try {
    resp = await fetch(`${base}/chat/qa`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      body: JSON.stringify(payload),
    })
  } catch {
    // 建连失败（网络不可达等）：受理阶段口径。
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

  const dispatch = (event: QaSseEvent): 'end' | 'continue' => {
    switch (event.type) {
      case 'sources':
        handlers.onSources(event)
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
        let event: QaSseEvent
        try {
          event = JSON.parse(line.slice(6)) as QaSseEvent
        } catch {
          // 理论不可达（\n\n 边界保证 JSON 完整）；脏块跳过不中断。
          continue
        }
        if (dispatch(event) === 'end') return
      }
    }
    // 流自然耗尽但无终结事件（服务端异常关闭）：合成错误。
    handlers.onError({ code: 0, message: '网络中断，请重试' })
  } catch {
    // reader.read() 抛错（浏览器侧网络中断）：已收到的 delta 保留。
    handlers.onError({ code: 0, message: '网络中断，请重试' })
  } finally {
    reader.releaseLock()
  }
}

/**
 * 历史问答分页查询：GET /chat/history（Axios 常规通道，统一解包）。
 *
 * @param page 页码（从 1 开始）。
 * @param pageSize 每页条数（1~100）。
 * @returns 分页数据（items 按 created_at 倒序，仅本人可见）。
 */
export function getChatHistory(
  page: number,
  pageSize: number,
): Promise<ChatHistoryResult> {
  return request.get('/chat/history', {
    params: { page, page_size: pageSize },
  }) as Promise<ChatHistoryResult>
}