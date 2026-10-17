/// <reference types="vite/client" />

/** 环境变量类型声明（与 .env.* 保持一致）。 */
interface ImportMetaEnv {
  /** 后端 API 基地址 */
  readonly VITE_API_BASE_URL: string
  /** 应用标题 */
  readonly VITE_APP_TITLE: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}

/** 允许 TS 识别 .vue 单文件组件。 */
declare module '*.vue' {
  import type { DefineComponent } from 'vue'
  const component: DefineComponent<Record<string, unknown>, Record<string, unknown>, unknown>
  export default component
}