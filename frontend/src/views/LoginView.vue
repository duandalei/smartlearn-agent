<script setup lang="ts">
/**
 * 登录 / 注册页（P3 接入后端认证）。
 *
 * - 登录：POST /auth/login，成功后 applyAuthState 并跳转 redirect 或 /dashboard。
 * - 注册：POST /auth/register，后端注册即返回 token（结构与登录一致），
 *   复用 applyAuthState 自动登录并跳 /dashboard。
 * - 失败提示：统一由 request.ts 拦截器展示后端 message（如 1002「用户名
 *   或密码错误」、1006「用户名已存在」），本页仅负责复位按钮状态。
 */
import { reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, type FormInstance, type FormRules } from 'element-plus'

import { login, register } from '@/api/auth'
import { useUserStore } from '@/stores/user'

const router = useRouter()
const route = useRoute()
const userStore = useUserStore()

/** 当前激活的 Tab：login / register。 */
const activeTab = ref<'login' | 'register'>('login')
const loading = ref(false)

const loginFormRef = ref<FormInstance>()
const registerFormRef = ref<FormInstance>()

/** 登录表单。 */
const loginForm = reactive({
  username: 'demo',
  password: '',
})

/** 注册表单。 */
const registerForm = reactive({
  username: '',
  password: '',
  confirmPassword: '',
})

/** 登录表单校验规则。 */
const loginRules: FormRules = {
  username: [{ required: true, message: '请输入用户名', trigger: 'blur' }],
  password: [{ required: true, message: '请输入密码', trigger: 'blur' }],
}

/** 注册表单校验规则（与后端 RegisterIn 约束一致）。 */
const registerRules: FormRules = {
  username: [
    { required: true, message: '请输入用户名', trigger: 'blur' },
    { min: 2, max: 50, message: '用户名长度须为 2-50 个字符', trigger: 'blur' },
  ],
  password: [
    { required: true, message: '请输入密码', trigger: 'blur' },
    { min: 6, max: 128, message: '密码至少 6 位', trigger: 'blur' },
  ],
  confirmPassword: [
    { required: true, message: '请再次输入密码', trigger: 'blur' },
    {
      validator: (_rule, value: string, callback) => {
        if (value !== registerForm.password) {
          callback(new Error('两次输入的密码不一致'))
        } else {
          callback()
        }
      },
      trigger: 'blur',
    },
  ],
}

/** 处理登录。 */
async function handleLogin(): Promise<void> {
  const valid = await loginFormRef.value?.validate().catch(() => false)
  if (!valid) return
  loading.value = true
  try {
    const result = await login({
      username: loginForm.username.trim(),
      password: loginForm.password,
    })
    userStore.applyAuthState(result)
    ElMessage.success('登录成功')
    const redirect = (route.query.redirect as string) || '/dashboard'
    router.push(redirect)
  } catch {
    // 失败提示已由 request.ts 拦截器统一展示（1002 等）
  } finally {
    loading.value = false
  }
}

/** 处理注册：成功即自动登录并跳 /dashboard。 */
async function handleRegister(): Promise<void> {
  const valid = await registerFormRef.value?.validate().catch(() => false)
  if (!valid) return
  loading.value = true
  try {
    const result = await register({
      username: registerForm.username.trim(),
      password: registerForm.password,
      confirm_password: registerForm.confirmPassword,
    })
    userStore.applyAuthState(result)
    ElMessage.success('注册成功，已自动登录')
    router.push('/dashboard')
  } catch {
    // 失败提示已由 request.ts 拦截器统一展示（1006 用户名已存在等）
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div class="login-page">
    <el-card class="login-card" shadow="always">
      <div class="login-header">
        <h1 class="login-title">彭城智学 SmartLearn Agent</h1>
        <p class="login-subtitle">AI 学习成长智能体</p>
      </div>

      <el-tabs v-model="activeTab" class="login-tabs">
        <!-- 登录 -->
        <el-tab-pane label="登录" name="login">
          <el-form
            ref="loginFormRef"
            :model="loginForm"
            :rules="loginRules"
            label-position="top"
            @submit.prevent="handleLogin"
          >
            <el-form-item label="用户名" prop="username">
              <el-input
                v-model="loginForm.username"
                placeholder="请输入用户名"
                clearable
              />
            </el-form-item>
            <el-form-item label="密码" prop="password">
              <el-input
                v-model="loginForm.password"
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
          <p class="demo-hint">演示账号：demo / 123456</p>
        </el-tab-pane>

        <!-- 注册 -->
        <el-tab-pane label="注册" name="register">
          <el-form
            ref="registerFormRef"
            :model="registerForm"
            :rules="registerRules"
            label-position="top"
            @submit.prevent="handleRegister"
          >
            <el-form-item label="用户名" prop="username">
              <el-input
                v-model="registerForm.username"
                placeholder="2-50 个字符"
                clearable
              />
            </el-form-item>
            <el-form-item label="密码" prop="password">
              <el-input
                v-model="registerForm.password"
                type="password"
                placeholder="至少 6 位"
                show-password
              />
            </el-form-item>
            <el-form-item label="确认密码" prop="confirmPassword">
              <el-input
                v-model="registerForm.confirmPassword"
                type="password"
                placeholder="请再次输入密码"
                show-password
                @keyup.enter="handleRegister"
              />
            </el-form-item>
            <el-form-item>
              <el-button
                type="primary"
                class="login-button"
                :loading="loading"
                @click="handleRegister"
              >
                注册并登录
              </el-button>
            </el-form-item>
          </el-form>
        </el-tab-pane>
      </el-tabs>
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
  margin-bottom: 16px;
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
.login-tabs {
  margin-top: 4px;
}
.login-button {
  width: 100%;
}
.demo-hint {
  text-align: center;
  font-size: 12px;
  color: #909399;
  margin: 4px 0 0;
}
</style>