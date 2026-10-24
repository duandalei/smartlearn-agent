<script setup lang="ts">
/**
 * diff 预览双栏对比（P13；design 2.4.4 / D6 / D13；spec §5.3.1 规则 2/3/6，裁定 #2）。
 *
 * 四段结构：① adjust_reason 显著卡片 ② 双栏 WeekGrid（compact + highlights）
 * ③ 结构化改动清单 ④ 操作区。「查看调整后的计划」（primary）与「关闭对比」
 * （close）共用同一 confirm 出口、以 source 参数区分路径（关闭路径父组件追加
 * 「新计划已生效」提示，spec §5.3.1 规则 6；ESC 与「关闭对比」同路径）；
 * 不提供任何回退调整的操作。
 *
 * 数据来源铁律（spec §5.3.1 规则 4-⑤）：右栏条目一律为 pending.items
 * （服务端取回），严禁用 oldItems + diff 前端重建。
 *
 * 高亮下标映射：markDiffHighlights 的 key 是各栏 items 数组下标——分别对
 * oldItems / items 调用并传入对应 WeekGrid，由 WeekGrid 内部按对象引用回溯
 * 下标，禁止把 item.id 当 key。
 */
import { computed, onMounted, onUnmounted } from 'vue'

import type { PendingNewPlan } from '@/types/plan'
import { formatHm, markDiffHighlights } from '@/utils/plan'
import WeekGrid from '@/components/plan/WeekGrid.vue'

const props = defineProps<{
  pending: PendingNewPlan
}>()

const emit = defineEmits<{
  (e: 'confirm', source: 'primary' | 'close'): void
}>()

/** ESC 与「关闭对比」同路径（source='close'，父组件提示「新计划已生效」）。 */
function onKeydown(e: KeyboardEvent): void {
  if (e.key === 'Escape') emit('confirm', 'close')
}
onMounted(() => window.addEventListener('keydown', onKeydown))
onUnmounted(() => window.removeEventListener('keydown', onKeydown))

/** 左栏（原计划）高亮：moved 标「移出」、removed 标「移除」。 */
const oldHighlights = computed(() =>
  markDiffHighlights(props.pending.oldItems, props.pending.diff, 'old'),
)
/** 右栏（新计划）高亮：moved 标「移入」、added 标「新增」。 */
const newHighlights = computed(() =>
  markDiffHighlights(props.pending.items, props.pending.diff, 'new'),
)

/** 三类清单是否全空（spec §5.3.3 场景 3：显示「本次调整无条目变动」）。 */
const isDiffEmpty = computed(() => {
  const d = props.pending.diff
  return d.moved.length === 0 && d.added.length === 0 && d.removed.length === 0
})

/** 时间位展示：null → 「休息时段」；否则 formatHm 截取 'HH:MM'。 */
function hmOrRest(t: string | null): string {
  return t == null ? '休息时段' : formatHm(t)
}
</script>

<template>
  <div class="diff-preview">
    <!-- ① 调整理由显著卡片（禁止折叠默认隐藏） -->
    <div class="reason-card">
      <div class="reason-title">调整说明</div>
      <div class="reason-text">{{ pending.adjustReason ?? '本次调整未提供说明' }}</div>
    </div>

    <!-- ② 双栏对比（compact 缩略 + 高亮） -->
    <div class="dual-pane">
      <div class="pane">
        <div class="pane-title">原计划（v{{ pending.plan.version - 1 }}）</div>
        <WeekGrid
          :plan="pending.plan"
          :items="pending.oldItems"
          compact
          :highlights="oldHighlights"
          highlight-side="old"
        />
      </div>
      <div class="pane">
        <div class="pane-title">
          新计划
          <el-tag size="small" type="primary" effect="plain">v{{ pending.plan.version }}</el-tag>
        </div>
        <WeekGrid
          :plan="pending.plan"
          :items="pending.items"
          compact
          :highlights="newHighlights"
          highlight-side="new"
        />
      </div>
    </div>

    <!-- ③ 结构化改动清单 -->
    <div class="change-list">
      <template v-if="!isDiffEmpty">
        <div v-for="(m, i) in pending.diff.moved" :key="`m${i}`" class="change-item">
          {{ m.topic }}：从 {{ m.from_date }} {{ hmOrRest(m.from_time) }} 挪到
          {{ m.to_date }} {{ hmOrRest(m.to_time) }}（{{ m.reason }}）
        </div>
        <div v-for="(r, i) in pending.diff.removed" :key="`r${i}`" class="change-item">
          {{ r.topic }} 被移出计划（{{ r.reason }}）
        </div>
        <div v-for="(a, i) in pending.diff.added" :key="`a${i}`" class="change-item">
          新增：{{ a.topic }}（{{ a.reason }}）
        </div>
      </template>
      <div v-else class="change-empty">本次调整无条目变动</div>
    </div>

    <!-- ④ 操作区：两个按钮共用同一 confirm 出口，source 区分路径 -->
    <div class="actions">
      <el-button type="primary" @click="emit('confirm', 'primary')">查看调整后的计划</el-button>
      <el-button plain @click="emit('confirm', 'close')">关闭对比</el-button>
    </div>
  </div>
</template>

<style scoped>
.diff-preview {
  display: flex;
  flex-direction: column;
  gap: 16px;
}
.reason-card {
  background: var(--el-color-warning-light-9);
  border-left: 4px solid var(--el-color-warning);
  border-radius: 4px;
  padding: 12px 16px;
}
.reason-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--el-text-color-primary);
  margin-bottom: 6px;
}
.reason-text {
  font-size: 15px;
  line-height: 1.7;
  color: var(--el-text-color-primary);
}
.dual-pane {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
  gap: 12px;
}
/* grid item 必须允许收缩到 0，否则 WeekGrid 的 min-width 会把右栏挤出视口；
   各栏内部由 WeekGrid 自己的 overflow-x:auto 横向滚动。 */
.pane {
  min-width: 0;
}
.pane-title {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
  font-weight: 600;
  color: var(--el-text-color-secondary);
  margin-bottom: 8px;
}
.change-list {
  background: var(--el-fill-color-light);
  border-radius: 6px;
  padding: 12px 16px;
}
.change-item {
  font-size: 13px;
  line-height: 2;
  color: var(--el-text-color-primary);
}
.change-empty {
  font-size: 13px;
  color: var(--el-text-color-secondary);
}
.actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
}
</style>