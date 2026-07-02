<script setup lang="ts">
import { useI18n } from 'vue-i18n'
const { t } = useI18n()
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
    error.value = e?.response?.data?.detail || 't("caseEdit.loadFailed")'
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
    alert('t("apiKeys.创建失败_1d9o4p")' + (e?.response?.data?.detail || e.message))
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
    alert('t("apiKeys.撤销失败_1liumu")' + (e?.response?.data?.detail || e.message))
  }
}

async function destroy(k: ApiKey) {
  if (!confirm(`删除「${k.name}」？此操作不可撤销。`)) return
  try {
    await api.delete(`/api/v1/api-keys/${k.id}`)
    await load()
  } catch (e: any) {
    alert('t("usersList.删除失败_1kc17l")' + (e?.response?.data?.detail || e.message))
  }
}

async function copyToken() {
  if (!newKey.value?.token) return
  try {
    await navigator.clipboard.writeText(newKey.value.token)
    copied.value = true
    setTimeout(() => (copied.value = false), 2000)
  } catch {
    alert('t("apiKeys.复制失败_1xgj2m")')
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
          {{ t('apiKeys.创建APIKey以便外部系统通过') }} <code class="px-1 rounded bg-ink-100">Authorization: Bearer ck_...</code> {{ t('apiKeys.调用') }}
        </p>
        <button class="btn-primary" @click="showCreate = !showCreate">
          {{ showCreate ? '取消' : '+ 新建 API Key' }}
        </button>
      </div>

      <!-- 新建表单 -->
      <form v-if="showCreate" class="card mb-6 space-y-3" @submit.prevent="create">
        <div>
          <label class="block text-sm font-medium mb-1">{{ t('roles.名称_b3i4lp') }}</label>
          <input v-model="form.name" required maxlength="100" class="input" :placeholder="t('apiKeys.如_m1bx0')" />
        </div>
        <div>
          <label class="block text-sm font-medium mb-1">{{ t('apiKeys.text_ecwic2') }}</label>
          <input v-model="form.scopes" class="input" placeholder="cms:product:read,cms:news:read" />
        </div>
        <div>
          <label class="block text-sm font-medium mb-1">{{ t('apiKeys.过期天数_xn6iyx') }}</label>
          <input v-model.number="form.expires_days" type="number" min="1" max="3650" class="input" placeholder="365" />
        </div>
        <button type="submit" class="btn-primary" :disabled="creating">
          {{ creating ? '创建中…' : '创建' }}
        </button>
      </form>

      <!-- 一次性显示新 token -->
      <div v-if="newKey" class="card mb-6 border-amber-300 bg-amber-50">
        <h3 class="text-sm font-semibold text-amber-800">{{ t('apiKeys.text_1x8682') }}</h3>
        <div class="mt-2 flex items-center gap-2">
          <code class="flex-1 px-3 py-2 bg-white border border-amber-200 rounded font-mono text-xs break-all">{{ newKey.token }}</code>
          <button class="btn-primary text-sm" @click="copyToken">{{ copied ? '已复制' : '复制' }}</button>
        </div>
        <button class="mt-3 text-xs text-amber-700 hover:underline" @click="newKey = null">{{ t('apiKeys.我已保存_11twiv') }}</button>
      </div>

      <!-- 列表 -->
      <div v-if="loading" class="card text-ink-500">{{ t('usersList.加载中_b0k5km') }}</div>
      <div v-else-if="error" class="card text-red-600">⚠️ {{ error }}</div>
      <div v-else-if="items.length === 0" class="card text-center text-ink-400 py-12">
        {{ t('apiKeys.还没有APIKey') }}
      </div>
      <div v-else class="card p-0 overflow-hidden">
        <table class="w-full text-sm">
          <thead class="bg-ink-50 border-b border-ink-200">
            <tr class="text-left text-ink-500">
              <th class="px-4 py-3 font-medium">{{ t('tags.名称_eyrn') }}</th>
              <th class="px-4 py-3 font-medium">{{ t('apiKeys.前缀_ep1v') }}</th>
              <th class="px-4 py-3 font-medium">Scopes</th>
              <th class="px-4 py-3 font-medium">{{ t('apiKeys.最后使用_dcdzx3') }}</th>
              <th class="px-4 py-3 font-medium">{{ t('usersList.状态_k1e3') }}</th>
              <th class="px-4 py-3 font-medium text-right">{{ t('usersList.操作_hkxb') }}</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="k in items" :key="k.id" class="border-b border-ink-100 last:border-0">
              <td class="px-4 py-3 font-medium">{{ k.name }}</td>
              <td class="px-4 py-3 font-mono text-xs">{{ k.prefix }}…</td>
              <td class="px-4 py-3 text-ink-500 text-xs">
                <span v-if="k.scopes.length === 0" class="text-ink-400">{{ t('apiKeys.text_winaf5') }}</span>
                <span v-for="s in k.scopes" :key="s" class="inline-block px-1.5 py-0.5 mr-1 mb-0.5 rounded bg-ink-100 text-ink-700 font-mono text-[10px]">{{ s }}</span>
              </td>
              <td class="px-4 py-3 text-ink-500 text-xs">{{ k.last_used_at || '-' }}</td>
              <td class="px-4 py-3">
                <span
                  v-if="k.revoked"
                  class="text-xs px-2 py-0.5 rounded-full bg-red-100 text-red-700"
                >{{ t('apiKeys.已撤销_e9b2m') }}</span>
                <span
                  v-else
                  class="text-xs px-2 py-0.5 rounded-full bg-emerald-100 text-emerald-700"
                >{{ t('apiKeys.生效中_hn8ec') }}</span>
              </td>
              <td class="px-4 py-3 text-right space-x-2">
                <button v-if="!k.revoked" class="text-sm text-amber-600 hover:underline" @click="revoke(k)">{{ t('apiKeys.撤销_hxp8') }}</button>
                <button class="text-sm text-red-600 hover:underline" @click="destroy(k)">{{ t('usersList.删除_eslg') }}</button>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </main>
  </div>
</template>
