<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { api } from '@/lib/api'

interface AppItem {
  key: string
  name: string
  version: string
  code_version: string | null
  db_version: string | null
  status: string
  description: string
  icon: string
}

const apps = ref<AppItem[]>([])
const loading = ref(true)
const error = ref('')
const acting = ref<string | null>(null)

const statusLabel: Record<string, string> = {
  installed: '已安装',
  not_installed: '未安装',
  needs_upgrade: '需升级',
  missing: '代码缺失',
}

async function load() {
  loading.value = true
  error.value = ''
  try {
    const { data } = await api.get('/api/v1/system/apps')
    apps.value = data.items
  } catch (e: any) {
    error.value = e?.response?.data?.detail || '加载失败'
  } finally {
    loading.value = false
  }
}

async function install(key: string) {
  acting.value = key
  try {
    await api.post(`/api/v1/system/apps/${key}/install`)
    await load()
  } catch (e: any) {
    alert(e?.response?.data?.detail || '安装失败')
  } finally {
    acting.value = null
  }
}

async function uninstall(key: string) {
  if (!confirm(`确定卸载 ${key}？`)) return
  acting.value = key
  try {
    await api.post(`/api/v1/system/apps/${key}/uninstall`)
    await load()
  } catch (e: any) {
    alert(e?.response?.data?.detail || '卸载失败')
  } finally {
    acting.value = null
  }
}

onMounted(load)
</script>

<template>
  <div>
    <h1 class="text-2xl font-semibold tracking-tight mb-2">应用中心</h1>
    <p class="text-ink-500 mb-6">管理平台已安装的业务 App（MVP：代码级模块化）。</p>

    <div v-if="loading" class="card text-ink-500">加载中…</div>
    <div v-else-if="error" class="card text-red-600">{{ error }}</div>
    <div v-else class="grid md:grid-cols-2 gap-4">
      <div v-for="app in apps" :key="app.key" class="card">
        <div class="flex items-start gap-3">
          <span class="text-2xl">{{ app.icon }}</span>
          <div class="flex-1">
            <h3 class="font-semibold">{{ app.name }}</h3>
            <code class="text-xs text-ink-400">{{ app.key }} @ {{ app.version }}</code>
            <p class="text-sm text-ink-600 mt-2">{{ app.description }}</p>
            <span class="inline-block mt-2 text-xs px-2 py-0.5 rounded-full bg-ink-100">
              {{ statusLabel[app.status] || app.status }}
            </span>
          </div>
        </div>
        <div class="mt-4 flex gap-2">
          <button
            v-if="app.status === 'not_installed' || app.status === 'needs_upgrade'"
            class="btn-primary text-sm"
            :disabled="acting === app.key"
            @click="install(app.key)"
          >
            {{ app.status === 'needs_upgrade' ? '升级' : '安装' }}
          </button>
          <button
            v-if="app.status === 'installed'"
            class="btn-ghost text-sm text-red-600"
            :disabled="acting === app.key"
            @click="uninstall(app.key)"
          >
            卸载
          </button>
        </div>
      </div>
    </div>
  </div>
</template>
