<script setup lang="ts">
/**
 * 登录页（骨架阶段静态实现）。
 *
 * 说明：本阶段**不接入后端认证接口**，点击登录仅写入占位 token 以便进入
 * 主布局验证路由与菜单。接入后端后将改为调用 POST /api/v1/auth/login。
 */
import { reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'

import { useUserStore } from '@/stores/user'

const router = useRouter()
const route = useRoute()
const userStore = useUserStore()

const loading = ref(false)

/** 登录表单（占位，暂不做真实校验与请求） */
const form = reactive({
  username: 'demo',
  password: 'demo123',
})

/** 骨架阶段占位 token（真实 token 由后端 JWT 签发） */
const PLACEHOLDER_TOKEN = 'dev-placeholder-token'

/** 处理登录：写入占位 token 并跳转。 */
function handleLogin(): void {
  if (!form.username || !form.password) {
    ElMessage.warning('请输入用户名和密码')
    return
  }
  loading.value = true
  userStore.setToken(PLACEHOLDER_TOKEN)
  userStore.setUserInfo({ id: 0, username: form.username })
  ElMessage.success('登录成功（骨架阶段占位登录）')
  const redirect = (route.query.redirect as string) || '/dashboard'
  loading.value = false
  router.push(redirect)
}
</script>

<template>
  <div class="login-page">
    <el-card class="login-card" shadow="always">
      <div class="login-header">
        <h1 class="login-title">彭城智学 SmartLearn Agent</h1>
        <p class="login-subtitle">AI 学习成长智能体</p>
      </div>

      <el-form :model="form" label-position="top" @submit.prevent="handleLogin">
        <el-form-item label="用户名">
          <el-input v-model="form.username" placeholder="请输入用户名" clearable />
        </el-form-item>
        <el-form-item label="密码">
          <el-input
            v-model="form.password"
            type="password"
            placeholder="请输入密码"
            show-password
            @keyup.enter="handleLogin"
          />
        </el-form-item>
        <el-form-item>
          <el-button
            type="primary"
            class="login-button"
            :loading="loading"
            @click="handleLogin"
          >
            登录
          </el-button>
        </el-form-item>
      </el-form>

      <el-alert
        title="骨架阶段说明：登录暂未接入后端，点击「登录」使用占位 token 进入主布局。"
        type="info"
        :closable="false"
        show-icon
      />
    </el-card>
  </div>
</template>

<style scoped>
.login-page {
  height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  background: linear-gradient(135deg, #1f3a5f 0%, #2f6fb0 100%);
}
.login-card {
  width: 400px;
  padding: 8px 12px;
}
.login-header {
  text-align: center;
  margin-bottom: 24px;
}
.login-title {
  font-size: 20px;
  font-weight: 700;
  margin: 0 0 8px;
}
.login-subtitle {
  font-size: 13px;
  color: #909399;
  margin: 0;
}
.login-button {
  width: 100%;
}
</style>