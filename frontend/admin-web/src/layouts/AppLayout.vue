<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { api } from '@/lib/api'

const router = useRouter()
const route = useRoute()
const auth = useAuthStore()
const me = ref(auth.user)

interface MenuItem {
  id: number
  key: string
  title: string
  path: string | null
  parent_id: number | null
  icon: string | null
}

const flatMenus = computed(() => me.value?.menus ?? [])

const navItems = computed(() => {
  const menus = flatMenus.value
  if (menus.length === 0) {
    return [
      { path: '/', title: 'Dashboard' },
      { path: '/cms/products', title: '产品' },
      { path: '/cms/cases', title: '案例' },
      { path: '/cms/news', title: '新闻' },
      { path: '/cms/site', title: '站点配置' },
      { path: '/cms/media', title: '媒体' },
      { path: '/system/users', title: '用户' },
      { path: '/system/roles', title: '角色' },
      { path: '/system/menus', title: '菜单' },
      { path: '/system/apps', title: '应用中心' },
      { path: '/system/audit', title: '审计' },
    ]
  }
  return menus.filter((m) => m.path).sort((a, b) => a.id - b.id)
})

onMounted(async () => {
  if (!auth.isAuthed) return
  try {
    const { data } = await api.get('/api/v1/auth/me')
    me.value = data
    auth.setToken(auth.token, data)
  } catch { /* ignore */ }
})

async function logout() {
  try { await api.post('/api/v1/auth/logout') } catch { /* ignore */ }
  auth.logout()
  router.push('/login')
}

function isActive(path: string) {
  if (path === '/') return route.path === '/'
  return route.path.startsWith(path)
}
</script>

<template>
  <div class="min-h-screen bg-ink-50">
    <header class="bg-white border-b border-ink-200 sticky top-0 z-40">
      <div class="max-w-7xl mx-auto px-6 h-14 flex items-center justify-between">
        <div class="flex items-center gap-6 min-w-0">
          <div class="flex items-center gap-2 shrink-0">
            <img src="/logo.svg" alt="Cenkor" class="w-7 h-7 rounded-lg" width="28" height="28">
            <span class="font-semibold hidden sm:inline">Cenkor Admin</span>
          </div>
          <nav class="flex items-center gap-1 text-sm overflow-x-auto">
            <router-link
              v-for="item in navItems"
              :key="item.path!"
              :to="item.path!"
              class="px-3 py-1.5 rounded-md text-ink-600 hover:bg-ink-100 whitespace-nowrap"
              :class="{ 'bg-ink-100 text-ink-900': isActive(item.path!) }"
            >
              {{ item.title }}
            </router-link>
          </nav>
        </div>
        <div class="flex items-center gap-3 shrink-0">
          <span v-if="me" class="text-sm text-ink-500 hidden sm:inline">{{ me.nickname || me.username }}</span>
          <button @click="logout" class="text-sm text-ink-500 hover:text-ink-900">登出</button>
        </div>
      </div>
    </header>
    <main class="max-w-7xl mx-auto px-6 py-10">
      <RouterView />
    </main>
  </div>
</template>
