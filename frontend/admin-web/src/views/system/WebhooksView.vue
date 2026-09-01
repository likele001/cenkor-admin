<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { api } from '@/lib/api'

interface Webhook {
  id: number; url: string; events: string[]; secret: string | null
  description: string | null; enabled: boolean
}

const EVENTS = ['entry.saved', 'entry.deleted', 'content_type.created', 'media.uploaded', 'user.login']
const items = ref<Webhook[]>([])
const loading = ref(false)
const showModal = ref(false)
const editing = ref<Webhook | null>(null)
const form = ref({ url: '', events: [] as string[], secret: '', description: '', enabled: true })

async function load() {
  loading.value = true
  try {
    const { data } = await api.get('/api/v1/system/webhooks')
    items.value = data.items || []
  } catch (e: any) { alert(e?.response?.data?.detail || '加载失败') } finally { loading.value = false }
}
function openCreate() {
  editing.value = null
  form.value = { url: '', events: ['entry.saved'], secret: '', description: '', enabled: true }
  showModal.value = true
}
function openEdit(w: Webhook) {
  editing.value = w
  form.value = { url: w.url, events: [...w.events], secret: w.secret || '', description: w.description || '', enabled: w.enabled }
  showModal.value = true
}
async function save() {
  if (!form.value.url) return alert('URL 必填')
  try {
    if (editing.value) {
      await api.patch(`/api/v1/system/webhooks/${editing.value.id}`, { ...form.value, secret: form.value.secret || null })
    } else {
      await api.post('/api/v1/system/webhooks', { ...form.value, secret: form.value.secret || null })
    }
    showModal.value = false
    await load()
  } catch (e: any) { alert(e?.response?.data?.detail || '保存失败') }
}
async function remove(w: Webhook) {
  if (!window.confirm(`确认删除该 Webhook？`)) return
  await api.delete(`/api/v1/system/webhooks/${w.id}`)
  await load()
}
function toggleEvent(ev: string) {
  const i = form.value.events.indexOf(ev)
  if (i >= 0) form.value.events.splice(i, 1)
  else form.value.events.push(ev)
}
onMounted(load)
</script>

<template>
  <div>
    <div class="flex items-center justify-between mb-6">
      <div class="flex items-center gap-2">
        <h1 class="text-2xl font-semibold tracking-tight">⚡ Webhook 事件推送</h1>
        <span class="text-sm text-ink-400">M3·P2</span>
      </div>
      <button class="btn-primary" @click="openCreate">新增订阅</button>
    </div>

    <div class="card overflow-hidden">
      <div v-if="loading" class="text-ink-500 p-6">加载中…</div>
      <table v-else class="w-full text-sm">
        <thead>
          <tr class="text-left text-ink-400 border-b">
            <th class="p-3">URL</th><th class="p-3">事件</th><th class="p-3">状态</th><th class="p-3 text-right">操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="w in items" :key="w.id" class="border-b last:border-0">
            <td class="p-3">
              <div class="font-mono text-xs truncate max-w-xs">{{ w.url }}</div>
              <div v-if="w.description" class="text-xs text-ink-400">{{ w.description }}</div>
            </td>
            <td class="p-3">
              <span v-for="ev in w.events" :key="ev" class="text-xs px-1.5 py-0.5 bg-blue-50 text-blue-600 rounded mr-1">{{ ev }}</span>
            </td>
            <td class="p-3">
              <span :class="w.enabled ? 'text-green-600' : 'text-ink-300'">{{ w.enabled ? '启用' : '停用' }}</span>
            </td>
            <td class="p-3 text-right space-x-2">
              <button class="btn-ghost text-sm" @click="openEdit(w)">编辑</button>
              <button class="btn-ghost text-sm text-red-600" @click="remove(w)">删除</button>
            </td>
          </tr>
          <tr v-if="!items.length"><td colspan="4" class="p-6 text-center text-ink-400">暂无订阅</td></tr>
        </tbody>
      </table>
    </div>

    <div v-if="showModal" class="fixed inset-0 bg-black/40 flex items-center justify-center z-50" @click.self="showModal = false">
      <div class="bg-white rounded-lg shadow-xl w-full max-w-md p-6">
        <h2 class="text-lg font-semibold mb-4">{{ editing ? '编辑订阅' : '新增订阅' }}</h2>
        <div class="space-y-3">
          <div>
            <label class="block text-sm font-medium mb-1">回调 URL</label>
            <input v-model="form.url" class="input" placeholder="https://example.com/hooks/cenkor" />
          </div>
          <div>
            <label class="block text-sm font-medium mb-1">订阅事件</label>
            <div class="flex flex-wrap gap-1.5">
              <label v-for="ev in EVENTS" :key="ev" class="flex items-center gap-1 px-2 py-1 rounded text-xs cursor-pointer border"
                :class="form.events.includes(ev) ? 'bg-blue-50 border-blue-300' : 'bg-white border-ink-200'">
                <input type="checkbox" :checked="form.events.includes(ev)" @change="toggleEvent(ev)" class="w-3 h-3" />
                {{ ev }}
              </label>
            </div>
          </div>
          <div>
            <label class="block text-sm font-medium mb-1">签名密钥（HMAC，可选）</label>
            <input v-model="form.secret" class="input" placeholder="留空则不签名" />
          </div>
          <div>
            <label class="block text-sm font-medium mb-1">描述</label>
            <input v-model="form.description" class="input" />
          </div>
          <label class="flex items-center gap-2">
            <input type="checkbox" v-model="form.enabled" /><span class="text-sm">启用</span>
          </label>
        </div>
        <div class="flex justify-end gap-2 mt-6">
          <button class="btn-ghost" @click="showModal = false">取消</button>
          <button class="btn-primary" @click="save">保存</button>
        </div>
      </div>
    </div>
  </div>
</template>
