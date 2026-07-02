/**
 * PluginManager — 动态加载 App 前端的插件管理器
 *
 * 工作流程:
 * 1. 应用启动时调用 loadInstalledPlugins()
 * 2. 请求 /api/v1/system/apps/plugins → 获取有前端资源的已安装 App
 * 3. 对每个 App，动态注入 <script> 加载 /.app-assets/{key}/plugin.js
 * 4. 每个 plugin.js 调用 window.__registerPlugin() 注册自身
 * 5. PluginManager 收集注册信息，合并路由/菜单/i18n
 */
import { type Router } from 'vue-router'
import { api } from '@/lib/api'
import { useAuthStore } from '@/stores/auth'
import type { PluginDefinition, InstalledPlugin } from './plugin.types'

// 全局注册函数 — plugin.js 调用此函数
declare global {
  interface Window {
    __registerPlugin: (def: PluginDefinition) => void
    __PLUGIN_TOKEN__: string
    __PLUGIN_API__: (method: string, path: string, body?: any) => Promise<any>
  }
}

/** 轻量 i18n 接口（避免 vue-i18n 复杂类型引用） */
interface I18nLike {
  global: {
    mergeLocaleMessage: (locale: string, messages: Record<string, any>) => void
  }
}

export class PluginManager {
  private router: Router
  private i18n: I18nLike
  private plugins: Map<string, PluginDefinition> = new Map()
  private loaded = false

  constructor({ router, i18n }: { router: Router; i18n: I18nLike }) {
    this.router = router
    this.i18n = i18n
    this.setupGlobalRegister()
  }

  /** 设置全局注册函数，供动态加载的 plugin.js 调用 */
  private setupGlobalRegister() {
    window.__registerPlugin = (def: PluginDefinition) => {
      if (this.plugins.has(def.id)) return
      this.plugins.set(def.id, def)
      this.applyPlugin(def)
    }
  }

  /** 应用单个插件 */
  private applyPlugin(def: PluginDefinition) {
    // 1. 注册路由
    if (def.routes) {
      for (const routeDef of def.routes) {
        this.router.addRoute('layout', {
          path: routeDef.path,
          name: routeDef.name,
          component: routeDef.component,
          meta: {
            permission: routeDef.meta?.permission,
            plugin: def.id,
            ...routeDef.meta,
          },
        })
      }
    }

    // 2. 合并国际化消息
    if (def.locales) {
      for (const [locale, messages] of Object.entries(def.locales)) {
        this.i18n.global.mergeLocaleMessage(locale, messages)
      }
    }

    // 3. 菜单项 — 存储在 window 上供 AppLayout 合并使用
    if (def.menus) {
      const existing = window.__pluginMenus || []
      window.__pluginMenus = [...existing, ...def.menus]
    }
  }

  /** 加载所有已安装的 App 前端插件 */
  async loadInstalledPlugins(): Promise<void> {
    if (this.loaded) return
    this.loaded = true

    // 向 plugin.js 注入运行时工具：当前 token + 一个带 auth 的 api fetch 包装
    // 这样 plugin.js 不需要自己 import admin-web 的依赖，也不必 hack localStorage
    const auth = useAuthStore()
    const syncToken = () => { window.__PLUGIN_TOKEN__ = auth.token || '' }
    syncToken()
    // token 变化时同步（登录/刷新/登出）
    auth.$subscribe(() => syncToken(), { detached: true })

    window.__PLUGIN_API__ = async (method, path, body) => {
      const headers: Record<string, string> = {}
      if (auth.token) headers['Authorization'] = `Bearer ${auth.token}`
      if (body !== undefined) headers['Content-Type'] = 'application/json'
      const r = await fetch(path, {
        method,
        headers,
        body: body !== undefined ? JSON.stringify(body) : undefined,
      })
      if (!r.ok) {
        const e = await r.json().catch(() => ({}))
        throw new Error(e.detail || r.statusText)
      }
      if (r.status === 204) return null
      const ct = r.headers.get('content-type') || ''
      return ct.includes('application/json') ? r.json() : r.text()
    }

    try {
      const { data } = await api.get('/api/v1/system/apps/plugins')
      const plugins: InstalledPlugin[] = data.items
      if (!plugins.length) return

      // 并行加载所有 plugin.js
      await Promise.allSettled(
        plugins.map(p => this.loadScript(p.script_url))
      )
    } catch {
      // 静默失败 — 插件加载不影响核心功能
    }
  }

  /** 动态注入 <script> 加载 JS */
  private loadScript(url: string): Promise<void> {
    return new Promise((resolve, reject) => {
      const script = document.createElement('script')
      script.src = url
      script.async = true
      script.onload = () => resolve()
      script.onerror = () => reject(new Error(`Failed to load plugin: ${url}`))
      document.body.appendChild(script)
    })
  }
}

// 插件菜单的全局存储（供 AppLayout 合并）
declare global {
  interface Window {
    __pluginMenus?: Array<{
      key: string
      title: string
      path: string
      icon?: string
      parentId?: number | null
      sort?: number
    }>
  }
}
