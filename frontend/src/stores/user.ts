/**
 * 用户状态（Pinia）：token 与用户信息。
 *
 * - token 同步写入 localStorage，key 固定 `smartlearn_token`（PROJECT_CONTEXT 7.4）。
 * - userInfo 通过持久化插件保底，页面刷新可恢复。
 * - 登录/登出分别写入与清除。
 */
import { defineStore } from 'pinia'
import { ref } from 'vue'

import type { AuthResult, UserInfo } from '@/types'

/** token 在 localStorage 中的固定 key。 */
export const TOKEN_KEY = 'smartlearn_token'

/**
 * 读取本地持久化的 token。
 *
 * @returns 已保存的 token，不存在时返回空字符串。
 */
function readToken(): string {
  return localStorage.getItem(TOKEN_KEY) || ''
}

export const useUserStore = defineStore(
  'user',
  () => {
    /** 认证 token（空字符串表示未登录）。 */
    const token = ref<string>(readToken())
    /** 当前用户信息（未登录为 null）。 */
    const userInfo = ref<UserInfo | null>(null)

    /**
     * 设置 token 并同步到 localStorage。
     *
     * @param value 新的 token。
     */
    function setToken(value: string): void {
      token.value = value
      localStorage.setItem(TOKEN_KEY, value)
    }

    /**
     * 设置用户信息。
     *
     * @param info 用户信息对象。
     */
    function setUserInfo(info: UserInfo | null): void {
      userInfo.value = info
    }

    /** 是否已登录。 */
    function isAuthenticated(): boolean {
      return Boolean(token.value)
    }

    /**
     * 统一写入认证状态（登录与注册共用）。
     *
     * 后端注册成功返回的 token 结构与登录完全一致（P3 裁决），
     * 两处复用同一存储方法，保证 token / userInfo 写入口径唯一。
     *
     * @param result 登录或注册接口返回的 AuthResult。
     */
    function applyAuthState(result: AuthResult): void {
      setToken(result.access_token)
      setUserInfo(result.user)
    }

    /** 登出：清除 token 与用户信息。 */
    function logout(): void {
      token.value = ''
      userInfo.value = null
      localStorage.removeItem(TOKEN_KEY)
    }

    return {
      token,
      userInfo,
      setToken,
      setUserInfo,
      applyAuthState,
      isAuthenticated,
      logout,
    }
  },
  {
    // 持久化用户信息（token 已单独写入 smartlearn_token，不重复持久化）。
    persist: {
      key: 'smartlearn_user_store',
      paths: ['userInfo'],
    },
  },
)