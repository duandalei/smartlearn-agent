/**
 * 知识域前端工具（P6 知识点规范化 + P8 知识库展示辅助）。
 *
 * P6 部分：与后端 `app/core/normalize.py` 数组管线为「三步无校验版」
 * 同语义镜像（无运行时依赖）：trim → 滤空 → 保序去重。**不做长度与
 * 空白判错**——后端是唯一权威校验源（422/1001 中文提示），前端复制
 * 校验规则会造成双口径漂移（design 决策 5）。分工（spec 5.2.1 规则 2）：
 * 前端对纯空白标签静默丢弃（体验优化），后端拦截并报错（权威兜底）。
 *
 * P8 部分：知识库列表展示辅助（大小/时间格式化 + 状态四色映射），
 * 纯函数无依赖（design.md 2.6.2-B）。
 */
import type { KnowledgeItemStatus } from '@/types'

/**
 * 知识点数组清洗：trim → 滤空 → 保序去重，返回新数组（纯函数）。
 *
 * @param kps 原始标签数组（空态由调用方处理）。
 * @returns 清洗后的新数组；全空白输入返回空数组。
 */
export function normalizeKnowledgePoints(kps: string[]): string[] {
  const seen = new Set<string>()
  const result: string[] = []
  for (const k of kps) {
    const trimmed = k.trim()
    if (trimmed.length === 0 || seen.has(trimmed)) continue
    seen.add(trimmed)
    result.push(trimmed)
  }
  return result
}
// ---------------------------------------------------------------------------
// 知识库展示辅助（P8，design.md 2.6.2-B）
// ---------------------------------------------------------------------------

/** 个位数补零。 */
function pad2(n: number): string {
  return String(n).padStart(2, '0')
}

/**
 * 文件大小格式化（file_size 字节数 → B/KB/MB 纯展示）。
 *
 * @param bytes 原件字节数（可空，存量行回填前为 null）。
 * @returns 如 '5.9 KB' / '1.2 MB'；null 返回 '—'。
 */
export function formatFileSize(bytes: number | null): string {
  if (bytes == null) return '—'
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

/**
 * ISO 时间格式化为 'YYYY-MM-DD HH:mm'；空值/非法值返回 '—'。
 * 纯原生 Date 实现，不引入日期库（用户约定）。
 */
export function formatDateTime(iso: string | null): string {
  if (!iso) return '—'
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return '—'
  return `${d.getFullYear()}-${pad2(d.getMonth() + 1)}-${pad2(d.getDate())} ${pad2(d.getHours())}:${pad2(d.getMinutes())}`
}

/** 状态展示元数据（四色映射：pending=info / parsing=warning / indexed=success / failed=danger）。 */
export const KB_STATUS_META: Record<
  KnowledgeItemStatus,
  { label: string; tag: 'info' | 'warning' | 'success' | 'danger' }
> = {
  pending: { label: '待处理', tag: 'info' },
  parsing: { label: '解析中', tag: 'warning' },
  indexed: { label: '已索引', tag: 'success' },
  failed: { label: '失败', tag: 'danger' },
}

/** 处中状态（重索引按钮禁用 + 轮询判定共用口径）。 */
export function isKbProcessing(status: KnowledgeItemStatus): boolean {
  return status === 'pending' || status === 'parsing'
}