<script setup lang="ts">
/**
 * 参考来源折叠卡（P9，design.md 2.6.4 / spec 5.4.1）。
 *
 * 卡片内容：来源标题（source_title）+ 片段摘要（折叠两行 / 展开
 * 全文）+ 相似度徽章（保留 2 位，沿用 SearchPanel 惯例）+ 归属徽章
 * （个人库 primary）+ 右上角 [n] 序号（与回答中引用编号一一对应）。
 *
 * 同文档多片段不去重合并：逐条独立卡片、编号连续（spec 5.4.1
 * 规则 6）。跳转：emit navigate 由视图统一 router.push；item_id
 * 为空（脏快照防御）时按钮禁用降级为纯展示。
 */
import { computed, ref } from 'vue'

import type { QaSourceItem } from '@/types'
import { renderInlineMarkdown } from '@/utils/markdown'

const props = defineProps<{
  /** 来源条目（sources 事件 / 历史快照同构）。 */
  source: QaSourceItem
  /** 引用编号（从 1 开始，与回答中 [n] 对应）。 */
  index: number
}>()

const emit = defineEmits<{
  (e: 'navigate', source: QaSourceItem): void
}>()

const expanded = ref(false)

/** 归属徽章类型（仅个人库）。 */
const scopeTagType = computed(() => 'primary' as const)

/** 归属徽章文案（仅个人库）。 */
const scopeLabel = computed(() => '个人库')

/** 相似度展示（保留 2 位，与 SearchPanel 同口径）。 */
const fmtScore = computed(() => props.source.score.toFixed(2))

/** 是否可跳转（item_id 缺失的脏快照防御）。 */
const canNavigate = computed(() => props.source.item_id != null)

function onCardClick(): void {
  if (canNavigate.value) {
    emit('navigate', props.source)
  }
}
</script>

<template>
  <div class="source-card" :class="{ clickable: canNavigate }" @click="onCardClick">
    <div class="source-head">
      <span class="source-index">[{{ props.index }}]</span>
      <span class="source-title" :title="props.source.source_title">
        {{ props.source.source_title }}
      </span>
      <el-tag size="small" :type="scopeTagType" effect="plain" class="source-scope">
        {{ scopeLabel }}
      </el-tag>
    </div>
    <p class="source-content" :class="{ collapsed: !expanded }">
      <span v-html="renderInlineMarkdown(props.source.content)" />
    </p>
    <div class="source-foot">
      <span class="source-score">相似度 {{ fmtScore }}</span>
      <el-button
        v-if="canNavigate"
        link
        type="primary"
        size="small"
        @click.stop="onCardClick"
      >
        查看原文
      </el-button>
      <el-button link size="small" @click.stop="expanded = !expanded">
        {{ expanded ? '收起' : '展开全文' }}
      </el-button>
    </div>
  </div>
</template>

<style scoped>
.source-card {
  padding: 9px 11px;
  background: var(--paper-3);
  border: 1px solid var(--line);
  border-radius: var(--radius);
  transition: border-color 0.16s var(--ease), background-color 0.16s var(--ease);
}

.source-card.clickable {
  cursor: pointer;
}

.source-card.clickable:hover {
  border-color: var(--vermilion);
  background: var(--vermilion-wash);
}

.source-head {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 5px;
}

.source-index {
  flex: 0 0 auto;
  font-family: var(--font-mono);
  font-size: 10px;
  font-weight: 600;
  color: var(--vermilion);
}

.source-title {
  flex: 1 1 auto;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 11px;
  color: var(--ink-2);
}

.source-scope {
  flex: 0 0 auto;
}

.source-content {
  margin: 0 0 6px;
  font-size: 11px;
  line-height: 1.7;
  color: var(--ink-3);
  white-space: pre-wrap;
  word-break: break-word;
}

.source-content.collapsed {
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.source-foot {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.source-score {
  font-family: var(--font-mono);
  font-size: 9px;
  color: var(--ink-4);
}
</style>