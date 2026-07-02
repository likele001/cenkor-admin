<script setup lang="ts">
import { ref, computed } from 'vue'
import { useRouter, useRoute, RouterView, RouterLink } from 'vue-router'

const router = useRouter()
const route = useRoute()
const user = ref(JSON.parse(localStorage.getItem('dev_user') || '{}'))

function logout() {
  localStorage.removeItem('dev_token')
  localStorage.removeItem('dev_user')
  router.push('/')
}

const navItems = [
  { path: '/dashboard', label: '概览', icon: '📊' },
  { path: '/dashboard/submit', label: '提交应用', icon: '📤' },
  { path: '/dashboard/my-apps', label: '我的应用', icon: '📦' },
  { path: '/dashboard/docs', label: '开发文档', icon: '📖' },
  { path: '/dashboard/profile', label: '个人设置', icon: '👤' },
]

function isActive(path: string) {
  if (path === '/dashboard') return route.path === '/dashboard'
  return route.path.startsWith(path)
}
</script>

<template>
  <div class="min-h-screen bg-ink-50 flex">
    <!-- Sidebar -->
    <aside class="w-56 bg-white border-r border-ink-200 flex flex-col shrink-0">
      <div class="h-14 flex items-center gap-2 px-4 border-b border-ink-200">
        <img src="/logo.svg" class="w-7 h-7 rounded-lg" width="28" height="28">
        <span class="font-semibold text-sm">Developer</span>
      </div>
      <nav class="flex-1 py-3 px-2">
        <RouterLink
          v-for="item in navItems"
          :key="item.path"
          :to="item.path"
          class="flex items-center gap-2 px-3 py-2 rounded-lg text-sm transition-colors mb-0.5"
          :class="isActive(item.path) ? 'bg-ink-100 text-ink-900 font-medium' : 'text-ink-600 hover:bg-ink-50'"
        >
          <span>{{ item.icon }}</span>
          {{ item.label }}
        </RouterLink>
      </nav>
      <div class="p-3 border-t border-ink-200">
        <div class="flex items-center gap-2 mb-2">
          <div class="w-8 h-8 rounded-full bg-ink-200 flex items-center justify-center text-xs">
            {{ (user.nickname || user.username || '?')[0].toUpperCase() }}
          </div>
          <div class="text-sm truncate">{{ user.nickname || user.username }}</div>
        </div>
        <button @click="logout" class="text-sm text-ink-500 hover:text-ink-900 w-full text-left">退出登录</button>
      </div>
    </aside>

    <!-- Main -->
    <div class="flex-1 min-w-0 flex flex-col">
      <header class="bg-white border-b border-ink-200 h-14 flex items-center px-6">
        <h1 class="font-semibold">{{ navItems.find(n => isActive(n.path))?.label || '开发者中心' }}</h1>
      </header>
      <main class="flex-1 p-6">
        <div class="max-w-5xl mx-auto">
          <RouterView />
        </div>
      </main>
    </div>
  </div>
</template>
