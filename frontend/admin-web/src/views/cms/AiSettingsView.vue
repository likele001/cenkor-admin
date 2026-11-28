<script setup lang="ts">
import { useI18n } from 'vue-i18n'
const { t } = useI18n()
import { computed, onMounted, ref } from 'vue'
import { api } from '@/lib/api'

interface ParamSpec {
  key: string
  type: 'float' | 'int' | 'str' | 'bool'
  min: number | null
  max: number | null
  enum: string[]
}

interface Binding {
  provider_id: number | null
  model: string
  params: Record<string, any>
  enabled: boolean
  updated_at: string | null
}

interface Effective {
  source: 'db' | 'env'
  provider_name: string
  model: string
  params: Record<string, any>
}

interface Capability {
  key: string
  label: string
  hint: string
  wired: boolean
  param_specs: ParamSpec[]
  binding: Binding | null
  effective: Effective | null
}

interface ProviderOption {
  id: number
  slug: string
  name: string
  enabled: boolean
  has_api_key: boolean
}

interface Provider {
  id: number
  slug: string
  name: string
  kind: string
  base_url: string
  api_key_hint: string
  has_api_key: boolean
  extra_headers: Record<string, string>
  timeout_seconds: number
  max_retries: number
  enabled: boolean
  remark: string | null
  is_builtin: boolean
  bound_capabilities: string[]
  last_test_at: string | null
  last_test_ok: boolean | null
  last_test_error: string | null
  updated_at: string | null
}

interface Preset {
  slug: string
  name: string
  kind: string
  base_url: string
  models: Record<string, string>
  note: string
}

const PARAM_LABELS: Record<string, string> = {
  temperature: '温度',
  max_tokens: '最大 Token',
  top_p: 'top_p',
  frequency_penalty: '频率惩罚',
  dim: '向量维度',
  batch: '批量大小',
  size: '尺寸',
  quality: '质量',
  n: '生成数量',
  detail: '细节精度',
  style: '风格',
  top_n: '返回条数',
  language: '语言',
  speed: '语速',
}

const PROVIDER_KINDS = [
  { value: 'openai', label: 'OpenAI 兼容协议' },
  { value: 'azure', label: 'Azure OpenAI' },
  { value: 'ollama', label: '本地 Ollama' },
]

const tab = ref<'capabilities' | 'providers'>('capabilities')
const loading = ref(true)
const error = ref('')

const capabilities = ref<Capability[]>([])
const providers = ref<Provider[]>([])
const providerOptions = ref<ProviderOption[]>([])
const presets = ref<Preset[]>([])
const overview = ref<any>(null)

const enabledOptions = computed(() => providerOptions.value.filter((p) => p.enabled))
const readyCount = computed(() => capabilities.value.filter((c) => c.effective).length)

function providerName(id: number | null): string {
  if (!id) return '未选择'
  return providerOptions.value.find((p) => p.id === id)?.name || `#${id}`
}

async function loadCapabilities() {
  const { data } = await api.get('/api/v1/cms/ai/capabilities')
  capabilities.value = data.capabilities
  providerOptions.value = data.providers
}

async function loadProviders() {
  const { data } = await api.get('/api/v1/cms/ai/providers')
  providers.value = data
}

async function loadOverview() {
  const { data } = await api.get('/api/v1/cms/ai/overview')
  overview.value = data
}

async function loadAll() {
  loading.value = true
  error.value = ''
  try {
    await Promise.all([loadCapabilities(), loadProviders(), loadOverview()])
  } catch (e: any) {
    error.value = e?.response?.data?.detail || e.message || t("dashboard.loadFailed")
  } finally {
    loading.value = false
  }
}

async function loadPresets() {
  if (presets.value.length) return
  try {
    const { data } = await api.get('/api/v1/cms/ai/presets')
    presets.value = data
  } catch {
    presets.value = []
  }
}

/* ---------------- 能力绑定 ---------------- */

const editingCap = ref<string | null>(null)
const capDraft = ref<{ provider_id: number | null; model: string; params: Record<string, any> }>({
  provider_id: null,
  model: '',
  params: {},
})
const capSaving = ref(false)
const capTesting = ref<string | null>(null)
const capTestResult = ref<Record<string, { ok: boolean; detail: string; latency_ms: number; result: any }>>({})

function openCapEditor(cap: Capability) {
  editingCap.value = cap.key
  capDraft.value = {
    provider_id: cap.binding?.provider_id ?? null,
    model: cap.binding?.model || cap.effective?.model || '',
    params: { ...(cap.binding?.params || {}) },
  }
}

function closeCapEditor() {
  editingCap.value = null
}

async function saveCapability(cap: Capability) {
  if (!capDraft.value.provider_id) {
    alert(t("aiSettings.请先选择_1p0ydj"))
    return
  }
  if (!capDraft.value.model.trim()) {
    alert(t("aiSettings.请填写模_1oz70f"))
    return
  }
  capSaving.value = true
  try {
    await api.put(`/api/v1/cms/ai/capabilities/${cap.key}`, {
      provider_id: capDraft.value.provider_id,
      model: capDraft.value.model.trim(),
      params: capDraft.value.params,
      enabled: true,
    })
    closeCapEditor()
    await loadAll()
  } catch (e: any) {
    alert(t("settings.保存失败_141keb") + (e?.response?.data?.detail || e.message))
  } finally {
    capSaving.value = false
  }
}

async function unbindCapability(cap: Capability) {
  if (!confirm(`解绑「${cap.label}」？解绑后该能力会回退到环境变量配置（若有），否则不可用。`)) return
  try {
    await api.delete(`/api/v1/cms/ai/capabilities/${cap.key}`)
    await loadAll()
  } catch (e: any) {
    alert(t("aiSettings.解绑失败_1mamm4") + (e?.response?.data?.detail || e.message))
  }
}

async function testCapability(cap: Capability) {
  capTesting.value = cap.key
  const cleared = { ...capTestResult.value }
  delete cleared[cap.key]
  capTestResult.value = cleared
  try {
    const { data } = await api.post(`/api/v1/cms/ai/capabilities/${cap.key}/test`)
    capTestResult.value = { ...capTestResult.value, [cap.key]: data }
  } catch (e: any) {
    capTestResult.value = {
      ...capTestResult.value,
      [cap.key]: {
        ok: false,
        detail: e?.response?.data?.detail || e.message,
        latency_ms: 0,
        result: null,
      },
    }
  } finally {
    capTesting.value = null
  }
}

/* ---------------- 服务商 ---------------- */

const showForm = ref(false)
const editingProvider = ref<Provider | null>(null)
const formSaving = ref(false)
const form = ref({
  slug: '',
  name: '',
  kind: 'openai',
  base_url: '',
  api_key: '',
  timeout_seconds: 60,
  max_retries: 2,
  enabled: true,
  remark: '',
  extra_headers_text: '',
})

const testingProvider = ref<number | null>(null)
const providerTestResult = ref<Record<number, { ok: boolean; detail: string; latency_ms: number; models?: string[] }>>({})

function openCreate() {
  editingProvider.value = null
  form.value = {
    slug: '',
    name: '',
    kind: 'openai',
    base_url: '',
    api_key: '',
    timeout_seconds: 60,
    max_retries: 2,
    enabled: true,
    remark: '',
    extra_headers_text: '',
  }
  showForm.value = true
  loadPresets()
}

function openEdit(p: Provider) {
  editingProvider.value = p
  form.value = {
    slug: p.slug,
    name: p.name,
    kind: p.kind,
    base_url: p.base_url,
    // 留空即不修改——后端把空值当作「保持原密钥」
    api_key: '',
    timeout_seconds: p.timeout_seconds,
    max_retries: p.max_retries,
    enabled: p.enabled,
    remark: p.remark || '',
    extra_headers_text: Object.entries(p.extra_headers || {})
      .map(([k, v]) => `${k}: ${v}`)
      .join('\n'),
  }
  showForm.value = true
  loadPresets()
}

function applyPreset(slug: string) {
  const preset = presets.value.find((p) => p.slug === slug)
  if (!preset) return
  form.value.slug = preset.slug
  form.value.name = preset.name
  form.value.kind = preset.kind
  form.value.base_url = preset.base_url
  form.value.remark = preset.note
}

function parseHeaders(text: string): Record<string, string> {
  const out: Record<string, string> = {}
  text
    .split('\n')
    .map((line) => line.trim())
    .filter(Boolean)
    .forEach((line) => {
      const idx = line.indexOf(':')
      if (idx > 0) out[line.slice(0, idx).trim()] = line.slice(idx + 1).trim()
    })
  return out
}

async function saveProvider() {
  if (!form.value.name.trim() || !form.value.base_url.trim()) {
    alert('名称与 base_url 必填')
    return
  }
  if (!editingProvider.value && !form.value.api_key.trim()) {
    alert('新建服务商必须填写密钥（本地 Ollama 可随便填一个）')
    return
  }
  formSaving.value = true
  try {
    const headers = parseHeaders(form.value.extra_headers_text)
    if (editingProvider.value) {
      const body: any = {
        name: form.value.name.trim(),
        kind: form.value.kind,
        base_url: form.value.base_url.trim(),
        timeout_seconds: Number(form.value.timeout_seconds),
        max_retries: Number(form.value.max_retries),
        enabled: form.value.enabled,
        remark: form.value.remark || null,
        extra_headers: headers,
      }
      if (form.value.api_key.trim()) body.api_key = form.value.api_key.trim()
      await api.patch(`/api/v1/cms/ai/providers/${editingProvider.value.id}`, body)
    } else {
      await api.post('/api/v1/cms/ai/providers', {
        slug: form.value.slug.trim() || form.value.name.trim().toLowerCase().replace(/\s+/g, '-'),
        name: form.value.name.trim(),
        kind: form.value.kind,
        base_url: form.value.base_url.trim(),
        api_key: form.value.api_key.trim(),
        timeout_seconds: Number(form.value.timeout_seconds),
        max_retries: Number(form.value.max_retries),
        enabled: form.value.enabled,
        remark: form.value.remark || null,
        extra_headers: headers,
      })
    }
    showForm.value = false
    await loadAll()
  } catch (e: any) {
    alert(t("settings.保存失败_141keb") + (e?.response?.data?.detail || e.message))
  } finally {
    formSaving.value = false
  }
}

async function removeProvider(p: Provider) {
  if (!confirm(`删除服务商「${p.name}」？此操作不可撤销。`)) return
  try {
    await api.delete(`/api/v1/cms/ai/providers/${p.id}`)
    await loadAll()
  } catch (e: any) {
    alert(t("apiKeys.删除失败_1kc17l") + (e?.response?.data?.detail || e.message))
  }
}

async function testProvider(p: Provider) {
  testingProvider.value = p.id
  try {
    const { data } = await api.post(`/api/v1/cms/ai/providers/${p.id}/test`)
    providerTestResult.value = { ...providerTestResult.value, [p.id]: data }
    await loadProviders()
  } catch (e: any) {
    providerTestResult.value = {
      ...providerTestResult.value,
      [p.id]: {
        ok: false,
        detail: e?.response?.data?.detail || e.message,
        latency_ms: 0,
      },
    }
  } finally {
    testingProvider.value = null
  }
}

function fmtTime(value: string | null): string {
  if (!value) return '—'
  const d = new Date(value)
  if (Number.isNaN(d.getTime())) return value
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${d.getMonth() + 1}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`
}

onMounted(loadAll)
</script>

<template>
  <div class="min-h-screen bg-ink-50">
    <header class="bg-white border-b border-ink-200">
      <div class="max-w-7xl mx-auto px-6 h-14 flex items-center gap-4">
        <router-link to="/" class="text-sm text-ink-500 hover:text-ink-900">← Dashboard</router-link>
        <span class="font-semibold">{{ t("aiSettings.text_11qd7s") }}</span>
        <span class="text-xs text-ink-400">{{ t("aiSettings.服务商_1atu7d") }}</span>
        <div class="ml-auto flex items-center gap-4">
          <router-link
            to="/cms/ai-batch"
            class="text-sm text-ink-600 hover:text-ink-900 underline underline-offset-4"
          >
            {{ t("aiBatch.批量生产_d11rha") }}
          </router-link>
          <router-link
            to="/cms/ai-prompts"
            class="text-sm text-ink-600 hover:text-ink-900 underline underline-offset-4"
          >
            {{ t("aiPrompts.提示词管_1ezhgm") }}
          </router-link>
        </div>
      </div>
    </header>

    <main class="max-w-6xl mx-auto px-6 py-8">
      <!-- 概览 -->
      <div class="card mb-6">
        <div class="flex flex-wrap items-center justify-between gap-4">
          <div>
            <h2 class="text-base font-semibold text-ink-900">{{ t("aiSettings.text_bafum9") }}</h2>
            <p class="mt-1 text-sm text-ink-500">
              {{ t("aiSettings.已就绪_e7qyz") }}
              <span class="font-semibold text-ink-900">{{ readyCount }}</span> / {{ capabilities.length }} 项能力
              · 服务商 {{ overview?.providers?.total ?? 0 }} 个（启用 {{ overview?.providers?.enabled ?? 0 }}）
            </p>
          </div>
          <div class="flex items-center gap-2">
            <span
              class="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-medium"
              :class="readyCount > 0 ? 'bg-emerald-50 text-emerald-700' : 'bg-ink-100 text-ink-500'"
            >
              <span class="w-1.5 h-1.5 rounded-full" :class="readyCount > 0 ? 'bg-emerald-500' : 'bg-ink-400'"></span>
              {{ readyCount > 0 ? 'AI 可用' : 'AI 未配置' }}
            </span>
          </div>
        </div>

        <p v-if="overview?.env_fallback?.AI_ENABLED && overview?.env_fallback?.has_key" class="mt-3 text-xs text-amber-700 bg-amber-50 border border-amber-200 rounded-lg px-3 py-2">
          {{ t("aiSettings.检测到_fvdvp") }} <code class="font-mono">.env</code> {{ t("aiSettings.里配置了_p1yqf3") }}<b>{{ t("aiSettings.一旦绑定_1mfwm4") }}</b>。
        </p>
        <p v-if="overview?.registry_error" class="mt-3 text-xs text-red-600">
          配置加载异常：{{ overview.registry_error }}
        </p>
      </div>

      <!-- 切换 -->
      <div class="flex items-center gap-1 mb-4">
        <button
          class="px-4 py-2 text-sm rounded-lg font-medium transition-colors"
          :class="tab === 'capabilities' ? 'bg-white text-ink-900 shadow-sm border border-ink-200' : 'text-ink-500 hover:text-ink-900'"
          @click="tab = 'capabilities'"
        >
          {{ t("aiSettings.能力绑定_gmed9j") }}
        </button>
        <button
          class="px-4 py-2 text-sm rounded-lg font-medium transition-colors"
          :class="tab === 'providers' ? 'bg-white text-ink-900 shadow-sm border border-ink-200' : 'text-ink-500 hover:text-ink-900'"
          @click="tab = 'providers'"
        >
          {{ t("aiSettings.服务商_fhwnm") }}
          <span class="ml-1 text-xs text-ink-400">{{ providers.length }}</span>
        </button>
      </div>

      <div v-if="loading" class="card text-ink-500">{{ t("apiKeys.加载中_b0k5km") }}</div>
      <div v-else-if="error" class="card text-red-600">⚠️ {{ error }}</div>

      <!-- ================= 能力绑定 ================= -->
      <div v-else-if="tab === 'capabilities'" class="space-y-3">
        <div
          v-for="cap in capabilities"
          :key="cap.key"
          class="card"
          :class="cap.wired ? '' : 'opacity-80'"
        >
          <div class="flex items-start justify-between gap-4">
            <div class="min-w-0">
              <div class="flex items-center gap-2 flex-wrap">
                <h3 class="font-semibold text-ink-900">{{ cap.label }}</h3>
                <code class="text-xs px-1.5 py-0.5 rounded bg-ink-100 text-ink-500 font-mono">{{ cap.key }}</code>
                <span v-if="!cap.wired" class="text-xs px-2 py-0.5 rounded-full bg-ink-100 text-ink-500">{{ t("aiSettings.未接入调_1cb4ib") }}</span>
                <span
                  v-else-if="cap.effective"
                  class="text-xs px-2 py-0.5 rounded-full"
                  :class="cap.effective.source === 'db' ? 'bg-emerald-50 text-emerald-700' : 'bg-sky-50 text-sky-700'"
                >
                  {{ cap.effective.source === 'db' ? '后台配置' : '环境变量' }}
                </span>
                <span v-else class="text-xs px-2 py-0.5 rounded-full bg-ink-100 text-ink-500">{{ t("aiSettings.未配置_fte97") }}</span>
              </div>
              <p class="mt-1 text-sm text-ink-500">{{ cap.hint }}</p>
              <p v-if="cap.effective" class="mt-2 text-xs text-ink-600">
                {{ t("aiSettings.生效中_f71mqe") }}<b>{{ cap.effective.provider_name }}</b> · <code class="font-mono">{{ cap.effective.model }}</code>
                <span v-if="Object.keys(cap.effective.params || {}).length" class="text-ink-400">
                  （{{ Object.entries(cap.effective.params).map(([k, v]) => `${PARAM_LABELS[k] || k}=${v}`).join('，') }}）
                </span>
              </p>
              <p v-else class="mt-2 text-xs text-ink-400">{{ t("aiSettings.尚未绑定_1sz2tv") }}</p>
            </div>

            <div class="flex items-center gap-2 shrink-0">
              <button class="btn-ghost text-sm" :disabled="!cap.effective || capTesting === cap.key" @click="testCapability(cap)">
                {{ capTesting === cap.key ? '测试中…' : '测试' }}
              </button>
              <button class="btn-secondary text-sm" @click="editingCap === cap.key ? closeCapEditor() : openCapEditor(cap)">
                {{ editingCap === cap.key ? '收起' : cap.effective ? '改绑' : '配置' }}
              </button>
              <button v-if="cap.binding" class="text-xs text-red-600 hover:underline px-1" @click="unbindCapability(cap)">
                {{ t("aiSettings.解绑_o5e6") }}
              </button>
            </div>
          </div>

          <!-- 测试结果 -->
          <div
            v-if="capTestResult[cap.key]"
            class="mt-3 text-xs rounded-lg px-3 py-2 border"
            :class="capTestResult[cap.key].ok ? 'bg-emerald-50 border-emerald-200 text-emerald-800' : 'bg-red-50 border-red-200 text-red-700'"
          >
            <div class="font-medium">
              {{ capTestResult[cap.key].ok ? '调用成功' : '调用失败' }}
              <span v-if="capTestResult[cap.key].latency_ms" class="font-normal text-ink-500">· {{ capTestResult[cap.key].latency_ms }} ms</span>
            </div>
            <div class="mt-0.5 break-all">{{ capTestResult[cap.key].detail }}</div>
            <pre v-if="capTestResult[cap.key].result" class="mt-1.5 whitespace-pre-wrap break-all font-mono text-[11px] bg-white/60 rounded p-2">{{ JSON.stringify(capTestResult[cap.key].result, null, 1) }}</pre>
          </div>

          <!-- 编辑面板 -->
          <div v-if="editingCap === cap.key" class="mt-4 pt-4 border-t border-ink-200 space-y-3">
            <div class="grid gap-3 sm:grid-cols-2">
              <div>
                <label class="block text-sm font-medium mb-1">{{ t("aiSettings.服务商_fhwnm") }}</label>
                <select v-model.number="capDraft.provider_id" class="input">
                  <option :value="null" disabled>{{ t("aiSettings.请选择_l72nr") }}</option>
                  <option v-for="p in enabledOptions" :key="p.id" :value="p.id">
                    {{ p.name }}{{ p.has_api_key ? '' : '（未填密钥）' }}
                  </option>
                </select>
                <p v-if="!enabledOptions.length" class="mt-1 text-xs text-amber-600">
                  {{ t("aiSettings.还没有可_h1x7rg") }}
                </p>
              </div>
              <div>
                <label class="block text-sm font-medium mb-1">{{ t("aiSettings.模型名_fyytf") }}</label>
                <input v-model="capDraft.model" class="input font-mono" :placeholder="t('aiSettings.如_1j4fd8')" />
              </div>
            </div>

            <div v-if="cap.param_specs.length" class="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
              <div v-for="spec in cap.param_specs" :key="spec.key">
                <label class="block text-sm font-medium mb-1">
                  {{ PARAM_LABELS[spec.key] || spec.key }}
                  <span v-if="spec.min !== null || spec.max !== null" class="text-xs text-ink-400 font-normal">
                    ({{ spec.min ?? '−∞' }} ~ {{ spec.max ?? '+∞' }})
                  </span>
                </label>
                <select v-if="spec.enum.length" v-model="capDraft.params[spec.key]" class="input">
                  <option value="">{{ t("aiSettings.默认_rs98") }}</option>
                  <option v-for="opt in spec.enum" :key="opt" :value="opt">{{ opt }}</option>
                </select>
                <input
                  v-else-if="spec.type === 'int' || spec.type === 'float'"
                  v-model.number="capDraft.params[spec.key]"
                  type="number"
                  :step="spec.type === 'float' ? 0.1 : 1"
                  :min="spec.min ?? undefined"
                  :max="spec.max ?? undefined"
                  class="input"
                  :placeholder="t('aiSettings.默认_rs98')"
                />
                <input v-else v-model="capDraft.params[spec.key]" class="input" :placeholder="t('aiSettings.默认_rs98')" />
              </div>
            </div>

            <div class="flex items-center gap-2">
              <button class="btn-primary text-sm" :disabled="capSaving" @click="saveCapability(cap)">
                {{ capSaving ? '保存中…' : '保存绑定' }}
              </button>
              <button class="btn-ghost text-sm" @click="closeCapEditor">{{ t("aiSettings.cancel") }}</button>
              <span class="text-xs text-ink-400">{{ t("aiSettings.参数留空_jram8y") }}</span>
            </div>
          </div>
        </div>
      </div>

      <!-- ================= 服务商 ================= -->
      <div v-else class="space-y-4">
        <div class="flex items-center justify-between">
          <p class="text-sm text-ink-500">
            {{ t("aiSettings.一家服务_31mprz") }}
          </p>
          <button class="btn-primary text-sm" @click="showForm ? (showForm = false) : openCreate()">
            {{ showForm ? '取消' : '+ 添加服务商' }}
          </button>
        </div>

        <!-- 表单 -->
        <form v-if="showForm" class="card space-y-3" @submit.prevent="saveProvider">
          <h3 class="font-semibold">{{ editingProvider ? `编辑：${editingProvider.name}` : '添加服务商' }}</h3>

          <div v-if="!editingProvider && presets.length" class="flex flex-wrap gap-2">
            <span class="text-xs text-ink-500 self-center">{{ t("aiSettings.快速填充_12fjle") }}</span>
            <button
              v-for="p in presets"
              :key="p.slug"
              type="button"
              class="text-xs px-2.5 py-1 rounded-full border border-ink-200 hover:bg-ink-50"
              :title="p.note"
              @click="applyPreset(p.slug)"
            >
              {{ p.name }}
            </button>
          </div>

          <div class="grid gap-3 sm:grid-cols-2">
            <div>
              <label class="block text-sm font-medium mb-1">{{ t("aiSettings.显示名称_deexj3") }}</label>
              <input v-model="form.name" class="input" :placeholder="t('aiSettings.如_fzxqw')" required />
            </div>
            <div>
              <label class="block text-sm font-medium mb-1">
                {{ t("aiSettings.标识_zgva8c") }}
                <span class="text-xs text-ink-400 font-normal">{{ t("aiSettings.text_1q57j9") }}</span>
              </label>
              <input v-model="form.slug" class="input font-mono" :disabled="!!editingProvider" placeholder="dashscope" />
            </div>
          </div>

          <div>
            <label class="block text-sm font-medium mb-1">{{ t("aiSettings.接口地址_17z8bj") }}</label>
            <input v-model="form.base_url" class="input font-mono" placeholder="https://api.example.com/v1" required />
            <p class="mt-1 text-xs text-ink-400">{{ t("aiSettings.填到_fhnp") }} <code>/v1</code> {{ t("aiSettings.为止_1ouy1d") }} <code>/chat/completions</code></p>
          </div>

          <div>
            <label class="block text-sm font-medium mb-1">
              {{ t("aiSettings.text_w1oo79") }}
              <span v-if="editingProvider" class="text-xs text-ink-400 font-normal">
                （当前 {{ editingProvider.api_key_hint || '未配置' }}，留空表示不修改）
              </span>
            </label>
            <input
              v-model="form.api_key"
              type="password"
              class="input font-mono"
              :placeholder="editingProvider ? '留空则不修改' : 'sk-...'"
              autocomplete="new-password"
            />
          </div>

          <div class="grid gap-3 sm:grid-cols-3">
            <div>
              <label class="block text-sm font-medium mb-1">{{ t("aiSettings.协议_exq7") }}</label>
              <select v-model="form.kind" class="input">
                <option v-for="k in PROVIDER_KINDS" :key="k.value" :value="k.value">{{ k.label }}</option>
              </select>
            </div>
            <div>
              <label class="block text-sm font-medium mb-1">{{ t("aiSettings.超时_1y1biz") }}</label>
              <input v-model.number="form.timeout_seconds" type="number" min="5" max="600" class="input" />
            </div>
            <div>
              <label class="block text-sm font-medium mb-1">{{ t("aiSettings.失败重试_bud8zg") }}</label>
              <input v-model.number="form.max_retries" type="number" min="0" max="5" class="input" />
            </div>
          </div>

          <div>
            <label class="block text-sm font-medium mb-1">
              {{ t("aiSettings.自定义请_1qfb71") }}
              <span class="text-xs text-ink-400 font-normal">{{ t("aiSettings.text_5ygo4n") }} <code>Key: Value</code>）</span>
            </label>
            <textarea v-model="form.extra_headers_text" rows="2" class="input font-mono" placeholder="X-Api-Version: 2024-01-01"></textarea>
          </div>

          <div>
            <label class="block text-sm font-medium mb-1">{{ t("aiSettings.备注_fqo1") }}</label>
            <input v-model="form.remark" class="input" :placeholder="t('aiSettings.用途说明_v0ocv3')" />
          </div>

          <label class="flex items-center gap-2 text-sm">
            <input v-model="form.enabled" type="checkbox" class="rounded border-ink-300" />
            {{ t("aiSettings.enable") }}
          </label>

          <div class="flex items-center gap-2 pt-1">
            <button type="submit" class="btn-primary text-sm" :disabled="formSaving">
              {{ formSaving ? '保存中…' : '保存' }}
            </button>
            <button type="button" class="btn-ghost text-sm" @click="showForm = false">{{ t("aiSettings.cancel") }}</button>
          </div>
        </form>

        <!-- 列表 -->
        <div v-if="!providers.length" class="card text-center text-ink-400 py-12">
          {{ t("aiSettings.还没有添_1q4xg4") }}
        </div>
        <div v-else class="card p-0 overflow-hidden">
          <div class="overflow-x-auto">
            <table class="w-full text-sm">
              <thead class="bg-ink-50 border-b border-ink-200">
                <tr class="text-left text-ink-500">
                  <th class="px-4 py-3 font-medium">{{ t("aiSettings.服务商_fhwnm") }}</th>
                  <th class="px-4 py-3 font-medium">{{ t("aiSettings.接口地址_cx5rhq") }}</th>
                  <th class="px-4 py-3 font-medium">{{ t("aiSettings.密钥_gfbz") }}</th>
                  <th class="px-4 py-3 font-medium">{{ t("aiSettings.绑定能力_gdv3s7") }}</th>
                  <th class="px-4 py-3 font-medium">{{ t("aiSettings.status") }}</th>
                  <th class="px-4 py-3 font-medium text-right">{{ t("aiSettings.actions") }}</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="p in providers" :key="p.id" class="border-b border-ink-100 last:border-0 align-top">
                  <td class="px-4 py-3">
                    <div class="font-medium text-ink-900">{{ p.name }}</div>
                    <div class="text-xs text-ink-400 font-mono">{{ p.slug }} · {{ p.kind }}</div>
                  </td>
                  <td class="px-4 py-3">
                    <code class="text-xs font-mono text-ink-600 break-all">{{ p.base_url }}</code>
                  </td>
                  <td class="px-4 py-3">
                    <code v-if="p.has_api_key" class="text-xs font-mono text-ink-500">{{ p.api_key_hint }}</code>
                    <span v-else class="text-xs text-amber-600">{{ t("aiSettings.未配置_fte97") }}</span>
                  </td>
                  <td class="px-4 py-3">
                    <div class="flex flex-wrap gap-1">
                      <span
                        v-for="c in p.bound_capabilities"
                        :key="c"
                        class="text-xs px-1.5 py-0.5 rounded bg-ink-100 text-ink-600 font-mono"
                      >{{ c }}</span>
                      <span v-if="!p.bound_capabilities.length" class="text-xs text-ink-400">—</span>
                    </div>
                  </td>
                  <td class="px-4 py-3">
                    <div class="flex items-center gap-1.5">
                      <span class="w-1.5 h-1.5 rounded-full" :class="p.enabled ? 'bg-emerald-500' : 'bg-ink-300'"></span>
                      <span class="text-xs" :class="p.enabled ? 'text-ink-700' : 'text-ink-400'">{{ p.enabled ? '启用' : '停用' }}</span>
                    </div>
                    <div v-if="p.last_test_at" class="mt-1 text-xs" :class="p.last_test_ok ? 'text-emerald-600' : 'text-red-600'">
                      {{ p.last_test_ok ? '上次测试通过' : '上次测试失败' }}
                      <span class="text-ink-400">· {{ fmtTime(p.last_test_at) }}</span>
                    </div>
                    <div v-if="providerTestResult[p.id]" class="mt-1 text-xs break-all" :class="providerTestResult[p.id].ok ? 'text-emerald-600' : 'text-red-600'">
                      {{ providerTestResult[p.id].detail }}
                      <span v-if="providerTestResult[p.id].latency_ms" class="text-ink-400">（{{ providerTestResult[p.id].latency_ms }}ms）</span>
                    </div>
                  </td>
                  <td class="px-4 py-3 text-right whitespace-nowrap">
                    <button class="text-xs text-ink-700 hover:underline mr-2" :disabled="testingProvider === p.id" @click="testProvider(p)">
                      {{ testingProvider === p.id ? '测试中…' : '测试' }}
                    </button>
                    <button class="text-xs text-ink-700 hover:underline mr-2" @click="openEdit(p)">{{ t("aiSettings.edit") }}</button>
                    <button class="text-xs text-red-600 hover:underline" @click="removeProvider(p)">{{ t("aiSettings.delete") }}</button>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>

        <p class="text-xs text-ink-400">
          {{ t("aiSettings.提示_kxl16j") }}
        </p>
      </div>
    </main>
  </div>
</template>
