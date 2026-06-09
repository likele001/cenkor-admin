<script setup lang="ts">
import { ref, onMounted, watch } from 'vue'
import { api } from '@/lib/api'
import { useAuthStore } from '@/stores/auth'
import SearchInput from '@/components/SearchInput.vue'
import CsvExportButton from '@/components/CsvExportButton.vue'

interface UserItem {
  id: number
  username: string
  email: string
  nickname: string
  avatar: string | null
  status: string
  is_superuser: boolean
  last_login_at: string | null
  created_at: string
  role_ids: number[]
}

const auth = useAuthStore()
const users = ref<UserItem[]>([])
const roles = ref<{ id: number; code: string; name: string }[]>([])
const loading = ref(true)
const error = ref('')
const showDialog = ref(false)
const isNew = ref(true)
const saving = ref(false)
const search = ref('')
const form = ref({
  id: 0,
  username: '',
  email: '',
  nickname: '',
  password: '',
  role_ids: [] as number[],
  is_superuser: false,
  status: 'active',
})

async function load() {
  loading.value = true
  error.value = ''
  try {
    const [u, r] = await Promise.all([
      api.get('/api/v1/auth/users', { params: { page_size: 100, search: search.value || undefined } }),
      api.get('/api/v1/rbac/roles'),
    ])
    users.value = u.data.items
    roles.value = r.data.items
  } catch (e: any) {
    error.value = e?.response?.data?.detail || '加载失败'
  } finally {
    loading.value = false
  }
}

function openNew() {
  isNew.value = true
  form.value = { id: 0, username: '', email: '', nickname: '', password: '', role_ids: [], is_superuser: false, status: 'active' }
  showDialog.value = true
}

function openEdit(u: UserItem) {
  isNew.value = false
  form.value = { ...u, password: '' }
  showDialog.value = true
}

async function save() {
  saving.value = true
  error.value = ''
  try {
    if (isNew.value) {
      await api.post('/api/v1/auth/users', form.value)
    } else {
      await api.patch(`/api/v1/auth/users/${form.value.id}`, form.value)
    }
    showDialog.value = false
    await load()
  } catch (e: any) {
    error.value = e?.response?.data?.detail || '保存失败'
  } finally {
    saving.value = false
  }
}

async function del(u: UserItem) {
  if (!confirm(`确定删除「${u.username}」吗？`)) return
  try {
    await api.delete(`/api/v1/auth/users/${u.id}`)
    await load()
  } catch (e: any) {
    alert('删除失败：' + (e?.response?.data?.detail || e.message))
  }
}

async function resetPwd(u: UserItem) {
  const np = prompt(`重置「${u.username}」的密码（至少 8 字符）：`)
  if (!np || np.length < 8) return alert('密码至少 8 字符')
  try {
    await api.post(`/api/v1/auth/users/${u.id}/change-password`, { new_password: np })
    alert('密码已重置')
  } catch (e: any) {
    alert('失败：' + (e?.response?.data?.detail || e.message))
  }
}

function roleName(id: number) {
  return roles.value.find(r => r.id === id)?.name || `#${id}`
}

onMounted(load)
watch(search, () => { load() })
</script>

<template>
  <div class="min-h-screen bg-ink-50">
    <header class="bg-white border-b border-ink-200">
      <div class="max-w-7xl mx-auto px-6 h-14 flex items-center gap-4">
        <router-link to="/" class="text-sm text-ink-500 hover:text-ink-900">← Dashboard</router-link>
        <span class="font-semibold">用户管理</span>
      </div>
    </header>

    <main class="max-w-7xl mx-auto px-6 py-10">
      <div v-if="loading" class="card text-ink-500">加载中…</div>
      <div v-else-if="error" class="card text-red-600">⚠️ {{ error }}</div>
      <div v-else>
        <div class="flex flex-wrap items-center justify-between gap-3 mb-6">
          <h1 class="text-2xl font-semibold tracking-tight">用户列表（{{ users.length }}）</h1>
          <div class="flex items-center gap-3">
            <SearchInput v-model="search" placeholder="按用户名/邮箱/昵称搜索…" />
            <CsvExportButton endpoint="/api/v1/auth/users/export" filename="users.csv" :params="{ search: search || undefined }" />
            <button @click="openNew" class="btn-primary">+ 新建用户</button>
          </div>
        </div>
        <div class="card overflow-hidden p-0">
          <table class="w-full text-sm">
            <thead class="bg-ink-50 border-b border-ink-200">
              <tr class="text-left text-ink-500">
                <th class="px-4 py-3 font-medium">用户名</th>
                <th class="px-4 py-3 font-medium">邮箱</th>
                <th class="px-4 py-3 font-medium">昵称</th>
                <th class="px-4 py-3 font-medium">角色</th>
                <th class="px-4 py-3 font-medium">状态</th>
                <th class="px-4 py-3 font-medium text-right">操作</th>
              </tr>
            </thead>
            <tbody>
              <tr v-if="users.length === 0">
                <td colspan="6" class="px-4 py-12 text-center text-ink-400">暂无用户</td>
              </tr>
              <tr v-for="u in users" :key="u.id" class="border-b border-ink-100 last:border-0 hover:bg-ink-50">
                <td class="px-4 py-3 font-medium">
                  {{ u.username }}
                  <span v-if="u.is_superuser" class="ml-1 text-xs px-2 py-0.5 rounded bg-ink-900 text-white">超管</span>
                </td>
                <td class="px-4 py-3 text-ink-600">{{ u.email }}</td>
                <td class="px-4 py-3 text-ink-600">{{ u.nickname }}</td>
                <td class="px-4 py-3">
                  <div class="flex flex-wrap gap-1">
                    <span v-for="rid in u.role_ids" :key="rid" class="text-xs px-2 py-0.5 rounded bg-ink-100 text-ink-700">
                      {{ roleName(rid) }}
                    </span>
                  </div>
                </td>
                <td class="px-4 py-3">
                  <span class="text-xs px-2 py-0.5 rounded-full"
                    :class="u.status === 'active' ? 'bg-emerald-100 text-emerald-700' : 'bg-ink-200 text-ink-600'">
                    {{ u.status === 'active' ? '活跃' : u.status }}
                  </span>
                </td>
                <td class="px-4 py-3 text-right space-x-2 whitespace-nowrap">
                  <button @click="openEdit(u)" class="text-sm text-ink-600 hover:text-ink-900">编辑</button>
                  <button @click="resetPwd(u)" class="text-sm text-ink-600 hover:text-ink-900">重置密码</button>
                  <button @click="del(u)" class="text-sm text-red-600 hover:underline">删除</button>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </main>

    <!-- 编辑/新建对话框 -->
    <div v-if="showDialog" class="fixed inset-0 z-50 flex items-center justify-center p-4 bg-ink-900/40" @click.self="showDialog = false">
      <div class="bg-white rounded-2xl w-full max-w-lg p-6 max-h-[90vh] overflow-y-auto">
        <h2 class="text-lg font-semibold mb-4">{{ isNew ? '新建用户' : '编辑用户' }}</h2>
        <form @submit.prevent="save" class="space-y-4">
          <div class="grid grid-cols-2 gap-4">
            <div>
              <label class="block text-sm font-medium mb-1.5">用户名 *</label>
              <input v-model="form.username" required :disabled="!isNew" class="input" />
            </div>
            <div>
              <label class="block text-sm font-medium mb-1.5">昵称</label>
              <input v-model="form.nickname" class="input" />
            </div>
          </div>
          <div>
            <label class="block text-sm font-medium mb-1.5">邮箱 *</label>
            <input v-model="form.email" type="email" required class="input" />
          </div>
          <div v-if="isNew">
            <label class="block text-sm font-medium mb-1.5">密码 * <span class="text-xs text-ink-400">（≥8 字符）</span></label>
            <input v-model="form.password" type="password" required minlength="8" class="input" />
          </div>
          <div>
            <label class="block text-sm font-medium mb-2">角色</label>
            <div class="space-y-1 max-h-40 overflow-y-auto border border-ink-200 rounded-xl p-3">
              <label v-for="r in roles" :key="r.id" class="flex items-center gap-2 text-sm">
                <input type="checkbox" :value="r.id" v-model="form.role_ids" class="rounded" />
                <span>{{ r.name }} <code class="text-xs text-ink-400">({{ r.code }})</code></span>
              </label>
            </div>
          </div>
          <div class="grid grid-cols-2 gap-4">
            <div>
              <label class="block text-sm font-medium mb-1.5">状态</label>
              <select v-model="form.status" class="input">
                <option value="active">活跃</option>
                <option value="disabled">禁用</option>
                <option value="locked">锁定</option>
              </select>
            </div>
            <div class="flex items-end">
              <label class="flex items-center gap-2 text-sm">
                <input v-model="form.is_superuser" type="checkbox" class="rounded" /> 超级管理员
              </label>
            </div>
          </div>
          <div v-if="error" class="text-sm text-red-600">{{ error }}</div>
          <div class="flex gap-3 pt-2">
            <button type="submit" :disabled="saving" class="btn-primary flex-1">
              {{ saving ? '保存中…' : isNew ? '创建' : '保存' }}
            </button>
            <button type="button" @click="showDialog = false" class="btn-ghost">取消</button>
          </div>
        </form>
      </div>
    </div>
  </div>
</template>
