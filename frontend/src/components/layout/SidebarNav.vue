<script setup lang="ts">
/**
 * 侧栏导航：书脊式分组索引。
 *
 * 不用图标，用页码（01–10）建立「一本书的目录」的骨架；
 * 激活项整块朱砂，是全局唯一的大面积强调色。
 */
import { RouterLink } from 'vue-router'

defineProps<{
  /** 当前路由路径（决定激活项）。 */
  activePath: string
}>()

const emit = defineEmits<{
  (e: 'navigate'): void
}>()

interface NavItem {
  path: string
  title: string
}

interface NavGroup {
  label: string
  items: NavItem[]
}

const groups: NavGroup[] = [
  {
    label: '学习',
    items: [
      { path: '/dashboard', title: '学习中心' },
      { path: '/goals', title: '学习目标' },
      { path: '/plans', title: '学习计划' },
      { path: '/tasks', title: '学习任务' },
      { path: '/learning-records', title: '学习记录' },
    ],
  },
  {
    label: '资料',
    items: [
      { path: '/knowledge-base', title: '知识库' },
      { path: '/ai-agent', title: 'AI 助手' },
      { path: '/reports', title: '成长报告' },
    ],
  },
  {
    label: '我的',
    items: [
      { path: '/profile', title: '学习档案' },
      { path: '/settings', title: '设置' },
    ],
  },
]

/** 按导航顺序生成 01–10 的页码。 */
const folioOf = (path: string): string => {
  const all = groups.flatMap((group) => group.items)
  const index = all.findIndex((item) => item.path === path)
  return String(index + 1).padStart(2, '0')
}
</script>

<template>
  <div class="sidebar">
    <div class="brand">
      <span class="seal" aria-hidden="true">智</span>
      <div class="brand-text">
        <div class="brand-name">彭城智学</div>
        <div class="brand-caption">SMARTLEARN · LOCAL</div>
      </div>
    </div>

    <nav class="nav" aria-label="主导航">
      <section v-for="group in groups" :key="group.label" class="nav-group">
        <div class="nav-group__label">{{ group.label }}</div>
        <RouterLink
          v-for="item in group.items"
          :key="item.path"
          :to="item.path"
          class="nav-item"
          :class="{ 'is-active': activePath === item.path }"
          :aria-current="activePath === item.path ? 'page' : undefined"
          @click="emit('navigate')"
        >
          <span class="nav-item__folio" aria-hidden="true">{{ folioOf(item.path) }}</span>
          <span class="nav-item__title">{{ item.title }}</span>
        </RouterLink>
      </section>
    </nav>

    <div class="side-foot">
      <div class="side-foot__rule" aria-hidden="true" />
      <div class="side-foot__loop">记录 · 分析 · 规划 · 执行</div>
      <div class="side-foot__note">数据仅保存在这台电脑</div>
    </div>
  </div>
</template>

<style scoped>
.sidebar {
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 0;
  background: var(--ink);
  color: #f3efe3;
}

/* Brand ------------------------------------------------------------------ */
.brand {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 26px 22px 22px;
}

.brand-text {
  min-width: 0;
}

.brand-name {
  font-family: var(--font-display);
  font-size: 19px;
  font-weight: 600;
  line-height: 1.2;
  letter-spacing: 0.08em;
  color: #f5f1e6;
}

.brand-caption {
  margin-top: 5px;
  font-family: var(--font-mono);
  font-size: 9px;
  line-height: 1;
  letter-spacing: 0.16em;
  color: rgba(245, 241, 230, 0.58);
}

/* Navigation ------------------------------------------------------------- */
.nav {
  flex: 1 1 auto;
  min-height: 0;
  overflow-y: auto;
  padding: 0 12px;
}

.nav-group {
  margin-top: 18px;
}

.nav-group:first-child {
  margin-top: 4px;
}

.nav-group__label {
  padding: 0 12px;
  margin-bottom: 6px;
  font-family: var(--font-mono);
  font-size: 9px;
  letter-spacing: 0.18em;
  color: rgba(245, 241, 230, 0.58);
}

.nav-item {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 9px 12px;
  margin-bottom: 2px;
  border-radius: var(--radius);
  color: rgba(245, 241, 230, 0.72);
  font-size: 13.5px;
  line-height: 1.4;
  text-decoration: none;
  transition: background-color 0.16s var(--ease), color 0.16s var(--ease);
}

.nav-item:hover {
  background: rgba(245, 241, 230, 0.07);
  color: #f5f1e6;
  text-decoration: none;
}

.nav-item:focus-visible {
  outline: 2px solid rgba(245, 241, 230, 0.8);
  outline-offset: -2px;
}

.nav-item__folio {
  width: 18px;
  flex: 0 0 18px;
  font-family: var(--font-mono);
  font-size: 9px;
  letter-spacing: 0.04em;
  color: rgba(245, 241, 230, 0.55);
}

.nav-item__title {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.nav-item.is-active {
  background: var(--vermilion);
  color: #fbf8f1;
}

.nav-item.is-active:hover {
  background: var(--vermilion-2);
}

.nav-item.is-active .nav-item__folio {
  color: rgba(251, 248, 241, 0.72);
}

/* Foot ------------------------------------------------------------------- */
.side-foot {
  flex: 0 0 auto;
  padding: 18px 24px 22px;
}

.side-foot__rule {
  height: 1px;
  margin-bottom: 14px;
  background: rgba(245, 241, 230, 0.14);
}

.side-foot__loop {
  font-family: var(--font-mono);
  font-size: 9px;
  letter-spacing: 0.1em;
  color: rgba(245, 241, 230, 0.62);
}

.side-foot__note {
  margin-top: 4px;
  font-size: 10px;
  line-height: 1.5;
  color: rgba(245, 241, 230, 0.58);
}
</style>
