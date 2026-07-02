import { createRouter, createWebHistory, type RouteRecordRaw } from 'vue-router'

const routes: RouteRecordRaw[] = [
  { path: '/', name: 'home', component: () => import('@/views/HomeView.vue'), meta: { public: true } },
  { path: '/login', name: 'login', component: () => import('@/views/LoginView.vue'), meta: { public: true } },
  { path: '/register', name: 'register', component: () => import('@/views/RegisterView.vue'), meta: { public: true } },
  { path: '/docs', name: 'docs', component: () => import('@/views/DocsView.vue'), meta: { public: true } },
  {
    path: '/dashboard',
    component: () => import('@/views/DashboardLayout.vue'),
    children: [
      { path: '', name: 'dashboard', component: () => import('@/views/DashboardView.vue') },
      { path: 'submit', name: 'submit', component: () => import('@/views/SubmitAppView.vue') },
      { path: 'my-apps', name: 'my-apps', component: () => import('@/views/MyAppsView.vue') },
      { path: 'profile', name: 'profile', component: () => import('@/views/ProfileView.vue') },
    ],
  },
  { path: '/store', name: 'store', component: () => import('@/views/StoreView.vue'), meta: { public: true } },
  { path: '/store/:key', name: 'store-detail', component: () => import('@/views/StoreDetailView.vue'), meta: { public: true } },
  { path: '/:pathMatch(.*)*', name: 'not-found', component: () => import('@/views/NotFoundView.vue'), meta: { public: true } },
]

export const router = createRouter({
  history: createWebHistory(),
  routes,
})

router.beforeEach((to) => {
  if (to.meta.public) return true
  const token = localStorage.getItem('dev_token')
  if (!token) return { name: 'login', query: { redirect: to.fullPath } }
  return true
})
