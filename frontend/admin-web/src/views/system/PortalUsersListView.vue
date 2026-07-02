<script setup lang="ts">
import { useI18n } from 'vue-i18n'
const { t } = useI18n()
import { ref, onMounted } from 'vue'
import { api } from '@/lib/api'

interface PortalUser {
  id: number; username: string; email: string | null; phone: string | null
  nickname: string; avatar: string | null
  status: string
  register_ip: string | null
  last_login_at: string | null; last_login_ip: string | null
  created_at: string | null; updated_at: string | null
}
interface PortalStats {
  total: number; active: number; disabled: number
  oauth_bindings: number; new_last_7d: number
}

const users = ref<PortalUser[]>([])
const stats = ref<PortalStats | null>(null)
const loading = ref(true)
const error = ref('')
const search = ref('')
const statusFilter = ref('')
const showCreate = ref(false)
const showReset = ref(false)
const resetTarget = ref<PortalUser | null>(null)
const createForm = ref({ username: '', email: '', password: '', nickname: '' })
const newPassword = ref('')
const total = ref(0)
const page = ref(1)
const pageSize = 20
const saving = ref(false)

async function load() {
  loading.value = true
  error.value = ''
  try {
    const params = new URLSearchParams({
      page: String(page.value), page_size: String(pageSize),
    })
    if (search.value) params.set('search', search.value)
    if (statusFilter.value) params.set('status', statusFilter.value)
    const [usersRes, statsRes] = await Promise.all([
      api.get(`/api/v1/portal-admin/users?${params}`),
      api.get('/api/v1/portal-admin/stats'),
    ])
    users.value = usersRes.data.items
    total.value = usersRes.data.total
    stats.value = statsRes.data
  } catch (e: any) {
    error.value = e?.response?.data?.detail || 't("caseEdit.loadFailed")'
  } finally { loading.value = false }
}

function openCreate() {
  createForm.value = { username: '', email: '', password: '', nickname: '' }
  showCreate.value = true
}

async function create() {
  saving.value = true
  try {
    await api.post('/api/v1/portal-admin/users', createForm.value)
    showCreate.value = false
    await load()
  } catch (e: any) {
    alert(e?.response?.data?.detail || 't("portalUsersList.创建失败")')
  } finally { saving.value = false }
}

function openReset(user: PortalUser) {
  resetTarget.value = user
  newPassword.value = ''
  showReset.value = true
}

async function doReset() {
  if (!resetTarget.value) return
  if (newPassword.value.length < 8) { alert('t("portalUsersList.密码至少_nlidtq")'); return }
  saving.value = true
  try {
    await api.post(`/api/v1/portal-admin/users/${resetTarget.value.id}/reset-password`, {
      new_password: newPassword.value,
    })
    showReset.value = false
    alert('t("usersList.密码已重_j7r1zs")')
  } catch (e: any) {
    alert(e?.response?.data?.detail || 't("portalUsersList.重置失败")')
  } finally { saving.value = false }
}

async function changeStatus(user: PortalUser, newStatus: string) {
  if (!confirm(`确定将 ${user.username} 状态改为 ${newStatus}？`)) return
  try {
    await api.patch(`/api/v1/portal-admin/users/${user.id}`, { status: newStatus })
    await load()
  } catch (e: any) {
    alert(e?.response?.data?.detail || 't("entryList.操作失败")')
  }
}

async function deleteUser(user: PortalUser) {
  if (!confirm(`确定软删 ${user.username}？`)) return
  try {
    await api.delete(`/api/v1/portal-admin/users/${user.id}`)
    await load()
  } catch (e: any) {
    alert(e?.response?.data?.detail || 't("categories.删除失败")')
  }
}

const totalPages = computed(() => Math.max(1, Math.ceil(total.value / pageSize)))

onMounted(load)

import { computed } from 'vue'
</script>

<template>
  <div>
    <div class="flex items-center justify-between mb-6">
      <div>
        <h1 class="text-2xl font-semibold tracking-tight">{{ t('portalUsersList.前台用户_jiwjh3') }}</h1>
        <p class="text-ink-500">{{ t('portalUsersList.管理_ftgw1u') }}</p>
      </div>
    </div>

    <!-- Stats -->
    <div v-if="stats" class="grid grid-cols-2 md:grid-cols-5 gap-3 mb-6">
      <div class="card py-3">
        <div class="text-xs text-ink-500">{{ t('portalUsersList.总用户_envyi') }}</div>
        <div class="text-2xl font-semibold">{{ stats.total }}</div>
      </div>
      <div class="card py-3">
        <div class="text-xs text-ink-500">{{ t('usersList.活跃_jcvc') }}</div>
        <div class="text-2xl font-semibold text-green-600">{{ stats.active }}</div>
      </div>
      <div class="card py-3">
        <div class="text-xs text-ink-500">{{ t('usersList.禁用_lb5z') }}</div>
        <div class="text-2xl font-semibold text-amber-600">{{ stats.disabled }}</div>
      </div>
      <div class="card py-3">
        <div class="text-xs text-ink-500">{{ t('portalUsersList.text_kvgff6') }}</div>
        <div class="text-2xl font-semibold text-blue-600">{{ stats.oauth_bindings }}</div>
      </div>
      <div class="card py-3">
        <div class="text-xs text-ink-500">{{ t('portalUsersList.text_ej1hc') }}</div>
        <div class="text-2xl font-semibold text-indigo-600">{{ stats.new_last_7d }}</div>
      </div>
    </div>

    <!-- Filters -->
    <div class="card mb-4 flex flex-wrap gap-3 items-center">
      <input v-model="search" type="text" class="input w-60" :placeholder="t('portalUsersList.按用户名_11s1ir')" @keyup.enter="load" />
      <select v-model="statusFilter" class="input w-32" @change="load">
        <option value="">{{ t('portalUsersList.全部状态_avez63') }}</option>
        <option value="active">{{ t('usersList.活跃_jcvc') }}</option>
        <option value="disabled">{{ t('usersList.禁用_lb5z') }}</option>
        <option value="locked">{{ t('usersList.锁定_puih') }}</option>
      </select>
      <button class="btn-ghost" @click="load">{{ t('portalUsersList.搜索_hpqe') }}</button>
      <button class="btn-primary ml-auto" @click="openCreate">{{ t('usersList.text_y2qiem') }}</button>
    </div>

    <!-- Table -->
    <div v-if="loading" class="card text-ink-500">{{ t('usersList.加载中_b0k5km') }}</div>
    <table v-else class="w-full text-sm">
      <thead class="text-left text-ink-500 border-b">
        <tr>
          <th class="py-2 px-2">ID</th>
          <th class="py-2 px-2"></th>
          <th class="py-2 px-2">{{ t('usersList.用户名_hmxge') }}</th>
          <th class="py-2 px-2">{{ t('usersList.昵称_i1y3') }}</th>
          <th class="py-2 px-2">{{ t('usersList.邮箱_padf') }}</th>
          <th class="py-2 px-2">{{ t('usersList.状态_k1e3') }}</th>
          <th class="py-2 px-2">{{ t('portalUsersList.注册IP') }}</th>
          <th class="py-2 px-2">{{ t('portalUsersList.最后登录_dckibs') }}</th>
          <th class="py-2 px-2">{{ t('portalUsersList.注册时间_e2y82q') }}</th>
          <th class="py-2 px-2 w-40">{{ t('usersList.操作_hkxb') }}</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="u in users" :key="u.id" class="border-b hover:bg-ink-50">
          <td class="py-2 px-2 text-ink-500">{{ u.id }}</td>
          <td class="py-2 px-2">
            <img v-if="u.avatar" :src="u.avatar" class="w-8 h-8 rounded-full object-cover" />
            <div v-else class="w-8 h-8 rounded-full bg-ink-200 flex items-center justify-center text-xs text-ink-500">{{ (u.username || '?')[0].toUpperCase() }}</div>
          </td>
          <td class="py-2 px-2 font-medium">{{ u.username }}</td>
          <td class="py-2 px-2">{{ u.nickname || '-' }}</td>
          <td class="py-2 px-2 text-ink-500">{{ u.email || '-' }}</td>
          <td class="py-2 px-2">
            <span
              class="text-xs px-1.5 py-0.5 rounded"
              :class="{
                'bg-green-50 text-green-700': u.status === 'active',
                'bg-amber-50 text-amber-700': u.status === 'disabled',
                'bg-red-50 text-red-700': u.status === 'locked',
              }"
            >{{ { active: '活跃', disabled: '禁用', locked: '锁定' }[u.status] || u.status }}</span>
          </td>
          <td class="py-2 px-2 text-ink-400 text-xs">{{ u.register_ip || '-' }}</td>
          <td class="py-2 px-2 text-ink-500 text-xs">
            <div>{{ u.last_login_at?.slice(0, 16) || '-' }}</div>
            <div class="text-ink-400">{{ u.last_login_ip || '' }}</div>
          </td>
          <td class="py-2 px-2 text-ink-500 text-xs">{{ u.created_at?.slice(0, 10) }}</td>
          <td class="py-2 px-2 space-x-1">
            <button
              v-if="u.status === 'active'"
              class="text-xs text-amber-600"
              @click="changeStatus(u, 'disabled')"
            >{{ t('usersList.禁用_lb5z') }}</button>
            <button
              v-else
              class="text-xs text-green-600"
              @click="changeStatus(u, 'active')"
            >{{ t('tasks.启用_eymx') }}</button>
            <button class="text-xs text-blue-600" @click="openReset(u)">{{ t('usersList.重置密码_ix54os') }}</button>
            <button class="text-xs text-red-600" @click="deleteUser(u)">{{ t('usersList.删除_eslg') }}</button>
          </td>
        </tr>
      </tbody>
    </table>

    <!-- Pagination -->
    <div v-if="totalPages > 1" class="mt-4 flex items-center justify-center gap-2 text-sm">
      <button class="btn-ghost" :disabled="page <= 1" @click="page--; load()">{{ t('portalUsersList.上一页_btlof') }}</button>
      <span>{{ page }} / {{ totalPages }}</span>
      <button class="btn-ghost" :disabled="page >= totalPages" @click="page++; load()">下一页</button>
    </div>

    <!-- Create Modal -->
    <div v-if="showCreate" class="fixed inset-0 bg-black/40 flex items-center justify-center z-50" @click.self="showCreate = false">
      <div class="bg-white rounded-lg shadow-xl w-full max-w-md p-6">
        <h2 class="text-lg font-semibold mb-4">{{ t('portalUsersList.新建前台_1s29kn') }}</h2>
        <div class="space-y-3">
          <div>
            <label class="block text-sm font-medium mb-1">{{ t('usersList.用户名_18merf') }}</label>
            <input v-model="createForm.username" class="input" />
          </div>
          <div>
            <label class="block text-sm font-medium mb-1">{{ t('usersList.邮箱_padf') }}</label>
            <input v-model="createForm.email" type="email" class="input" />
          </div>
          <div>
            <label class="block text-sm font-medium mb-1">{{ t('usersList.昵称_i1y3') }}</label>
            <input v-model="createForm.nickname" class="input" />
          </div>
          <div>
            <label class="block text-sm font-medium mb-1">{{ t('portalUsersList.密码_wbituu') }}</label>
            <input v-model="createForm.password" type="password" minlength="8" class="input" />
          </div>
        </div>
        <div class="flex justify-end gap-2 mt-6">
          <button class="btn-ghost" @click="showCreate = false">{{ t('usersList.取消_ev02') }}</button>
          <button class="btn-primary" :disabled="saving" @click="create">{{ saving ? '创建中…' : '创建' }}</button>
        </div>
      </div>
    </div>

    <!-- Reset Password Modal -->
    <div v-if="showReset" class="fixed inset-0 bg-black/40 flex items-center justify-center z-50" @click.self="showReset = false">
      <div class="bg-white rounded-lg shadow-xl w-full max-w-md p-6">
        <h2 class="text-lg font-semibold mb-4">重置密码 — {{ resetTarget?.username }}</h2>
        <div>
          <label class="block text-sm font-medium mb-1">{{ t('portalUsersList.新密码_11z82o') }}</label>
          <input v-model="newPassword" type="password" minlength="8" class="input" />
        </div>
        <p class="text-xs text-amber-600 mt-2">{{ t('portalUsersList.text_lgd7kg') }}</p>
        <div class="flex justify-end gap-2 mt-6">
          <button class="btn-ghost" @click="showReset = false">{{ t('usersList.取消_ev02') }}</button>
          <button class="btn-primary" :disabled="saving" @click="doReset">{{ t('portalUsersList.确认重置_frzj5j') }}</button>
        </div>
      </div>
    </div>
  </div>
</template>