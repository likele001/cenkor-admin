<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { useAuthStore } from '@/stores/auth'
import { api } from '@/lib/api'
import NotificationBell from '@/components/NotificationBell.vue'
import LocaleSwitcher from '@/components/LocaleSwitcher.vue'
import WsStatus from '@/components/WsStatus.vue'

const router = useRouter()
const route = useRoute()
const auth = useAuthStore()
const { t } = useI18n()
const me = ref(auth.user)
const sidebarOpen = ref(true)
const expandedGroup = ref<string | null>(null)

interface MenuItem {
  id: number
  key: string
  title: string
  path: string | null
  parent_id: number | null
  icon: string | null
  sort?: number
}

const flatMenus = computed(() => {
  const backend = me.value?.menus ?? []
  const pluginMenus = window.__pluginMenus ?? []
  if (!pluginMenus.length) return backend
  // 将插件菜单转换为与后端菜单相同的格式合并
  // 按 (key, path) 去重：后端优先（已绑定角色权限），插件仅作补充
  const seen = new Set<string>()
  for (const m of backend) seen.add(`${m.key}::${m.path ?? ''}`)
  const pluginItems: MenuItem[] = []
  for (let i = 0; i < pluginMenus.length; i++) {
    const m = pluginMenus[i]
    const dedup = `${m.key}::${m.path ?? ''}`
    if (seen.has(dedup)) continue
    seen.add(dedup)
    pluginItems.push({
      id: 9999 + i,
      key: m.key,
      title: m.title,
      path: m.path,
      parent_id: m.parentId ?? null,
      icon: m.icon ?? null,
      sort: m.sort ?? 90,
    })
  }
  return [...backend, ...pluginItems]
})

const navKeyMap: Record<string, string> = {
  '/': 'nav.dashboard',
  '/cms/content-types': 'nav.contentTypes',
  '/cms/categories': 'nav.categories',
  '/cms/tags': 'nav.tags',
  '/cms/entries': 'nav.entries',
  '/cms/products': 'nav.products',
  '/cms/cases': 'nav.cases',
  '/cms/news': 'nav.news',
  '/cms/site': 'nav.site',
  '/cms/media': 'nav.media',
  '/cms/templates': 'nav.templates',
  '/system/users': 'nav.users',
  '/system/portal-users': 'nav.portalUsers',
  '/system/roles': 'nav.roles',
  '/system/menus': 'nav.menus',
  '/system/apps': 'nav.apps',
  '/system/audit': 'nav.audit',
  '/system/api-keys': 'nav.apiKeys',
  '/system/tasks': 'nav.tasks',
  '/system/settings': 'nav.settings',
  '/system/notifications': 'nav.notifications',
  '/announcements': 'nav.announcements',
  '/tickets': 'nav.tickets',
  '/links': 'nav.links',
}

function resolveTitle(item: { title?: string; key?: string; path?: string | null }) {
  if (item.key && item.path && navKeyMap[item.path]) return t(navKeyMap[item.path])
  if (item.key) {
    const k = `nav.${item.key.replace(/^cms:|^system:|^announcements:|^tickets:|^links:/, '')}`
    const translated = t(k)
    if (translated !== k) return translated
  }
  return item.title || ''
}

// 图标解析：优先按 emoji / 字符串直接渲染；lucide 风格名 → emoji 映射
const ICON_MAP: Record<string, string> = {
  'newspaper': '📄',
  'settings-2': '⚙️',
  'settings': '⚙️',
  'megaphone': '📢',
  'ticket': '🎫',
  'link': '🔗',
  'sticky-note': '📝',
  'list-todo': '✅',
  'database': '🗄️',
  'layout-dashboard': '📊',
  'users': '👥',
  'shield': '🛡️',
  'bell': '🔔',
  'key': '🔑',
  'cog': '⚙️',
  'folder': '📁',
  'tag': '🏷️',
  'package': '📦',
  'globe': '🌐',
  'image': '🖼️',
  'shopping-bag': '🛍️',
}
function resolveIcon(icon: string | null | undefined): string {
  if (!icon) return ''
  // 已经是 emoji（包含非 ASCII 字符）就直接显示
  if (icon.length <= 4 || /[\u{1F300}-\u{1FAFF}\u{2600}-\u{27BF}]/u.test(icon)) {
    return icon
  }
  return ICON_MAP[icon] || '📋'
}

// 构建侧边栏菜单树
const sidebarMenus = computed(() => {
  const menus = flatMenus.value
  if (menus.length === 0) return []

  const groups: { key: string; title: string; icon: string; items: MenuItem[] }[] = []
  const orphans: MenuItem[] = []

  // 找出分组（无 path 的父级）
  const groupMap: Record<number, { key: string; title: string; icon: string; items: MenuItem[] }> = {}

  for (const m of menus) {
    if (!m.path && m.parent_id === null) {
      // 可能是分组
      groupMap[m.id] = { key: m.key, title: resolveTitle(m), icon: m.icon || '', items: [] }
    }
  }

  for (const m of menus) {
    if (m.path) {
      if (m.parent_id && groupMap[m.parent_id]) {
        groupMap[m.parent_id].items.push(m)
      } else {
        orphans.push(m)
      }
    }
  }

  // 按 sort 排序分组
  for (const g of Object.values(groupMap)) {
    if (g.items.length > 0) {
      groups.push(g)
    }
  }

  // 没有分组的孤儿子项
  if (orphans.length > 0) {
    groups.unshift({ key: '_home', title: '', icon: '', items: orphans })
  }

  return groups
})

function isActive(path: string) {
  if (path === '/') return route.path === '/'
  return route.path.startsWith(path)
}

function isGroupActive(items: MenuItem[]) {
  return items.some(i => isActive(i.path!))
}

onMounted(async () => {
  if (!auth.isAuthed) return
  try {
    const { data } = await api.get('/api/v1/auth/me')
    me.value = data
    auth.setToken(auth.token, data)
    // 自动展开当前所在分组
    for (const group of sidebarMenus.value) {
      if (isGroupActive(group.items)) {
        expandedGroup.value = group.key
        break
      }
    }
  } catch { /* ignore */ }
})

async function logout() {
  try { await api.post('/api/v1/auth/logout') } catch { /* ignore */ }
  auth.logout()
  router.push('/login')
}
</script>

<template>
  <div class="min-h-screen bg-ink-50 flex">
    <!-- Sidebar -->
    <aside
      class="bg-white border-r border-ink-200 flex flex-col shrink-0 transition-all duration-200 z-30"
      :class="sidebarOpen ? 'w-56' : 'w-0 overflow-hidden'"
    >
      <!-- Logo -->
      <div class="h-14 flex items-center gap-2 px-4 border-b border-ink-200 shrink-0">
        <img src="/logo.svg" :alt="t('app.name')" class="w-7 h-7 rounded-lg" width="28" height="28">
        <span class="font-semibold text-sm">{{ t('app.name') }}</span>
      </div>

      <!-- Menu -->
      <nav class="flex-1 overflow-y-auto py-2 px-2">
        <template v-for="group in sidebarMenus" :key="group.key">
          <!-- 无分组的顶级菜单 -->
          <template v-if="group.key === '_home'">
            <router-link
              v-for="item in group.items"
              :key="item.path!"
              :to="item.path!"
              class="flex items-center gap-2 px-3 py-2 rounded-lg text-sm transition-colors mb-0.5"
              :class="isActive(item.path!) ? 'bg-ink-100 text-ink-900 font-medium' : 'text-ink-600 hover:bg-ink-50'"
            >
              <span v-if="resolveIcon(item.icon)" class="text-base">{{ resolveIcon(item.icon) }}</span>
              {{ resolveTitle(item) }}
            </router-link>
          </template>

          <!-- 有分组的菜单 -->
          <template v-else>
            <button
              class="w-full flex items-center justify-between px-3 py-2 rounded-lg text-sm font-medium transition-colors mb-0.5"
              :class="isGroupActive(group.items) ? 'text-ink-900 bg-ink-50' : 'text-ink-700 hover:bg-ink-50'"
              @click="expandedGroup = expandedGroup === group.key ? null : group.key"
            >
              <span class="flex items-center gap-2">
                <span v-if="resolveIcon(group.icon)" class="text-base">{{ resolveIcon(group.icon) }}</span>
                {{ group.title }}
              </span>
              <svg class="w-4 h-4 transition-transform" :class="{ 'rotate-90': expandedGroup === group.key }" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5l7 7-7 7" />
              </svg>
            </button>
            <div v-show="expandedGroup === group.key" class="ml-2">
              <router-link
                v-for="item in group.items"
                :key="item.path!"
                :to="item.path!"
                class="flex items-center gap-2 px-3 py-1.5 rounded-lg text-sm transition-colors mb-0.5"
                :class="isActive(item.path!) ? 'bg-ink-100 text-ink-900 font-medium' : 'text-ink-500 hover:text-ink-700 hover:bg-ink-50'"
              >
                <span v-if="resolveIcon(item.icon)" class="text-base">{{ resolveIcon(item.icon) }}</span>
                {{ resolveTitle(item) }}
              </router-link>
            </div>
          </template>
        </template>
      </nav>
    </aside>

    <!-- Main -->
    <div class="flex-1 min-w-0 flex flex-col">
      <!-- Top bar -->
      <header class="bg-white border-b border-ink-200 sticky top-0 z-20">
        <div class="h-14 flex items-center px-4 gap-3">
          <button @click="sidebarOpen = !sidebarOpen" class="p-1.5 rounded-md hover:bg-ink-100 text-ink-500">
            <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 6h16M4 12h16M4 18h16" />
            </svg>
          </button>
          <div class="flex-1" />
          <div class="flex items-center gap-3">
            <NotificationBell v-if="me" />
            <LocaleSwitcher />
            <span v-if="me" class="text-sm text-ink-500 hidden sm:inline">{{ me.nickname || me.username }}</span>
            <button @click="logout" class="text-sm text-ink-500 hover:text-ink-900">{{ t('nav.logout', '登出') }}</button>
          </div>
        </div>
      </header>

      <!-- Content -->
      <main class="flex-1 p-6">
        <div class="max-w-7xl mx-auto">
          <RouterView />
        </div>
      </main>
    </div>

    <WsStatus />
  </div>
</template>
