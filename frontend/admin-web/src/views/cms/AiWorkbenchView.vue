<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { api } from '@/lib/api'
import { useAuthStore } from '@/stores/auth'

interface ContentType { id: number; key: string; name: string; translatable?: boolean }
interface Language { code: string; name: string; flag?: string; is_default: boolean; enabled: boolean }
interface EntryRow { id: number; title: string; slug?: string; status: string }

interface Draft {
  content_type_id: number
  content_type_key?: string
  title: string
  slug?: string
  content: { summary?: string; body?: string }
  custom_fields: Record<string, any>
  seo: Record<string, any>
  dropped_fields?: string[]
  _meta?: { model?: string; tokens_in?: number; tokens_out?: number }
}

interface Hit {
  entry_id: number
  title: string
  slug?: string
  score: number
  vector_score: number
  keyword_score: number
  snippet?: string
  status?: string
}

type Tab = 'draft' | 'translate' | 'seo' | 'similar'

const router = useRouter()

const tab = ref<Tab>('draft')
const aiUnavailable = ref(false)
const errorMsg = ref('')
const notice = ref('')

const contentTypes = ref<ContentType[]>([])
const languages = ref<Language[]>([])
const entries = ref<EntryRow[]>([])

const ctId = ref<number | null>(null)
const entryId = ref<number | null>(null)
const entryFilter = ref('')

const busy = ref(false)

// 流式起草状态：正文逐段透出，done 后落到 draft
interface StreamState {
  title: string
  slug: string
  body: string
  phase: 'connecting' | 'writing' | 'enriching'
}
const streaming = ref<StreamState | null>(null)
let abortDraft: AbortController | null = null

// 起草
const brief = ref('')
const draftLang = ref('zh-CN')
const draft = ref<Draft | null>(null)
const savedEntryId = ref<number | null>(null)

// 素材直入：附件解析成文本后追加到 brief
interface AttachedFile {
  name: string
  kind: string
  chars: number
  warnings: string[]
}
const attached = ref<AttachedFile[]>([])
const ingesting = ref(false)
const ingestError = ref('')
const dragOver = ref(false)
const fileInput = ref<HTMLInputElement | null>(null)

const KIND_LABEL: Record<string, string> = {
  pdf: 'PDF',
  docx: 'Word',
  xlsx: 'Excel',
  image: '图片',
  video: '视频',
  html: '网页',
  text: '文本',
}

// 翻译
const targetLangs = ref<string[]>([])
const overwrite = ref(false)
const translateResult = ref<Record<string, any> | null>(null)

// SEO
const seoResult = ref<Record<string, any> | null>(null)

// 相似
const similarHits = ref<Hit[]>([])
const searchQ = ref('')
const searchHits = ref<Hit[]>([])

const currentCt = computed(() => contentTypes.value.find((c) => c.id === ctId.value) || null)
const translatableLangs = computed(() => languages.value.filter((l) => l.enabled && !l.is_default))
const filteredEntries = computed(() => {
  const q = entryFilter.value.trim().toLowerCase()
  if (!q) return entries.value
  return entries.value.filter((e) => e.title.toLowerCase().includes(q))
})
const canDraft = computed(() => !!ctId.value && brief.value.trim().length >= 4 && !busy.value)
const canEntryAction = computed(() => !!entryId.value && !busy.value)

function errText(e: any): string {
  if (e?.response?.status === 503) {
    aiUnavailable.value = true
    return e.response?.data?.detail || 'AI 未配置'
  }
  const d = e?.response?.data?.detail
  if (Array.isArray(d)) return d.map((x: any) => x.msg || JSON.stringify(x)).join('; ')
  return d || e?.message || '请求失败'
}

async function loadBase() {
  try {
    const [ct, lg] = await Promise.all([
      api.get('/api/v1/cms/content-types'),
      api.get('/api/v1/cms/languages'),
    ])
    contentTypes.value = (ct.data.items || ct.data || []).filter((c: any) => c.status !== 'archived')
    languages.value = lg.data.items || []
    if (contentTypes.value.length && !ctId.value) ctId.value = contentTypes.value[0].id
  } catch (e: any) {
    errorMsg.value = errText(e)
  }
}

async function loadEntries() {
  if (!ctId.value) return
  entries.value = []
  entryId.value = null
  try {
    const { data } = await api.get('/api/v1/cms/entries', {
      params: { content_type_id: ctId.value, page: 1, page_size: 100 },
    })
    entries.value = data.items || []
  } catch (e: any) {
    if (e?.response?.status !== 404) errorMsg.value = errText(e)
  }
}

function parseSseEvent(raw: string): { event: string; data: any } | null {
  let event = 'message'
  let data = ''
  for (const line of raw.split('\n')) {
    if (line.startsWith('event:')) event = line.slice(6).trim()
    else if (line.startsWith('data:')) data += line.slice(5).trim()
  }
  if (!data) return null
  try {
    return { event, data: JSON.parse(data) }
  } catch {
    return null
  }
}

function handleStreamEvent(event: string, data: any) {
  if (event === 'meta') {
    if (streaming.value) {
      streaming.value.title = data.title || ''
      streaming.value.slug = data.slug || ''
      streaming.value.phase = 'writing'
    }
  } else if (event === 'delta') {
    if (streaming.value) streaming.value.body += data.t || ''
  } else if (event === 'extra') {
    if (streaming.value) {
      streaming.value.phase = 'enriching'
    }
  } else if (event === 'done') {
    draft.value = data as Draft
    streaming.value = null
  } else if (event === 'error') {
    errorMsg.value = data.detail || '生成失败'
    streaming.value = null
  }
}

function pickFiles() {
  fileInput.value?.click()
}

function onFileChange(e: Event) {
  const input = e.target as HTMLInputElement
  const files = Array.from(input.files || [])
  input.value = '' // 允许重复选同一个文件
  if (files.length) void ingestFiles(files)
}

function onDrop(e: DragEvent) {
  dragOver.value = false
  const files = Array.from(e.dataTransfer?.files || [])
  if (files.length) void ingestFiles(files)
}

async function ingestFiles(files: File[]) {
  if (ingesting.value) return
  ingesting.value = true
  ingestError.value = ''
  try {
    const fd = new FormData()
    files.slice(0, 5).forEach((f) => fd.append('files', f))
    // 解析可能是「视频抽帧 + 视觉识别」，axios 默认 15s 必然超时
    const { data } = await api.post('/api/v1/cms/ai/ingest/extract', fd, { timeout: 300000 })
    for (const r of data.results || []) {
      attached.value.push({
        name: r.filename,
        kind: r.kind,
        chars: r.chars,
        warnings: r.warnings || [],
      })
    }
    if (data.brief) {
      brief.value = brief.value.trim() ? `${brief.value.trim()}\n\n${data.brief}` : data.brief
    }
    const fails = (data.failures || []).map((f: any) => `${f.filename}：${f.error}`)
    if (fails.length) {
      ingestError.value = fails.join('；')
    } else if ((data.results || []).length) {
      notice.value = `已解析 ${data.results.length} 个素材，共 ${data.chars} 字`
    }
  } catch (e: any) {
    ingestError.value = errText(e)
  } finally {
    ingesting.value = false
  }
}

function resetBrief() {
  brief.value = ''
  attached.value = []
  ingestError.value = ''
}

async function doDraft() {
  if (!canDraft.value) return
  busy.value = true
  errorMsg.value = ''
  notice.value = ''
  draft.value = null
  savedEntryId.value = null
  streaming.value = { title: '', slug: '', body: '', phase: 'connecting' }
  const auth = useAuthStore()
  const base = import.meta.env.VITE_API_BASE_URL || ''
  abortDraft = new AbortController()
  try {
    // axios 默认 15s 超时接不住 40s 的生成，起草走原生 fetch + SSE
    const resp = await fetch(`${base}/api/v1/cms/ai/entries/draft/stream`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        ...(auth.token ? { Authorization: `Bearer ${auth.token}` } : {}),
      },
      body: JSON.stringify({
        content_type_id: ctId.value,
        brief: brief.value.trim(),
        lang: draftLang.value,
      }),
      signal: abortDraft.signal,
    })
    if (!resp.ok || !resp.body) {
      let detail = `HTTP ${resp.status}`
      try {
        const j = await resp.json()
        detail = j.detail || detail
      } catch {
        /* 非 JSON 错误体 */
      }
      if (resp.status === 503) aiUnavailable.value = true
      throw new Error(detail)
    }
    const reader = resp.body.getReader()
    const decoder = new TextDecoder()
    let buf = ''
    for (;;) {
      const { done, value } = await reader.read()
      if (done) break
      buf += decoder.decode(value, { stream: true })
      let idx: number
      while ((idx = buf.indexOf('\n\n')) >= 0) {
        const raw = buf.slice(0, idx)
        buf = buf.slice(idx + 2)
        const ev = parseSseEvent(raw)
        if (ev) handleStreamEvent(ev.event, ev.data)
      }
    }
  } catch (e: any) {
    if (e?.name !== 'AbortError') errorMsg.value = e?.message || '生成失败'
  } finally {
    streaming.value = null
    busy.value = false
    abortDraft = null
  }
}

function cancelDraft() {
  abortDraft?.abort()
}

async function saveDraft() {
  if (!draft.value) return
  busy.value = true
  errorMsg.value = ''
  try {
    // 保存前查重：命中高相似则二次确认，避免重复落库
    let dupTop: any = null
    try {
      const { data: dup } = await api.post('/api/v1/cms/ai/entries/dedup', {
        title: draft.value.title,
        content: draft.value.content || {},
        content_type_id: ctId.value,
      })
      if (dup.has_duplicate && dup.duplicates?.length) dupTop = dup.duplicates[0]
    } catch {
      /* 查重接口异常不阻断保存 */
    }
    if (dupTop) {
      const ok = window.confirm(
        `检测到与《${dupTop.title}》高度相似（相似度 ${dupTop.score}），可能重复内容。仍要保存为草稿吗？`
      )
      if (!ok) {
        busy.value = false
        return
      }
    }
    const { data } = await api.post('/api/v1/cms/ai/entries/draft/save', draft.value)
    savedEntryId.value = data.entry_id
    notice.value = `已保存为草稿条目：${data.title}`
    await loadEntries()
  } catch (e: any) {
    errorMsg.value = errText(e)
  } finally {
    busy.value = false
  }
}

async function doTranslate() {
  if (!canEntryAction.value || !targetLangs.value.length) return
  busy.value = true
  errorMsg.value = ''
  notice.value = ''
  translateResult.value = null
  try {
    const { data } = await api.post(`/api/v1/cms/ai/entries/${entryId.value}/translate`, {
      langs: targetLangs.value,
      overwrite: overwrite.value,
    })
    translateResult.value = data.results || {}
  } catch (e: any) {
    errorMsg.value = errText(e)
  } finally {
    busy.value = false
  }
}

async function doSeo() {
  if (!canEntryAction.value) return
  busy.value = true
  errorMsg.value = ''
  notice.value = ''
  seoResult.value = null
  try {
    const { data } = await api.post(`/api/v1/cms/ai/entries/${entryId.value}/seo`, { lang: 'zh-CN' })
    seoResult.value = data.seo || data
  } catch (e: any) {
    errorMsg.value = errText(e)
  } finally {
    busy.value = false
  }
}

async function doSimilar() {
  if (!canEntryAction.value) return
  busy.value = true
  errorMsg.value = ''
  similarHits.value = []
  try {
    const { data } = await api.get(`/api/v1/cms/ai/entries/${entryId.value}/similar`, {
      params: { limit: 8 },
    })
    similarHits.value = data.results || []
  } catch (e: any) {
    errorMsg.value = errText(e)
  } finally {
    busy.value = false
  }
}

async function doSearch() {
  const q = searchQ.value.trim()
  if (!q) return
  busy.value = true
  errorMsg.value = ''
  searchHits.value = []
  try {
    const { data } = await api.get('/api/v1/cms/ai/search', {
      params: { q, content_type_id: ctId.value ?? undefined, limit: 10 },
    })
    searchHits.value = data.results || []
  } catch (e: any) {
    errorMsg.value = errText(e)
  } finally {
    busy.value = false
  }
}

function toggleLang(code: string) {
  const i = targetLangs.value.indexOf(code)
  if (i >= 0) targetLangs.value.splice(i, 1)
  else targetLangs.value.push(code)
}

function openEntry(id: number) {
  router.push({ name: 'cms-entry-edit', params: { id } })
}

function pretty(v: any): string {
  try {
    return JSON.stringify(v, null, 2)
  } catch {
    return String(v)
  }
}

watch(ctId, () => {
  loadEntries()
  draft.value = null
  similarHits.value = []
  searchHits.value = []
})

onMounted(async () => {
  await loadBase()
  await loadEntries()
})

onUnmounted(() => {
  abortDraft?.abort()
})
</script>

<template>
  <div class="min-h-screen bg-ink-50">
    <header class="bg-white border-b border-ink-200">
      <div class="max-w-7xl mx-auto px-6 h-14 flex items-center gap-4">
        <router-link to="/" class="text-sm text-ink-500 hover:text-ink-900">← Dashboard</router-link>
        <span class="font-semibold">AI 内容工作台</span>
        <span class="text-xs text-ink-400">起草 · 翻译 · SEO · 相似推荐</span>
      </div>
    </header>

    <main class="max-w-7xl mx-auto px-6 py-8">
      <div
        v-if="aiUnavailable"
        class="mb-6 text-sm text-amber-800 bg-amber-50 border border-amber-200 rounded-xl px-4 py-3"
      >
        AI 尚未配置。
        <router-link to="/cms/ai-settings" class="font-medium underline">去 AI 设置绑定服务商与密钥 →</router-link>
      </div>

      <p v-if="errorMsg" class="mb-4 text-sm text-red-600 bg-red-50 border border-red-200 rounded-xl px-4 py-2.5">
        {{ errorMsg }}
      </p>
      <p v-if="notice" class="mb-4 text-sm text-emerald-700 bg-emerald-50 border border-emerald-200 rounded-xl px-4 py-2.5">
        {{ notice }}
      </p>

      <!-- 全局：内容类型 -->
      <div class="card mb-6">
        <div class="flex flex-wrap items-end gap-4">
          <div class="min-w-[220px]">
            <label class="block text-xs font-medium text-ink-700">内容类型</label>
            <select v-model.number="ctId" class="input mt-1.5">
              <option :value="null" disabled>选择内容类型</option>
              <option v-for="c in contentTypes" :key="c.id" :value="c.id">
                {{ c.name }}（{{ c.key }}）
              </option>
            </select>
          </div>
          <div v-if="tab !== 'draft'" class="flex-1 min-w-[280px]">
            <label class="block text-xs font-medium text-ink-700">
              目标条目 <span class="text-ink-400 font-normal">（{{ filteredEntries.length }} 条）</span>
            </label>
            <div class="mt-1.5 flex gap-2">
              <input v-model="entryFilter" class="input" placeholder="按标题筛选…" />
              <select v-model.number="entryId" class="input w-64">
                <option :value="null" disabled>选择条目</option>
                <option v-for="e in filteredEntries" :key="e.id" :value="e.id">
                  #{{ e.id }} {{ e.title }}
                </option>
              </select>
            </div>
          </div>
        </div>
        <p v-if="!contentTypes.length" class="mt-3 text-xs text-ink-500">
          还没有内容类型。
          <router-link to="/cms/ai-builder" class="underline font-medium">用 AI 建模向导创建一个 →</router-link>
        </p>
      </div>

      <!-- Tabs -->
      <div class="flex items-center gap-1 mb-4">
        <button
          v-for="t in [
            { key: 'draft', label: 'AI 起草' },
            { key: 'translate', label: '批量翻译' },
            { key: 'seo', label: 'SEO 建议' },
            { key: 'similar', label: '相似 / 检索' },
          ]"
          :key="t.key"
          class="px-4 py-2 text-sm rounded-lg font-medium transition-colors"
          :class="tab === t.key ? 'bg-white text-ink-900 shadow-sm border border-ink-200' : 'text-ink-500 hover:text-ink-900'"
          @click="tab = t.key as Tab"
        >
          {{ t.label }}
        </button>
      </div>

      <!-- 起草 -->
      <div v-if="tab === 'draft'" class="grid grid-cols-1 lg:grid-cols-5 gap-6">
        <div class="lg:col-span-2 card h-fit">
          <h3 class="text-base font-semibold text-ink-900">给素材，AI 写草稿</h3>
          <p class="mt-1 text-xs text-ink-500 leading-relaxed">
            素材里没有的具体数字、客户名、日期，AI 不会编，会标「（待补充）」。
          </p>

          <div class="mt-4 flex items-center justify-between gap-2">
            <label class="text-xs font-medium text-ink-700">素材 / 大纲</label>
            <button
              v-if="brief"
              class="text-[11px] text-ink-400 hover:text-red-500"
              @click="resetBrief"
            >
              清空
            </button>
          </div>

          <!-- 素材直入：附件解析成文本后追加到下面素材框 -->
          <div
            class="mt-1.5 rounded-lg border border-dashed px-3 py-3 text-center cursor-pointer transition-colors"
            :class="dragOver ? 'border-emerald-400 bg-emerald-50' : 'border-ink-300 hover:border-ink-400'"
            @click="pickFiles"
            @dragover.prevent="dragOver = true"
            @dragleave.prevent="dragOver = false"
            @drop.prevent="onDrop"
          >
            <input
              ref="fileInput"
              type="file"
              multiple
              class="hidden"
              accept=".pdf,.docx,.xlsx,.xlsm,.png,.jpg,.jpeg,.webp,.gif,.bmp,.mp4,.mov,.webm,.txt,.md,.csv,.html,.htm"
              @change="onFileChange"
            />
            <p class="text-xs text-ink-600">
              <template v-if="ingesting">
                <span class="inline-block h-2 w-2 rounded-full bg-emerald-500 animate-pulse align-middle"></span>
                正在解析素材…
              </template>
              <template v-else>
                拖入 PDF / Word / Excel / 图片 / 视频，或
                <span class="font-medium text-ink-900 underline">点击选择</span>
              </template>
            </p>
            <p class="mt-1 text-[11px] text-ink-400">
              扫描件自动 OCR，视频抽 3 帧识别 · 单个 ≤ 20MB · 一次最多 5 个
            </p>
          </div>

          <div v-if="attached.length" class="mt-2 flex flex-wrap gap-1.5">
            <span
              v-for="(f, i) in attached"
              :key="i"
              class="inline-flex items-center gap-1 rounded-md bg-ink-100 px-2 py-1 text-[11px] text-ink-700"
              :title="f.warnings.join('；')"
            >
              {{ KIND_LABEL[f.kind] || f.kind }} · {{ f.name }} · {{ f.chars }} 字
            </span>
          </div>
          <p v-if="ingestError" class="mt-1.5 text-[11px] text-red-500">{{ ingestError }}</p>

          <textarea
            v-model="brief"
            rows="9"
            class="input mt-1.5 resize-y"
            placeholder="例：介绍 DN100 不锈钢法兰球阀，用于化工管道，工作压力 1.6MPa，材质 304，连接方式法兰，适用介质酸碱液体。客户反馈密封性好、维护方便。"
          ></textarea>

          <label class="block mt-3 text-xs font-medium text-ink-700">输出语言</label>
          <select v-model="draftLang" class="input mt-1.5">
            <option value="zh-CN">简体中文</option>
            <option v-for="l in languages" :key="l.code" :value="l.code">{{ l.name }}（{{ l.code }}）</option>
          </select>

          <div class="flex items-center justify-between gap-3 mt-4">
            <button class="btn-primary flex-1" :disabled="!canDraft" @click="doDraft">
              {{ busy ? '正在生成…' : '生成草稿' }}
            </button>
            <button v-if="busy && streaming" class="btn-outline shrink-0" @click="cancelDraft">取消</button>
          </div>
        </div>

        <div class="lg:col-span-3">
          <!-- 流式生成中：标题先到，正文逐段长出来 -->
          <div v-if="streaming" class="card">
            <div class="flex items-center gap-2">
              <span class="inline-block h-2 w-2 rounded-full bg-emerald-500 animate-pulse"></span>
              <h3 class="text-sm font-semibold text-ink-900">
                {{
                  streaming.phase === 'connecting'
                    ? 'AI 正在构思…'
                    : streaming.phase === 'writing'
                      ? '正在写作…'
                      : '正在补充摘要与字段…'
                }}
              </h3>
            </div>
            <template v-if="streaming.title">
              <h4 class="mt-3 text-lg font-semibold text-ink-900">{{ streaming.title }}</h4>
              <p v-if="streaming.slug" class="mt-1 text-xs font-mono text-ink-400">/{{ streaming.slug }}</p>
            </template>
            <pre
              v-if="streaming.body"
              class="mt-3 text-xs text-ink-700 bg-ink-50 border border-ink-200 rounded-lg p-3 whitespace-pre-wrap break-words max-h-96 overflow-auto"
              >{{ streaming.body }}▌</pre
            >
            <p v-else class="mt-6 text-xs text-ink-400">正在等模型出第一句…（约 5~15 秒）</p>
          </div>

          <div v-else-if="!draft" class="card flex flex-col items-center justify-center py-20 text-center">
            <div class="text-4xl">✍️</div>
            <p class="mt-3 text-sm font-medium text-ink-700">还没有草稿</p>
            <p class="mt-1 text-xs text-ink-400 max-w-xs leading-relaxed">
              左侧粘贴素材，AI 按当前内容类型的字段结构生成草稿。生成后是草稿状态，需要人工过一遍再发布。
            </p>
          </div>

          <div v-else class="space-y-4">
            <div v-if="savedEntryId" class="card border-emerald-200 bg-emerald-50">
              <p class="text-sm font-medium text-emerald-800">已保存为草稿条目 #{{ savedEntryId }}</p>
              <button class="btn-outline mt-3" @click="openEntry(savedEntryId)">打开条目编辑 →</button>
            </div>

            <div class="card">
              <div class="flex items-start justify-between gap-3">
                <div>
                  <p class="text-xs text-ink-400">标题</p>
                  <h3 class="mt-1 text-lg font-semibold text-ink-900">{{ draft.title }}</h3>
                  <p v-if="draft.slug" class="mt-1 text-xs font-mono text-ink-400">/{{ draft.slug }}</p>
                </div>
                <span class="shrink-0 px-2 py-1 rounded-full text-xs bg-ink-100 text-ink-600">草稿</span>
              </div>

              <div v-if="draft.dropped_fields?.length" class="mt-3 text-xs text-amber-800 bg-amber-50 border border-amber-200 rounded-lg px-3 py-2">
                模型多给了这些字段，但内容类型里没有定义，已丢弃：<code class="font-mono">{{ draft.dropped_fields.join(', ') }}</code>
              </div>

              <div v-if="draft.content?.summary" class="mt-4">
                <p class="text-xs font-medium text-ink-700">摘要</p>
                <p class="mt-1 text-sm text-ink-600 leading-relaxed">{{ draft.content.summary }}</p>
              </div>

              <div v-if="draft.content?.body" class="mt-4">
                <p class="text-xs font-medium text-ink-700">正文</p>
                <pre class="mt-1 text-xs text-ink-700 bg-ink-50 border border-ink-200 rounded-lg p-3 whitespace-pre-wrap break-words max-h-72 overflow-auto">{{ draft.content.body }}</pre>
              </div>

              <div v-if="Object.keys(draft.custom_fields || {}).length" class="mt-4">
                <p class="text-xs font-medium text-ink-700">自定义字段</p>
                <table class="mt-1.5 w-full text-xs">
                  <tbody>
                    <tr v-for="(v, k) in draft.custom_fields" :key="k" class="border-b border-ink-100 last:border-0">
                      <td class="py-1.5 pr-3 font-mono text-ink-500 align-top w-40">{{ k }}</td>
                      <td class="py-1.5 text-ink-800 break-words">{{ Array.isArray(v) ? v.join('、') : (v ?? '—') }}</td>
                    </tr>
                  </tbody>
                </table>
              </div>

              <div v-if="draft.seo && Object.keys(draft.seo).length" class="mt-4">
                <p class="text-xs font-medium text-ink-700">SEO</p>
                <pre class="mt-1 text-xs text-ink-600 bg-ink-50 border border-ink-200 rounded-lg p-2.5 whitespace-pre-wrap break-words">{{ pretty(draft.seo) }}</pre>
              </div>

              <div class="mt-5 flex items-center gap-3">
                <button class="btn-primary" :disabled="busy || !!savedEntryId" @click="saveDraft">
                  {{ savedEntryId ? '已保存' : busy ? '保存中…' : '保存为草稿条目' }}
                </button>
                <span class="text-xs text-ink-400">落库后状态固定为 draft，不能直接发布</span>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- 翻译 -->
      <div v-if="tab === 'translate'" class="grid grid-cols-1 lg:grid-cols-5 gap-6">
        <div class="lg:col-span-2 card h-fit">
          <h3 class="text-base font-semibold text-ink-900">批量翻译</h3>
          <p class="mt-1 text-xs text-ink-500 leading-relaxed">
            JSON 结构与 key 保持不变，只翻译值；品牌名、型号、URL 原样保留。
          </p>

          <label class="block mt-4 text-xs font-medium text-ink-700">目标语言</label>
          <div v-if="!translatableLangs.length" class="mt-2 text-xs text-ink-500">
            没有可用目标语言。
            <router-link to="/cms/languages" class="underline">先去语言管理添加 →</router-link>
          </div>
          <div v-else class="mt-2 flex flex-wrap gap-2">
            <button
              v-for="l in translatableLangs"
              :key="l.code"
              class="px-3 py-1.5 rounded-lg text-xs border transition-colors"
              :class="targetLangs.includes(l.code) ? 'bg-ink-900 text-white border-ink-900' : 'bg-white text-ink-700 border-ink-200 hover:border-ink-400'"
              @click="toggleLang(l.code)"
            >
              {{ l.flag }} {{ l.name }}
            </button>
          </div>

          <label class="mt-4 inline-flex items-center gap-2 text-xs text-ink-700">
            <input v-model="overwrite" type="checkbox" class="rounded border-ink-300" />
            覆盖已存在的译文
          </label>

          <button
            class="btn-primary w-full mt-4"
            :disabled="!canEntryAction || !targetLangs.length"
            @click="doTranslate"
          >
            {{ busy ? '翻译中…' : `翻译到 ${targetLangs.length} 种语言` }}
          </button>
        </div>

        <div class="lg:col-span-3 card">
          <h3 class="text-sm font-semibold text-ink-900">结果</h3>
          <div v-if="!translateResult" class="py-16 text-center text-xs text-ink-400">
            选择条目与目标语言后开始翻译
          </div>
          <ul v-else class="mt-3 space-y-2">
            <li
              v-for="(r, lang) in translateResult"
              :key="lang"
              class="flex items-start gap-3 text-xs border border-ink-200 rounded-lg px-3 py-2.5"
            >
              <span class="shrink-0 font-mono text-ink-600">{{ lang }}</span>
              <span
                class="shrink-0 px-2 py-0.5 rounded-full"
                :class="r.ok ? 'bg-emerald-50 text-emerald-700' : 'bg-red-50 text-red-700'"
              >
                {{ r.ok ? '成功' : '失败' }}
              </span>
              <span class="text-ink-500 break-words">{{ r.ok ? (r.status || '已写入译文') : (r.error || '未知错误') }}</span>
            </li>
          </ul>
        </div>
      </div>

      <!-- SEO -->
      <div v-if="tab === 'seo'" class="grid grid-cols-1 lg:grid-cols-5 gap-6">
        <div class="lg:col-span-2 card h-fit">
          <h3 class="text-base font-semibold text-ink-900">SEO 元数据建议</h3>
          <p class="mt-1 text-xs text-ink-500 leading-relaxed">
            基于标题、正文与自定义字段生成。这里只给建议，不会覆盖条目现有 SEO。
          </p>
          <button class="btn-primary w-full mt-4" :disabled="!canEntryAction" @click="doSeo">
            {{ busy ? '生成中…' : '生成建议' }}
          </button>
        </div>
        <div class="lg:col-span-3 card">
          <h3 class="text-sm font-semibold text-ink-900">建议</h3>
          <div v-if="!seoResult" class="py-16 text-center text-xs text-ink-400">选择条目后生成</div>
          <dl v-else class="mt-3 space-y-3">
            <div v-for="(v, k) in seoResult" :key="k">
              <dt class="text-xs font-medium text-ink-500 font-mono">{{ k }}</dt>
              <dd class="mt-1 text-sm text-ink-800 leading-relaxed break-words">
                {{ Array.isArray(v) ? v.join('、') : v }}
              </dd>
            </div>
          </dl>
        </div>
      </div>

      <!-- 相似 / 检索 -->
      <div v-if="tab === 'similar'" class="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div class="card">
          <div class="flex items-center justify-between">
            <h3 class="text-sm font-semibold text-ink-900">与选中条目相似</h3>
            <button class="btn-ghost text-xs" :disabled="!canEntryAction" @click="doSimilar">查找相似</button>
          </div>
          <ul v-if="similarHits.length" class="mt-3 space-y-2">
            <li
              v-for="h in similarHits"
              :key="h.entry_id"
              class="border border-ink-200 rounded-lg px-3 py-2.5 hover:bg-ink-50 cursor-pointer"
              @click="openEntry(h.entry_id)"
            >
              <div class="flex items-center justify-between gap-2">
                <span class="text-sm font-medium text-ink-900 truncate">{{ h.title }}</span>
                <span class="shrink-0 text-xs font-mono text-ink-500">{{ (h.score * 100).toFixed(0) }}%</span>
              </div>
              <p v-if="h.snippet" class="mt-1 text-xs text-ink-500 line-clamp-2">{{ h.snippet }}</p>
              <p class="mt-1 text-xs text-ink-400">
                向量 {{ (h.vector_score * 100).toFixed(0) }}% · 关键词 {{ (h.keyword_score * 100).toFixed(0) }}%
              </p>
            </li>
          </ul>
          <p v-else class="py-14 text-center text-xs text-ink-400">选择条目后查找相似内容</p>
        </div>

        <div class="card">
          <div class="flex items-center justify-between gap-2">
            <h3 class="text-sm font-semibold text-ink-900">自然语言检索</h3>
          </div>
          <div class="mt-3 flex gap-2">
            <input
              v-model="searchQ"
              class="input"
              placeholder="例：耐高温的化工用阀门"
              @keyup.enter="doSearch"
            />
            <button class="btn-outline shrink-0" :disabled="!searchQ.trim() || busy" @click="doSearch">
              检索
            </button>
          </div>
          <ul v-if="searchHits.length" class="mt-3 space-y-2">
            <li
              v-for="h in searchHits"
              :key="h.entry_id"
              class="border border-ink-200 rounded-lg px-3 py-2.5 hover:bg-ink-50 cursor-pointer"
              @click="openEntry(h.entry_id)"
            >
              <div class="flex items-center justify-between gap-2">
                <span class="text-sm font-medium text-ink-900 truncate">{{ h.title }}</span>
                <span class="shrink-0 text-xs font-mono text-ink-500">{{ (h.score * 100).toFixed(0) }}%</span>
              </div>
              <p v-if="h.snippet" class="mt-1 text-xs text-ink-500 line-clamp-2">{{ h.snippet }}</p>
            </li>
          </ul>
          <p v-else class="py-14 text-center text-xs text-ink-400">
            {{ searchQ ? '输入后回车检索' : '向量 + 关键词混合检索当前内容类型' }}
          </p>
        </div>
      </div>
    </main>
  </div>
</template>
