/**
 * 知识库接口封装（P8，design.md 2.2.2 接口清单）。
 *
 * - POST   /knowledge/upload                上传受理（multipart，进度回调）
 * - GET    /knowledge/items                 文档列表（分页，仅本人个人库）
 * - GET    /knowledge/items/{id}            文档详情（P9 跳转承接用，按 id 直取）
 * - DELETE /knowledge/items/{id}            删除个人库文档（级联清理）
 * - POST   /knowledge/items/{id}/reindex    重新索引（幂等重跑）
 * - GET    /knowledge/items/{id}/chunks     按文档查看全部分块
 * - POST   /knowledge/search                语义检索（mode + Top-K 结果）
 *
 * 错误提示由 request.ts 拦截器统一处理，业务层无需重复弹错。
 */
import type { AxiosProgressEvent } from 'axios'

import request from '@/api/request'
import type {
  KnowledgeChunk,
  KnowledgeItem,
  KnowledgeSearchPayload,
  KnowledgeSearchResult,
  KnowledgeUploadResult,
  PageResult,
} from '@/types'

/**
 * 上传学习文档（异步受理，立即返回 item_id 与 pending 状态）。
 *
 * @param file 上传文件（PDF/DOCX/PPTX/MD/TXT，≤20MB）。
 * @param onProgress 可选的 axios 上传进度回调（驱动逐文件进度条）。
 * @returns 受理结果（item_id + status='pending'，后续流转由列表轮询观察）。
 */
export function uploadKnowledge(
  file: File,
  onProgress?: (event: AxiosProgressEvent) => void,
): Promise<KnowledgeUploadResult> {
  const form = new FormData()
  form.append('file', file)
  return request.post('/knowledge/upload', form, {
    onUploadProgress: onProgress,
  }) as unknown as Promise<KnowledgeUploadResult>
}

/**
 * 分页查询本人可见文档列表（仅个人库，id 降序新上传置顶）。
 *
 * @param page 页码（1 起）。
 * @param page_size 每页条数。
 * @returns 分页结果（items 为 KnowledgeItem 数组）。
 */
export function listKnowledgeItems(
  page: number,
  page_size: number,
): Promise<PageResult<KnowledgeItem>> {
  return request.get('/knowledge/items', {
    params: { page, page_size },
  }) as unknown as Promise<PageResult<KnowledgeItem>>
}

/**
 * 删除个人库文档（SQLite 同步级联删除，向量与原件由后台清理）。
 *
 * @param id 文档 id（不可见或不存在后端返回 1005）。
 * @returns data 为 null 的成功响应。
 */
export function deleteKnowledgeItem(id: number): Promise<null> {
  return request.delete(`/knowledge/items/${id}`) as unknown as Promise<null>
}

/**
 * 触发重新索引（幂等重跑；处理中状态后端拒绝 1007）。
 *
 * @param id 文档 id。
 * @returns 受理结果（item_id + status='parsing'）。
 */
export function reindexKnowledgeItem(id: number): Promise<KnowledgeUploadResult> {
  return request.post(
    `/knowledge/items/${id}/reindex`,
  ) as unknown as Promise<KnowledgeUploadResult>
}

/**
 * 按文档 id 查询详情（P9 跳转承接用：问答来源卡定位时文档可能不在
 * 当前页列表中，详情端点直接按 id 取；不可见或已删除统一 404/1005）。
 *
 * 纯追加导出（不改既有函数，与后端裁决 #3 同精神）。
 *
 * @param id 文档 id。
 * @returns 文档对象（仅本人个人库可见范围）。
 */
export function getKnowledgeItem(id: number): Promise<KnowledgeItem> {
  return request.get(`/knowledge/items/${id}`) as unknown as Promise<KnowledgeItem>
}

/**
 * 按文档查看全部分块（chunk_index 升序，全量不分页）。
 *
 * @param itemId 文档 id。
 * @returns 分块列表（含 heading_path 标题层级路径）。
 */
export function listKnowledgeChunks(itemId: number): Promise<KnowledgeChunk[]> {
  return request.get(
    `/knowledge/items/${itemId}/chunks`,
  ) as unknown as Promise<KnowledgeChunk[]>
}

/**
 * 语义检索（查询向量化 → 个人库排序）。
 *
 * @param payload 检索入参（query 非空 ≤500 字符；top_k 1~20 默认 5）。
 * @returns mode（online/offline，离线警示条的权威信号）+ 按分数降序的命中列表。
 */
export function searchKnowledge(
  payload: KnowledgeSearchPayload,
): Promise<KnowledgeSearchResult> {
  return request.post(
    '/knowledge/search',
    payload,
  ) as unknown as Promise<KnowledgeSearchResult>
}