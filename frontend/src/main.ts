/**
 * 应用入口：装配 Vue、Pinia（含持久化）、Vue Router、Element Plus。
 *
 * 图标由使用方按需 import（MessageItem / ToolCallCard），不再全量全局注册，
 * 避免把整套图标打进首屏包。
 */
import { createApp } from 'vue'
import { createPinia } from 'pinia'
import piniaPluginPersistedstate from 'pinia-plugin-persistedstate'
import ElementPlus from 'element-plus'
import zhCn from 'element-plus/es/locale/lang/zh-cn'

import 'element-plus/dist/index.css'

import App from './App.vue'
import router from './router'
import './assets/main.css'

const app = createApp(App)

// Pinia（本地用户信息）
const pinia = createPinia()
pinia.use(piniaPluginPersistedstate)

app.use(pinia)
app.use(router)
app.use(ElementPlus, { locale: zhCn })

app.mount('#app')