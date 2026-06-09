import { createRouter, createWebHistory, type RouteRecordRaw } from 'vue-router'
import { useAuthStore } from '@/stores/auth'

import AppLayout from '@/layouts/AppLayout.vue'
import LoginView from '@/views/LoginView.vue'
import FeishuCallbackView from '@/views/FeishuCallbackView.vue'
import DashboardView from '@/views/DashboardView.vue'
import ProductsListView from '@/views/cms/ProductsListView.vue'
import ProductEditView from '@/views/cms/ProductEditView.vue'
import CasesListView from '@/views/cms/CasesListView.vue'
import CaseEditView from '@/views/cms/CaseEditView.vue'
import NewsListView from '@/views/cms/NewsListView.vue'
import NewsEditView from '@/views/cms/NewsEditView.vue'
import MediaView from '@/views/cms/MediaView.vue'
import SiteConfigView from '@/views/cms/SiteConfigView.vue'
import UsersListView from '@/views/system/UsersListView.vue'
import RolesView from '@/views/system/RolesView.vue'
import MenusView from '@/views/system/MenusView.vue'
import AuditView from '@/views/system/AuditView.vue'
import AppsView from '@/views/system/AppsView.vue'
import ApiKeysView from '@/views/system/ApiKeysView.vue'
import TasksView from '@/views/system/TasksView.vue'
import SettingsView from '@/views/system/SettingsView.vue'
import ForbiddenView from '@/views/ForbiddenView.vue'
import NotFoundView from '@/views/NotFoundView.vue'

const routes: RouteRecordRaw[] = [
  { path: '/login', name: 'login', component: LoginView, meta: { public: true } },
  { path: '/auth/feishu/callback', name: 'feishu-callback', component: FeishuCallbackView, meta: { public: true } },
  {
    path: '/',
    component: AppLayout,
    children: [
      { path: '', name: 'dashboard', component: DashboardView },
      { path: 'cms/products', name: 'cms-products', component: ProductsListView, meta: { permission: 'cms:product:read' } },
      { path: 'cms/products/new', name: 'cms-product-new', component: ProductEditView, meta: { permission: 'cms:product:write' } },
      { path: 'cms/products/:id', name: 'cms-product-edit', component: ProductEditView, meta: { permission: 'cms:product:write' } },
      { path: 'cms/cases', name: 'cms-cases', component: CasesListView, meta: { permission: 'cms:case:read' } },
      { path: 'cms/cases/new', name: 'cms-case-new', component: CaseEditView, meta: { permission: 'cms:case:write' } },
      { path: 'cms/cases/:id', name: 'cms-case-edit', component: CaseEditView, meta: { permission: 'cms:case:write' } },
      { path: 'cms/news', name: 'cms-news', component: NewsListView, meta: { permission: 'cms:news:read' } },
      { path: 'cms/news/new', name: 'cms-news-new', component: NewsEditView, meta: { permission: 'cms:news:write' } },
      { path: 'cms/news/:id', name: 'cms-news-edit', component: NewsEditView, meta: { permission: 'cms:news:write' } },
      { path: 'cms/site', name: 'cms-site', component: SiteConfigView, meta: { permission: 'cms:site:read' } },
      { path: 'cms/media', name: 'cms-media', component: MediaView, meta: { permission: 'media:upload' } },
      { path: 'system/users', name: 'system-users', component: UsersListView, meta: { permission: 'rbac:user:read' } },
      { path: 'system/roles', name: 'system-roles', component: RolesView, meta: { permission: 'rbac:role:read' } },
      { path: 'system/menus', name: 'system-menus', component: MenusView, meta: { permission: 'rbac:menu:read' } },
      { path: 'system/apps', name: 'system-apps', component: AppsView, meta: { permission: 'rbac:role:read' } },
      { path: 'system/audit', name: 'system-audit', component: AuditView, meta: { permission: 'system:audit:read' } },
      { path: 'system/api-keys', name: 'system-api-keys', component: ApiKeysView, meta: { permission: 'apikey:read' } },
      { path: 'system/tasks', name: 'system-tasks', component: TasksView, meta: { permission: 'task:read' } },
      { path: 'system/settings', name: 'system-settings', component: SettingsView, meta: { permission: 'settings:read' } },
      { path: '403', name: 'forbidden', component: ForbiddenView },
    ],
  },
  { path: '/:pathMatch(.*)*', name: 'not-found', component: NotFoundView, meta: { public: true } },
]

export const router = createRouter({
  history: createWebHistory(),
  routes,
})

router.beforeEach((to) => {
  const auth = useAuthStore()
  if (to.meta.public) return true
  if (!auth.isAuthed) {
    return { name: 'login', query: { redirect: to.fullPath } }
  }
  const perm = to.meta.permission as string | undefined
  if (perm && !auth.hasPermission(perm)) {
    return { name: 'forbidden' }
  }
  return true
})
