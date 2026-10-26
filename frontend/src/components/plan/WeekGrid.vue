<script setup lang="ts">
/**
 * 周视图网格（P13；design 2.4.2 / D4 / D13；spec §5.1.1 规则 2/3/4/5/6/9）。
 *
 * 纯展示组件：原生 CSS grid（72px + 7 列，不用 el-table），三时段行 × 7 列
 * + 每列独立休息区块；compact 缩略形态供 diff 双栏复用。零请求、零交互出口
 * （无任何点击编辑/拖拽入口）。
 *
 * 高亮下标映射：markDiffHighlights 的 key 是「items 数组下标」（design 2.4.3），
 * buildWeekGrid 分组后丢失原始下标——渲染前按对象引用建立 indexOf 映射
 * （buildWeekGrid 保留同一对象引用），禁止把 item.id 当 key 查 highlights。
 *
 * 时间显示：后端 time 序列化为 'HH:MM:SS'，一律经 formatHm 截取 'HH:MM'。
 */
import { computed } from 'vue'

import type { ItemHighlight, Plan, PlanItem } from '@/types/plan'
import { buildWeekGrid, formatHm } from '@/utils/plan'

const props = withDefaults(
  defineProps<{
    plan: Plan
    items: PlanItem[]
    compact?: boolean
    highlights?: Map<number, ItemHighlight>
    /** diff 双栏场景的本栏标识（moved 角标「移出/移入」判定依据）；主视图不传。 */
    highlightSide?: 'old' | 'new'
  }>(),
  { compact: false, highlights: undefined, highlightSide: undefined },
)

/** 三时段行（行头 label + slots 键；渲染序与 design 2.2.2-(9) 一致）。 */
const SLOT_ROWS = [
  { key: 'morning', label: '上午' },
  { key: 'afternoon', label: '下午' },
  { key: 'evening', label: '晚上' },
] as const

/** 7 列网格（date/label/slots/rests；越界条目已被纯函数剔除）。 */
const columns = computed(() => buildWeekGrid(props.plan, props.items))

/** 条目对象 → 原数组下标（对象引用做 key，分组后仍可回溯）。 */
const indexOf = computed(() => new Map(props.items.map((it, i) => [it, i])))

/** 条目高亮类别（无 highlights 或匹配不上 → undefined，不渲染不报错）。 */
function highlightOf(item: PlanItem): ItemHighlight | undefined {
  if (!props.highlights) return undefined
  const idx = indexOf.value.get(item)
  return idx === undefined ? undefined : props.highlights.get(idx)
}

/** 高亮角标文案：moved 左栏「移出」/ 右栏「移入」、added「新增」、removed「移除」。 */
function highlightBadge(item: PlanItem): string {
  const h = highlightOf(item)
  if (h === 'moved') return props.highlightSide === 'old' ? '移出' : '移入'
  if (h === 'added') return '新增'
  if (h === 'removed') return '移除'
  return ''
}
</script>

<template>
  <div class="week-grid-scroll" :class="{ compact: props.compact }">
    <div class="week-grid">
      <!-- 列头行：首格留空（时段行头列） -->
      <div class="cell corner" />
      <div v-for="col in columns" :key="col.date" class="cell col-head">{{ col.label }}</div>

      <!-- 三时段行 × 7 列 -->
      <template v-for="row in SLOT_ROWS" :key="row.key">
        <div class="cell row-head">{{ row.label }}</div>
        <div v-for="col in columns" :key="col.date" class="cell slot-cell">
          <div
            v-for="item in col.slots[row.key]"
            :key="item.id"
            class="item-card"
            :class="[
              `is-${item.status}`,
              highlightOf(item) ? `is-highlight-${highlightOf(item)}` : '',
              { 'has-badge': highlightOf(item) },
            ]"
          >
            <span v-if="highlightOf(item)" class="hl-badge">{{ highlightBadge(item) }}</span>
            <div class="item-topic-row">
              <span class="item-status" :class="`is-${item.status}`" aria-hidden="true" />
              <span class="item-topic">{{ item.topic }}</span>
            </div>
            <div class="item-time">{{ formatHm(item.start_time) }} ~ {{ formatHm(item.end_time) }}</div>
            <template v-if="!props.compact">
              <div v-if="item.estimated_minutes != null" class="item-minutes">
                约 {{ item.estimated_minutes }} 分钟
              </div>
              <span v-if="item.task_id != null" class="task-chip">任务</span>
              <span v-if="item.status === 'done'" class="done-mark" aria-label="已完成">✓</span>
            </template>
          </div>
        </div>
      </template>

      <!-- 休息区块行：每列独立；无 rest 条目的列空白占位维持列对齐 -->
      <div class="cell row-head">休息</div>
      <div v-for="col in columns" :key="col.date" class="cell rest-cell">
        <div v-for="item in col.rests" :key="item.id" class="rest-card">{{ item.topic }}</div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.week-grid-scroll {
  overflow-x: auto;
  background: var(--line);
  border: 1px solid var(--line);
  border-radius: var(--radius);
}

.week-grid {
  display: grid;
  grid-template-columns: 64px repeat(7, minmax(118px, 1fr));
  gap: 1px;
  min-width: 920px;
  background: var(--line);
}

.cell {
  min-height: 40px;
  background: var(--paper-2);
}

.corner {
  background: var(--paper-3);
}

.col-head {
  padding: 10px 4px;
  text-align: center;
  font-family: var(--font-display);
  font-size: 13px;
  font-weight: 600;
  color: var(--ink);
  background: var(--paper-3);
}

.row-head {
  display: flex;
  align-items: flex-start;
  justify-content: center;
  padding-top: 12px;
  font-family: var(--font-display);
  font-size: 12px;
  color: var(--ink-3);
  background: var(--paper-3);
}

.slot-cell {
  min-height: 82px;
  padding: 6px;
  background: var(--paper-2);
}

.item-card {
  position: relative;
  padding: 7px 8px;
  margin-bottom: 5px;
  font-size: 12px;
  background: var(--paper-3);
  border: 1px solid var(--line-soft);
  border-radius: var(--radius);
  transition: border-color 0.16s var(--ease), background-color 0.16s var(--ease);
}

.item-card:last-child {
  margin-bottom: 0;
}

.item-card:hover {
  border-color: var(--line-strong);
}

.item-topic-row {
  display: flex;
  align-items: flex-start;
  gap: 6px;
}

.item-card.has-badge .item-topic-row {
  padding-right: 34px;
}

/* 状态标注：小方块 + 文字状态，不只靠颜色 */
.item-status {
  width: 5px;
  height: 5px;
  flex: 0 0 5px;
  margin-top: 5px;
  border-radius: 1px;
  background: var(--dust);
}

.item-status.is-planned {
  background: var(--vermilion);
}

.item-status.is-done {
  background: var(--jade);
}

.item-status.is-skipped {
  background: var(--ink-4);
}

.item-topic {
  min-width: 0;
  line-height: 1.45;
  color: var(--ink);
  font-weight: 500;
  word-break: break-word;
}

.item-card.is-done {
  opacity: 0.72;
}

.item-card.is-done .item-topic {
  color: var(--ink-3);
}

.item-card.is-skipped {
  opacity: 0.62;
}

.item-card.is-skipped .item-topic {
  color: var(--ink-3);
  text-decoration: line-through;
}

.item-time {
  margin-top: 3px;
  font-family: var(--font-mono);
  font-size: 9px;
  color: var(--ink-4);
}

.item-minutes {
  margin-top: 2px;
  font-family: var(--font-mono);
  font-size: 9px;
  color: var(--ink-4);
}

.task-chip {
  display: inline-block;
  margin-top: 4px;
  padding: 0 4px;
  font-family: var(--font-mono);
  font-size: 8px;
  line-height: 14px;
  color: var(--ink-3);
  background: var(--paper-2);
  border: 1px solid var(--line);
  border-radius: var(--radius);
}

.done-mark {
  position: absolute;
  top: 5px;
  right: 7px;
  color: var(--jade);
  font-weight: 700;
  line-height: 1;
}

/* diff 高亮（compact 双栏） */
.item-card.is-highlight-moved {
  border-color: var(--ochre);
  background: var(--ochre-wash);
}

.item-card.is-highlight-added {
  border-color: var(--jade);
  background: var(--jade-wash);
}

.item-card.is-highlight-removed {
  border-color: var(--vermilion);
  background: var(--danger-wash);
}

.hl-badge {
  position: absolute;
  top: 3px;
  right: 3px;
  padding: 0 4px;
  font-family: var(--font-mono);
  font-size: 8px;
  line-height: 14px;
  color: var(--paper-2);
  background: var(--ochre);
  border-radius: 1px;
}

.is-highlight-added .hl-badge {
  background: var(--jade);
}

.is-highlight-removed .hl-badge {
  background: var(--vermilion);
}

/* compact 缩略形态：缩小内边距与字号（diff 双栏复用） */
.compact .item-card {
  padding: 4px 6px;
  font-size: 11px;
}

.compact .week-grid {
  grid-template-columns: 52px repeat(7, minmax(0, 1fr));
  min-width: 560px;
}

.compact .slot-cell {
  min-height: 54px;
  padding: 4px;
}

.compact .item-card.is-done,
.compact .item-card.is-skipped {
  opacity: 1;
}

.compact .item-card.is-done .item-topic,
.compact .item-card.is-skipped .item-topic {
  color: var(--ink);
  text-decoration: none;
}

.compact .col-head,
.compact .row-head {
  font-size: 11px;
}

.compact .col-head {
  padding: 7px 3px;
}

.compact .row-head {
  padding-top: 9px;
}

.rest-cell {
  padding: 6px;
}

.rest-card {
  padding: 4px 6px;
  margin-bottom: 4px;
  font-size: 10px;
  line-height: 1.5;
  color: var(--ink-3);
  text-align: center;
  background: var(--paper-3);
  border: 1px dashed var(--line);
  border-radius: var(--radius);
}
</style>