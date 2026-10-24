<script setup lang="ts">
/**
 * 主框架布局：左侧菜单 + 顶部栏 + 内容区。
 *
 * 菜单项与 PROJECT_CONTEXT 7.1 路由表一一对应，
 * 点击菜单执行路由跳转（el-menu router 模式）。
 */
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessageBox } from 'element-plus'

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

const menus: MenuItem[] = [
  { index: '/dashboard', title: '学习中心', icon: 'Odometer' },
  { index: '/profile', title: '学习档案', icon: 'User' },
  { index: '/goals', title: '学习目标', icon: 'Aim' },
  { index: '/plans', title: '学习计划', icon: 'Calendar' },
  { index: '/tasks', title: '学习任务', icon: 'List' },
  { index: '/learning-records', title: '学习记录', icon: 'Notebook' },
  { index: '/knowledge-base', title: '知识库', icon: 'Collection' },

  { index: '/ai-agent', title: 'AI 助手', icon: 'ChatDotRound' },
  { index: '/reports', title: '成长报告', icon: 'DataAnalysis' },
  // 设置页暂未实现：菜单先隐藏；以后接入时恢复此项与 router 的 /settings 路由
]

/** 当前高亮菜单项 = 当前路由路径 */
const activeMenu = computed(() => route.path)
/** 顶部栏标题 = 当前路由 meta.title */
const currentTitle = computed(() => (route.meta.title as string) || '')

/** 退出登录 */
async function handleLogout(): Promise<void> {
  try {
    await ElMessageBox.confirm('确定要退出登录吗？', '提示', {
      confirmButtonText: '确定',
      cancelButtonText: '取消',
      type: 'warning',
    })
    userStore.logout()
    router.push('/login')
  } catch {
    // 用户取消，忽略
  }
}
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
            {{ userStore.userInfo?.username || '未登录用户' }}
          </span>
          <el-button link type="primary" @click="handleLogout">退出登录</el-button>
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