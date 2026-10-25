/**
 * 路由表（PROJECT_CONTEXT 7.1）。
 *
 * 本地单用户：不设登录页与鉴权守卫，打开即进入主布局。
 */
import { createRouter, createWebHistory, type RouteRecordRaw } from 'vue-router'

import MainLayout from '@/layouts/MainLayout.vue'

const routes: RouteRecordRaw[] = [
  {
    path: '/',
    component: MainLayout,
    redirect: '/dashboard',
    children: [
      {
        path: 'dashboard',
        name: 'dashboard',
        component: () => import('@/views/DashboardView.vue'),
        meta: { title: '学习中心' },
      },
      {
        path: 'profile',
        name: 'profile',
        component: () => import('@/views/ProfileView.vue'),
        meta: { title: '学习档案' },
      },
      {
        path: 'goals',
        name: 'goals',
        component: () => import('@/views/GoalsView.vue'),
        meta: { title: '学习目标' },
      },
      {
        path: 'plans',
        name: 'plans',
        component: () => import('@/views/PlanView.vue'),
        meta: { title: '学习计划' },
      },
      {
        path: 'tasks',
        name: 'tasks',
        component: () => import('@/views/TasksView.vue'),
        meta: { title: '学习任务' },
      },
      {
        path: 'learning-records',
        name: 'learning-records',
        component: () => import('@/views/LearningRecordsView.vue'),
        meta: { title: '学习记录' },
      },
      {
        path: 'knowledge-base',
        name: 'knowledge-base',
        component: () => import('@/views/KnowledgeBaseView.vue'),
        meta: { title: '知识库' },
      },
      {
        // AI 问答入口已收敛至 AI 助手；AskView.vue 与 /chat/qa 链路
        // 完整保留作回退，仅不再路由可达（L2 agent_absorb_ask）
        path: 'ask',
        redirect: '/ai-agent',
      },
      {
        path: 'ai-agent',
        name: 'ai-agent',
        component: () => import('@/views/AgentView.vue'),
        meta: { title: 'AI 助手' },
      },
      {
        path: 'reports',
        name: 'reports',
        component: () => import('@/views/ReportsView.vue'),
        meta: { title: '成长报告' },
      },
      {
        path: 'settings',
        name: 'settings',
        component: () => import('@/views/SettingsView.vue'),
        meta: { title: '设置' },
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

export default router