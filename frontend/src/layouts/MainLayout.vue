<script setup lang="ts">
/**
 * 主框架布局：左侧菜单 + 顶部栏 + 内容区。
 *
 * 菜单项与 PROJECT_CONTEXT 7.1 路由表一一对应，
 * 点击菜单执行路由跳转（el-menu router 模式）。
 */
import { computed, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessageBox } from 'element-plus'

import { fetchLlmSettings } from '@/api/settings'
import { useUserStore } from '@/stores/user'

interface MenuItem {
  /** 路由路径（作为 el-menu-item 的 index） */
  index: string
  /** 菜单标题 */
  title: string
  /** Element Plus 图标组件名 */
  icon: string
}

const route = useRoute()
const router = useRouter()
const userStore = useUserStore()

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

const menus: MenuItem[] = [
  { index: '/dashboard', title: '学习中心', icon: 'Odometer' },
  { index: '/goals', title: '学习目标', icon: 'Aim' },
  { index: '/plans', title: '学习计划', icon: 'Calendar' },
  { index: '/tasks', title: '学习任务', icon: 'List' },
  { index: '/learning-records', title: '学习记录', icon: 'Notebook' },
  { index: '/knowledge-base', title: '知识库', icon: 'Collection' },
  { index: '/ai-agent', title: 'AI 助手', icon: 'ChatDotRound' },
  { index: '/reports', title: '成长报告', icon: 'DataAnalysis' },
  // 学习档案为低频账号入口，沉底；设置永远在最底部
  { index: '/profile', title: '学习档案', icon: 'User' },
  { index: '/settings', title: '设置', icon: 'Setting' },
]

/** 当前高亮菜单项 = 当前路由路径 */
const activeMenu = computed(() => route.path)
/** 顶部栏标题 = 当前路由 meta.title */
const currentTitle = computed(() => (route.meta.title as string) || '')
</script>

<template>
  <el-container class="layout">
    <!-- 左侧菜单 -->
    <el-aside width="220px" class="layout-aside">
      <div class="logo">彭城智学</div>
      <el-menu
        router
        :default-active="activeMenu"
        class="layout-menu"
        background-color="#001529"
        text-color="#c9d1d9"
        active-text-color="#ffffff"
      >
        <el-menu-item v-for="item in menus" :key="item.index" :index="item.index">
          <el-icon><component :is="item.icon" /></el-icon>
          <span>{{ item.title }}</span>
        </el-menu-item>
      </el-menu>
    </el-aside>

    <el-container>
      <!-- 顶部栏 -->
      <el-header class="layout-header">
        <span class="header-title">{{ currentTitle }}</span>
        <div class="header-right">
          <span class="header-user">
            {{ userStore.userInfo?.username || '本地用户' }}
          </span>
        </div>
      </el-header>

      <!-- 内容区 -->
      <el-main class="layout-main">
        <router-view />
      </el-main>
    </el-container>
  </el-container>
</template>

<style scoped>
.layout {
  height: 100vh;
}
.layout-aside {
  background-color: #001529;
  overflow-y: auto;
}
.logo {
  height: 60px;
  line-height: 60px;
  text-align: center;
  color: #ffffff;
  font-size: 18px;
  font-weight: 700;
  letter-spacing: 2px;
}
.layout-menu {
  border-right: none;
}
.layout-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  background-color: #ffffff;
  border-bottom: 1px solid #e4e7ed;
}
.header-title {
  font-size: 16px;
  font-weight: 600;
}
.header-right {
  display: flex;
  align-items: center;
  gap: 12px;
}
.header-user {
  color: #606266;
  font-size: 14px;
}
.layout-main {
  background-color: #f5f7fa;
  padding: 16px;
}
</style>