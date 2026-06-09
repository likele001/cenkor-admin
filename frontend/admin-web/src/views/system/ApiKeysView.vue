<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { api } from '@/lib/api'

interface ApiKey {
  id: number
  name: string
  prefix: string
  scopes: string[]
  expires_at: string | null
  last_used_at: string | null
  revoked: boolean
  created_at: string | null
  token?: string
}

const items = ref<ApiKey[]>([])
const loading = ref(true)
const error = ref('')
const showCreate = ref(false)
const creating = ref(false)
const newKey = ref<ApiKey | null>(null)
const copied = ref(false)
const form = ref({ name: '', scopes: '', expires_days: '' as string | number })

async function load() {
  loading.value = true
  error.value = ''
  try {
    const { data } = await api.get('/api/v1/api-keys')
    items.value = data.items
  } catch (e: any) {
    error.value = e?.response?.data?.detail || '加载失败'
  } finally {
    loading.value = false
  }
}

async function create() {
  if (!form.value.name) return
  creating.value = true
  try {
    const body: any = { name: form.value.name, scopes: form.value.scopes.split(',').map(s => s.trim()).filter(Boolean) }
    if (form.value.expires_days) body.expires_days = Number(form.value.expires_days)
    const { data } = await api.post('/api/v1/api-keys', body)
    newKey.value = data
    form.value = { name: '', scopes: '', expires_days: '' }
    await load()
  } catch (e: any) {
    alert('创建失败：' + (e?.response?.data?.detail || e.message))
  } finally {
    creating.value = false
  }
}

async function revoke(k: ApiKey) {
  if (!confirm(`撤销「${k.name}」？撤销后调用方将立即收到 401。`)) return
  try {
    await api.post(`/api/v1/api-keys/${k.id}/revoke`)
    await load()
  } catch (e: any) {
    alert('撤销失败：' + (e?.response?.data?.detail || e.message))
  }
}

async function destroy(k: ApiKey) {
  if (!confirm(`删除「${k.name}」？此操作不可撤销。`)) return
  try {
    await api.delete(`/api/v1/api-keys/${k.id}`)
    await load()
  } catch (e: any) {
    alert('删除失败：' + (e?.response?.data?.detail || e.message))
  }
}

async function copyToken() {
  if (!newKey.value?.token) return
  try {
    await navigator.clipboard.writeText(newKey.value.token)
    copied.value = true
    setTimeout(() => (copied.value = false), 2000)
  } catch {
    alert('复制失败，请手动选中复制')
  }
}

onMounted(load)
</script>

<template>
  <div class="min-h-screen bg-ink-50">
    <header class="bg-white border-b border-ink-200">
      <div class="max-w-7xl mx-auto px-6 h-14 flex items-center gap-4">
        <router-link to="/" class="text-sm text-ink-500 hover:text-ink-900">← Dashboard</router-link>
        <span class="font-semibold">API Keys</span>
      </div>
    </header>

    <main class="max-w-5xl mx-auto px-6 py-10">
      <div class="flex items-center justify-between mb-4">
        <p class="text-sm text-ink-500">
          创建 API Key 以便外部系统通过 <code class="px-1 rounded bg-ink-100">Authorization: Bearer ck_...</code> 调用。
        </p>
        <button class="btn-primary" @click="showCreate = !showCreate">
          {{ showCreate ? '取消' : '+ 新建 API Key' }}
        </button>
      </div>

      <!-- 新建表单 -->
      <form v-if="showCreate" class="card mb-6 space-y-3" @submit.prevent="create">
        <div>
          <label class="block text-sm font-medium mb-1">名称 *</label>
          <input v-model="form.name" required maxlength="100" class="input" placeholder="如：CI/CD 自动化部署" />
        </div>
        <div>
          <label class="block text-sm font-medium mb-1">Scopes（可选，逗号分隔）</label>
          <input v-model="form.scopes" class="input" placeholder="cms:product:read,cms:news:read" />
        </div>
        <div>
          <label class="block text-sm font-medium mb-1">过期天数（留空=永不过期）</label>
          <input v-model.number="form.expires_days" type="number" min="1" max="3650" class="input" placeholder="365" />
        </div>
        <button type="submit" class="btn-primary" :disabled="creating">
          {{ creating ? '创建中…' : '创建' }}
        </button>
      </form>

      <!-- 一次性显示新 token -->
      <div v-if="newKey" class="card mb-6 border-amber-300 bg-amber-50">
        <h3 class="text-sm font-semibold text-amber-800">⚠️ 请立即保存此 Token（仅显示一次）</h3>
        <div class="mt-2 flex items-center gap-2">
          <code class="flex-1 px-3 py-2 bg-white border border-amber-200 rounded font-mono text-xs break-all">{{ newKey.token }}</code>
          <button class="btn-primary text-sm" @click="copyToken">{{ copied ? '已复制' : '复制' }}</button>
        </div>
        <button class="mt-3 text-xs text-amber-700 hover:underline" @click="newKey = null">我已保存，关闭</button>
      </div>

      <!-- 列表 -->
      <div v-if="loading" class="card text-ink-500">加载中…</div>
      <div v-else-if="error" class="card text-red-600">⚠️ {{ error }}</div>
      <div v-else-if="items.length === 0" class="card text-center text-ink-400 py-12">
        还没有 API Key
      </div>
      <div v-else class="card p-0 overflow-hidden">
        <table class="w-full text-sm">
          <thead class="bg-ink-50 border-b border-ink-200">
            <tr class="text-left text-ink-500">
              <th class="px-4 py-3 font-medium">名称</th>
              <th class="px-4 py-3 font-medium">前缀</th>
              <th class="px-4 py-3 font-medium">Scopes</th>
              <th class="px-4 py-3 font-medium">最后使用</th>
              <th class="px-4 py-3 font-medium">状态</th>
              <th class="px-4 py-3 font-medium text-right">操作</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="k in items" :key="k.id" class="border-b border-ink-100 last:border-0">
              <td class="px-4 py-3 font-medium">{{ k.name }}</td>
              <td class="px-4 py-3 font-mono text-xs">{{ k.prefix }}…</td>
              <td class="px-4 py-3 text-ink-500 text-xs">
                <span v-if="k.scopes.length === 0" class="text-ink-400">（全部）</span>
                <span v-for="s in k.scopes" :key="s" class="inline-block px-1.5 py-0.5 mr-1 mb-0.5 rounded bg-ink-100 text-ink-700 font-mono text-[10px]">{{ s }}</span>
              </td>
              <td class="px-4 py-3 text-ink-500 text-xs">{{ k.last_used_at || '-' }}</td>
              <td class="px-4 py-3">
                <span
                  v-if="k.revoked"
                  class="text-xs px-2 py-0.5 rounded-full bg-red-100 text-red-700"
                >已撤销</span>
                <span
                  v-else
                  class="text-xs px-2 py-0.5 rounded-full bg-emerald-100 text-emerald-700"
                >生效中</span>
              </td>
              <td class="px-4 py-3 text-right space-x-2">
                <button v-if="!k.revoked" class="text-sm text-amber-600 hover:underline" @click="revoke(k)">撤销</button>
                <button class="text-sm text-red-600 hover:underline" @click="destroy(k)">删除</button>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </main>
  </div>
</template>
