<script setup lang="ts">
/**
 * Agent 来源区容器（L2 agent_absorb_ask，spec §5.2.1 / design 2.2.2-(3)）。
 *
 * import 复用 ask 域 SourceCard，零复制、ask 资产零改动（design
 * §1.2.5——SourceCard 转为跨域活代码）；「参考来源」小标题 + 逐条
 * 卡片（index 从 1 连续编号，与回答中 [n] 引用序号对齐）。
 *
 * 空集合由父级 v-if 拦截，本组件不处理空态；单条 item_id 为空的
 * 降级由 SourceCard 内部 canNavigate 自治（纯展示、无跳转按钮）；
 * navigate 原样上抛不拦截（父级统一 router.push）。
 */
import { computed } from 'vue'

import type { QaSourceItem } from '@/types'

import SourceCard from '@/components/ask/SourceCard.vue'

const props = defineProps<{
  /** 规范化后的来源集合（父级保证非空才挂载）。 */
  sources: QaSourceItem[]
  /** 回答实际引用的序号（1-based）；仅这些来源进入卡片区。 */
  citedIndices?: number[]
}>()

const emit = defineEmits<{
  (e: 'navigate', source: QaSourceItem): void
}>()

/** 只展示回答实际引用的来源；未引用命中留在工具卡中审计。 */
const visibleSources = computed(() =>
  props.sources
    .map((source, index) => ({ source, index: index + 1 }))
    .filter((item) =>
      props.citedIndices === undefined
        ? true
        : props.citedIndices.includes(item.index),
    ),
)
</script>

<template>
  <div v-if="visibleSources.length" class="knowledge-sources">
    <div class="sources-title">参考来源</div>
    <SourceCard
      v-for="item in visibleSources"
      :key="`${item.source.item_id ?? 'x'}-${item.source.chunk_index ?? 'x'}-${item.index}`"
      :source="item.source"
      :index="item.index"
      @navigate="(s) => emit('navigate', s)"
    />
  </div>
</template>

<style scoped>
.knowledge-sources {
  display: flex;
  flex-direction: column;
  gap: 6px;
  margin-top: 4px;
}
.sources-title {
  font-size: 12px;
  color: var(--el-text-color-placeholder);
}
</style>