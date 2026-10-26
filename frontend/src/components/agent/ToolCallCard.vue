<script setup lang="ts">
/**
 * 工具调用卡片（P11 前端，design 2.4.1——评审核心可视化载体）。
 *
 * 四态纯数据驱动（决策 A3——无模式 prop，实时流与历史回放共用
 * 同一组件保证样式一致，F8 的编译期保证）：
 * - `call.result === null` → 调用中（Loading 旋转 +「正在调用
 *   name(args)…」，同为 36px 单行——决策 A7 零高度跳变）；
 * - `result.ok === false` → 失败（CircleClose + 警示边框底色，
 *   完成态的警示变体，可展开）；
 * - `expanded === true` → 展开（头部行 36px + 详情区）；
 * - 否则 → 完成折叠（CircleCheck +「✓ name · 耗时 · 摘要」单行）。
 *
 * 高度控制（用户设计重点 ①，design 2.4.1-B）：折叠行锁定 36px
 * （CSS 变量 --toolcard-row-height）+ 全列 nowrap/ellipsis 永不换行；
 * 堆叠 gap 6px → 4 连卡片 = 4×36+3×6 = 162px ≤ 对话区 1/3
 * （500px 保守估算 1/3 ≈ 167px ✓）——对话不被卡片淹没。自绘
 * div+CSS 折叠卡（决策 A9：el-collapse 结构内 36px 像素级锁定不可达）。
 */
import { computed, ref } from 'vue'
import { ArrowDown, ArrowRight, CircleCheck, CircleClose, Loading } from '@element-plus/icons-vue'

import type { ToolCallView } from '@/types/agent'

/** 折叠行锁定高度（design 2.4.1-B 视觉规格）。 */
const TOOLCARD_ROW_HEIGHT = 36

/** 参数值紧凑显示截断长度（spec §5.4.1 规则 1：超 20 字符截断加省略号）。 */
const ARG_VALUE_MAX_LEN = 20

/** 耗时格式化阈值（ms → s 换算，<1000 显示 ms）。 */
const ELAPSED_S_THRESHOLD = 1000

const props = defineProps<{
  /** 工具调用视图（result===null 即调用中态）。 */
  call: ToolCallView
}>()

const emit = defineEmits<{
  (e: 'toggle', callId: string, expanded: boolean): void
}>()

/** 展开态（默认折叠——spec §5.4.1 规则 3）。 */
const expanded = ref(false)

/** 卡片当前态（纯数据驱动）。 */
const isPending = computed(() => props.call.result === null)
const isFailed = computed(() => props.call.result !== null && !props.call.result.ok)

/** 参数紧凑串：对象 → key=value 逗号连接；字符串（历史容错降级）→ 原文截断。 */
const argsCompact = computed((): string => {
  const args = props.call.arguments
  if (typeof args === 'string') return args.length > ARG_VALUE_MAX_LEN ? `${args.slice(0, ARG_VALUE_MAX_LEN)}…` : args
  const entries = Object.entries(args)
  if (!entries.length) return ''
  return entries
    .map(([key, value]) => {
      const text = String(value)
      const brief = text.length > ARG_VALUE_MAX_LEN ? `${text.slice(0, ARG_VALUE_MAX_LEN)}…` : text
      return `${key}=${brief}`
    })
    .join(', ')
})

/** 调用中文案：name(args)（空参显示 name()）。 */
const callLabel = computed(
  () => `${props.call.name}(${argsCompact.value})`,
)

/** 耗时格式化：<1000 → '8ms'；≥1000 → '1.2s'（一位小数）；null → 空。 */
const elapsedText = computed((): string => {
  const ms = props.call.result?.elapsed_ms
  if (ms == null) return ''
  return ms < ELAPSED_S_THRESHOLD ? `${ms}ms` : `${(ms / ELAPSED_S_THRESHOLD).toFixed(1)}s`
})

/** 展开态详情内容：历史卡格式化 JSON；实时卡 summary 全文。 */
const detailContent = computed((): string => {
  const result = props.call.result
  if (!result) return ''
  if (result.raw_content != null) {
    // 历史回放：完整结果 JSON 格式化（解析失败降级原文——spec §5.6 规则 4）。
    try {
      return JSON.stringify(JSON.parse(result.raw_content), null, 2)
    } catch {
      return result.raw_content
    }
  }
  return result.summary
})

/** 展开态是否显示截断标记（实时卡 summary 服务端已截断时）。 */
const detailTruncated = computed(
  () => props.call.result?.raw_content == null && props.call.result?.truncated === true,
)

/** 把原始 JSON 摘要压成一句可读的话（完整 JSON 仍保留在展开区审计）。 */
function readableSummary(raw: string): string {
  const text = raw.trim()
  if (!text) return '已完成'
  if (!text.startsWith('{') && !text.startsWith('[')) return text
  try {
    const data: unknown = JSON.parse(text)
    if (
      props.call.name === 'search_knowledge_base' &&
      data != null &&
      typeof data === 'object' &&
      Array.isArray((data as { results?: unknown }).results)
    ) {
      return `检索到 ${(data as { results: unknown[] }).results.length} 条资料`
    }
    if (Array.isArray(data)) return `返回 ${data.length} 条结果`
    if (data != null && typeof data === 'object') {
      const keys = Object.keys(data)
      if (keys.length > 0 && keys.length <= 4) return `${keys.join('、')} 已返回`
    }
  } catch {
    // 非 JSON 或解析失败：走通用文案
  }
  return '已完成'
}

/** 失败态摘要（服务端下发的中文错误说明，error 色）。 */
const summaryText = computed((): string => {
  const result = props.call.result
  if (!result) return ''
  if (!result.ok) return result.summary || '工具执行失败'
  return readableSummary(result.summary)
})

/** 头部行可点击（调用中态整卡不可点）。 */
function onToggle(): void {
  if (isPending.value) return
  expanded.value = !expanded.value
  emit('toggle', props.call.call_id, expanded.value)
}
</script>

<template>
  <!-- 失败态警示变体：警示边框 + 极浅警示底（design 2.4.1-A 四态规格） -->
  <div class="tool-card" :class="{ failed: isFailed, pending: isPending }">
    <div class="tool-row" :class="{ clickable: !isPending }" @click="onToggle">
      <!-- 状态图标区 22px -->
      <span class="status-icon">
        <el-icon v-if="isPending" class="is-loading" :size="16"><Loading /></el-icon>
        <el-icon v-else-if="isFailed" class="fail" :size="16"><CircleClose /></el-icon>
        <el-icon v-else class="ok" :size="16"><CircleCheck /></el-icon>
      </span>
      <!-- 工具名（等宽 600） -->
      <span class="tool-name">{{ props.call.name }}</span>
      <!-- 紧凑参数（secondary） -->
      <span v-if="argsCompact" class="tool-args">({{ argsCompact }})</span>
      <span v-else class="tool-args">()</span>
      <!-- 耗时（历史卡 null 省略） -->
      <span v-if="elapsedText" class="tool-elapsed">{{ elapsedText }}</span>
      <!-- 摘要弹性区（失败态为中文错误说明 error 色） -->
      <span v-if="isPending" class="tool-summary pending-text">正在调用 {{ callLabel }} …</span>
      <span v-else class="tool-summary" :class="{ fail: isFailed }">{{ summaryText }}</span>
      <!-- 展开箭头 -->
      <el-icon v-if="!isPending" class="arrow" :size="14">
        <ArrowDown v-if="expanded" />
        <ArrowRight v-else />
      </el-icon>
    </div>
    <!-- 详情区（惰性渲染——回放性能，design 2.9 风险 2） -->
    <div v-if="expanded && !isPending" class="tool-detail">
      <div class="detail-block">
        <div class="detail-label">参数</div>
        <pre class="detail-pre">{{ props.call.name }}({{ argsCompact }})</pre>
      </div>
      <div class="detail-block">
        <div class="detail-label">{{ props.call.result?.raw_content != null ? '完整结果' : '结果摘要' }}</div>
        <pre class="detail-pre">{{ detailContent }}</pre>
        <div v-if="detailTruncated" class="detail-truncated">…（已截断）</div>
      </div>
    </div>
  </div>
</template>


<style scoped>
.tool-card {
  --toolcard-row-height: 36px;
  border: 1px solid var(--line);
  border-radius: var(--radius);
  overflow: hidden;
  background: var(--paper-2);
}

.tool-card.pending {
  background: var(--paper-3);
}

.tool-card.failed {
  border-color: #d8aaa2;
  background: var(--danger-wash);
}

.tool-row {
  display: flex;
  align-items: center;
  gap: 4px;
  height: var(--toolcard-row-height);
  padding: 0 12px 0 9px;
  box-sizing: border-box;
  white-space: nowrap;
}

.tool-row.clickable {
  cursor: pointer;
}

.tool-row.clickable:hover {
  background: var(--paper-3);
}

.status-icon {
  flex: 0 0 20px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
}

.status-icon .ok {
  color: var(--jade);
}

.status-icon .fail {
  color: var(--vermilion);
}

.tool-name {
  flex: 0 1 auto;
  max-width: 40%;
  overflow: hidden;
  text-overflow: ellipsis;
  font-family: var(--font-mono);
  font-size: 11px;
  font-weight: 600;
  color: var(--ink);
}

.tool-args {
  flex: 0 1 auto;
  max-width: 30%;
  overflow: hidden;
  text-overflow: ellipsis;
  font-family: var(--font-mono);
  font-size: 10px;
  color: var(--ink-3);
}

.tool-elapsed {
  flex: 0 0 auto;
  font-family: var(--font-mono);
  font-size: 9px;
  color: var(--ink-4);
}

.tool-summary {
  flex: 1 1 auto;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  font-size: 11px;
  color: var(--ink-2);
}

.tool-summary.fail {
  color: var(--vermilion);
}

.tool-summary.pending-text {
  color: var(--ink-3);
}

.arrow {
  flex: 0 0 auto;
  color: var(--ink-4);
}

.tool-detail {
  border-top: 1px solid var(--line);
  background: var(--paper-3);
  padding: 10px 12px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.detail-block {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.detail-label {
  font-family: var(--font-mono);
  font-size: 9px;
  letter-spacing: 0.08em;
  color: var(--ink-4);
}

.detail-pre {
  margin: 0;
  padding: 9px 10px;
  border-radius: var(--radius);
  background: var(--paper-2);
  border: 1px solid var(--line);
  font-family: var(--font-mono);
  font-size: 11px;
  line-height: 1.65;
  color: var(--ink-2);
  white-space: pre-wrap;
  word-break: break-word;
  max-height: 240px;
  overflow-y: auto;
}

.detail-truncated {
  font-family: var(--font-mono);
  font-size: 9px;
  color: var(--ink-4);
}
</style>