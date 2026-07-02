<script setup lang="ts">
import { useI18n } from 'vue-i18n'
const { t } = useI18n()
import { ref, onMounted, computed } from 'vue'
import { api } from '@/lib/api'

interface AppItem {
  key: string
  name: string
  version: string
  code_version: string | null
  db_version: string | null
  status: 'installed' | 'not_installed' | 'needs_upgrade' | 'missing'
  description: string
  icon: string
  category?: string
  permissions_required: string[]
  content_types: { key: string; name: string; icon?: string }[]
  field_groups: any[]
  field_definitions: any[]
  categories_seed: any[]
  public_routes_prefix: string
  permissions_grants: Record<string, string[]>
  registered_counts: {
    content_types?: number
    field_definitions?: number
    categories?: number
    tags?: number
    entries?: number
  }
}

interface PendingApp {
  id: number
  app_key: string
  name: string
  version: string
  description: string
  author: string
  status: string
  created_at: string
}

const apps = ref<AppItem[]>([])
const pendingApps = ref<PendingApp[]>([])
const loading = ref(true)
const error = ref('')
const acting = ref<string | null>(null)
const expanded = ref<string | null>(null)
const showGrantsModal = ref(false)
const editingGrants = ref<{ key: string; grants: Record<string, string[]> }>({ key: '', grants: {} })
const newRoleKey = ref('')
const newPermCode = ref('')
const activeTab = ref<'installed' | 'store' | 'pending'>('installed')
const subTab = ref<'pending' | 'approved' | 'installed'>('pending')
const categoryFilter = ref('')

const statusLabel: Record<string, string> = {
  installed: t('apps.status_installed'),
  not_installed: t('apps.status_not_installed'),
  needs_upgrade: t('apps.status_needs_upgrade'),
  missing: t('apps.status_missing'),
}

async function load() {
  loading.value = true
  error.value = ''
  try {
    const { data } = await api.get('/api/v1/system/apps')
    apps.value = data.items
  } catch (e: any) {
    error.value = e?.response?.data?.detail || t('apps.loadFailed')
  } finally {
    loading.value = false
  }
}

async function install(key: string) {
  acting.value = key
  try {
    const r = await api.post(`/api/v1/system/apps/${key}/install`)
    if (!r.data.ok) throw new Error(r.data.detail || t('apps.installFailed'))
    await load()
  } catch (e: any) {
    alert(e?.response?.data?.detail || e?.message || t('apps.installFailed'))
  } finally {
    acting.value = null
  }
}

async function uninstall(key: string) {
  if (!confirm(t('apps.confirmUninstall', { key }))) return
  acting.value = key
  try {
    await api.post(`/api/v1/system/apps/${key}/uninstall`)
    await load()
  } catch (e: any) {
    alert(e?.response?.data?.detail || t('apps.uninstallFailed'))
  } finally {
    acting.value = null
  }
}

function openGrants(app: AppItem) {
  editingGrants.value = {
    key: app.key,
    grants: JSON.parse(JSON.stringify(app.permissions_grants || {})),
  }
  showGrantsModal.value = true
}

function addRole() {
  if (!newRoleKey.value || editingGrants.value.grants[newRoleKey.value]) return
  editingGrants.value.grants[newRoleKey.value] = []
  newRoleKey.value = ''
}

function removeRole(role: string) {
  delete editingGrants.value.grants[role]
}

function addPerm(role: string) {
  if (!newPermCode.value) return
  if (!editingGrants.value.grants[role].includes(newPermCode.value)) {
    editingGrants.value.grants[role].push(newPermCode.value)
  }
  newPermCode.value = ''
}

function removePerm(role: string, perm: string) {
  editingGrants.value.grants[role] = editingGrants.value.grants[role].filter(p => p !== perm)
}

async function saveGrants() {
  try {
    await api.put(`/api/v1/system/apps/${editingGrants.value.key}/permissions-grants`, editingGrants.value.grants)
    showGrantsModal.value = false
    await load()
  } catch (e: any) {
    alert(e?.response?.data?.detail || t('apps.saveFailed'))
  }
}

async function loadPending() {
  try {
    // 用 only_active=true：每个 app_key 只返回当前活跃的那条（避免看到 1.0.0 + 1.0.2 两条 installed）
    // 后端会再过滤 platform_apps.status='installed'，确保"已卸载的不再显示"
    const [pending, approved, installed] = await Promise.all([
      api.get('/api/v1/store/submissions', { params: { status: 'pending', only_active: true } }),
      api.get('/api/v1/store/submissions', { params: { status: 'approved', only_active: true } }),
      api.get('/api/v1/store/submissions', { params: { status: 'installed', only_active: true } }),
    ])
    pendingApps.value = [
      ...(pending.data.items || []),
      ...(approved.data.items || []),
      ...(installed.data.items || []),
    ]
  } catch (e: any) {
    console.error('load pending submissions fail', e)
  }
}

async function reviewSubmission(id: number, action: 'approve' | 'reject') {
  acting.value = `review-${id}`
  try {
    await api.post(`/api/v1/store/submissions/${id}/review`, { action })
    await loadPending()
  } catch (e: any) {
    alert(e?.response?.data?.detail || '操作失败')
  } finally {
    acting.value = null
  }
}

async function installSubmission(id: number) {
  acting.value = `install-${id}`
  try {
    await api.post(`/api/v1/store/submissions/${id}/install`)
    await loadPending()
  } catch (e: any) {
    alert(e?.response?.data?.detail || '安装失败')
  } finally {
    acting.value = null
  }
}

onMounted(() => {
  load()
  loadPending()
})

const installedApps = computed(() => apps.value.filter(a => a.status === 'installed' || a.status === 'needs_upgrade'))
const filteredSubmissions = computed(() => pendingApps.value.filter(s => s.status === subTab.value))

const storeApps = computed(() => {
  let list = apps.value.filter(a => a.status === 'not_installed' || a.status === 'missing')
  if (categoryFilter.value) list = list.filter(a => (a as any).category === categoryFilter.value)
  return list
})
</script>

<template>
  <div>
    <h1 class="text-2xl font-semibold tracking-tight mb-2">{{ t('apps.title') }}</h1>
    <p class="text-ink-500 mb-6">{{ t('apps.subtitle') }}</p>

    <div class="flex gap-1 mb-6 border-b border-ink-200">
      <button
        class="px-4 py-2 text-sm font-medium border-b-2 transition-colors"
        :class="activeTab === 'installed' ? 'border-ink-900 text-ink-900' : 'border-transparent text-ink-500 hover:text-ink-700'"
        @click="activeTab = 'installed'"
      >{{ t('apps.tabInstalled') }} ({{ installedApps.length }})</button>
      <button
        class="px-4 py-2 text-sm font-medium border-b-2 transition-colors"
        :class="activeTab === 'store' ? 'border-ink-900 text-ink-900' : 'border-transparent text-ink-500 hover:text-ink-700'"
        @click="activeTab = 'store'"
      >{{ t('apps.tabStore') }} ({{ storeApps.length }})</button>
      <button
        class="px-4 py-2 text-sm font-medium border-b-2 transition-colors"
        :class="activeTab === 'pending' ? 'border-ink-900 text-ink-900' : 'border-transparent text-ink-500 hover:text-ink-700'"
        @click="activeTab = 'pending'; subTab = 'pending'"
      >{{ t('apps.tabSubmissions') }} ({{ pendingApps.length }})</button>
    </div>

    <div v-if="activeTab === 'store'" class="mb-4 flex gap-2">
      <button class="btn-ghost text-xs" :class="!categoryFilter && 'bg-ink-100'" @click="categoryFilter = ''">{{ t('apps.filterAll') }}</button>
      <button class="btn-ghost text-xs" :class="categoryFilter === 'content' && 'bg-ink-100'" @click="categoryFilter = 'content'">{{ t('apps.filterContent') }}</button>
      <button class="btn-ghost text-xs" :class="categoryFilter === 'productivity' && 'bg-ink-100'" @click="categoryFilter = 'productivity'">{{ t('apps.filterProductivity') }}</button>
      <button class="btn-ghost text-xs" :class="categoryFilter === 'system' && 'bg-ink-100'" @click="categoryFilter = 'system'">{{ t('apps.filterSystem') }}</button>
    </div>

    <div v-if="loading" class="card text-ink-500">{{ t('apps.loading') }}</div>
    <div v-else-if="error" class="card text-red-600">{{ error }}</div>
    <div v-else class="space-y-3">

      <div v-if="activeTab === 'installed' && installedApps.length === 0" class="card text-ink-500 text-center py-12">
        {{ t('apps.emptyInstalled') }}
      </div>
      <div v-for="app in installedApps" v-if="activeTab === 'installed'" :key="app.key" class="card">
        <div class="flex items-start gap-3">
          <span class="text-2xl">{{ app.icon }}</span>
          <div class="flex-1 min-w-0">
            <div class="flex items-center gap-2">
              <h3 class="font-semibold">{{ app.name }}</h3>
              <code class="text-xs text-ink-400">{{ app.key }} @ {{ app.version }}</code>
              <span
                class="text-xs px-2 py-0.5 rounded-full"
                :class="{
                  'bg-green-50 text-green-700': app.status === 'installed',
                  'bg-yellow-50 text-yellow-700': app.status === 'needs_upgrade',
                }"
              >{{ statusLabel[app.status] }}</span>
            </div>
            <p class="text-sm text-ink-600 mt-1">{{ app.description }}</p>
            <div v-if="app.registered_counts" class="flex flex-wrap gap-2 mt-2 text-xs">
              <span v-if="app.registered_counts.content_types" class="px-1.5 py-0.5 bg-blue-50 text-blue-600 rounded">
                {{ app.registered_counts.content_types }} {{ t('apps.countContentTypes') }}
              </span>
              <span v-if="app.registered_counts.field_definitions" class="px-1.5 py-0.5 bg-purple-50 text-purple-600 rounded">
                {{ app.registered_counts.field_definitions }} {{ t('apps.countFields') }}
              </span>
              <span v-if="app.registered_counts.categories" class="px-1.5 py-0.5 bg-green-50 text-green-600 rounded">
                {{ app.registered_counts.categories }} {{ t('apps.countCategories') }}
              </span>
              <span v-if="app.registered_counts.entries" class="px-1.5 py-0.5 bg-amber-50 text-amber-600 rounded">
                {{ app.registered_counts.entries }} {{ t('apps.countEntries') }}
              </span>
            </div>
          </div>
        </div>
        <div class="mt-3 flex gap-2 flex-wrap border-t pt-3">
          <button
            v-if="app.status === 'needs_upgrade'"
            class="btn-primary text-sm"
            :disabled="acting === app.key"
            @click="install(app.key)"
          >{{ t('apps.upgrade') }}</button>
          <button
            v-if="app.status === 'installed'"
            class="btn-ghost text-sm text-red-600"
            :disabled="acting === app.key"
            @click="uninstall(app.key)"
          >{{ t('apps.uninstall') }}</button>
          <button
            class="btn-ghost text-sm"
            @click="expanded = expanded === app.key ? null : app.key"
          >{{ expanded === app.key ? t('apps.collapse') : t('apps.details') }}</button>
          <button
            v-if="app.status === 'installed'"
            class="btn-ghost text-sm"
            @click="openGrants(app)"
          >{{ t('apps.permissions') }}</button>
        </div>
        <div v-if="expanded === app.key" class="mt-3 pt-3 border-t space-y-3 text-sm">
          <div v-if="app.content_types?.length">
            <h4 class="font-medium text-ink-500 mb-1">{{ t('apps.contentTypes') }}</h4>
            <div class="flex flex-wrap gap-1">
              <span v-for="ct in app.content_types" :key="ct.key" class="text-xs px-1.5 py-0.5 bg-blue-50 text-blue-600 rounded">
                {{ ct.icon }} {{ ct.name }} ({{ ct.key }})
              </span>
            </div>
          </div>
          <div v-if="app.permissions_required?.length">
            <h4 class="font-medium text-ink-500 mb-1">{{ t('apps.requiredPermissions') }}</h4>
            <div class="flex flex-wrap gap-1">
              <code v-for="p in app.permissions_required" :key="p" class="text-xs px-1.5 py-0.5 bg-ink-50 rounded">{{ p }}</code>
            </div>
          </div>
          <div v-if="Object.keys(app.permissions_grants || {}).length">
            <h4 class="font-medium text-ink-500 mb-1">{{ t('apps.permissionGrants') }}</h4>
            <div v-for="(perms, role) in app.permissions_grants" :key="role" class="text-xs mb-1">
              <code class="bg-ink-50 px-1 rounded">{{ role }}</code>:
              <code v-for="p in perms" :key="p" class="ml-1 bg-purple-50 text-purple-600 px-1 rounded">{{ p }}</code>
            </div>
          </div>
        </div>
      </div>

      <div v-if="activeTab === 'store' && storeApps.length === 0" class="card text-ink-500 text-center py-12">
        {{ t('apps.emptyStore') }}
      </div>
      <div v-for="app in storeApps" v-if="activeTab === 'store'" :key="app.key" class="card">
        <div class="flex items-start gap-3">
          <span class="text-2xl">{{ app.icon }}</span>
          <div class="flex-1 min-w-0">
            <div class="flex items-center gap-2">
              <h3 class="font-semibold">{{ app.name }}</h3>
              <code class="text-xs text-ink-400">{{ app.key }} @ {{ app.version }}</code>
              <span class="text-xs px-2 py-0.5 rounded-full bg-ink-100 text-ink-500">{{ t('apps.status_not_installed') }}</span>
            </div>
            <p class="text-sm text-ink-600 mt-1">{{ app.description }}</p>
          </div>
        </div>
        <div class="mt-3 flex gap-2 border-t pt-3">
          <button
            class="btn-primary text-sm"
            :disabled="acting === app.key"
            @click="install(app.key)"
          >{{ t('apps.install') }}</button>
          <button
            class="btn-ghost text-sm"
            @click="expanded = expanded === app.key ? null : app.key"
          >{{ expanded === app.key ? t('apps.collapse') : t('apps.details') }}</button>
        </div>
        <div v-if="expanded === app.key" class="mt-3 pt-3 border-t space-y-3 text-sm">
          <div v-if="app.permissions_required?.length">
            <h4 class="font-medium text-ink-500 mb-1">{{ t('apps.requiredPermissions') }}</h4>
            <div class="flex flex-wrap gap-1">
              <code v-for="p in app.permissions_required" :key="p" class="text-xs px-1.5 py-0.5 bg-ink-50 rounded">{{ p }}</code>
            </div>
          </div>
        </div>
      </div>
    </div>

    <div v-if="activeTab === 'pending'">
      <div class="flex gap-1 mb-4 border-b border-ink-200">
        <button class="px-3 py-1.5 text-xs font-medium border-b-2 transition-colors"
          :class="subTab === 'pending' ? 'border-ink-900 text-ink-900' : 'border-transparent text-ink-500 hover:text-ink-700'"
          @click="subTab = 'pending'">{{ t('apps.subPending') }} ({{ pendingApps.filter(s => s.status === 'pending').length }})</button>
        <button class="px-3 py-1.5 text-xs font-medium border-b-2 transition-colors"
          :class="subTab === 'approved' ? 'border-ink-900 text-ink-900' : 'border-transparent text-ink-500 hover:text-ink-700'"
          @click="subTab = 'approved'">{{ t('apps.subApproved') }} ({{ pendingApps.filter(s => s.status === 'approved').length }})</button>
        <button class="px-3 py-1.5 text-xs font-medium border-b-2 transition-colors"
          :class="subTab === 'installed' ? 'border-ink-900 text-ink-900' : 'border-transparent text-ink-500 hover:text-ink-700'"
          @click="subTab = 'installed'">{{ t('apps.subInstalled') }} ({{ pendingApps.filter(s => s.status === 'installed').length }})</button>
      </div>

      <div v-if="filteredSubmissions.length === 0" class="card text-ink-500 text-center py-12">
        {{ t('apps.emptyPending') }}
      </div>
      <div v-for="app in filteredSubmissions" :key="app.id" class="card">
        <div class="flex items-start gap-3">
          <div class="flex-1 min-w-0">
            <div class="flex items-center gap-2">
              <h3 class="font-semibold">{{ app.name }}</h3>
              <code class="text-xs text-ink-400">{{ app.app_key }} @ {{ app.version }}</code>
              <span class="text-xs px-2 py-0.5 rounded-full"
                :class="app.status === 'pending' ? 'bg-yellow-50 text-yellow-700' : app.status === 'approved' ? 'bg-blue-50 text-blue-700' : 'bg-green-50 text-green-700'">{{ app.status }}</span>
            </div>
            <p class="text-sm text-ink-600 mt-1">{{ app.description }}</p>
            <p class="text-xs text-ink-400 mt-1">{{ t('apps.author') }}: {{ app.author }} · {{ app.created_at }}</p>
          </div>
        </div>
        <div class="mt-3 flex gap-2 border-t pt-3">
          <template v-if="app.status === 'pending'">
            <button class="btn-ghost text-sm text-green-600" :disabled="acting === `review-${app.id}`" @click="reviewSubmission(app.id, 'approve')">{{ t('apps.approve') }}</button>
            <button class="btn-ghost text-sm text-red-600" :disabled="acting === `review-${app.id}`" @click="reviewSubmission(app.id, 'reject')">{{ t('apps.reject') }}</button>
          </template>
          <button v-else-if="app.status === 'approved'" class="btn-primary text-sm" :disabled="acting === `install-${app.id}`" @click="installSubmission(app.id)">{{ t('apps.install') }}</button>
          <span v-else-if="app.status === 'installed'" class="text-sm text-green-600">{{ t('apps.status_installed') }}</span>
        </div>
      </div>
    </div>

    <div v-if="showGrantsModal" class="fixed inset-0 bg-black/40 flex items-center justify-center z-50" @click.self="showGrantsModal = false">
      <div class="bg-white rounded-lg shadow-xl w-full max-w-2xl p-6 max-h-[90vh] overflow-y-auto">
        <h2 class="text-lg font-semibold mb-4">{{ t('apps.grantsTitle') }} — {{ editingGrants.key }}</h2>
        <p class="text-sm text-ink-500 mb-4">
          {{ t('apps.grantsDesc') }}
        </p>
        <div class="space-y-3">
          <div v-for="(perms, role) in editingGrants.grants" :key="role" class="card">
            <div class="flex items-center justify-between mb-2">
              <code class="text-sm bg-ink-50 px-2 py-0.5 rounded font-medium">{{ role }}</code>
              <button class="text-red-500 text-xs" @click="removeRole(role)">{{ t('apps.removeRole') }}</button>
            </div>
            <div class="flex flex-wrap gap-1 mb-2">
              <span v-for="p in perms" :key="p" class="text-xs px-1.5 py-0.5 bg-purple-50 text-purple-600 rounded flex items-center gap-1">
                {{ p }}
                <button class="text-red-400 hover:text-red-600" @click="removePerm(role, p)">&times;</button>
              </span>
            </div>
            <div class="flex gap-1">
              <input v-model="newPermCode" class="input text-xs flex-1" placeholder="permission_code" @keyup.enter="addPerm(role)" />
              <button class="btn-ghost text-xs" @click="addPerm(role)">{{ t('apps.add') }}</button>
            </div>
          </div>
          <div class="flex gap-2">
            <input v-model="newRoleKey" class="input flex-1" placeholder="role_code" @keyup.enter="addRole" />
            <button class="btn-ghost" @click="addRole">{{ t('apps.addRole') }}</button>
          </div>
        </div>
        <div class="flex justify-end gap-2 mt-6">
          <button class="btn-ghost" @click="showGrantsModal = false">{{ t('apps.cancel') }}</button>
          <button class="btn-primary" @click="saveGrants">{{ t('apps.save') }}</button>
        </div>
      </div>
    </div>
  </div>
</template>
