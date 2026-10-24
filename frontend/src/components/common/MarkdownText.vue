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
  line-height: 1.7;
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
  margin: 14px 0 6px;
  font-weight: 600;
  line-height: 1.4;
  color: var(--el-text-color-primary);
}
.markdown-body :deep(h1) {
  font-size: 18px;
}
.markdown-body :deep(h2) {
  font-size: 16px;
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
  margin: 4px 0 8px;
  padding-left: 20px;
}
.markdown-body :deep(li) {
  margin: 3px 0;
}
.markdown-body :deep(strong) {
  font-weight: 600;
}
.markdown-body :deep(em) {
  font-style: italic;
}
.markdown-body :deep(del) {
  color: var(--el-text-color-secondary);
}
.markdown-body :deep(code) {
  padding: 1px 4px;
  border-radius: 3px;
  background: var(--el-fill-color);
  font-family: Consolas, Monaco, 'Courier New', monospace;
  font-size: 13px;
}
.markdown-body :deep(pre) {
  margin: 8px 0;
  padding: 8px 10px;
  overflow-x: auto;
  border-radius: 4px;
  background: var(--el-fill-color-light);
}
.markdown-body :deep(pre code) {
  padding: 0;
  background: transparent;
  white-space: pre;
}
.markdown-body :deep(blockquote) {
  margin: 8px 0;
  padding: 2px 0 2px 10px;
  border-left: 3px solid var(--el-color-info);
  color: var(--el-text-color-secondary);
}
.markdown-body :deep(blockquote p) {
  margin: 0;
}
.markdown-body :deep(hr) {
  margin: 12px 0;
  border: 0;
  border-top: 1px solid var(--el-border-color-lighter);
}
.markdown-body :deep(a) {
  color: var(--el-color-primary);
  text-decoration: none;
}
.markdown-body :deep(a:hover) {
  text-decoration: underline;
}
.markdown-body :deep(table) {
  width: 100%;
  margin: 8px 0;
  border-collapse: collapse;
  font-size: 13px;
}
.markdown-body :deep(th),
.markdown-body :deep(td) {
  padding: 4px 6px;
  border: 1px solid var(--el-border-color-lighter);
  text-align: left;
  vertical-align: top;
}
.markdown-body :deep(th) {
  background: var(--el-fill-color-light);
  font-weight: 600;
}
</style>
