import { createApp } from 'vue'
import { createPinia } from 'pinia'
import { VueQueryPlugin, QueryClient } from '@tanstack/vue-query'

import App from './App.vue'
import { router } from './router'
import { i18n, setupLocaleWatcher } from './locales'
import { PluginManager } from './core/plugin'
import './style.css'

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
app.use(router)
app.use(i18n)
app.use(VueQueryPlugin, { queryClient })

// 初始化插件管理器（加载已安装 App 的前端资源）
const pluginManager = new PluginManager({ router, i18n })

// 激活 auth store（确保 plugin.js 注入 __PLUGIN_TOKEN__ 时能读到 token）
import('@/stores/auth').then(({ useAuthStore }) => useAuthStore())

// 启动 locale 双向同步（Pinia store <-> vue-i18n）
setupLocaleWatcher().then(async () => {
  // 先加载插件路由，再挂载应用。避免直接打开插件 URL 时路由未注册导致 404。
  try {
    await pluginManager.loadInstalledPlugins()
  } catch {
    // 插件加载失败不影响核心应用启动
  }
  app.mount('#app')
})
