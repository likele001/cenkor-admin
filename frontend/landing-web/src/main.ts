import { createApp, createSSRApp } from 'vue'
import { createPinia } from 'pinia'
import { createHead } from '@unhead/vue'
import { createWebHistory } from 'vue-router'
import App from './App.vue'
import { createAppRouter } from './router'
import { PRERENDERED_HEAD_SELECTOR } from './config/seo'
import './styles/global.scss'

// router 实例在这里创建（而不是在 router/index.ts 顶层）：
// 顶层 new createWebHistory() 会让 Node 侧的预渲染在 import 阶段就访问 window 而崩。
const router = createAppRouter(createWebHistory(import.meta.env.BASE_URL))

const mountEl = document.getElementById('app')

// 预渲染产物（scripts/prerender.mjs）会把服务端渲染好的 HTML 放进 #app 里，
// 此时必须用 createSSRApp 走 hydration，否则 Vue 会清空容器重建 → 首屏白闪一次、
// 预渲染的内容白做。开发态/未预渲染时容器是空的，用普通 createApp。
const hasPrerendered = !!mountEl && mountEl.innerHTML.trim().length > 0

if (hasPrerendered) {
  // 静态 HTML 里的 title/description/canonical/og:* 是给爬虫的；
  // 客户端 unhead 会重新创建同名标签 → 不清理就会同时存在两份
  // （Google 见到多个 canonical 会直接全部忽略）。移除后由 unhead 全量接管。
  document.head
    .querySelectorAll(PRERENDERED_HEAD_SELECTOR)
    .forEach((el) => el.remove())
}

const app = hasPrerendered ? createSSRApp(App) : createApp(App)

app.use(createPinia())
app.use(router)
app.use(createHead())

app.mount('#app')
