/**
 * 构建期预渲染（SSR）入口 —— 只被 scripts/prerender.mjs 通过 vite SSR 构建加载，
 * 不会进入浏览器产物。
 *
 * 目标：让 https://admin.cenkor.cn/landing/<route> 在不执行 JS 的情况下也能返回
 * 带真实正文与独立 head 的 HTML（百度等不跑 JS 的爬虫目前只能看到空壳）。
 */
import { createSSRApp } from 'vue'
import { renderToString } from 'vue/server-renderer'
import { createMemoryHistory } from 'vue-router'
import { createHead } from '@unhead/vue'
import { createPinia } from 'pinia'
import App from './App.vue'
import { createAppRouter } from './router'

// 供 prerender 脚本读取 SEO 元数据（与前端共用同一份，见 src/config/seo.ts）
export { SEO, SITE_BASE, SHARED_META, canonicalFor, normalizePath } from './config/seo'

export async function render(url: string): Promise<{ html: string }> {
  const app = createSSRApp(App)

  // base 必须与线上一致（/landing/）：否则 SSR 输出的 <router-link> href 会丢掉前缀。
  // route.path 仍是去掉 base 的形态（'/features'），与 seo.ts 的 key 对得上。
  const router = createAppRouter(createMemoryHistory(import.meta.env.BASE_URL))

  app.use(createPinia())
  app.use(router)
  app.use(createHead())

  await router.push(url)
  await router.isReady()

  const html = await renderToString(app)
  return { html }
}
