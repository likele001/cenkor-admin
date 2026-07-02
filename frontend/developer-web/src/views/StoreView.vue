<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { api } from '@/lib/api'

const apps = ref<any[]>([])
const loading = ref(true)

onMounted(async () => {
  try {
    const { data } = await api.get('/api/v1/system/apps')
    apps.value = data.items
  } catch { /* ignore */ } finally { loading.value = false }
})
</script>

<template>
  <div class="min-h-screen bg-ink-50">
    <header class="bg-white border-b border-ink-200">
      <div class="max-w-6xl mx-auto px-6 h-14 flex items-center justify-between">
        <div class="flex items-center gap-2">
          <router-link to="/" class="flex items-center gap-2">
            <img src="/logo.svg" class="w-7 h-7 rounded-lg" width="28" height="28">
            <span class="font-semibold">应用商店</span>
          </router-link>
        </div>
        <div class="flex items-center gap-4">
          <router-link to="/login" class="text-sm text-ink-600 hover:text-ink-900">登录</router-link>
          <router-link to="/register" class="btn-primary text-sm">成为开发者</router-link>
        </div>
      </div>
    </header>
    <main class="max-w-6xl mx-auto px-6 py-8">
      <h1 class="text-2xl font-semibold mb-6">应用商店</h1>
      <div v-if="loading" class="text-ink-500">加载中...</div>
      <div v-else-if="apps.length === 0" class="text-ink-500 text-center py-12">暂无应用</div>
      <div v-else class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        <router-link
          v-for="app in apps"
          :key="app.key"
          :to="`/store/${app.key}`"
          class="card p-4 hover:shadow-md transition-shadow"
        >
          <div class="flex items-start gap-3">
            <span class="text-2xl">{{ app.icon }}</span>
            <div>
              <h3 class="font-semibold">{{ app.name }}</h3>
              <p class="text-xs text-ink-400">{{ app.key }} @ {{ app.version }}</p>
              <p class="text-sm text-ink-600 mt-1 line-clamp-2">{{ app.description }}</p>
            </div>
          </div>
        </router-link>
      </div>
    </main>
  </div>
</template>
