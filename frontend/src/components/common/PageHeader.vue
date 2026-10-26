<script setup lang="ts">
/**
 * 页面标题区：书页眉 → 大标题 → 一句导语 → 朱砂起笔的细线。
 * 所有页面共用，保证每页的起手节奏一致。
 */
defineProps<{
  /** 卷次与页名，例如「卷一 · 今日」。 */
  folio: string
  /** 页面主标题。 */
  title: string
  /** 一句话导语，说明这一页先回答什么问题。 */
  lead?: string
}>()
</script>

<template>
  <header class="page-header">
    <div class="page-header__main">
      <div class="page-header__folio">{{ folio }}</div>
      <h1 class="page-header__title">{{ title }}</h1>
      <p v-if="lead" class="page-header__lead">{{ lead }}</p>
    </div>
    <div v-if="$slots.actions" class="page-header__actions">
      <slot name="actions" />
    </div>
    <div class="page-header__rule" aria-hidden="true" />
  </header>
</template>

<style scoped>
.page-header__rule {
  flex-basis: 100%;
}
</style>
