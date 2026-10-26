<script setup lang="ts">
/**
 * 主框架布局：墨色书脊侧栏 + 纸面顶栏 + 内容区。
 *
 * 视觉由 DESIGN.md 定义；菜单分组与页码在 SidebarNav 内。
 * 窄屏（≤960px）侧栏收进抽屉，顶栏出现菜单按钮。
 */
import { computed, nextTick, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessageBox } from 'element-plus'

import SidebarNav from '@/components/layout/SidebarNav.vue'
import { fetchLlmSettings } from '@/api/settings'
import { useUserStore } from '@/stores/user'

const route = useRoute()
const router = useRouter()
const userStore = useUserStore()

const mobileNavOpen = ref(false)
const mainEl = ref<HTMLElement | null>(null)

/** 页面切换后回到顶部，避免长页面切换时停在半截。 */
watch(
  () => route.fullPath,
  async () => {
    await nextTick()
    if (mainEl.value) mainEl.value.scrollTop = 0
  },
)

onMounted(async () => {
  await userStore.loadUser()
  await maybePromptLlmSettings()
})

/** 首次进入：未配置模型 API 时提示去设置（本次会话可稍后）。 */
async function maybePromptLlmSettings(): Promise<void> {
  const suppressKey = 'smartlearn.llm_prompt_suppressed'
  if (sessionStorage.getItem(suppressKey) === '1') return
  if (route.path === '/settings') return
  try {
    const status = await fetchLlmSettings()
    if (status.configured) return
    try {
      await ElMessageBox.confirm(
        '还没有配置模型 API。不配置也能记录学习，但 AI 问答、计划生成和成长报告不可用。',
        '先配置模型 API',
        {
          confirmButtonText: '去设置',
          cancelButtonText: '稍后',
          type: 'warning',
        },
      )
      void router.push('/settings')
    } catch {
      // 「稍后」：只关本次会话，下次启动继续提示
      sessionStorage.setItem(suppressKey, '1')
    }
  } catch {
    // 设置状态读取失败不阻塞首页
  }
}

/** 顶部栏标题 = 当前路由 meta.title */
const currentTitle = computed(() => (route.meta.title as string) || '')

/** 今天的日期：10.26 · 周一 */
const todayLabel = computed(() => {
  const now = new Date()
  const month = String(now.getMonth() + 1).padStart(2, '0')
  const day = String(now.getDate()).padStart(2, '0')
  const weekday = ['日', '一', '二', '三', '四', '五', '六'][now.getDay()]
  return `${month}.${day} · 周${weekday}`
})
</script>

<template>
  <div class="layout">
    <aside class="layout-aside">
      <SidebarNav :active-path="route.path" />
    </aside>

    <div class="layout-body">
      <header class="layout-header">
        <div class="header-left">
          <button
            class="nav-toggle"
            type="button"
            aria-label="打开导航"
            @click="mobileNavOpen = true"
          >
            <span /><span /><span />
          </button>
          <div class="header-location">
            <span class="header-location__dot" aria-hidden="true" />
            <span class="header-location__brand">彭城智学</span>
            <span class="header-location__sep" aria-hidden="true">/</span>
            <span class="header-location__title">{{ currentTitle }}</span>
          </div>
        </div>

        <div class="header-right">
          <span class="header-date">{{ todayLabel }}</span>
          <span class="header-divider" aria-hidden="true" />
          <span class="header-user">
            <span class="header-user__dot" aria-hidden="true" />
            {{ userStore.userInfo?.username || '本地用户' }}
          </span>
        </div>
      </header>

      <main ref="mainEl" class="layout-main">
        <router-view v-slot="{ Component }">
          <transition name="route-fade" mode="out-in">
            <component :is="Component" />
          </transition>
        </router-view>
      </main>
    </div>

    <el-drawer
      v-model="mobileNavOpen"
      direction="ltr"
      size="276px"
      :with-header="false"
      class="mobile-nav-drawer"
    >
      <SidebarNav :active-path="route.path" @navigate="mobileNavOpen = false" />
    </el-drawer>
  </div>
</template>

<style scoped>
.layout {
  display: flex;
  height: 100vh;
  overflow: hidden;
  background: var(--paper);
}

.layout-aside {
  flex: 0 0 248px;
  width: 248px;
  height: 100%;
  background: var(--ink);
  border-right: 1px solid rgba(28, 42, 36, 0.4);
}

.layout-body {
  flex: 1 1 auto;
  min-width: 0;
  display: flex;
  flex-direction: column;
  height: 100%;
}

/* Top bar ---------------------------------------------------------------- */
.layout-header {
  flex: 0 0 64px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 0 32px;
  border-bottom: 1px solid var(--line);
  background: rgba(247, 246, 242, 0.92);
}

.header-left {
  display: flex;
  align-items: center;
  gap: 14px;
  min-width: 0;
}

.header-location {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
}

.header-location__dot {
  width: 5px;
  height: 5px;
  flex: 0 0 5px;
  background: var(--vermilion);
  border-radius: 1px;
}

.header-location__brand {
  font-family: var(--font-display);
  font-size: 13px;
  font-weight: 600;
  color: var(--ink-2);
  letter-spacing: 0.05em;
  white-space: nowrap;
}

.header-location__sep {
  font-family: var(--font-mono);
  font-size: 10px;
  color: var(--line-strong);
}

.header-location__title {
  font-family: var(--font-mono);
  font-size: 10px;
  letter-spacing: 0.06em;
  color: var(--ink-3);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.header-right {
  display: flex;
  align-items: center;
  gap: 14px;
  flex: 0 0 auto;
}

.header-date {
  font-family: var(--font-mono);
  font-size: 10px;
  letter-spacing: 0.06em;
  color: var(--ink-3);
  white-space: nowrap;
}

.header-divider {
  width: 1px;
  height: 14px;
  background: var(--line-strong);
}

.header-user {
  display: flex;
  align-items: center;
  gap: 7px;
  font-size: 12px;
  color: var(--ink-3);
  white-space: nowrap;
}

.header-user__dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--jade);
}

/* Menu toggle (mobile only) ---------------------------------------------- */
.nav-toggle {
  display: none;
  flex-direction: column;
  justify-content: center;
  gap: 4px;
  width: 30px;
  height: 30px;
  padding: 6px;
  background: transparent;
  border: 1px solid var(--line-strong);
  border-radius: var(--radius);
  cursor: pointer;
}

.nav-toggle span {
  display: block;
  width: 100%;
  height: 1px;
  background: var(--ink);
}

.nav-toggle:hover {
  border-color: var(--vermilion);
}

.nav-toggle:hover span {
  background: var(--vermilion);
}

/* Main ------------------------------------------------------------------- */
.layout-main {
  flex: 1 1 auto;
  min-height: 0;
  overflow-y: auto;
  position: relative;
}

/* Responsive ------------------------------------------------------------- */
@media (max-width: 1200px) {
  .layout-header {
    padding: 0 28px;
  }
}

@media (max-width: 960px) {
  .layout-aside {
    display: none;
  }

  .layout-header {
    padding: 0 20px;
  }

  .nav-toggle {
    display: flex;
  }
}

@media (max-width: 720px) {
  .layout-header {
    padding: 0 16px;
  }

  .header-date {
    display: none;
  }

  .header-divider {
    display: none;
  }
}
</style>

<style>
/* 抽屉被 teleport 到 body，需全局作用域设置墨色背景 */
.mobile-nav-drawer {
  background: var(--ink) !important;
}

.mobile-nav-drawer .el-drawer__body {
  padding: 0 !important;
  height: 100%;
}
</style>
