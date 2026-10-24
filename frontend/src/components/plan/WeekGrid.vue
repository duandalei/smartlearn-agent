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
            ]"
          >
            <span v-if="highlightOf(item)" class="hl-badge">{{ highlightBadge(item) }}</span>
            <div class="item-topic">{{ item.topic }}</div>
            <div class="item-time">{{ formatHm(item.start_time) }} ~ {{ formatHm(item.end_time) }}</div>
            <template v-if="!props.compact">
              <div v-if="item.estimated_minutes != null" class="item-minutes">
                约 {{ item.estimated_minutes }} 分钟
              </div>
              <el-tag v-if="item.task_id != null" size="small" effect="plain" class="task-tag">
                关联任务
              </el-tag>
              <span v-if="item.status === 'done'" class="done-mark">✓</span>
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
}
.week-grid {
  display: grid;
  grid-template-columns: 72px repeat(7, minmax(120px, 1fr));
  gap: 4px;
  min-width: 912px;
}
.cell {
  min-height: 40px;
}
.corner {
  background: transparent;
}
.col-head {
  text-align: center;
  font-size: 13px;
  font-weight: 600;
  color: var(--el-text-color-primary);
  padding: 6px 4px;
  background: var(--el-fill-color-light);
  border-radius: 4px;
}
.row-head {
  display: flex;
  align-items: flex-start;
  justify-content: center;
  padding-top: 10px;
  font-size: 13px;
  color: var(--el-text-color-secondary);
  background: var(--el-fill-color-light);
  border-radius: 4px;
}
.slot-cell {
  background: var(--el-fill-color-lighter);
  border-radius: 4px;
  padding: 4px;
}
.item-card {
  position: relative;
  background: var(--el-bg-color);
  border-radius: 4px;
  padding: 6px 8px;
  margin-bottom: 4px;
  font-size: 12px;
  border: 1px solid transparent;
}
/* 状态标注：仅依据条目自身 status 字段（spec §5.1.1 规则 6） */
.item-card.is-planned {
  border-left: 3px solid var(--el-color-warning);
}
.item-card.is-done {
  opacity: 0.65;
}
.item-card.is-done .item-topic {
  color: var(--el-text-color-secondary);
}
.item-card.is-skipped {
  opacity: 0.65;
}
.item-card.is-skipped .item-topic {
  text-decoration: line-through;
  color: var(--el-text-color-secondary);
}
.item-topic {
  color: var(--el-text-color-primary);
  line-height: 1.4;
}
.item-time {
  margin-top: 2px;
  color: var(--el-text-color-secondary);
}
.item-minutes {
  margin-top: 2px;
  color: var(--el-text-color-placeholder);
}
.task-tag {
  margin-top: 4px;
}
.done-mark {
  position: absolute;
  top: 4px;
  right: 6px;
  color: var(--el-color-success);
  font-weight: 600;
}
/* diff 高亮（compact 双栏） */
.item-card.is-highlight-moved {
  border-color: var(--el-color-warning);
}
.item-card.is-highlight-added {
  border-color: var(--el-color-success);
}
.item-card.is-highlight-removed {
  border-color: var(--el-color-danger);
}
.hl-badge {
  position: absolute;
  top: -8px;
  right: 4px;
  font-size: 10px;
  line-height: 1.4;
  padding: 0 4px;
  border-radius: 3px;
  color: var(--el-bg-color);
  background: var(--el-color-warning);
}
.is-highlight-added .hl-badge {
  background: var(--el-color-success);
}
.is-highlight-removed .hl-badge {
  background: var(--el-color-danger);
}
/* compact 缩略形态：缩小内边距与字号（diff 双栏复用） */
.compact .item-card {
  padding: 4px 6px;
  font-size: 11px;
}
/* compact 列宽收窄：双栏各占一半时仍能并排容纳 7 天（1440px 视口），
   极窄屏由 min-width + .week-grid-scroll 内部横向滚动兜底。 */
.compact .week-grid {
  grid-template-columns: 56px repeat(7, minmax(0, 1fr));
  min-width: 560px;
}
/* compact 关闭状态视觉（design 2.4.2-5 仅 topic + 时间），diff 高亮边框保留 */
.compact .item-card.is-planned:not(.is-highlight-moved):not(.is-highlight-added):not(.is-highlight-removed) {
  border-left-color: transparent;
}
.compact .item-card.is-done,
.compact .item-card.is-skipped {
  opacity: 1;
}
.compact .item-card.is-done .item-topic,
.compact .item-card.is-skipped .item-topic {
  color: var(--el-text-color-primary);
  text-decoration: none;
}
.compact .col-head,
.compact .row-head {
  font-size: 12px;
}
.rest-cell {
  padding: 4px;
}
.rest-card {
  background: var(--el-fill-color);
  border-radius: 4px;
  padding: 4px 8px;
  margin-bottom: 4px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
  text-align: center;
}
</style>