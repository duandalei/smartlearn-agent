/**
 * Vite 构建配置。
 *
 * - 端口固定 5173（与后端 CORS 白名单一致）。
 * - /api 代理到后端 http://localhost:8000（联调备用；主用 .env 的绝对地址）。
 * - 别名 @ 指向 src。
 */
import { fileURLToPath, URL } from 'node:url'

import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
    },
  },
  server: {
    port: 5173,
    host: '0.0.0.0',
    proxy: {
      // 前端以 /api 开头的请求转发到后端，规避跨域。
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },
})