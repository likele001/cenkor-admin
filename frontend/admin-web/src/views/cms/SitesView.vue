<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { api } from '@/lib/api'
import { getSiteId, setSiteId } from '@/lib/site'

interface Stats {
  entries: number
  categories: number
  tags: number
  media: number
  pages: number
  forms: number
  trashed: number
}

interface Site {
  id: number
  key: string
  name: string
  kind: string
  domain: string | null
  locale: string
  default_lang: string | null
  site_mode: string
  status: string
  sort: number
  stats: Stats
}

const router = useRouter()
const sites = ref<Site[]>([])
const loading = ref(false)
const error = ref('')
const notice = ref('')
const currentId = ref<number | null>(getSiteId())

const showForm = ref(false)
const editingId = ref<number | null>(null)
const saving = ref(false)
const form = reactive({ key: '', name: '', domain: '', locale: 'zh-CN', sort: 0 })

// 站点级自动化开关
const featOpen = ref(false)
const featSite = ref<Site | null>(null)
const featSaving = ref(false)
const features = ref<Record<string, boolean>>({})
const featLabels = ref<Record<string, string>>({})

async function openFeatures(s: Site) {
  featSite.value = s
  featOpen.value = true
  error.value = ''
  try {
    const { data } = await api.get(`/api/v1/cms/sites/${s.id}/features`)
    features.value = data.features
    featLabels.value = data.labels
  } catch (e: any) {
    error.value = e?.response?.data?.detail || '开关加载失败'
    featOpen.value = false
  }
}

async function saveFeatures() {
  if (!featSite.value) return
  featSaving.value = true
  error.value = ''
  try {
    const { data } = await api.put(`/api/v1/cms/sites/${featSite.value.id}/features`, features.value)
    features.value = data.features
    featOpen.value = false
    notice.value = '自动化开关已保存，下一次调度就按新设置走'
  } catch (e: any) {
    const detail = e?.response?.data?.detail
    error.value = typeof detail === 'string' ? detail : '保存失败'
  } finally {
    featSaving.value = false
  }
}

async function load() {
  loading.value = true
  error.value = ''
  try {
    const { data } = await api.get<Site[]>('/api/v1/cms/sites')
    sites.value = data
  } catch (e: any) {
    error.value = e?.response?.data?.detail || '站点列表加载失败'
  } finally {
    loading.value = false
  }
}

function openCreate() {
  editingId.value = null
  Object.assign(form, { key: '', name: '', domain: '', locale: 'zh-CN', sort: sites.value.length })
  showForm.value = true
}

function openEdit(s: Site) {
  editingId.value = s.id
  Object.assign(form, {
    key: s.key,
    name: s.name,
    domain: s.domain || '',
    locale: s.locale || 'zh-CN',
    sort: s.sort ?? 0,
  })
  showForm.value = true
}

async function save() {
  error.value = ''
  if (!form.name.trim()) { error.value = '站点名称不能为空'; return }
  if (!editingId.value && !form.key.trim()) { error.value = '站点标识不能为空'; return }
  saving.value = true
  try {
    const payload: Record<string, unknown> = {
      name: form.name.trim(),
      domain: form.domain.trim() || null,
      locale: form.locale.trim() || 'zh-CN',
      sort: Number(form.sort) || 0,
    }
    if (editingId.value) {
      await api.put(`/api/v1/cms/sites/${editingId.value}`, payload)
      notice.value = '已保存'
    } else {
      payload.key = form.key.trim()
      await api.post('/api/v1/cms/sites', payload)
      notice.value = '站点已创建，可以进入并开始配置栏目'
    }
    showForm.value = false
    await load()
  } catch (e: any) {
    const detail = e?.response?.data?.detail
    error.value = typeof detail === 'string' ? detail : JSON.stringify(detail || '保存失败')
  } finally {
    saving.value = false
  }
}

async function remove(s: Site) {
  const total = s.stats ? s.stats.entries + s.stats.pages : 0
  if (!confirm(`删除站点「${s.name}」？${total > 0 ? `该站已有 ${total} 条内容，后端会拒绝并要求先清理。` : ''}`)) return
  error.value = ''
  try {
    await api.delete(`/api/v1/cms/sites/${s.id}`)
    notice.value = '站点已删除'
    if (currentId.value === s.id) { setSiteId(null); currentId.value = null }
    await load()
  } catch (e: any) {
    const detail = e?.response?.data?.detail
    error.value = typeof detail === 'string' ? detail : '删除失败：站点内还有内容，请先清理'
  }
}

function enter(s: Site) {
  setSiteId(s.id)
  currentId.value = s.id
  router.push('/')
}

onMounted(load)
</script>

<template>
  <div class="space-y-4">
    <div class="flex items-center justify-between gap-3 flex-wrap">
      <div>
        <h1 class="text-lg font-semibold text-ink-900">站点管理</h1>
        <p class="text-sm text-ink-500 mt-1">一个后台管多个站点：切换后所有内容操作都只落在当前站点。</p>
      </div>
      <button class="btn btn-primary text-sm" @click="openCreate">新建站点</button>
    </div>

    <div v-if="error" class="rounded-md bg-red-50 border border-red-200 text-red-700 text-sm px-3 py-2">{{ error }}</div>
    <div v-if="notice" class="rounded-md bg-emerald-50 border border-emerald-200 text-emerald-700 text-sm px-3 py-2">{{ notice }}</div>

    <div class="overflow-x-auto rounded-lg border border-ink-200 bg-white">
      <table class="w-full text-sm">
        <thead class="bg-ink-50 text-ink-600">
          <tr>
            <th class="text-left px-3 py-2 font-medium">站点</th>
            <th class="text-left px-3 py-2 font-medium">域名</th>
            <th class="text-left px-3 py-2 font-medium">类型 / 模式</th>
            <th class="text-right px-3 py-2 font-medium">条目</th>
            <th class="text-right px-3 py-2 font-medium">栏目</th>
            <th class="text-right px-3 py-2 font-medium">页面</th>
            <th class="text-right px-3 py-2 font-medium">媒体</th>
            <th class="text-left px-3 py-2 font-medium">状态</th>
            <th class="text-right px-3 py-2 font-medium">操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-if="loading"><td class="px-3 py-6 text-center text-ink-400" colspan="9">加载中…</td></tr>
          <tr v-else-if="!sites.length"><td class="px-3 py-6 text-center text-ink-400" colspan="9">还没有站点</td></tr>
          <tr v-for="s in sites" :key="s.id" class="border-t border-ink-100">
            <td class="px-3 py-2">
              <div class="flex items-center gap-2">
                <span class="font-medium text-ink-900">{{ s.name }}</span>
                <span v-if="currentId === s.id" class="text-[11px] px-1.5 py-0.5 rounded bg-sky-100 text-sky-700">当前</span>
              </div>
              <div class="font-mono text-[11px] text-ink-400">{{ s.key }} · #{{ s.id }}</div>
            </td>
            <td class="px-3 py-2 text-ink-600">{{ s.domain || '—' }}</td>
            <td class="px-3 py-2 text-ink-600">{{ s.kind }} / {{ s.site_mode }}</td>
            <td class="px-3 py-2 text-right">{{ s.stats?.entries ?? '—' }}</td>
            <td class="px-3 py-2 text-right">{{ s.stats?.categories ?? '—' }}</td>
            <td class="px-3 py-2 text-right">{{ s.stats?.pages ?? '—' }}</td>
            <td class="px-3 py-2 text-right">{{ s.stats?.media ?? '—' }}</td>
            <td class="px-3 py-2">
              <span class="text-[11px] px-1.5 py-0.5 rounded" :class="s.status === 'active' ? 'bg-emerald-100 text-emerald-700' : 'bg-ink-100 text-ink-500'">{{ s.status }}</span>
            </td>
            <td class="px-3 py-2 text-right whitespace-nowrap space-x-2">
              <button class="text-sky-600 hover:underline" @click="enter(s)">进入</button>
              <button class="text-ink-600 hover:underline" @click="openFeatures(s)">开关</button>
              <button class="text-ink-600 hover:underline" @click="openEdit(s)">编辑</button>
              <button class="text-red-600 hover:underline" @click="remove(s)">删除</button>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <div v-if="showForm" class="fixed inset-0 z-40 bg-black/30 flex items-center justify-center p-4" @click.self="showForm = false">
      <div class="bg-white rounded-lg shadow-lg w-full max-w-md p-5 space-y-3">
        <h2 class="font-semibold text-ink-900">{{ editingId ? '编辑站点' : '新建站点' }}</h2>
        <div class="space-y-2">
          <label class="block text-sm text-ink-600">站点标识 <span class="text-red-500">*</span>
            <input v-model="form.key" class="input mt-1 text-sm" :disabled="!!editingId" placeholder="例如 hydraulic-shandong" />
          </label>
          <label class="block text-sm text-ink-600">站点名称 <span class="text-red-500">*</span>
            <input v-model="form.name" class="input mt-1 text-sm" placeholder="例如 山东液压官网" />
          </label>
          <label class="block text-sm text-ink-600">绑定域名
            <input v-model="form.domain" class="input mt-1 text-sm" placeholder="例如 www.example.com（可留空）" />
          </label>
          <div class="grid grid-cols-2 gap-2">
            <label class="block text-sm text-ink-600">语言
              <input v-model="form.locale" class="input mt-1 text-sm" placeholder="zh-CN" />
            </label>
            <label class="block text-sm text-ink-600">排序
              <input v-model.number="form.sort" type="number" class="input mt-1 text-sm" />
            </label>
          </div>
        </div>
        <p class="text-xs text-ink-400">类型、内容模式、SEO 默认值等建站后再到「站点配置」里调。</p>
        <div class="flex justify-end gap-2 pt-1">
          <button class="btn text-sm" @click="showForm = false">取消</button>
          <button class="btn btn-primary text-sm" :disabled="saving" @click="save">{{ saving ? '保存中…' : '保存' }}</button>
        </div>
      </div>
    </div>

    <div v-if="featOpen" class="fixed inset-0 z-40 bg-black/30 flex items-center justify-center p-4" @click.self="featOpen = false">
      <div class="bg-white rounded-lg shadow-lg w-full max-w-md p-5 space-y-3">
        <h2 class="font-semibold text-ink-900">自动化开关 · {{ featSite?.name }}</h2>
        <p class="text-xs text-ink-400">关掉哪个，哪条自动化链路就停住，其余照常；手动操作永远不受影响。</p>
        <div class="space-y-2">
          <label
            v-for="(_val, key) in features"
            :key="key"
            class="flex items-center justify-between gap-3 rounded-md border border-ink-200 px-3 py-2"
          >
            <span class="text-sm text-ink-700">{{ featLabels[key] || key }}</span>
            <input v-model="features[key]" type="checkbox" class="h-4 w-4" />
          </label>
        </div>
        <div class="flex justify-end gap-2 pt-1">
          <button class="btn text-sm" @click="featOpen = false">取消</button>
          <button class="btn btn-primary text-sm" :disabled="featSaving" @click="saveFeatures">{{ featSaving ? '保存中…' : '保存' }}</button>
        </div>
      </div>
    </div>
  </div>
</template>
