/**
 * 路由表与全局前置守卫（PROJECT_CONTEXT 7.1）。
 *
 * 所有页面已注册（组件为骨架阶段占位组件）；守卫规则：
 * - 目标路由 needsAuth 且无 token -> 跳 /login；
 * - 已登录访问 /login -> 跳 /dashboard。
 */
import { createRouter, createWebHistory, type RouteRecordRaw } from 'vue-router'

import { useUserStore } from '@/stores/user'
import MainLayout from '@/layouts/MainLayout.vue'

const routes: RouteRecordRaw[] = [
  {
    path: '/login',
    name: 'login',
    component: () => import('@/views/LoginView.vue'),
    meta: { title: '登录', needsAuth: false },
  },
  {
    path: '/',
    component: MainLayout,
    redirect: '/dashboard',
    children: [
      {
        path: 'dashboard',
        name: 'dashboard',
        component: () => import('@/views/DashboardView.vue'),
        meta: { title: '学习中心', needsAuth: true },
      },
      {
        path: 'profile',
        name: 'profile',
        component: () => import('@/views/ProfileView.vue'),
        meta: { title: '学习档案', needsAuth: true },
      },
      {
        path: 'goals',
        name: 'goals',
        component: () => import('@/views/GoalsView.vue'),
        meta: { title: '学习目标', needsAuth: true },
      },
      {
        path: 'plans',
        name: 'plans',
        component: () => import('@/views/PlanView.vue'),
        meta: { title: '学习计划', needsAuth: true },
      },
      {
        path: 'tasks',
        name: 'tasks',
        component: () => import('@/views/TasksView.vue'),
        meta: { title: '学习任务', needsAuth: true },
      },
      {
        path: 'learning-records',
        name: 'learning-records',
        component: () => import('@/views/LearningRecordsView.vue'),
        meta: { title: '学习记录', needsAuth: true },
      },
      {
        path: 'knowledge-base',
        name: 'knowledge-base',
        component: () => import('@/views/KnowledgeBaseView.vue'),
        meta: { title: '知识库', needsAuth: true },
      },
      {
        path: 'ask',
        name: 'ask',
        component: () => import('@/views/AskView.vue'),
        meta: { title: 'AI 问答', needsAuth: true },
      },
      {
        path: 'ai-agent',
        name: 'ai-agent',
        component: () => import('@/views/AgentView.vue'),
        meta: { title: 'AI 助手', needsAuth: true },
      },
      {
        path: 'reports',
        name: 'reports',
        component: () => import('@/views/ReportsView.vue'),
        meta: { title: '成长报告', needsAuth: true },
      },
      {
        // 设置页暂未实现：菜单已隐藏，直接访问重定向到学习中心；
        // 以后接入时改回 component: () => import('@/views/SettingsView.vue')
        path: 'settings',
        redirect: '/dashboard',
      },
    ],
  },
  {
    // 兜底：未匹配路由回首页
    path: '/:pathMatch(.*)*',
    redirect: '/dashboard',
  },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

router.beforeEach((to) => {
  const userStore = useUserStore()
  const needsAuth = to.meta.needsAuth !== false
  const authed = userStore.isAuthenticated()

  if (needsAuth && !authed) {
    return { path: '/login', query: { redirect: to.fullPath } }
  }
  if (to.path === '/login' && authed) {
    return { path: '/dashboard' }
  }
  return true
})

export default router