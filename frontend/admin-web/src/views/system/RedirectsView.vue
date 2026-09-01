<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { api } from '@/lib/api'

interface Redirect { id: number; from_path: string; to_path: string; code: number; enabled: boolean }

const items = ref<Redirect[]>([])
const search = ref('')
const showModal = ref(false)
const editing = ref<Redirect | null>(null)
const form = ref({ from_path: '', to_path: '', code: 301, enabled: true })

async function load() {
  try {
    const { data } = await api.get('/api/v1/system/redirects', { params: search.value ? { search: search.value } : {} })
    items.value = data.items || []
  } catch (e: any) { alert(e?.response?.data?.detail || '加载失败') }
}
function openCreate() { editing.value = null; form.value = { from_path: '', to_path: '', code: 301, enabled: true }; showModal.value = true }
function openEdit(r: Redirect) {
  editing.value = r
  form.value = { from_path: r.from_path, to_path: r.to_path, code: r.code, enabled: r.enabled }
  showModal.value = true
}
async function save() {
  if (!form.value.from_path || !form.value.to_path) return alert('起止路径必填')
  try {
    if (editing.value) await api.patch(`/api/v1/system/redirects/${editing.value.id}`, form.value)
    else await api.post('/api/v1/system/redirects', form.value)
    showModal.value = false
    await load()
  } catch (e: any) { alert(e?.response?.data?.detail || '保存失败') }
}
async function remove(r: Redirect) {
  if (!window.confirm('确认删除该重定向？')) return
  await api.delete(`/api/v1/system/redirects/${r.id}`)
  await load()
}
onMounted(load)
</script>

<template>
  <div>
    <div class="flex items-center justify-between mb-6">
      <div class="flex items-center gap-2">
        <h1 class="text-2xl font-semibold tracking-tight">↪️ URL 重定向</h1>
        <span class="text-sm text-ink-400">M3·P2 · 301/302</span>
      </div>
      <div class="flex gap-2">
        <input v-model="search" class="input w-56" placeholder="搜索路径…" @keyup.enter="load" />
        <button class="btn-primary" @click="openCreate">新增重定向</button>
      </div>
    </div>

    <div class="card overflow-hidden">
      <table class="w-full text-sm">
        <thead>
          <tr class="text-left text-ink-400 border-b">
            <th class="p-3">来源路径</th><th class="p-3">目标路径</th><th class="p-3">状态码</th><th class="p-3">启用</th><th class="p-3 text-right">操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="r in items" :key="r.id" class="border-b last:border-0">
            <td class="p-3 font-mono text-xs">{{ r.from_path }}</td>
            <td class="p-3 font-mono text-xs text-blue-600">→ {{ r.to_path }}</td>
            <td class="p-3"><span class="text-xs px-1.5 py-0.5 bg-ink-50 rounded">{{ r.code }}</span></td>
            <td class="p-3"><span :class="r.enabled ? 'text-green-600' : 'text-ink-300'">{{ r.enabled ? '是' : '否' }}</span></td>
            <td class="p-3 text-right space-x-2">
              <button class="btn-ghost text-sm" @click="openEdit(r)">编辑</button>
              <button class="btn-ghost text-sm text-red-600" @click="remove(r)">删除</button>
            </td>
          </tr>
          <tr v-if="!items.length"><td colspan="5" class="p-6 text-center text-ink-400">暂无重定向</td></tr>
        </tbody>
      </table>
    </div>

    <div v-if="showModal" class="fixed inset-0 bg-black/40 flex items-center justify-center z-50" @click.self="showModal = false">
      <div class="bg-white rounded-lg shadow-xl w-full max-w-md p-6">
        <h2 class="text-lg font-semibold mb-4">{{ editing ? '编辑重定向' : '新增重定向' }}</h2>
        <div class="space-y-3">
          <div>
            <label class="block text-sm font-medium mb-1">来源路径（from_path）</label>
            <input v-model="form.from_path" class="input" placeholder="/old-page" />
          </div>
          <div>
            <label class="block text-sm font-medium mb-1">目标路径（to_path）</label>
            <input v-model="form.to_path" class="input" placeholder="/new-page" />
          </div>
          <div>
            <label class="block text-sm font-medium mb-1">状态码</label>
            <select v-model.number="form.code" class="input">
              <option :value="301">301（永久）</option>
              <option :value="302">302（临时）</option>
            </select>
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
