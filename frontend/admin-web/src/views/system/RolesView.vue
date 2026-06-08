<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { api } from '@/lib/api'

interface Role {
  id: number
  code: string
  name: string
  description: string | null
  is_system: boolean
  created_at: string
}

interface Permission {
  id: number
  code: string
  type: string
  name: string
}

const roles = ref<Role[]>([])
const permissions = ref<Permission[]>([])
const loading = ref(true)
const error = ref('')
const showDialog = ref(false)
const isNew = ref(true)
const saving = ref(false)
const form = ref({
  id: 0,
  code: '',
  name: '',
  description: '',
  permission_ids: [] as number[],
  menu_ids: [] as number[],
})

async function load() {
  loading.value = true
  error.value = ''
  try {
    const [r, p] = await Promise.all([
      api.get('/api/v1/rbac/roles'),
      api.get('/api/v1/rbac/permissions'),
    ])
    roles.value = r.data.items
    permissions.value = p.data
  } catch (e: any) {
    error.value = e?.response?.data?.detail || '加载失败'
  } finally {
    loading.value = false
  }
}

function openNew() {
  isNew.value = true
  form.value = { id: 0, code: '', name: '', description: '', permission_ids: [], menu_ids: [] }
  showDialog.value = true
}

async function openEdit(r: Role) {
  isNew.value = false
  try {
    const { data } = await api.get(`/api/v1/rbac/roles/${r.id}`)
    form.value = {
      id: data.id,
      code: data.code,
      name: data.name,
      description: data.description || '',
      permission_ids: data.permission_ids || [],
      menu_ids: data.menu_ids || [],
    }
    showDialog.value = true
  } catch (e: any) {
    error.value = e?.response?.data?.detail || '加载角色失败'
  }
}

async function save() {
  saving.value = true
  error.value = ''
  try {
    if (isNew.value) {
      await api.post('/api/v1/rbac/roles', form.value)
    } else {
      await api.patch(`/api/v1/rbac/roles/${form.value.id}`, form.value)
    }
    showDialog.value = false
    await load()
  } catch (e: any) {
    error.value = e?.response?.data?.detail || '保存失败'
  } finally {
    saving.value = false
  }
}

async function del(r: Role) {
  if (!confirm(`确定删除角色「${r.name}」吗？`)) return
  try {
    await api.delete(`/api/v1/rbac/roles/${r.id}`)
    await load()
  } catch (e: any) {
    alert('删除失败：' + (e?.response?.data?.detail || e.message))
  }
}

// 权限按 code 前缀分组显示
const groupedPerms = () => {
  const groups: Record<string, Permission[]> = {}
  for (const p of permissions.value) {
    const prefix = p.code.split(':')[0] || '其他'
    if (!groups[prefix]) groups[prefix] = []
    groups[prefix].push(p)
  }
  return groups
}

onMounted(load)
</script>

<template>
  <div class="min-h-screen bg-ink-50">
    <header class="bg-white border-b border-ink-200">
      <div class="max-w-7xl mx-auto px-6 h-14 flex items-center gap-4">
        <router-link to="/" class="text-sm text-ink-500 hover:text-ink-900">← Dashboard</router-link>
        <span class="font-semibold">角色 & 权限</span>
      </div>
    </header>

    <main class="max-w-7xl mx-auto px-6 py-10">
      <div v-if="loading" class="card text-ink-500">加载中…</div>
      <div v-else-if="error" class="card text-red-600">⚠️ {{ error }}</div>
      <div v-else>
        <div class="flex items-center justify-between mb-6">
          <h1 class="text-2xl font-semibold tracking-tight">角色列表（{{ roles.length }}）</h1>
          <button @click="openNew" class="btn-primary">+ 新建角色</button>
        </div>
        <div class="grid md:grid-cols-2 lg:grid-cols-3 gap-4">
          <div v-for="r in roles" :key="r.id" class="card flex flex-col">
            <div class="flex items-start justify-between mb-2">
              <div>
                <h3 class="font-semibold">{{ r.name }}</h3>
                <code class="text-xs text-ink-400">{{ r.code }}</code>
              </div>
              <span v-if="r.is_system" class="text-xs px-2 py-0.5 rounded bg-ink-900 text-white">系统</span>
            </div>
            <p v-if="r.description" class="text-sm text-ink-600 mb-3">{{ r.description }}</p>
            <div class="text-xs text-ink-400 mt-auto">
              {{ r.created_at?.slice(0, 10) }}
            </div>
            <div class="mt-3 flex gap-2">
              <button @click="openEdit(r)" class="text-sm text-ink-600 hover:text-ink-900">编辑</button>
              <button v-if="!r.is_system" @click="del(r)" class="text-sm text-red-600 hover:underline">删除</button>
            </div>
          </div>
        </div>
      </div>
    </main>

    <!-- 对话框 -->
    <div v-if="showDialog" class="fixed inset-0 z-50 flex items-center justify-center p-4 bg-ink-900/40" @click.self="showDialog = false">
      <div class="bg-white rounded-2xl w-full max-w-2xl p-6 max-h-[90vh] overflow-y-auto">
        <h2 class="text-lg font-semibold mb-4">{{ isNew ? '新建角色' : '编辑角色' }}</h2>
        <form @submit.prevent="save" class="space-y-4">
          <div class="grid grid-cols-2 gap-4">
            <div>
              <label class="block text-sm font-medium mb-1.5">Code *</label>
              <input v-model="form.code" required :disabled="!isNew" class="input" placeholder="cms_editor" />
            </div>
            <div>
              <label class="block text-sm font-medium mb-1.5">名称 *</label>
              <input v-model="form.name" required class="input" placeholder="内容编辑" />
            </div>
          </div>
          <div>
            <label class="block text-sm font-medium mb-1.5">描述</label>
            <textarea v-model="form.description" rows="2" class="input"></textarea>
          </div>
          <div>
            <label class="block text-sm font-medium mb-2">权限（{{ permissions.length }} 个）</label>
            <div class="border border-ink-200 rounded-xl p-3 max-h-80 overflow-y-auto space-y-3">
              <div v-for="(perms, prefix) in groupedPerms()" :key="prefix">
                <div class="text-xs font-medium text-ink-500 uppercase tracking-widest mb-1">{{ prefix }}</div>
                <div class="space-y-1">
                  <label v-for="p in perms" :key="p.id" class="flex items-center gap-2 text-sm">
                    <input type="checkbox" :value="p.id" v-model="form.permission_ids" class="rounded" />
                    <span>{{ p.name }} <code class="text-xs text-ink-400">{{ p.code }}</code></span>
                  </label>
                </div>
              </div>
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
