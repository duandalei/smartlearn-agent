/**
 * 知识点标签前端规范化（P6 缺陷修复，提交预处理与渲染兜底共用单点）。
 *
 * 与后端 `app/core/normalize.py` 数组管线为「三步无校验版」同语义镜像
 * （无运行时依赖）：trim → 滤空 → 保序去重。**不做长度与空白判错**——
 * 后端是唯一权威校验源（422/1001 中文提示），前端复制校验规则会造成
 * 双口径漂移（design 决策 5）。分工（spec 5.2.1 规则 2）：前端对纯
 * 空白标签静默丢弃（体验优化），后端拦截并报错（权威兜底）。
 */

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