<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { api } from '@/lib/api'

interface Task {
  name: string
  title: string
  description: string
  default_schedule: string
  schedule: { enabled: boolean; cron: string | null }
}

const items = ref<Task[]>([])
const loading = ref(true)
const error = ref('')
const editingCron = ref<string | null>(null)
const draftCron = ref('')

async function load() {
  loading.value = true
  error.value = ''
  try {
    const { data } = await api.get('/api/v1/system/tasks')
    items.value = data.items
  } catch (e: any) {
    error.value = e?.response?.data?.detail || '加载失败'
  } finally {
    loading.value = false
  }
}

async function toggle(t: Task) {
  try {
    await api.put(`/api/v1/system/tasks/${t.name}/schedule`, {
      enabled: !t.schedule.enabled,
      cron: t.schedule.cron,
    })
    await load()
  } catch (e: any) {
    alert('操作失败：' + (e?.response?.data?.detail || e.message))
  }
}

async function saveCron(t: Task) {
  try {
    await api.put(`/api/v1/system/tasks/${t.name}/schedule`, {
      enabled: t.schedule.enabled,
      cron: draftCron.value || null,
    })
    editingCron.value = null
    await load()
  } catch (e: any) {
    alert('保存失败：' + (e?.response?.data?.detail || e.message))
  }
}

async function runNow(t: Task) {
  try {
    const { data } = await api.post(`/api/v1/system/tasks/${t.name}/run`)
    if (data.ok) {
      alert(`已触发任务，task_id: ${data.task_id ?? '(无)'}，transport: ${data.transport}`)
    } else {
      alert(`触发失败：${data.reason ?? 'unknown'}（dev 环境无 Celery worker 是正常的）`)
    }
  } catch (e: any) {
    alert('触发失败：' + (e?.response?.data?.detail || e.message))
  }
}

function startEditCron(t: Task) {
  editingCron.value = t.name
  draftCron.value = t.schedule.cron || ''
}

onMounted(load)
</script>

<template>
  <div class="min-h-screen bg-ink-50">
    <header class="bg-white border-b border-ink-200">
      <div class="max-w-7xl mx-auto px-6 h-14 flex items-center gap-4">
        <router-link to="/" class="text-sm text-ink-500 hover:text-ink-900">← Dashboard</router-link>
        <span class="font-semibold">定时任务</span>
      </div>
    </header>

    <main class="max-w-5xl mx-auto px-6 py-10">
      <p class="text-sm text-ink-500 mb-4">
        调度配置存储于应用内存，重启后恢复为 <code class="px-1 rounded bg-ink-100">default_schedule</code>。
        生产环境建议接入 Celery Beat + Beat Schedule DB。
      </p>

      <div v-if="loading" class="card text-ink-500">加载中…</div>
      <div v-else-if="error" class="card text-red-600">⚠️ {{ error }}</div>
      <div v-else class="card p-0 overflow-hidden">
        <table class="w-full text-sm">
          <thead class="bg-ink-50 border-b border-ink-200">
            <tr class="text-left text-ink-500">
              <th class="px-4 py-3 font-medium">任务</th>
              <th class="px-4 py-3 font-medium">描述</th>
              <th class="px-4 py-3 font-medium">调度 (cron)</th>
              <th class="px-4 py-3 font-medium">启用</th>
              <th class="px-4 py-3 font-medium text-right">操作</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="t in items" :key="t.name" class="border-b border-ink-100 last:border-0">
              <td class="px-4 py-3">
                <div class="font-mono text-xs">{{ t.name }}</div>
                <div class="text-ink-700 font-medium">{{ t.title }}</div>
              </td>
              <td class="px-4 py-3 text-ink-600 max-w-xs">{{ t.description }}</td>
              <td class="px-4 py-3 font-mono text-xs">
                <div v-if="editingCron === t.name" class="flex items-center gap-1.5">
                  <input v-model="draftCron" placeholder="如 0 3 * * *" class="input text-xs font-mono" />
                  <button class="text-xs text-brand-600 hover:underline" @click="saveCron(t)">保存</button>
                  <button class="text-xs text-ink-500 hover:underline" @click="editingCron = null">取消</button>
                </div>
                <button
                  v-else
                  type="button"
                  class="text-left hover:underline"
                  @click="startEditCron(t)"
                >
                  {{ t.schedule.cron || t.default_schedule || 'on_demand' }}
                </button>
              </td>
              <td class="px-4 py-3">
                <label class="inline-flex items-center cursor-pointer">
                  <input
                    type="checkbox"
                    :checked="t.schedule.enabled"
                    class="rounded"
                    @change="toggle(t)"
                  />
                </label>
              </td>
              <td class="px-4 py-3 text-right">
                <button class="text-sm text-brand-600 hover:underline" @click="runNow(t)">
                  立即运行
                </button>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </main>
  </div>
</template>
