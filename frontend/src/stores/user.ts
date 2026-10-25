/**
 * 本地用户状态（Pinia）。
 *
 * 项目为本地单用户，不再有登录 / token / 退出登录；
 * 启动时从 GET /auth/me 拉取本地用户信息用于顶部栏展示。
 */
import { defineStore } from 'pinia'
import { ref } from 'vue'

import { fetchMe } from '@/api/auth'
import type { UserInfo } from '@/types'

export const useUserStore = defineStore('user', () => {
  /** 当前本地用户信息（加载失败时为 null）。 */
  const userInfo = ref<UserInfo | null>(null)
  /** 是否已尝试加载过（避免重复请求）。 */
  const loaded = ref(false)

  /** 设置用户信息。 */
  function setUserInfo(info: UserInfo | null): void {
    userInfo.value = info
  }

  /** 加载本地用户信息（只请求一次）。 */
  async function loadUser(): Promise<void> {
    if (loaded.value) return
    try {
      userInfo.value = await fetchMe()
    } catch {
      userInfo.value = null
    } finally {
      loaded.value = true
    }
  }

  return { userInfo, loaded, setUserInfo, loadUser }
})
