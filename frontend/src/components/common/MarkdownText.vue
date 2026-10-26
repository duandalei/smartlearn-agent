<script setup lang="ts">
/**
 * Markdown 文本渲染（L2 体验补丁，零依赖）。
 *
 * AI 回答常含标题 / 粗体 / 列表 / 代码块；这里统一用安全子集渲染，
 * 原始 HTML 先转义，只输出白名单标签（详见 utils/markdown.ts）。
 * 用于 Agent 消息、Ask 气泡与报告摘要，避免各页面各写一套。
 */
import { computed } from 'vue'

import { renderMarkdown } from '@/utils/markdown'

const props = defineProps<{
  content: string | null | undefined
}>()

const html = computed(() => renderMarkdown(props.content ?? ''))
</script>

<template>
  <div class="markdown-body" v-html="html" />
</template>

<style scoped>
.markdown-body {
  white-space: normal;
  word-break: break-word;
  line-height: 1.78;
  color: var(--ink-2);
}

.markdown-body :deep(p) {
  margin: 0 0 8px;
}

.markdown-body :deep(p:last-child) {
  margin-bottom: 0;
}

.markdown-body :deep(h1),
.markdown-body :deep(h2),
.markdown-body :deep(h3),
.markdown-body :deep(h4),
.markdown-body :deep(h5),
.markdown-body :deep(h6) {
  margin: 16px 0 7px;
  font-family: var(--font-display);
  font-weight: 600;
  line-height: 1.45;
  color: var(--ink);
}

.markdown-body :deep(h1) {
  font-size: 19px;
}

.markdown-body :deep(h2) {
  font-size: 17px;
}

.markdown-body :deep(h3) {
  font-size: 15px;
}

.markdown-body :deep(h4),
.markdown-body :deep(h5),
.markdown-body :deep(h6) {
  font-size: 14px;
}

.markdown-body :deep(h1:first-child),
.markdown-body :deep(h2:first-child),
.markdown-body :deep(h3:first-child) {
  margin-top: 0;
}

.markdown-body :deep(ul),
.markdown-body :deep(ol) {
  margin: 4px 0 9px;
  padding-left: 20px;
}

.markdown-body :deep(li) {
  margin: 3px 0;
}

.markdown-body :deep(li::marker) {
  color: var(--vermilion);
}

.markdown-body :deep(strong) {
  font-weight: 600;
  color: var(--ink);
}

.markdown-body :deep(em) {
  font-style: italic;
}

.markdown-body :deep(del) {
  color: var(--ink-3);
}

.markdown-body :deep(code) {
  padding: 1px 5px;
  border-radius: var(--radius);
  background: var(--paper-3);
  border: 1px solid var(--line-soft);
  font-family: var(--font-mono);
  font-size: 12px;
  color: var(--ink-2);
}

.markdown-body :deep(pre) {
  margin: 9px 0;
  padding: 10px 12px;
  overflow-x: auto;
  border-radius: var(--radius);
  background: var(--paper-3);
  border: 1px solid var(--line);
}

.markdown-body :deep(pre code) {
  padding: 0;
  background: transparent;
  border: none;
  white-space: pre;
}

.markdown-body :deep(blockquote) {
  margin: 9px 0;
  padding: 9px 12px;
  background: var(--paper-3);
  border: 1px solid var(--line);
  border-radius: var(--radius);
  color: var(--ink-3);
}

.markdown-body :deep(blockquote p) {
  margin: 0;
}

.markdown-body :deep(hr) {
  margin: 14px 0;
  border: 0;
  border-top: 1px solid var(--line);
}

.markdown-body :deep(a) {
  color: var(--vermilion);
  text-decoration: none;
  text-underline-offset: 3px;
}

.markdown-body :deep(a:hover) {
  text-decoration: underline;
}

.markdown-body :deep(table) {
  width: 100%;
  margin: 9px 0;
  border-collapse: collapse;
  font-size: 12px;
}

.markdown-body :deep(th),
.markdown-body :deep(td) {
  padding: 5px 7px;
  border: 1px solid var(--line);
  text-align: left;
  vertical-align: top;
}

.markdown-body :deep(th) {
  background: var(--paper-3);
  font-weight: 600;
  color: var(--ink);
}
</style>
