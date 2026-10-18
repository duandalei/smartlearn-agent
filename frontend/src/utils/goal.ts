/**
 * 学习目标纯函数工具（P4，可离线验证）。
 *
 * - calcGoalProgress       目标时间进度三态计算（防除零 / NaN）
 * - toEChartsTree          RoadmapNode → ECharts tree 数据（注入默认折叠）
 * - breakdownErrorMessage  拆解失败二分类文案（spec 裁定⑧）
 */
import axios from 'axios'

import type { RoadmapNode } from '@/types'

/** 一天的毫秒数（本地零点差值换算用）。 */
const DAY_MS = 86400000

// ---------------------------------------------------------------------------
// 进度环三态计算（spec 裁定④）
// ---------------------------------------------------------------------------

/** calcGoalProgress 的输出：驱动 GoalCard 进度区三态渲染。 */
export interface GoalProgress {
  /** 是否渲染进度环（起止日期齐全才有环）。 */
  showRing: boolean
  /** 时间进度百分比 0~100（已过天数 ÷ 总天数，clamp 上限 100）。 */
  percent: number
  /** 剩余天数（截止 − 今天，本地零点比较；负数即已过期）。 */
  remainingDays: number
  /** 是否已过期。 */
  expired: boolean
  /** 仅 end_date 时仍显示剩余天数文本（环退化为占位）。 */
  showRemainingText: boolean
}

/**
 * 把 'YYYY-MM-DD' 字符串解析为本地零点 Date（避免时区误差）。
 *
 * @param s 日期字符串（可能为 null / 空串 / 非法格式）。
 * @returns 本地零点 Date；无法解析时返回 null。
 */
function toDateOnly(s: string | null): Date | null {
  if (!s) return null
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(s)
  if (!m) return null
  const y = Number(m[1])
  const mo = Number(m[2])
  const d = Number(m[3])
  const date = new Date(y, mo - 1, d)
  // 拦截 2026-02-31 这类被 Date 自动进位的非法日期。
  if (date.getFullYear() !== y || date.getMonth() !== mo - 1 || date.getDate() !== d) {
    return null
  }
  return date
}

/**
 * 计算目标时间进度（三态规则，spec 裁定④）。
 *
 * 规则：
 * - end 为空         → showRing=false, showRemainingText=false（模板渲染「未设置截止日期」）；
 * - end 非空         → remainingDays = 截止 − 今天（本地零点比较），负数为 expired；
 * - start 也非空     → showRing=true，percent = clamp(floor(已过/总天数 × 100), 0, 100)，
 *                      expired 时固定 100（后端已保证 end ≥ start，此处防御 total ≤ 0）；
 * - 仅 end 无 start  → showRing=false, showRemainingText=true（环退化占位，天数仍展示）。
 *
 * @param start 开始日期 'YYYY-MM-DD'（可空）。
 * @param end 截止日期 'YYYY-MM-DD'（可空）。
 * @param today 当前时间（默认 new Date()，供测试注入）。
 * @returns GoalProgress。
 */
export function calcGoalProgress(
  start: string | null,
  end: string | null,
  today: Date = new Date(),
): GoalProgress {
  const todayOnly = new Date(today.getFullYear(), today.getMonth(), today.getDate())
  const endD = toDateOnly(end)

  // 态三：未设置截止日期 —— 不算环、不算天数（杜绝除零 / NaN）。
  if (!end || endD === null) {
    return { showRing: false, percent: 0, remainingDays: 0, expired: false, showRemainingText: false }
  }

  const remainingDays = Math.round((endD.getTime() - todayOnly.getTime()) / DAY_MS)
  const expired = remainingDays < 0

  const startD = toDateOnly(start)
  // 态二：仅有截止日期 —— 环退化占位，仅显示剩余天数文本。
  if (!start || startD === null) {
    return { showRing: false, percent: 0, remainingDays, expired, showRemainingText: true }
  }

  // 态一：起止齐全 —— 渲染进度环。
  const totalDays = Math.round((endD.getTime() - startD.getTime()) / DAY_MS)
  let percent: number
  if (expired || totalDays <= 0) {
    percent = 100
  } else {
    const elapsed = Math.round((todayOnly.getTime() - startD.getTime()) / DAY_MS)
    percent = Math.min(100, Math.max(0, Math.floor((elapsed / totalDays) * 100)))
  }
  return { showRing: true, percent, remainingDays, expired, showRemainingText: false }
}

// ---------------------------------------------------------------------------
// ECharts 树图数据转换
// ---------------------------------------------------------------------------

/** ECharts tree 节点（与 RoadmapNode 同构，仅多 collapsed 折叠标记）。 */
export interface EChartsTreeNode {
  name: string
  children: EChartsTreeNode[]
  collapsed?: boolean
}

/**
 * RoadmapNode → ECharts tree 数据（注入默认折叠状态）。
 *
 * 折叠策略（按用户实测规模 104 节点 / 7 顶层分支裁定，调整为 depth > 1）：
 * 第 1 层（根 + 顶层领域）展开、第 2 层起默认折叠 —— 初始仅 ~8 个节点，
 * 避免原 depth > 2（初始 ~43 节点、~35 行叶子）在抽屉 ~600px 内容区内
 * 被 ECharts 自适应缩放压至标签重叠；用户逐层点击增量展开（每次 3~7
 * 节点），配合 series.roam 缩放平移浏览全树。Canvas 渲染性能两档均无
 * 压力，本裁定依据为视觉可读性。
 *
 * @param node 后端知识树节点。
 * @param depth 当前层级（根为 1，内部递归用）。
 * @returns EChartsTreeNode（collapsed: depth > 1）。
 */
export function toEChartsTree(node: RoadmapNode, depth = 1): EChartsTreeNode {
  return {
    name: node.name,
    collapsed: depth > 1,
    children: node.children.map((c) => toEChartsTree(c, depth + 1)),
  }
}

/**
 * 统计知识树叶子节点数（即「知识点」数，已入掌握度体系）。
 *
 * @param node 知识树节点。
 * @returns 叶子节点总数（树内同名叶子按多次计，展示口径用）。
 */
export function countLeaves(node: RoadmapNode): number {
  if (!node.children || node.children.length === 0) return 1
  return node.children.reduce((sum, c) => sum + countLeaves(c), 0)
}

// ---------------------------------------------------------------------------
// 拆解失败二分类（spec 裁定⑧）
// ---------------------------------------------------------------------------

/**
 * 拆解失败分类文案（两类不得共用同一条模糊提示）。
 *
 * 分类依据为后端 message 关键字（同为 code=3000，以 message 区分的既定
 * 裁定，不引入额外传输字段）；连续两类失败先后发生时文案随类别变化。
 *
 * @param error catch 到的异常（可能是 Error、axios 错误或字符串）。
 * @returns 分类后的展示文案。
 */
export function breakdownErrorMessage(error: unknown): string {
  // 前端 90s 超时：axios 以 ECONNABORTED 拒绝 → 服务类。
  if (axios.isAxiosError(error) && error.code === 'ECONNABORTED') {
    return 'AI 服务暂时不可用，请稍后重试'
  }
  const message = error instanceof Error ? error.message : String(error ?? '')
  if (message.includes('AI 解析失败')) {
    return 'AI 解析失败，请重试'
  }
  if (message.includes('AI 服务暂时不可用')) {
    return 'AI 服务暂时不可用，请稍后重试'
  }
  if (message.includes('AI 服务未配置')) {
    return 'AI 服务未配置，请联系管理员或检查环境变量'
  }
  // 1007 互斥等业务冲突直接透出原文案；空 message 兜底。
  return message || 'AI 拆解失败，请重试'
}