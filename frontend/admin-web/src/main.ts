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

// 硬刷新直接访问插件路由（如 /erp/...、/cloud_storage）时，初始导航会先落到 not-found；
// 此时等待插件注册完成，再按原路径重新解析一次 — 保证插件深链可用。
// 普通页面不受影响：不等待插件、立即渲染。
router.beforeEach(async (to) => {
  if (to.matched.some((r) => r.name === 'not-found') && !pluginManager.isReady()) {
    await pluginManager.whenReady()
    return { path: to.path, query: to.query, hash: to.hash, replace: true }
  }
  return true
})

// 启动 locale 双向同步（Pinia store <-> vue-i18n）
setupLocaleWatcher().then(() => {
  // 先启动插件加载（不 await）：plugin.js 在后台注册插件路由/菜单/i18n。
  // 之前实现是「等全部插件下载完才 mount」，慢网络下首屏白屏可达数十秒，故改为非阻塞。
  pluginManager.loadInstalledPlugins().catch(() => {})
  app.use(router)
  app.mount('#app')
})
