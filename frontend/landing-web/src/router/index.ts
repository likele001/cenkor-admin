import { createRouter, type RouterHistory } from 'vue-router'

/**
 * 路由表 + 工厂函数。**刻意不在这里导出 router 实例**：
 * 模块顶层 new 一个 createWebHistory() 会在 Node 侧（预渲染）加载时立刻访问 window
 * 而抛 `ReferenceError: window is not defined`。
 * 浏览器实例由 src/main.ts 自行创建。
 */
export const routes = [
  {
    path: '/',
    name: 'Home',
    component: () => import('@/views/Home.vue')
  },
  {
    path: '/ai-cms',
    name: 'AiCms',
    component: () => import('@/views/AiCms.vue')
  },
  {
    path: '/features',
    name: 'Features',
    component: () => import('@/views/Features.vue')
  },
  {
    path: '/advantages',
    name: 'Advantages',
    component: () => import('@/views/Advantages.vue')
  },
  {
    path: '/deploy',
    name: 'Deploy',
    component: () => import('@/views/Deploy.vue')
  },
  {
    path: '/docs/guide',
    name: 'Guide',
    component: () => import('@/views/docs/Guide.vue')
  },
  {
    path: '/docs',
    name: 'Docs',
    component: () => import('@/views/docs/DocsCenter.vue')
  },
  {
    // /docs/<相对路径>：文档阅读页，客户端 fetch docs-content 下的 md 渲染
    path: '/docs/:pathMatch(.*)*',
    name: 'DocsRead',
    component: () => import('@/views/docs/DocsCenter.vue')
  }
]

const scrollBehavior = () => ({ top: 0 })

export function createAppRouter(history: RouterHistory) {
  return createRouter({ history, routes, scrollBehavior })
}
