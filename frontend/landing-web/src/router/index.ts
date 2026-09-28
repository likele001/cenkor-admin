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
  }
]

const scrollBehavior = () => ({ top: 0 })

export function createAppRouter(history: RouterHistory) {
  return createRouter({ history, routes, scrollBehavior })
}
