<script setup lang="ts">
import { useI18n } from 'vue-i18n'
const { t } = useI18n()
import { ref, onMounted, onBeforeUnmount, computed } from 'vue'
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

interface StoreApp {
  id: number
  key: string
  app_key: string
  name: string
  version: string
  description: string
  icon: string
  category: string
  author: string
  download_count: number
  updated_at?: string | null
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
const activeTab = ref<'installed' | 'store' | 'pending' | 'cloud'>('installed')
const subTab = ref<'pending' | 'approved' | 'installed'>('pending')
const categoryFilter = ref('')
const storeCatalog = ref<StoreApp[]>([])
const storeLoaded = ref(false)

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

async function loadStore() {
  try {
    const { data } = await api.get('/api/v1/store/apps')
    storeCatalog.value = data.items || []
  } catch (e: any) {
    console.error('load store catalog fail', e)
  } finally {
    storeLoaded.value = true
  }
}

// ============================================================
// 官方应用市场（客户实例专属：连官方云账号 → 浏览 → 装已购）
// ============================================================

interface CloudPrice {
  model: string
  enabled: boolean
  unit_price: string
  list_price: string
  is_discounted: boolean
  discount_label: string | null
  promo_state: string
  promo_label: string | null
}

interface CloudApp {
  app_key: string
  name: string
  version: string
  description: string
  icon: string
  category: string
  author: string
  price: CloudPrice | null
  installed: boolean
  installed_version: string | null
  needs_upgrade: boolean
}

interface CloudPurchase {
  license_key: string
  app_key: string
  app_name: string
  model: string
  seats: number
  status: string
  expires_at: string | null
  permanent: boolean
}

const cloudRole = ref<'hub' | 'spoke'>('hub')
const cloudStatus = ref<any>({})
const cloudApps = ref<CloudApp[]>([])
const cloudPurchases = ref<CloudPurchase[]>([])
const cloudLoaded = ref(false)
const cloudError = ref('')
const bindCode = ref<any>(null)
const bindPolling = ref(false)
const installing = ref<string | null>(null)
let bindTimer: number | null = null

/** 离线安装：上传本地 ZIP 应用包（如从官方门户「我的应用」下载的授权包） */
const zipInput = ref<HTMLInputElement | null>(null)
const uploading = ref(false)

async function onZipPicked(e: Event) {
  const input = e.target as HTMLInputElement
  const f = input.files?.[0]
  input.value = '' // 清空以便重复选择同一个文件
  if (!f) return
  if (!f.name.toLowerCase().endsWith('.zip')) {
    alert('只支持 .zip 应用包')
    return
  }
  uploading.value = true
  try {
    const fd = new FormData()
    fd.append('file', f)
    const { data } = await api.post('/api/v1/system/apps/install-zip', fd, {
      headers: { 'Content-Type': 'multipart/form-data' },
      timeout: 300_000,
    })
    alert(`已安装 ${data.key}${data.version ? ' @ ' + data.version : ''}`)
    await load()
  } catch (err: any) {
    alert(err?.response?.data?.detail || '安装失败')
  } finally {
    uploading.value = false
  }
}

// 授权中心（官方实例）自己就是货源，不需要这个 tab
const isSpoke = computed(() => cloudRole.value === 'spoke')

const purchasedMap = computed(() => {
  const m = new Map<string, CloudPurchase>()
  for (const p of cloudPurchases.value) if (!m.has(p.app_key)) m.set(p.app_key, p)
  return m
})

function purchaseOf(key: string): CloudPurchase | undefined {
  return purchasedMap.value.get(key)
}

async function loadCloudStatus() {
  try {
    const { data } = await api.get('/api/v1/store/cloud/status')
    cloudStatus.value = data
    cloudRole.value = data.role === 'spoke' ? 'spoke' : 'hub'
    if (cloudRole.value === 'spoke') await loadCloud()
  } catch {
    // 老版本后端 / 开源部署没有这个接口：静默当作授权中心，不显示该 tab
    cloudRole.value = 'hub'
  }
}

async function loadCloud() {
  cloudLoaded.value = false
  cloudError.value = ''
  try {
    const cat = await api.get('/api/v1/store/cloud/catalog')
    cloudApps.value = cat.data.items || []
    if (cloudStatus.value?.bound) {
      const pur = await api.get('/api/v1/store/cloud/purchases')
      cloudPurchases.value = pur.data.items || []
    } else {
      cloudPurchases.value = []
    }
  } catch (e: any) {
    cloudError.value = e?.response?.data?.detail || '官方应用市场不可达'
    cloudApps.value = []
  } finally {
    cloudLoaded.value = true
  }
}

async function startBind() {
  try {
    const { data } = await api.post('/api/v1/store/cloud/bind/start', {})
    bindCode.value = data
    startBindPolling(data.device_code)
  } catch (e: any) {
    alert(e?.response?.data?.detail || '申请绑定码失败')
  }
}

function startBindPolling(deviceCode: string) {
  stopBindPolling()
  bindPolling.value = true
  bindTimer = window.setInterval(async () => {
    try {
      const { data } = await api.post('/api/v1/store/cloud/bind/poll', { device_code: deviceCode })
      if (data.status === 'approved') {
        stopBindPolling()
        bindCode.value = null
        await loadCloudStatus()
      } else if (data.status === 'denied' || data.status === 'expired') {
        stopBindPolling()
        bindCode.value = null
        alert(data.status === 'denied' ? '门户拒绝了本次绑定' : '绑定码已过期，请重新发起绑定')
      }
    } catch (e: any) {
      stopBindPolling()
      alert(e?.response?.data?.detail || '轮询绑定结果失败')
    }
  }, 3000)
}

function stopBindPolling() {
  bindPolling.value = false
  if (bindTimer !== null) {
    window.clearInterval(bindTimer)
    bindTimer = null
  }
}

async function unbind() {
  if (!confirm('解绑后本实例将无法下载已购应用，确认解绑？')) return
  try {
    await api.post('/api/v1/store/cloud/unbind')
    cloudPurchases.value = []
    await loadCloudStatus()
  } catch (e: any) {
    alert(e?.response?.data?.detail || '解绑失败')
  }
}

async function installCloud(app: CloudApp) {
  const p = purchaseOf(app.app_key)
  if (!p) {
    alert('该应用尚未购买，请先到官方门户购买后再安装')
    return
  }
  installing.value = app.app_key
  try {
    const { data } = await api.post('/api/v1/store/cloud/install', { license_key: p.license_key })
    alert(`已安装 ${data.app_key || app.app_key}`)
    await Promise.all([load(), loadCloud()])
  } catch (e: any) {
    alert(e?.response?.data?.detail || '安装失败')
  } finally {
    installing.value = null
  }
}

function cloudPriceText(app: CloudApp): string {
  const p = app.price
  if (!p || p.enabled === false) return '免费'
  const unit = p.unit_price || '0.00'
  return p.model === 'seat' ? `¥${unit} / 席` : `¥${unit}`
}

function cloudListPriceText(app: CloudApp): string {
  const p = app.price
  if (!p || !p.is_discounted) return ''
  const lp = p.list_price || ''
  return parseFloat(lp) > 0 ? `¥${lp}` : ''
}

onBeforeUnmount(() => stopBindPolling())


onMounted(() => {
  load()
  loadPending()
  loadStore()
  loadCloudStatus()
})

const installedApps = computed(() => apps.value.filter(a => a.status === 'installed' || a.status === 'needs_upgrade'))
const filteredSubmissions = computed(() => pendingApps.value.filter(s => s.status === subTab.value))

// 已安装应用的 key -> 当前版本（用于比对商店版本，得出「可升级」）
const installedMap = computed(() => {
  const m = new Map<string, string>()
  for (const a of apps.value) {
    if (a.status === 'installed' || a.status === 'needs_upgrade') m.set(a.key, a.version)
  }
  return m
})

// 商店目录 = 后端已审核通过/已安装的最新版本（与 dev.cenkor.cn/store 同源）
const storeApps = computed(() => {
  let list = storeCatalog.value
  if (categoryFilter.value) list = list.filter(a => a.category === categoryFilter.value)
  return list
})

type StoreState = 'installed' | 'upgradable' | 'installable'
function storeState(app: StoreApp): StoreState {
  const cur = installedMap.value.get(app.key)
  if (!cur) return 'installable'
  return cur === app.version ? 'installed' : 'upgradable'
}

// 用 key 映射 + 调用时求值，保证切换语言时标签跟着变
const CATEGORY_KEYS: Record<string, string> = {
  business: 'apps.filterBusiness',
  productivity: 'apps.filterProductivity',
  system: 'apps.filterSystem',
  content: 'apps.filterContent',
}
function categoryLabel(c: string): string {
  const k = CATEGORY_KEYS[c]
  return k ? t(k) : c
}
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
      <button
        v-if="isSpoke"
        class="px-4 py-2 text-sm font-medium border-b-2 transition-colors"
        :class="activeTab === 'cloud' ? 'border-ink-900 text-ink-900' : 'border-transparent text-ink-500 hover:text-ink-700'"
        @click="activeTab = 'cloud'; loadCloud()"
      >官方应用市场 ({{ cloudApps.length }})</button>
    </div>

    <div v-if="activeTab === 'installed'" class="mb-4 flex flex-wrap items-center gap-2">
      <input ref="zipInput" type="file" accept=".zip" class="hidden" @change="onZipPicked" />
      <button
        class="btn-ghost text-xs"
        :disabled="uploading"
        @click="zipInput?.click()"
      >{{ uploading ? '安装中…' : '上传安装包（.zip）' }}</button>
      <span class="text-xs text-ink-400">离线安装：上传从官方门户「我的应用」下载的授权包</span>
    </div>

    <div v-if="activeTab === 'store'" class="mb-4 flex gap-2">
      <button class="btn-ghost text-xs" :class="!categoryFilter && 'bg-ink-100'" @click="categoryFilter = ''">{{ t('apps.filterAll') }}</button>
      <button class="btn-ghost text-xs" :class="categoryFilter === 'business' && 'bg-ink-100'" @click="categoryFilter = 'business'">{{ t('apps.filterBusiness') }}</button>
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
        {{ storeLoaded ? t('apps.emptyStoreCatalog') : t('apps.loading') }}
      </div>
      <div v-for="app in storeApps" v-if="activeTab === 'store'" :key="app.key" class="card">
        <div class="flex items-start gap-3">
          <span class="text-2xl">{{ app.icon }}</span>
          <div class="flex-1 min-w-0">
            <div class="flex items-center gap-2 flex-wrap">
              <h3 class="font-semibold">{{ app.name }}</h3>
              <code class="text-xs text-ink-400">{{ app.key }} @ {{ app.version }}</code>
              <span
                class="text-xs px-2 py-0.5 rounded-full"
                :class="storeState(app) === 'installed' ? 'bg-green-50 text-green-700'
                       : storeState(app) === 'upgradable' ? 'bg-amber-50 text-amber-700'
                       : 'bg-ink-100 text-ink-500'"
              >{{ storeState(app) === 'installed' ? t('apps.status_installed')
                  : storeState(app) === 'upgradable' ? t('apps.status_upgradable')
                  : t('apps.status_not_installed') }}</span>
              <span class="text-xs px-2 py-0.5 rounded-full bg-blue-50 text-blue-600">{{ categoryLabel(app.category) }}</span>
            </div>
            <p class="text-sm text-ink-600 mt-1">{{ app.description }}</p>
            <p class="text-xs text-ink-400 mt-1">{{ t('apps.author') }}: {{ app.author }}</p>
          </div>
        </div>
        <div class="mt-3 flex gap-2 border-t pt-3">
          <button
            v-if="storeState(app) !== 'installed'"
            class="btn-primary text-sm"
            :disabled="acting === `install-${app.id}`"
            @click="installSubmission(app.id)"
          >{{ storeState(app) === 'upgradable'
              ? t('apps.upgradeTo', { version: app.version })
              : t('apps.install') }}</button>
          <button v-else class="btn-ghost text-sm" disabled>{{ t('apps.status_installed') }}</button>
          <button
            class="btn-ghost text-sm"
            @click="expanded = expanded === app.key ? null : app.key"
          >{{ expanded === app.key ? t('apps.collapse') : t('apps.details') }}</button>
        </div>
        <div v-if="expanded === app.key" class="mt-3 pt-3 border-t space-y-2 text-sm">
          <div class="flex flex-wrap gap-4 text-xs text-ink-500">
            <span>{{ t('apps.category') }}: <code class="bg-ink-50 px-1 rounded">{{ app.category }}</code></span>
            <span>{{ t('apps.downloads') }}: {{ app.download_count }}</span>
            <span v-if="installedMap.get(app.key)">
              {{ t('apps.installedVersion') }}: <code class="bg-ink-50 px-1 rounded">{{ installedMap.get(app.key) }}</code>
            </span>
          </div>
          <p class="text-xs text-ink-400">{{ t('apps.packageHint') }}</p>
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

    <template v-if="activeTab === 'cloud'">
      <!-- 绑定状态 -->
      <div class="card">
        <div v-if="!cloudStatus.bound">
          <h3 class="font-semibold mb-1">连接 Cenkor 账号</h3>
          <p class="text-sm text-ink-600 mb-3">
            绑定官方账号后，即可直接浏览官方应用市场、查看本账号已购应用并一键下载安装。
            购买请前往
            <a
              :href="(cloudStatus.gateway_url || 'https://portal.cenkor.cn') + '/apps'"
              target="_blank"
              class="text-blue-600 underline"
            >{{ cloudStatus.gateway_url || 'portal.cenkor.cn' }}</a>。
          </p>

          <div v-if="bindCode" class="rounded border border-ink-200 bg-ink-50 p-3 mb-3">
            <p class="text-sm text-ink-600 mb-1">请在浏览器中打开下面的地址，输入绑定码完成确认：</p>
            <p class="text-xl font-mono font-semibold tracking-widest mb-1">{{ bindCode.user_code }}</p>
            <a
              :href="bindCode.verification_uri_complete || bindCode.verification_uri"
              target="_blank"
              class="text-sm text-blue-600 underline break-all"
            >{{ bindCode.verification_uri }}</a>
            <p class="text-xs text-ink-400 mt-2">
              {{ bindPolling ? '正在等待门户确认…（也可直接点上面链接）' : '已停止等待，可重新发起' }}
            </p>
          </div>

          <button class="btn-primary text-sm" @click="startBind">连接 Cenkor 账号</button>
        </div>

        <div v-else class="flex items-start justify-between gap-3">
          <div class="min-w-0">
            <h3 class="font-semibold mb-1">已连接 Cenkor 账号</h3>
            <p class="text-sm text-ink-600">
              账号：<code class="bg-ink-50 px-1 rounded">{{ cloudStatus.account || '—' }}</code>
              <span class="mx-2 text-ink-300">|</span>
              官方云：<code class="bg-ink-50 px-1 rounded break-all">{{ cloudStatus.hub || '—' }}</code>
            </p>
          </div>
          <button class="btn-ghost text-sm text-red-600 shrink-0" @click="unbind">解绑</button>
        </div>
      </div>

      <div v-if="cloudError" class="card text-red-600">{{ cloudError }}</div>

      <div v-if="cloudLoaded && !cloudError && cloudApps.length === 0" class="card text-ink-500 text-center py-12">
        官方应用市场暂无可用应用
      </div>
      <div v-else-if="!cloudLoaded && !cloudError" class="card text-ink-500">加载中…</div>

      <div v-for="app in cloudApps" :key="app.app_key" class="card">
        <div class="flex items-start gap-3">
          <span class="text-2xl">{{ app.icon || '📦' }}</span>
          <div class="flex-1 min-w-0">
            <div class="flex items-center gap-2 flex-wrap">
              <h3 class="font-semibold">{{ app.name }}</h3>
              <code class="text-xs text-ink-400">{{ app.app_key }} @ {{ app.version }}</code>
              <span
                v-if="purchaseOf(app.app_key)"
                class="text-xs px-2 py-0.5 rounded-full bg-green-50 text-green-700"
              >已购</span>
              <span
                v-if="app.installed"
                class="text-xs px-2 py-0.5 rounded-full"
                :class="app.needs_upgrade ? 'bg-amber-50 text-amber-700' : 'bg-blue-50 text-blue-700'"
              >{{ app.needs_upgrade ? '可升级' : '已安装' }}</span>
            </div>
            <p class="text-sm text-ink-600 mt-1">{{ app.description }}</p>
            <p class="mt-1.5 text-sm">
              <span class="font-semibold text-ink-900">{{ cloudPriceText(app) }}</span>
              <span v-if="cloudListPriceText(app)" class="ml-2 text-xs text-ink-400 line-through">
                {{ cloudListPriceText(app) }}
              </span>
              <span
                v-if="app.price && app.price.promo_state === 'active'"
                class="ml-2 text-xs px-1.5 py-0.5 rounded bg-red-50 text-red-600"
              >促销中{{ app.price.discount_label ? ' · ' + app.price.discount_label : '' }}</span>
              <span v-else-if="app.price && app.price.discount_label" class="ml-2 text-xs text-red-600">
                {{ app.price.discount_label }}
              </span>
            </p>
          </div>
        </div>

        <div class="mt-3 flex gap-2 border-t pt-3 flex-wrap">
          <button
            v-if="purchaseOf(app.app_key)"
            class="btn-primary text-sm"
            :disabled="installing === app.app_key"
            @click="installCloud(app)"
          >{{ installing === app.app_key ? '安装中…'
              : app.installed ? (app.needs_upgrade ? '升级到最新' : '重新安装')
              : '下载安装' }}</button>
          <a
            v-else
            :href="(cloudStatus.gateway_url || 'https://portal.cenkor.cn') + '/apps/' + app.app_key"
            target="_blank"
            class="btn-ghost text-sm"
          >去官方门户购买</a>
          <button
            class="btn-ghost text-sm"
            @click="expanded = expanded === app.app_key ? null : app.app_key"
          >{{ expanded === app.app_key ? t('apps.collapse') : t('apps.details') }}</button>
        </div>

        <div v-if="expanded === app.app_key" class="mt-3 pt-3 border-t space-y-2 text-sm">
          <div class="flex flex-wrap gap-4 text-xs text-ink-500">
            <span>分类：<code class="bg-ink-50 px-1 rounded">{{ app.category }}</code></span>
            <span>作者：{{ app.author }}</span>
            <span v-if="app.installed_version">
              已装版本：<code class="bg-ink-50 px-1 rounded">{{ app.installed_version }}</code>
            </span>
          </div>
          <div v-if="purchaseOf(app.app_key)" class="text-xs text-ink-500">
            授权码：<code class="bg-ink-50 px-1 rounded">{{ purchaseOf(app.app_key)?.license_key }}</code>
            <span class="ml-2">
              {{ purchaseOf(app.app_key)?.permanent ? '永久有效' : '有效期至 ' + purchaseOf(app.app_key)?.expires_at }}
            </span>
          </div>
          <p v-else class="text-xs text-ink-400">
            尚未购买。购买发生在官方门户，付款后授权自动归到已绑定的账号，回到这里刷新即可安装。
          </p>
        </div>
      </div>
    </template>

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
