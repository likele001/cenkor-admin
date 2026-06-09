<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { api } from '@/lib/api'
import AuditDetailDrawer from '@/components/AuditDetailDrawer.vue'

interface AuditEntry {
  id: number
  request_id: string
  user_id: number | null
  method: string
  path: string
  status_code: number
  duration_ms: number
  ip: string | null
  error: string | null
  created_at: string
}

const entries = ref<AuditEntry[]>([])
const stats = ref<any>({})
const loading = ref(true)
const error = ref('')
const selectedId = ref<number | null>(null)

const filters = ref({
  method: '',
  status_code: '' as string | number,
  path: '',
})

async function load() {
  loading.value = true
  error.value = ''
  try {
    const params: any = { page_size: 50 }
    if (filters.value.method) params.method = filters.value.method
    if (filters.value.status_code) params.status_code = filters.value.status_code
    if (filters.value.path) params.path_contains = filters.value.path

    const [listRes, statsRes] = await Promise.all([
      api.get('/api/v1/system/audit', { params }),
      api.get('/api/v1/system/audit/stats'),
    ])
    entries.value = listRes.data.items
    stats.value = statsRes.data
  } catch (e: any) {
    error.value = e?.response?.data?.detail || '加载失败'
  } finally {
    loading.value = false
  }
}

function statusClass(code: number) {
  if (code >= 500) return 'bg-red-100 text-red-700'
  if (code >= 400) return 'bg-amber-100 text-amber-700'
  if (code >= 300) return 'bg-blue-100 text-blue-700'
  return 'bg-emerald-100 text-emerald-700'
}

onMounted(load)
</script>

<template>
  <div class="min-h-screen bg-ink-50">
    <header class="bg-white border-b border-ink-200">
      <div class="max-w-7xl mx-auto px-6 h-14 flex items-center gap-4">
        <router-link to="/" class="text-sm text-ink-500 hover:text-ink-900">← Dashboard</router-link>
        <span class="font-semibold">审计日志</span>
      </div>
    </header>

    <main class="max-w-7xl mx-auto px-6 py-10">
      <!-- 统计卡片 -->
      <div v-if="stats && stats.total !== undefined" class="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
        <div class="card text-center">
          <div class="text-3xl font-semibold">{{ stats.total }}</div>
          <div class="text-sm text-ink-500 mt-1">近 7 天总数</div>
        </div>
        <div class="card text-center">
          <div class="text-3xl font-semibold text-amber-600">{{ stats.errors || 0 }}</div>
          <div class="text-sm text-ink-500 mt-1">错误数</div>
        </div>
        <div class="card text-center">
          <div class="text-3xl font-semibold text-emerald-600">{{ stats.by_status?.[200] || 0 }}</div>
          <div class="text-sm text-ink-500 mt-1">200 OK</div>
        </div>
        <div class="card text-center">
          <div class="text-3xl font-semibold text-red-600">{{ stats.by_status?.[500] || 0 }}</div>
          <div class="text-sm text-ink-500 mt-1">500 错误</div>
        </div>
      </div>

      <!-- 筛选 -->
      <div class="card mb-6">
        <div class="flex flex-wrap items-end gap-3">
          <div>
            <label class="block text-xs text-ink-500 mb-1">方法</label>
            <select v-model="filters.method" class="input">
              <option value="">全部</option>
              <option value="POST">POST</option>
              <option value="PATCH">PATCH</option>
              <option value="PUT">PUT</option>
              <option value="DELETE">DELETE</option>
            </select>
          </div>
          <div>
            <label class="block text-xs text-ink-500 mb-1">状态码</label>
            <input v-model.number="filters.status_code" type="number" placeholder="如 200" class="input" />
          </div>
          <div class="flex-1 min-w-[200px]">
            <label class="block text-xs text-ink-500 mb-1">路径包含</label>
            <input v-model="filters.path" placeholder="/api/v1/cms" class="input" />
          </div>
          <button @click="load" class="btn-primary">应用</button>
        </div>
      </div>

      <div v-if="loading" class="card text-ink-500">加载中…</div>
      <div v-else-if="error" class="card text-red-600">⚠️ {{ error }}</div>
      <div v-else>
        <div class="card overflow-hidden p-0">
          <table class="w-full text-sm">
            <thead class="bg-ink-50 border-b border-ink-200">
              <tr class="text-left text-ink-500">
                <th class="px-4 py-3 font-medium">时间</th>
                <th class="px-4 py-3 font-medium">方法</th>
                <th class="px-4 py-3 font-medium">状态</th>
                <th class="px-4 py-3 font-medium">路径</th>
                <th class="px-4 py-3 font-medium">用户</th>
                <th class="px-4 py-3 font-medium">耗时</th>
                <th class="px-4 py-3 font-medium">IP</th>
                <th class="px-4 py-3 font-medium text-right">操作</th>
              </tr>
            </thead>
            <tbody>
              <tr v-if="entries.length === 0">
                <td colspan="8" class="px-4 py-12 text-center text-ink-400">暂无审计记录</td>
              </tr>
              <tr v-for="e in entries" :key="e.id" class="border-b border-ink-100 last:border-0 hover:bg-ink-50">
                <td class="px-4 py-3 text-ink-500 text-xs font-mono">{{ e.created_at?.slice(11, 19) }}</td>
                <td class="px-4 py-3 font-mono text-xs">{{ e.method }}</td>
                <td class="px-4 py-3">
                  <span class="text-xs px-2 py-0.5 rounded-full" :class="statusClass(e.status_code)">
                    {{ e.status_code }}
                  </span>
                </td>
                <td class="px-4 py-3 font-mono text-xs">{{ e.path }}</td>
                <td class="px-4 py-3 text-ink-500">{{ e.user_id || '-' }}</td>
                <td class="px-4 py-3 text-ink-500">{{ e.duration_ms }}ms</td>
                <td class="px-4 py-3 text-ink-400 text-xs">{{ e.ip || '-' }}</td>
                <td class="px-4 py-3 text-right">
                  <button class="text-sm text-brand-600 hover:underline" @click="selectedId = e.id">
                    详情
                  </button>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </main>

    <AuditDetailDrawer :audit-id="selectedId" @close="selectedId = null" />
  </div>
</template>
