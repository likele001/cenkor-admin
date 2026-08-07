import { createApp } from 'vue'
import * as Vue from 'vue'
import { createPinia } from 'pinia'
import { VueQueryPlugin, QueryClient } from '@tanstack/vue-query'

import App from './App.vue'
import { router } from './router'
import { i18n, setupLocaleWatcher } from './locales'
import { PluginManager } from './core/plugin'
import './style.css'

// 把 Vue 挂到 window,让 plugin.js (iife 模式 + external vue) 共享同一份 runtime
// 避免 plugin.js 内部 inline 一份 Vue 造成响应式追踪/组件实例不兼容
;(window as any).Vue = Vue

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 30_000,
      retry: 1,
      refetchOnWindowFocus: false,
    },
  },
})

const app = createApp(App)
app.use(createPinia())
app.use(i18n)
app.use(VueQueryPlugin, { queryClient })

// 初始化插件管理器（加载已安装 App 的前端资源）
const pluginManager = new PluginManager({ router, i18n })

// 激活 auth store（确保 plugin.js 注入 __PLUGIN_TOKEN__ 时能读到 token）
import('@/stores/auth').then(({ useAuthStore }) => useAuthStore())

// 启动 locale 双向同步（Pinia store <-> vue-i18n）
setupLocaleWatcher().then(async () => {
  // 先加载插件路由，再安装 router 并挂载应用。
  // 关键：app.use(router) 会触发 vue-router 的初始导航（用当前 URL 匹配路由表），
  // 必须在插件路由注册完成之后执行，否则硬刷新 /cloud_storage 等插件 URL 时，
  // 初始导航会在路由注册前完成 → 落到 not-found（404）。
  try {
    await pluginManager.loadInstalledPlugins()
  } catch {
    // 插件加载失败不影响核心应用启动
  }
  app.use(router)
  app.mount('#app')
})
