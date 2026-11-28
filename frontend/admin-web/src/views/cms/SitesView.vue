<script setup lang="ts">
import { useI18n } from 'vue-i18n'
const { t } = useI18n()
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

interface DomainStatus {
  status: 'unset' | 'dns_missing' | 'dns_www_only' | 'ip_mismatch' | 'dns_ok' | 'nginx_ok' | 'live'
  domain: string | null
  domain_source: 'site' | 'config' | null
  alt_domain?: string | null
  resolved: string[]
  expected: string | null
  site_id: number
  site_key: string
  site_name: string
  hint: string
  nginx_has_server: boolean
  cert_exists: boolean
  http_status: number | null
  /** 'http' = 后端从本机 HTTP 探测得来；'caller' = 未探测（DNS 没通） */
  probe: 'http' | 'caller' | null
  commands: DomainCommand[]
}

interface DomainCommand {
  title: string
  lang: string
  code: string
  note: string
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

// 域名绑定状态面板
const domOpen = ref(false)
const domSite = ref<Site | null>(null)
const domLoading = ref(false)
const domInfo = ref<DomainStatus | null>(null)
const domError = ref('')
const domEditing = ref('')
const domSaving = ref(false)
const copiedIdx = ref<number | null>(null)

// 状态 → 徽标样式。五档递进，绿=可用，红=卡住，灰=还没配。
const DOM_BADGE: Record<string, string> = {
  unset: 'bg-ink-100 text-ink-500',
  dns_missing: 'bg-red-100 text-red-700',
  dns_www_only: 'bg-amber-100 text-amber-700',
  ip_mismatch: 'bg-red-100 text-red-700',
  dns_ok: 'bg-amber-100 text-amber-700',
  nginx_ok: 'bg-amber-100 text-amber-700',
  live: 'bg-emerald-100 text-emerald-700',
}
// 用函数而非常量：常量在 setup 里求值一次，切语言不会跟着变
const DOM_LABEL_KEY: Record<string, string> = {
  unset: 'sites.未绑定_fq1zn',
  dns_missing: 'sites.text_icakaz',
  dns_www_only: 'sites.裸域未解_1x0y7z',
  ip_mismatch: 'sites.IP_1x1x1x',
  dns_ok: 'sites.text_169c62',
  nginx_ok: 'sites.text_1wlq8q',
  live: 'sites.已上线_e5c9z',
}
function domLabel(status: string): string {
  const k = DOM_LABEL_KEY[status]
  return k ? t(k) : status
}

async function loadDomain(s: Site, fillInput = true) {
  domError.value = ''
  domLoading.value = true
  try {
    const { data } = await api.get<DomainStatus>(`/api/v1/cms/sites/${s.id}/domain`)
    domInfo.value = data
    // fillInput=false 用于「保存后重新检测」与「重新检测」按钮：那时输入框里
    // 是用户正在编辑/刚提交的值，不该被后端回退口径（可能来自 brand.domain）盖掉。
    if (fillInput) domEditing.value = data.domain || ''
    else if (data.domain) domEditing.value = data.domain
  } catch (e: any) {
    domError.value = e?.response?.data?.detail || t('sites.域名状态_uk6swa')
  } finally {
    domLoading.value = false
  }
}

async function refreshDomain() {
  if (domSite.value) await loadDomain(domSite.value, false)
}

async function openDomain(s: Site) {
  domSite.value = s
  domOpen.value = true
  domInfo.value = null
  copiedIdx.value = null
  await loadDomain(s)
}

async function saveDomain() {
  if (!domSite.value) return
  domSaving.value = true
  domError.value = ''
  try {
    const d = domEditing.value.trim()
    // 直接用 PUT 的返回值更新 domSite：它是保存后的权威状态。
    // 先 load() 再 find() 依赖列表刷新时序，容易拿到旧对象。
    const { data } = await api.put<Site>(`/api/v1/cms/sites/${domSite.value.id}`, {
      domain: d || null,
    })
    domSite.value = data
    notice.value = t('sites.域名保存_17frhl')
    await loadDomain(data, false)
    await load()
  } catch (e: any) {
    const detail = e?.response?.data?.detail
    domError.value = typeof detail === 'string' ? detail : t('sites.检测失败_do2x27')
  } finally {
    domSaving.value = false
  }
}

async function copyCmd(text: string, idx: number) {
  if (!text) return
  try {
    await navigator.clipboard.writeText(text)
    copiedIdx.value = idx
    setTimeout(() => { if (copiedIdx.value === idx) copiedIdx.value = null }, 1500)
  } catch {
    domError.value = t('sites.检测失败_do2x27')
  }
}

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
    error.value = e?.response?.data?.detail || t("sites.开关加载_1h8g81")
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
    notice.value = t('sites.自动化开_1m6wuh')
  } catch (e: any) {
    const detail = e?.response?.data?.detail
    error.value = typeof detail === 'string' ? detail : t("aiMemory.saveFailed")
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
    error.value = e?.response?.data?.detail || t("sites.站点列表_4gx3s2")
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
  if (!form.name.trim()) { error.value = t("sites.站点名称_16vr6z"); return }
  if (!editingId.value && !form.key.trim()) { error.value = t('sites.站点标识_1bvt3j'); return }
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
      notice.value = t("sites.已保存_e5ggd")
    } else {
      payload.key = form.key.trim()
      await api.post('/api/v1/cms/sites', payload)
      notice.value = t('sites.站点已创_16uqkf')
    }
    showForm.value = false
    await load()
  } catch (e: any) {
    const detail = e?.response?.data?.detail
    error.value = typeof detail === 'string' ? detail : JSON.stringify(detail || t("aiMemory.saveFailed"))
  } finally {
    saving.value = false
  }
}

async function remove(s: Site) {
  const total = s.stats ? s.stats.entries + s.stats.pages : 0
  const tail = total > 0 ? t('sites.该站已有_1qva1a', { n: total }) : ''
  if (!confirm(t('sites.删除站点_1nfxr7', { name: s.name }) + tail)) return
  error.value = ''
  try {
    await api.delete(`/api/v1/cms/sites/${s.id}`)
    notice.value = t('sites.站点已删_1wr9fa')
    if (currentId.value === s.id) { setSiteId(null); currentId.value = null }
    await load()
  } catch (e: any) {
    const detail = e?.response?.data?.detail
    error.value = typeof detail === 'string' ? detail : t("sites.删除失败_1kshs5")
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
        <h1 class="text-lg font-semibold text-ink-900">{{ t("sites.站点管理_fyx091") }}</h1>
        <p class="text-sm text-ink-500 mt-1">{{ t("sites.一个后台_1qc9om") }}</p>
      </div>
      <button class="btn btn-primary text-sm" @click="openCreate">{{ t("sites.新建站点_d88e6i") }}</button>
    </div>

    <div v-if="error" class="rounded-md bg-red-50 border border-red-200 text-red-700 text-sm px-3 py-2">{{ error }}</div>
    <div v-if="notice" class="rounded-md bg-emerald-50 border border-emerald-200 text-emerald-700 text-sm px-3 py-2">{{ notice }}</div>

    <div class="overflow-x-auto rounded-lg border border-ink-200 bg-white">
      <table class="w-full text-sm">
        <thead class="bg-ink-50 text-ink-600">
          <tr>
            <th class="text-left px-3 py-2 font-medium">{{ t("sites.站点_liio") }}</th>
            <th class="text-left px-3 py-2 font-medium">{{ t("sites.域名_feoe") }}</th>
            <th class="text-left px-3 py-2 font-medium">{{ t("sites.类型_nbcklr") }}</th>
            <th class="text-right px-3 py-2 font-medium">{{ t("sites.条目_i8j1") }}</th>
            <th class="text-right px-3 py-2 font-medium">{{ t("sites.栏目_icov") }}</th>
            <th class="text-right px-3 py-2 font-medium">{{ t("sites.页面_qrgt") }}</th>
            <th class="text-right px-3 py-2 font-medium">{{ t("sites.媒体_fu9t") }}</th>
            <th class="text-left px-3 py-2 font-medium">{{ t("sites.status") }}</th>
            <th class="text-right px-3 py-2 font-medium">{{ t("sites.actions") }}</th>
          </tr>
        </thead>
        <tbody>
          <tr v-if="loading"><td class="px-3 py-6 text-center text-ink-400" colspan="9">{{ t("apiKeys.加载中_b0k5km") }}</td></tr>
          <tr v-else-if="!sites.length"><td class="px-3 py-6 text-center text-ink-400" colspan="9">{{ t("sites.还没有站_8bcxuo") }}</td></tr>
          <tr v-for="s in sites" :key="s.id" class="border-t border-ink-100">
            <td class="px-3 py-2">
              <div class="flex items-center gap-2">
                <span class="font-medium text-ink-900">{{ s.name }}</span>
                <span v-if="currentId === s.id" class="text-[11px] px-1.5 py-0.5 rounded bg-sky-100 text-sky-700">{{ t("sites.当前_gnyy") }}</span>
              </div>
              <div class="font-mono text-[11px] text-ink-400">{{ s.key }} · #{{ s.id }}</div>
            </td>
            <td class="px-3 py-2 text-ink-600">
              <button class="hover:underline" @click="openDomain(s)">{{ s.domain || '—' }}</button>
            </td>
            <td class="px-3 py-2 text-ink-600">{{ s.kind }} / {{ s.site_mode }}</td>
            <td class="px-3 py-2 text-right">{{ s.stats?.entries ?? '—' }}</td>
            <td class="px-3 py-2 text-right">{{ s.stats?.categories ?? '—' }}</td>
            <td class="px-3 py-2 text-right">{{ s.stats?.pages ?? '—' }}</td>
            <td class="px-3 py-2 text-right">{{ s.stats?.media ?? '—' }}</td>
            <td class="px-3 py-2">
              <span class="text-[11px] px-1.5 py-0.5 rounded" :class="s.status === 'active' ? 'bg-emerald-100 text-emerald-700' : 'bg-ink-100 text-ink-500'">{{ s.status }}</span>
            </td>
            <td class="px-3 py-2 text-right whitespace-nowrap space-x-2">
              <button class="text-sky-600 hover:underline" @click="enter(s)">{{ t("sites.进入_owyy") }}</button>
              <button class="text-ink-600 hover:underline" @click="openDomain(s)">{{ t("sites.域名状态_bfuuft") }}</button>
              <button class="text-ink-600 hover:underline" @click="openFeatures(s)">{{ t("sites.开关_gltf") }}</button>
              <button class="text-ink-600 hover:underline" @click="openEdit(s)">{{ t("sites.edit") }}</button>
              <button class="text-red-600 hover:underline" @click="remove(s)">{{ t("sites.delete") }}</button>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <div v-if="showForm" class="fixed inset-0 z-40 bg-black/30 flex items-center justify-center p-4" @click.self="showForm = false">
      <div class="bg-white rounded-lg shadow-lg w-full max-w-md p-5 space-y-3">
        <h2 class="font-semibold text-ink-900">{{ editingId ? t('sites.编辑站点_gmoakb') : t('sites.新建站点_d88e6i') }}</h2>
        <div class="space-y-2">
          <label class="block text-sm text-ink-600">{{ t("sites.站点标识_fytswv") }} <span class="text-red-500">*</span>
            <input v-model="form.key" class="input mt-1 text-sm" :disabled="!!editingId" :placeholder="t('sites.例如_100usp')" />
          </label>
          <label class="block text-sm text-ink-600">{{ t("sites.站点名称_fyqb2b") }} <span class="text-red-500">*</span>
            <input v-model="form.name" class="input mt-1 text-sm" :placeholder="t('sites.例如_10j0on')" />
          </label>
          <label class="block text-sm text-ink-600">{{ t("sites.绑定域名_gdo4af") }}
            <input v-model="form.domain" class="input mt-1 text-sm" :placeholder="t('sites.例如_1697yh')" />
          </label>
          <div class="grid grid-cols-2 gap-2">
            <label class="block text-sm text-ink-600">{{ t("sites.语言_ok37") }}
              <input v-model="form.locale" class="input mt-1 text-sm" placeholder="zh-CN" />
            </label>
            <label class="block text-sm text-ink-600">{{ t("sites.排序_hge5") }}
              <input v-model.number="form.sort" type="number" class="input mt-1 text-sm" />
            </label>
          </div>
        </div>
        <p class="text-xs text-ink-400">{{ t("sites.类型_p0upab") }}</p>
        <div class="flex justify-end gap-2 pt-1">
          <button class="btn text-sm" @click="showForm = false">{{ t("sites.cancel") }}</button>
          <button class="btn btn-primary text-sm" :disabled="saving" @click="save">{{ saving ? t('sites.保存中_agdrec') : t('sites.保存_e32z') }}</button>
        </div>
      </div>
    </div>

    <div v-if="domOpen" class="fixed inset-0 z-40 bg-black/30 flex items-center justify-center p-4" @click.self="domOpen = false">
      <div class="bg-white rounded-lg shadow-lg w-full max-w-2xl p-5 space-y-3 max-h-[85vh] overflow-y-auto">
        <div class="flex items-center justify-between gap-2">
          <h2 class="font-semibold text-ink-900">{{ t('sites.域名状态_bfuuft') }} · {{ domSite?.name }}</h2>
          <span
            v-if="domInfo"
            class="text-[11px] px-2 py-0.5 rounded"
            :class="DOM_BADGE[domInfo.status]"
          >{{ domLabel(domInfo.status) }}</span>
        </div>

        <div v-if="domError" class="rounded-md bg-red-50 border border-red-200 text-red-700 text-sm px-3 py-2">{{ domError }}</div>

        <div class="space-y-2">
          <label class="block text-sm text-ink-600">{{ t('sites.绑定域名_gdo4af') }}
            <div class="flex gap-2 mt-1">
              <input v-model="domEditing" class="input text-sm flex-1" :placeholder="t('sites.例如_1697yh')" />
              <button class="btn btn-primary text-sm whitespace-nowrap" :disabled="domSaving" @click="saveDomain">
                {{ domSaving ? '保存中…' : t('sites.已保存_e5ggd') }}
              </button>
            </div>
          </label>
          <p v-if="domInfo?.domain_source === 'config'" class="text-xs text-amber-600">
            {{ t('sites.当前域名_175m15') }}
          </p>
        </div>

        <div v-if="domLoading" class="text-sm text-ink-400 py-4 text-center">{{ t('apiKeys.加载中_b0k5km') }}</div>

        <template v-else-if="domInfo">
          <div class="grid grid-cols-2 gap-2 text-sm">
            <div class="rounded-md border border-ink-200 px-3 py-2">
              <div class="text-xs text-ink-400">{{ t('sites.解析到_kp51f') }}</div>
              <div class="font-mono text-ink-800 break-all">
                {{ domInfo.resolved.length ? domInfo.resolved.join(', ') : '—' }}
              </div>
            </div>
            <div class="rounded-md border border-ink-200 px-3 py-2">
              <div class="text-xs text-ink-400">{{ t('sites.本机_1p9k2y') }}</div>
              <div class="font-mono text-ink-800 break-all">{{ domInfo.expected || '—' }}</div>
            </div>
            <div class="rounded-md border border-ink-200 px-3 py-2">
              <div class="text-xs text-ink-400">{{ t('sites.text_19r651') }}</div>
              <div class="text-ink-800">
                <template v-if="domInfo.probe !== 'http'">{{ t('sites.未探测_1u7n0b') }}</template>
                <template v-else>{{ domInfo.nginx_has_server ? t('sites.已有_gjmf') : t('sites.缺失_m4on') }}</template>
              </div>
            </div>
            <div class="rounded-md border border-ink-200 px-3 py-2">
              <div class="text-xs text-ink-400">{{ t('sites.证书_o79h') }}</div>
              <div class="text-ink-800">
                <template v-if="domInfo.probe !== 'http'">{{ t('sites.未探测_1u7n0b') }}</template>
                <template v-else>{{ domInfo.cert_exists ? t('sites.已有_gjmf') : t('sites.缺失_m4on') }}</template>
              </div>
            </div>
          </div>

          <div class="rounded-md bg-sky-50 border border-sky-200 px-3 py-2 text-sm text-sky-800">
            <span class="font-medium">{{ t('sites.下一步该_1cvfax') }}：</span>{{ domInfo.hint }}
          </div>

          <div v-if="domInfo.commands.length" class="space-y-1">
            <div class="flex items-center justify-between">
              <span class="text-sm font-medium text-ink-700">{{ t('sites.服务端命_1mpdu9') }}</span>
              <button class="text-xs text-sky-600 hover:underline" @click="refreshDomain">
                {{ t('sites.重新检测_itfjgu') }}
              </button>
            </div>
            <p class="text-xs text-ink-400">{{ t('sites.在服务器_pq7h6b') }}</p>
            <div v-for="(cmd, i) in domInfo.commands" :key="i" class="space-y-1">
              <div class="text-xs font-medium text-ink-700">{{ cmd.title }}</div>
              <div
                class="relative rounded-md bg-ink-900 text-ink-100 font-mono text-xs px-3 py-2 pr-16 whitespace-pre-wrap break-all"
              >
                {{ cmd.code }}
                <button
                  class="absolute top-1.5 right-2 text-[11px] px-1.5 py-0.5 rounded bg-white/15 hover:bg-white/25"
                  @click="copyCmd(cmd.code, i)"
                >{{ copiedIdx === i ? t('sites.已复制_e6ywr') : t('sites.复制_fljd') }}</button>
              </div>
              <div v-if="cmd.note" class="text-[11px] text-ink-400">{{ cmd.note }}</div>
            </div>
          </div>
          <div v-else class="flex justify-end">
            <button class="text-xs text-sky-600 hover:underline" @click="refreshDomain">
              {{ t('sites.重新检测_itfjgu') }}
            </button>
          </div>
        </template>

        <div class="flex justify-end gap-2 pt-1">
          <button class="btn text-sm" @click="domOpen = false">{{ t('sites.cancel') }}</button>
        </div>
      </div>
    </div>

    <div v-if="featOpen" class="fixed inset-0 z-40 bg-black/30 flex items-center justify-center p-4" @click.self="featOpen = false">
      <div class="bg-white rounded-lg shadow-lg w-full max-w-md p-5 space-y-3">
        <h2 class="font-semibold text-ink-900">{{ t('sites.自动化开_440ned', { name: featSite?.name }) }}</h2>
        <p class="text-xs text-ink-400">{{ t("sites.关掉哪个_86xii1") }}</p>
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
          <button class="btn text-sm" @click="featOpen = false">{{ t("sites.cancel") }}</button>
          <button class="btn btn-primary text-sm" :disabled="featSaving" @click="saveFeatures">{{ featSaving ? t('sites.保存中_agdrec') : t('sites.保存_e32z') }}</button>
        </div>
      </div>
    </div>
  </div>
</template>
