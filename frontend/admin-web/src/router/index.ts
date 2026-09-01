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
import ContentTypeListView from '@/views/cms/ContentTypeListView.vue'
import FieldDefinitionsView from '@/views/cms/FieldDefinitionsView.vue'
import CategoriesView from '@/views/cms/CategoriesView.vue'
import TagsView from '@/views/cms/TagsView.vue'
import EntryListView from '@/views/cms/EntryListView.vue'
import EntryEditView from '@/views/cms/EntryEditView.vue'
import LanguagesView from '@/views/cms/LanguagesView.vue'
import SearchResultsView from '@/views/cms/SearchResultsView.vue'
import WebhooksView from '@/views/system/WebhooksView.vue'
import RedirectsView from '@/views/system/RedirectsView.vue'
import CommentsView from '@/views/system/CommentsView.vue'
import FormsView from '@/views/system/FormsView.vue'
import BuilderPagesView from '@/views/builder/BuilderPagesView.vue'
import TemplatePreviewView from '@/views/cms/TemplatePreviewView.vue'
import UsersListView from '@/views/system/UsersListView.vue'
import RolesView from '@/views/system/RolesView.vue'
import MenusView from '@/views/system/MenusView.vue'
import AuditView from '@/views/system/AuditView.vue'
import AppsView from '@/views/system/AppsView.vue'
import ApiKeysView from '@/views/system/ApiKeysView.vue'
import TasksView from '@/views/system/TasksView.vue'
import SettingsView from '@/views/system/SettingsView.vue'
import AnnouncementsView from '@/views/system/AnnouncementsView.vue'
import TicketsView from '@/views/system/TicketsView.vue'
import LinksView from '@/views/system/LinksView.vue'
import NotificationsView from '@/views/system/NotificationsView.vue'
import PortalUsersListView from '@/views/system/PortalUsersListView.vue'
import ForbiddenView from '@/views/ForbiddenView.vue'
import NotFoundView from '@/views/NotFoundView.vue'

const routes: RouteRecordRaw[] = [
  { path: '/login', name: 'login', component: LoginView, meta: { public: true } },
  { path: '/auth/feishu/callback', name: 'feishu-callback', component: FeishuCallbackView, meta: { public: true } },
  {
    path: '/',
    name: 'layout',
    component: AppLayout,
    children: [
      { path: '', name: 'dashboard', component: DashboardView },
      // CMS - 内容引擎
      { path: 'cms/content-types', name: 'cms-content-types', component: ContentTypeListView, meta: { permission: 'cms:content_types:read' } },
      { path: 'cms/content-types/:id/fields', name: 'cms-content-type-fields', component: FieldDefinitionsView, meta: { permission: 'cms:field_definitions:read' } },
      { path: 'cms/categories', name: 'cms-categories', component: CategoriesView, meta: { permission: 'cms:categories:read' } },
      { path: 'cms/tags', name: 'cms-tags', component: TagsView, meta: { permission: 'cms:tags:read' } },
      // CMS - 通用内容
      { path: 'cms/entries', name: 'cms-entries', component: EntryListView, meta: { permission: 'cms:entries:read' } },
      { path: 'cms/entries/new', name: 'cms-entry-new', component: EntryEditView, meta: { permission: 'cms:entries:write' } },
      { path: 'cms/entries/:id', name: 'cms-entry-edit', component: EntryEditView, meta: { permission: 'cms:entries:write' } },
      { path: 'cms/templates', name: 'cms-templates', component: TemplatePreviewView, meta: { permission: 'cms:site:read' } },
      { path: 'cms/languages', name: 'cms-languages', component: LanguagesView, meta: { permission: 'cms:entries:read' } },
      { path: 'cms/search', name: 'cms-search', component: SearchResultsView, meta: { permission: 'cms:entries:read' } },
      { path: 'builder/pages', name: 'builder-pages', component: BuilderPagesView, meta: { permission: 'settings:read' } },
      // CMS - 传统内容
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
      // System
      { path: 'system/users', name: 'system-users', component: UsersListView, meta: { permission: 'rbac:user:read' } },
      { path: 'system/portal-users', name: 'system-portal-users', component: PortalUsersListView, meta: { permission: 'portal:users:read' } },
      { path: 'system/roles', name: 'system-roles', component: RolesView, meta: { permission: 'rbac:role:read' } },
      { path: 'system/menus', name: 'system-menus', component: MenusView, meta: { permission: 'rbac:menu:read' } },
      { path: 'system/apps', name: 'system-apps', component: AppsView, meta: { permission: 'rbac:role:read' } },
      { path: 'system/audit', name: 'system-audit', component: AuditView, meta: { permission: 'system:audit:read' } },
      { path: 'system/notifications', name: 'system-notifications', component: NotificationsView, meta: { permission: 'notification:read' } },
      { path: 'system/api-keys', name: 'system-api-keys', component: ApiKeysView, meta: { permission: 'apikey:read' } },
      { path: 'system/tasks', name: 'system-tasks', component: TasksView, meta: { permission: 'task:read' } },
      { path: 'system/settings', name: 'system-settings', component: SettingsView, meta: { permission: 'settings:read' } },
      { path: 'system/webhooks', name: 'system-webhooks', component: WebhooksView, meta: { permission: 'settings:read' } },
      { path: 'system/redirects', name: 'system-redirects', component: RedirectsView, meta: { permission: 'settings:read' } },
      { path: 'system/comments', name: 'system-comments', component: CommentsView, meta: { permission: 'settings:read' } },
      { path: 'system/forms', name: 'system-forms', component: FormsView, meta: { permission: 'settings:read' } },
      // Apps
      { path: 'announcements', name: 'announcements', component: AnnouncementsView, meta: { permission: 'announcements:read' } },
      { path: 'tickets', name: 'tickets', component: TicketsView, meta: { permission: 'tickets:read' } },
      { path: 'links', name: 'links', component: LinksView, meta: { permission: 'links:read' } },
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
