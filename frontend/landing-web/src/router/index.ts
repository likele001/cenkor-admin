import { createRouter, createWebHistory } from 'vue-router'

const router = createRouter({
  history: createWebHistory(),
  routes: [
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
  ],
  scrollBehavior() {
    return { top: 0 }
  }
})

export default router
