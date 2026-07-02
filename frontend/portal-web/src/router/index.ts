import { createRouter, createWebHistory } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import LoginView from '@/views/LoginView.vue'
import RegisterView from '@/views/RegisterView.vue'
import ForgotPasswordView from '@/views/ForgotPasswordView.vue'
import ResetPasswordView from '@/views/ResetPasswordView.vue'
import ProfileView from '@/views/ProfileView.vue'
import HomeView from '@/views/HomeView.vue'
import ContentListView from '@/views/ContentListView.vue'
import ContentDetailView from '@/views/ContentDetailView.vue'

export const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/login', component: LoginView, meta: { public: true } },
    { path: '/register', component: RegisterView, meta: { public: true } },
    { path: '/forgot-password', component: ForgotPasswordView, meta: { public: true } },
    { path: '/reset-password', component: ResetPasswordView, meta: { public: true } },
    { path: '/', component: HomeView, meta: { public: true } },
    { path: '/list/:ct', component: ContentListView, meta: { public: true } },
    { path: '/list/:ct/:id', component: ContentDetailView, meta: { public: true } },
    { path: '/profile', component: ProfileView },
    { path: '/products', redirect: '/list/product' },
    { path: '/cases', redirect: '/list/case' },
  ],
})

router.beforeEach((to) => {
  const auth = useAuthStore()
  if (to.meta.public) return true
  if (!auth.isAuthed) return { path: '/login' }
  return true
})
