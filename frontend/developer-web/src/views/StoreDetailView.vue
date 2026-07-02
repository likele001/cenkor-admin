<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { api } from '@/lib/api'

const route = useRoute()
const app = ref<any>(null)
const loading = ref(true)

onMounted(async () => {
  try {
    const { data } = await api.get('/api/v1/system/apps')
    app.value = data.items.find((a: any) => a.key === route.params.key)
  } catch { /* ignore */ } finally { loading.value = false }
})
</script>

<template>
  <div class="min-h-screen bg-ink-50">
    <header class="bg-white border-b border-ink-200">
      <div class="max-w-6xl mx-auto px-6 h-14 flex items-center">
        <router-link to="/store" class="text-sm text-ink-500 hover:text-ink-900">← 返回商店</router-link>
      </div>
    </header>
    <main class="max-w-6xl mx-auto px-6 py-8">
      <div v-if="loading" class="text-ink-500">加载中...</div>
      <div v-else-if="!app" class="text-ink-500 text-center py-12">应用不存在</div>
      <div v-else class="card p-6">
        <div class="flex items-start gap-4 mb-6">
          <span class="text-4xl">{{ app.icon }}</span>
          <div>
            <h1 class="text-2xl font-semibold">{{ app.name }}</h1>
            <p class="text-ink-400">{{ app.key }} @ {{ app.version }}</p>
            <p class="text-ink-600 mt-2">{{ app.description }}</p>
          </div>
        </div>
        <div v-if="app.content_types?.length" class="mb-4">
          <h3 class="font-medium mb-2">内容类型</h3>
          <div class="flex flex-wrap gap-1">
            <span v-for="ct in app.content_types" :key="ct.key" class="text-xs px-2 py-1 bg-blue-50 text-blue-600 rounded">
              {{ ct.icon }} {{ ct.name }}
            </span>
          </div>
        </div>
        <div v-if="app.permissions_required?.length" class="mb-4">
          <h3 class="font-medium mb-2">所需权限</h3>
          <div class="flex flex-wrap gap-1">
            <code v-for="p in app.permissions_required" :key="p" class="text-xs px-2 py-1 bg-ink-50 rounded">{{ p }}</code>
          </div>
        </div>
      </div>
    </main>
  </div>
</template>
