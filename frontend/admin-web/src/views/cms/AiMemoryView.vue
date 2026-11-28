<script setup lang="ts">
import { useI18n } from 'vue-i18n'
const { t } = useI18n()
/**
 * AI 记忆页。
 *
 * 解决的问题：CMS 每次起草都是一次性交易 —— 同一个站，今天写的和上个月写的
 * 没有任何关联。术语写法飘、参数口径前后矛盾、同一个选题写三遍。
 *
 * 这里是记忆的「账本」：
 * 左边管记忆条目（什么被记住了），右边是「AI 实际吃到的原文」。
 *
 * 为什么要把预览放在主界面上：记忆配错最难排查 —— AI 输出怪怪的，你分不清
 * 是模型问题、提示词问题，还是记忆里混进了一条相反的指令。能直接读原文，
 * 排查就从「猜」变成「看」。
 */
import { computed, onMounted, ref } from 'vue'
import { api } from '@/lib/api'

interface MemoryItem {
  id: number
  scope: string
  scope_label: string
  key: string
  content: string
  weight: number
  enabled: boolean
  source: string
  status: string
  injection_count: number
  created_at?: string | null
}

interface ScopeStat {
  scope: string
  label: string
  count: number
}

interface Stats {
  approved: number
  pending: number
  injection_total: number
  by_scope: ScopeStat[]
  digests: number
  entries: number
  coverage: number
}

interface DigestItem {
  entry_id: number
  title: string
  digest: string
  topics: string[]
  built_at?: string | null
}

interface Preview {
  block: string
  injected: number
  truncated: number
  content_memory: number
  chars: number
}

const SCOPE_HINT: Record<string, string> = {
  brand: '语气、人称、价值主张。决定「像不像这家公司在说话」',
  fact: '产品参数、公司口径、业务边界。AI 说错就是事故，只能人工写',
  term: '统一写法。左边填规范说法，右边填易错写法或说明',
  ban: '禁止出现的词，以及该换成什么',
  style: '句式、结构、篇幅、标题写法',
  audience: '读者是谁、什么水平、关心什么',
}

const loading = ref(false)
const errorMsg = ref('')
const okMsg = ref('')
const busy = ref('')

const items = ref<MemoryItem[]>([])
const stats = ref<Stats | null>(null)
const scopes = ref<{ value: string; label: string }[]>([])

const preview = ref<Preview | null>(null)
const previewBusy = ref(false)
const budget = ref(2000)
const withContent = ref(true)

const digests = ref<DigestItem[]>([])
const digestOpen = ref(false)

// ---- 编辑弹窗 ----
const editorOpen = ref(false)
const draft = ref({
  id: null as number | null,
  scope: 'brand',
  key: '',
  content: '',
  weight: 70,
})

const approved = computed(() => items.value.filter((i) => i.status === 'approved'))
const pending = computed(() => items.value.filter((i) => i.status === 'pending'))

/** 按 scope 分组，顺序跟后端渲染顺序一致（权重高的类别在前） */
const grouped = computed(() => {
  const order = ['brand', 'fact', 'term', 'ban', 'style', 'audience']
  const map = new Map<string, MemoryItem[]>()
  for (const it of approved.value) {
    const list = map.get(it.scope) ?? []
    list.push(it)
    map.set(it.scope, list)
  }
  return order
    .filter((s) => map.has(s))
    .map((s) => ({ scope: s, label: map.get(s)![0].scope_label, items: map.get(s)! }))
})

/** 从来没被注入过的记忆：写了却没生效，最容易被忽略 */
const zombie = computed(() => approved.value.filter((i) => i.injection_count === 0))

async function load() {
  loading.value = true
  errorMsg.value = ''
  try {
    const { data } = await api.get('/api/v1/cms/ai/memory')
    items.value = data.items ?? []
    stats.value = data.stats
    scopes.value = data.scopes ?? []
  } catch (e: any) {
    errorMsg.value = e?.response?.data?.detail || e?.message || t("dashboard.loadFailed")
  } finally {
    loading.value = false
  }
}

async function loadPreview() {
  previewBusy.value = true
  try {
    const { data } = await api.get<Preview>('/api/v1/cms/ai/memory/preview', {
      params: { budget: budget.value, with_content: withContent.value },
    })
    preview.value = data
  } catch (e: any) {
    errorMsg.value = e?.response?.data?.detail || t("aiMemory.预览失败_jt50ig")
  } finally {
    previewBusy.value = false
  }
}

function openEditor(it?: MemoryItem, scope?: string) {
  if (it) {
    draft.value = {
      id: it.id,
      scope: it.scope,
      key: it.key,
      content: it.content,
      weight: it.weight,
    }
  } else {
    draft.value = {
      id: null,
      scope: scope || 'brand',
      key: '',
      content: '',
      weight: 70,
    }
  }
  errorMsg.value = ''
  okMsg.value = ''
  editorOpen.value = true
}

async function saveMemory() {
  if (!draft.value.content.trim()) {
    errorMsg.value = t("aiMemory.内容不能_lhkgdg")
    return
  }
  busy.value = 'save'
  errorMsg.value = ''
  okMsg.value = ''
  try {
    await api.post('/api/v1/cms/ai/memory', {
      id: draft.value.id,
      scope: draft.value.scope,
      key: draft.value.key.trim(),
      content: draft.value.content.trim(),
      weight: draft.value.weight,
      source: 'manual',
      status: 'approved',
    })
    editorOpen.value = false
    okMsg.value = '已保存，下次起草立刻生效'
    await load()
    await loadPreview()
  } catch (e: any) {
    errorMsg.value = e?.response?.data?.detail || t("aiMemory.saveFailed")
  } finally {
    busy.value = ''
  }
}

async function setStatus(it: MemoryItem, status: string) {
  busy.value = `s-${it.id}`
  errorMsg.value = ''
  try {
    await api.patch(`/api/v1/cms/ai/memory/${it.id}`, { status })
    await load()
    await loadPreview()
  } catch (e: any) {
    errorMsg.value = e?.response?.data?.detail || t("aiMemory.操作失败_d1rj43")
  } finally {
    busy.value = ''
  }
}

async function toggleEnabled(it: MemoryItem) {
  busy.value = `e-${it.id}`
  try {
    await api.patch(`/api/v1/cms/ai/memory/${it.id}`, { enabled: !it.enabled })
    await load()
    await loadPreview()
  } catch (e: any) {
    errorMsg.value = e?.response?.data?.detail || t("aiMemory.操作失败_d1rj43")
  } finally {
    busy.value = ''
  }
}

async function removeMemory(it: MemoryItem) {
  if (!confirm(`删除这条记忆？\n\n${it.content.slice(0, 80)}`)) return
  busy.value = `d-${it.id}`
  try {
    await api.delete(`/api/v1/cms/ai/memory/${it.id}`)
    okMsg.value = t("aiMemory.已删除_e65yu")
    await load()
    await loadPreview()
  } catch (e: any) {
    errorMsg.value = e?.response?.data?.detail || t("aiMemory.删除失败_azdahk")
  } finally {
    busy.value = ''
  }
}

async function approveAll() {
  busy.value = 'approve-all'
  try {
    for (const p of pending.value) {
      await api.patch(`/api/v1/cms/ai/memory/${p.id}`, { status: 'approved' })
    }
    okMsg.value = `已通过 ${pending.value.length} 条`
    await load()
    await loadPreview()
  } catch (e: any) {
    errorMsg.value = e?.response?.data?.detail || t("aiMemory.操作失败_d1rj43")
  } finally {
    busy.value = ''
  }
}

async function distill() {
  busy.value = 'distill'
  errorMsg.value = ''
  okMsg.value = ''
  try {
    const { data } = await api.post(
      '/api/v1/cms/ai/memory/distill',
      {},
      { params: { sample: 12 }, timeout: 300_000 },
    )
    if (!data.ok) {
      errorMsg.value = data.reason || t("aiMemory.样本不足_dkp9sr")
    } else if (!data.created) {
      okMsg.value = `已分析 ${data.sample} 篇，没有新的可提炼项（已有建议未处理）`
    } else {
      okMsg.value = `已提炼 ${data.created} 条，在下方「待审」里确认后才会生效`
    }
    await load()
  } catch (e: any) {
    errorMsg.value = e?.response?.data?.detail || t("aiMemory.提炼失败_d25yww")
  } finally {
    busy.value = ''
  }
}

async function rebuildDigests() {
  busy.value = 'rebuild'
  errorMsg.value = ''
  okMsg.value = ''
  try {
    // 条数多时一批要跑几分钟，默认 15s 超时接不住
    const { data } = await api.post(
      '/api/v1/cms/ai/memory/digests/rebuild',
      {},
      { params: { limit: 40 }, timeout: 600_000 },
    )
    okMsg.value = `扫描 ${data.scanned} 篇，新索引 ${data.built} 篇，跳过 ${data.skipped}，失败 ${data.failed}`
    await load()
    if (digestOpen.value) await loadDigests()
  } catch (e: any) {
    errorMsg.value = e?.response?.data?.detail || t("aiMemory.重建失败_isdokh")
  } finally {
    busy.value = ''
  }
}

async function loadDigests() {
  try {
    const { data } = await api.get('/api/v1/cms/ai/memory/digests', {
      params: { limit: 60 },
    })
    digests.value = data.items ?? []
  } catch {
    digests.value = []
  }
}

async function toggleDigests() {
  digestOpen.value = !digestOpen.value
  if (digestOpen.value && !digests.value.length) await loadDigests()
}

// ---------------------------------------------------------------- 会话记忆
// 站点记忆是「全站通用的规矩」，会话记忆是「这一篇稿子的来龙去脉」。
// 两者用途不同：调性错了改站点记忆；这篇的临时要求（别提前几版的结论）
// 写到会话里，不会污染其他文章。

interface SessionItem {
  id: number
  entry_id: number | null
  title: string
  turn_count: number
  updated_at?: string | null
  last_kind: string
  last_content: string
}

interface TurnItem {
  id: number
  role: string
  kind: string
  kind_label: string
  content: string
  meta?: Record<string, unknown>
  created_at?: string | null
}

interface SessionDetail {
  id: number
  entry_id: number | null
  title: string
  turn_count: number
  updated_at?: string | null
  turns: TurnItem[]
}

const view = ref<'memory' | 'session'>('memory')
const sessions = ref<SessionItem[]>([])
const sessionStats = ref<{ sessions: number; turns: number; notes: number } | null>(null)
const sessionDetail = ref<SessionDetail | null>(null)
const sessionBusy = ref('')
const noteText = ref('')

async function loadSessions() {
  try {
    const { data } = await api.get('/api/v1/cms/ai/sessions', { params: { limit: 60 } })
    sessions.value = data.items ?? []
    sessionStats.value = data.stats ?? null
  } catch (e: any) {
    errorMsg.value = e?.response?.data?.detail || t("aiMemory.会话加载_1nc33u")
  }
}

async function openSession(id: number) {
  sessionBusy.value = 'open'
  try {
    const { data } = await api.get<SessionDetail>(`/api/v1/cms/ai/sessions/${id}`)
    sessionDetail.value = data
    noteText.value = ''
  } catch (e: any) {
    errorMsg.value = e?.response?.data?.detail || t("aiMemory.会话详情_1tienb")
  } finally {
    sessionBusy.value = ''
  }
}

async function switchView(v: 'memory' | 'session') {
  view.value = v
  if (v === 'session' && !sessions.value.length) await loadSessions()
}

async function addNote() {
  const sid = sessionDetail.value?.id
  if (!sid || !noteText.value.trim()) return
  sessionBusy.value = 'note'
  try {
    const { data } = await api.post(`/api/v1/cms/ai/sessions/${sid}/notes`, {
      content: noteText.value.trim(),
    })
    sessionDetail.value = data.session
    noteText.value = ''
    okMsg.value = '备注已写入，下次 AI 处理这篇会带上'
    await loadSessions()
  } catch (e: any) {
    errorMsg.value = e?.response?.data?.detail || t("aiMemory.备注写入_4ij135")
  } finally {
    sessionBusy.value = ''
  }
}

async function removeTurn(t: TurnItem) {
  if (!confirm('删除这条记录？删除后 AI 不再知道这次改动。')) return
  sessionBusy.value = `turn-${t.id}`
  try {
    await api.delete(`/api/v1/cms/ai/sessions/turns/${t.id}`)
    if (sessionDetail.value) await openSession(sessionDetail.value.id)
    await loadSessions()
  } catch (e: any) {
    errorMsg.value = e?.response?.data?.detail || '删除失败'
  } finally {
    sessionBusy.value = ''
  }
}

async function removeSession(s: SessionItem) {
  if (!confirm(`删除「${s.title || t("aiMemory.未命名_fitay")}」的整条会话？时间线将全部清空。`)) return
  sessionBusy.value = `sess-${s.id}`
  try {
    await api.delete(`/api/v1/cms/ai/sessions/${s.id}`)
    if (sessionDetail.value?.id === s.id) sessionDetail.value = null
    await loadSessions()
    okMsg.value = t("aiMemory.会话已删_177230")
  } catch (e: any) {
    errorMsg.value = e?.response?.data?.detail || t("aiMemory.删除失败_azdahk")
  } finally {
    sessionBusy.value = ''
  }
}

function fmtTime(v?: string | null) {
  if (!v) return ''
  const d = new Date(v)
  const p = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`
}

onMounted(async () => {
  await load()
  await loadPreview()
  await loadSessions()
})
</script>

<template>
  <div class="p-6 max-w-[1280px] mx-auto space-y-5">
    <div class="flex items-start gap-3 flex-wrap">
      <div>
        <h1 class="text-xl font-semibold text-ink-900">{{ $t('aiMemory.text_11q6mm') }}</h1>
        <p class="text-xs text-ink-500 mt-0.5">
          {{ $t('aiMemory.让_1sl52n') }}
        </p>
      </div>
      <div class="ml-auto flex items-center gap-2">
        <button
          class="px-3 py-1.5 text-xs rounded-lg border border-ink-200 bg-white text-ink-600 hover:bg-ink-50 disabled:opacity-50"
          :disabled="!!busy"
          @click="distill"
        >{{ busy === 'distill' ? $t('aiMemory.提炼中_d23hxh') : $t('aiMemory.text_7qk3rm') }}</button>
        <button
          class="px-3 py-1.5 text-xs rounded-lg border border-ink-200 bg-white text-ink-600 hover:bg-ink-50 disabled:opacity-50"
          :disabled="!!busy"
          @click="rebuildDigests"
        >{{ busy === 'rebuild' ? $t('aiMemory.索引中_g6hc0c') : $t('aiMemory.重建内容_cl61xw') }}</button>
        <button
          class="px-3 py-1.5 text-xs rounded-lg bg-ink-900 text-white hover:bg-ink-800"
          @click="openEditor()"
        >{{ $t('aiMemory.新增记忆_d7dmro') }}</button>
      </div>
    </div>

    <div
      v-if="errorMsg"
      class="text-sm text-red-600 bg-red-50 border border-red-200 rounded-lg px-3 py-2 flex items-start gap-2"
    >
      <span class="flex-1">{{ errorMsg }}</span>
      <button class="text-red-400 hover:text-red-700" @click="errorMsg = ''">×</button>
    </div>
    <div
      v-if="okMsg"
      class="text-sm text-emerald-700 bg-emerald-50 border border-emerald-200 rounded-lg px-3 py-2 flex items-start gap-2"
    >
      <span class="flex-1">{{ okMsg }}</span>
      <button class="text-emerald-500 hover:text-emerald-700" @click="okMsg = ''">×</button>
    </div>

    <!-- 统计 -->
    <div v-if="stats" class="grid grid-cols-2 lg:grid-cols-4 gap-3">
      <div class="card !p-4">
        <div class="text-xs text-ink-500">{{ $t('aiMemory.生效中的_1574o2') }}</div>
        <div class="text-2xl font-semibold text-ink-900 mt-1 tabular-nums">{{ stats.approved }}</div>
        <div class="text-[11px] text-ink-400 mt-1">
          {{ stats.by_scope.map((s) => `${s.label}${s.count}`).join(' · ') || $t('aiMemory.还没有任_u4f3jk') }}
        </div>
      </div>
      <div class="card !p-4">
        <div class="text-xs text-ink-500">{{ $t('aiMemory.待审_gxqa29') }}</div>
        <div class="text-2xl font-semibold mt-1 tabular-nums"
             :class="stats.pending ? 'text-amber-600' : 'text-ink-900'">{{ stats.pending }}</div>
        <div class="text-[11px] text-ink-400 mt-1">{{ $t('aiMemory.审核通过_1le2fv') }}</div>
      </div>
      <div class="card !p-4">
        <div class="text-xs text-ink-500">{{ $t('aiMemory.内容索引_ranvbr') }}</div>
        <div class="text-2xl font-semibold text-ink-900 mt-1 tabular-nums">
          {{ stats.digests }}<span class="text-sm text-ink-400"> / {{ stats.entries }}</span>
        </div>
        <div class="text-[11px] text-ink-400 mt-1">
          {{ stats.entries ? `${Math.round(stats.coverage * 100)}% 的条目有摘要` : $t('aiMemory.暂无条目_dcvky3') }}
        </div>
      </div>
      <div class="card !p-4">
        <div class="text-xs text-ink-500">{{ $t('aiMemory.累计注入_gde0y7') }}</div>
        <div class="text-2xl font-semibold text-ink-900 mt-1 tabular-nums">{{ stats.injection_total }}</div>
        <div class="text-[11px] text-ink-400 mt-1">{{ $t('aiMemory.被写进提_1nc7rw') }}</div>
      </div>
    </div>

    <!-- 待审区 -->
    <div v-if="pending.length && view === 'memory'" class="card border-amber-200 bg-amber-50/50">
      <div class="flex items-center gap-3 mb-3">
        <h2 class="text-sm font-semibold text-amber-900">{{ $t('aiMemory.text_1rkib2') }}{{ pending.length }}）</h2>
        <span class="text-[11px] text-amber-700">
          {{ $t('aiMemory.机器归纳_ql3qii') }}
        </span>
        <button
          class="ml-auto px-2.5 py-1 text-xs rounded-lg bg-amber-600 text-white hover:bg-amber-700 disabled:opacity-50"
          :disabled="!!busy"
          @click="approveAll"
        >{{ $t('aiMemory.全部通过_avk8kt') }}</button>
      </div>
      <div class="space-y-2">
        <div
          v-for="p in pending"
          :key="p.id"
          class="flex items-start gap-3 bg-white rounded-lg border border-amber-200 px-3 py-2.5"
        >
          <span class="px-1.5 py-0.5 text-[10px] rounded bg-amber-100 text-amber-700 shrink-0 mt-0.5">
            {{ p.scope_label }}
          </span>
          <div class="flex-1 text-sm text-ink-800">{{ p.content }}</div>
          <button
            class="text-xs text-emerald-600 hover:text-emerald-800 shrink-0"
            :disabled="!!busy"
            @click="setStatus(p, 'approved')"
          >{{ $t('aiMemory.通过_past') }}</button>
          <button
            class="text-xs text-ink-400 hover:text-red-600 shrink-0"
            :disabled="!!busy"
            @click="setStatus(p, 'rejected')"
          >{{ $t('aiMemory.驳回_qqx7') }}</button>
        </div>
      </div>
    </div>

    <div class="flex items-center gap-1 border-b border-ink-200">
      <button
        class="-mb-px px-3 py-2 text-xs border-b-2 transition-colors"
        :class="view === 'memory'
          ? 'border-ink-900 text-ink-900 font-medium'
          : 'border-transparent text-ink-500 hover:text-ink-800'"
        @click="switchView('memory')"
      >{{ $t('aiMemory.站点记忆_fyzml2') }}</button>
      <button
        class="-mb-px px-3 py-2 text-xs border-b-2 transition-colors"
        :class="view === 'session'
          ? 'border-ink-900 text-ink-900 font-medium'
          : 'border-transparent text-ink-500 hover:text-ink-800'"
        @click="switchView('session')"
      >{{ $t('aiMemory.会话记忆_akbwih') }}
        <span v-if="sessionStats?.sessions" class="ml-1 text-ink-400">{{ sessionStats.sessions }}</span>
      </button>
    </div>

    <div v-show="view === 'memory'" class="grid grid-cols-1 xl:grid-cols-[1fr_400px] gap-5 items-start">
      <!-- 左：记忆条目 -->
      <div class="card">
        <div class="flex items-center gap-3 mb-3">
          <h2 class="text-sm font-semibold text-ink-900">{{ $t('aiMemory.记忆条目_i0svur') }}</h2>
          <span class="text-xs text-ink-400">{{ $t('aiMemory.权重高的_11jca7') }}</span>
          <button class="ml-auto text-xs text-ink-500 hover:text-ink-900" @click="toggleDigests">
            {{ digestOpen ? $t('aiMemory.收起内容_19xtqx') : $t('aiMemory.查看内容_1ygcvy') }}
          </button>
        </div>

        <div v-if="loading && !items.length" class="py-12 text-center text-sm text-ink-400">{{ $t('aiMemory.加载中_b0k5km') }}</div>

        <div v-else-if="!approved.length" class="py-14 text-center">
          <p class="text-sm text-ink-500">{{ $t('aiMemory.还没有任_bnsbde') }}</p>
          <p class="text-xs text-ink-400 mt-1.5 max-w-md mx-auto leading-relaxed">
            {{ $t('aiMemory.最小起步_dstoev') }}
          </p>
          <button
            class="mt-4 px-3 py-1.5 text-xs rounded-lg bg-ink-900 text-white hover:bg-ink-800"
            @click="openEditor()"
          >{{ $t('aiMemory.添加第一_eroga0') }}</button>
        </div>

        <div v-else class="space-y-5">
          <div v-for="g in grouped" :key="g.scope">
            <div class="flex items-center gap-2 mb-1.5">
              <h3 class="text-xs font-semibold text-ink-700">{{ g.label }}</h3>
              <span class="text-[10px] text-ink-300">{{ g.items.length }}</span>
              <span class="text-[10px] text-ink-300 truncate">{{ SCOPE_HINT[g.scope] }}</span>
              <button
                class="ml-auto text-[11px] text-ink-400 hover:text-ink-900 shrink-0"
                @click="openEditor(undefined, g.scope)"
              >{{ $t('aiMemory.text_1b9y2') }}</button>
            </div>
            <div class="space-y-1">
              <div
                v-for="it in g.items"
                :key="it.id"
                class="group flex items-start gap-2 rounded-lg px-2.5 py-2 hover:bg-ink-50"
                :class="it.enabled ? '' : 'opacity-50'"
              >
                <span
                  v-if="it.key"
                  class="px-1.5 py-0.5 rounded bg-ink-100 text-ink-700 text-[11px] font-mono shrink-0 mt-0.5"
                >{{ it.key }}</span>
                <div class="flex-1 min-w-0">
                  <p class="text-sm text-ink-800 leading-relaxed">{{ it.content }}</p>
                  <p class="text-[10px] text-ink-300 mt-0.5">
                    {{ $t('aiMemory.权重_id4a') }} {{ it.weight }}
                    {{ $t('aiMemory.text_3shae') }} {{ it.injection_count }} {{ $t('aiMemory.次_l5t') }}
                    <span v-if="it.source === 'ai'" class="text-amber-500">{{ $t('aiMemory.text_31ba63') }}</span>
                    <span v-if="!it.enabled" class="text-red-400">{{ $t('aiMemory.text_37cgr9') }}</span>
                  </p>
                </div>
                <div class="flex items-center gap-2 opacity-0 group-hover:opacity-100 transition shrink-0">
                  <button class="text-[11px] text-ink-500 hover:text-ink-900" @click="openEditor(it)">{{ $t('aiMemory.改_jzt') }}</button>
                  <button class="text-[11px] text-ink-500 hover:text-ink-900" @click="toggleEnabled(it)">
                    {{ it.enabled ? $t('aiMemory.停用_eb7w') : $t('aiMemory.启用_eymx') }}
                  </button>
                  <button class="text-[11px] text-red-400 hover:text-red-700" @click="removeMemory(it)">{{ $t('aiMemory.删_g80') }}</button>
                </div>
              </div>
            </div>
          </div>
        </div>

        <!-- 内容索引 -->
        <div v-if="digestOpen" class="mt-5 pt-4 border-t border-ink-100">
          <div class="flex items-center gap-2 mb-2">
            <h3 class="text-xs font-semibold text-ink-700">{{ $t('aiMemory.内容索引_wjkayu') }}</h3>
            <span class="text-[10px] text-ink-400">{{ $t('aiMemory.起草时会_1ipa7k') }}</span>
          </div>
          <div v-if="!digests.length" class="text-xs text-ink-400 py-6 text-center">
            {{ $t('aiMemory.还没有索_1rxyfg') }}
          </div>
          <div v-else class="space-y-2 max-h-[380px] overflow-y-auto pr-1">
            <div v-for="d in digests" :key="d.entry_id" class="rounded-lg border border-ink-100 px-3 py-2">
              <div class="text-xs font-medium text-ink-800">{{ d.title }}</div>
              <div class="text-[11px] text-ink-500 mt-1 leading-relaxed">{{ d.digest }}</div>
              <div class="flex flex-wrap gap-1 mt-1.5">
                <span
                  v-for="t in d.topics"
                  :key="t"
                  class="px-1.5 py-px rounded bg-ink-50 text-[10px] text-ink-500"
                >{{ t }}</span>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- 右：注入预览 -->
      <div class="card xl:sticky xl:top-4">
        <div class="flex items-center gap-2 mb-2">
          <h2 class="text-sm font-semibold text-ink-900">{{ $t('aiMemory.text_1xopjm') }}</h2>
          <button
            class="ml-auto text-[11px] text-ink-500 hover:text-ink-900 disabled:opacity-50"
            :disabled="previewBusy"
            @click="loadPreview"
          >{{ previewBusy ? $t('aiMemory.刷新中_askp0y') : $t('aiMemory.刷新_ejix') }}</button>
        </div>
        <div class="flex items-center gap-3 mb-3 text-[11px] text-ink-500">
          <label class="flex items-center gap-1">
            {{ $t('aiMemory.预算_qmc3') }}
            <input
              v-model.number="budget"
              type="number"
              min="200"
              max="8000"
              step="200"
              class="w-16 px-1.5 py-0.5 rounded border border-ink-200 text-ink-700"
              @change="loadPreview"
            />
            {{ $t('aiMemory.字_i1j') }}
          </label>
          <label class="flex items-center gap-1">
            <input v-model="withContent" type="checkbox" @change="loadPreview" />
            {{ $t('aiMemory.含内容记_1jn80b') }}
          </label>
        </div>

        <div v-if="preview" class="flex items-center gap-1.5 flex-wrap mb-2">
          <span class="px-1.5 py-0.5 rounded bg-ink-100 text-ink-600 text-[10px]">
            {{ $t('aiMemory.注入_iyyl') }} {{ preview.injected }} {{ $t('aiMemory.条_kf5') }}
          </span>
          <span v-if="preview.content_memory" class="px-1.5 py-0.5 rounded bg-ink-100 text-ink-600 text-[10px]">
            {{ $t('aiMemory.内容记忆_ao9azu') }} {{ preview.content_memory }} {{ $t('aiMemory.篇_og7') }}
          </span>
          <span v-if="preview.truncated" class="px-1.5 py-0.5 rounded bg-amber-100 text-amber-700 text-[10px]">
            {{ preview.truncated }} {{ $t('aiMemory.条超预算_1k4tn1') }}
          </span>
          <span class="px-1.5 py-0.5 rounded bg-ink-100 text-ink-600 text-[10px]">
            {{ preview.chars }} {{ $t('aiMemory.字_i1j') }}
          </span>
        </div>

        <pre
          v-if="preview && preview.block"
          class="text-[11px] leading-relaxed text-ink-700 bg-ink-50 rounded-lg p-3 whitespace-pre-wrap break-words max-h-[520px] overflow-y-auto font-mono"
        >{{ preview.block }}</pre>
        <div v-else class="text-xs text-ink-400 py-10 text-center">
          {{ $t('aiMemory.当前没有_5u6roy') }}
        </div>

        <p class="text-[11px] text-ink-400 mt-3 leading-relaxed">
          {{ $t('aiMemory.这段文本_18c8id') }} <span class="text-ink-600">{{ $t('aiMemory.末尾_i1yr') }}</span> {{ $t('aiMemory.text_uudiwe') }}
        </p>

        <div v-if="zombie.length" class="mt-3 rounded-lg bg-ink-50 px-3 py-2">
          <p class="text-[11px] text-ink-500 leading-relaxed">
            {{ $t('aiMemory.有_kcp') }} {{ zombie.length }} {{ $t('aiMemory.条记忆从_ggv1cu') }}
          </p>
        </div>
      </div>
    </div>

    <!-- 会话记忆：这一篇稿子的来龙去脉 -->
    <div v-show="view === 'session'" class="grid grid-cols-1 xl:grid-cols-[360px_1fr] gap-5 items-start">
      <div class="card">
        <div class="flex items-center gap-2 mb-3">
          <h2 class="text-sm font-semibold text-ink-900">{{ $t('aiMemory.会话_e803') }}</h2>
          <span class="text-[11px] text-ink-400">
            {{ sessionStats?.sessions ?? 0 }} {{ $t('aiMemory.篇_i4p3q') }} {{ sessionStats?.turns ?? 0 }} {{ $t('aiMemory.条记录_ftebq') }}
          </span>
          <button class="ml-auto text-xs text-ink-500 hover:text-ink-900" @click="loadSessions">
            {{ $t('aiMemory.刷新_ejix') }}
          </button>
        </div>

        <div v-if="!sessions.length" class="text-xs text-ink-400 py-10 text-center leading-relaxed">
          {{ $t('aiMemory.还没有会_18ij6y') }}<br />
          {{ $t('aiMemory.在工作台_qh4en5') }}
        </div>

        <div v-else class="space-y-1.5 max-h-[600px] overflow-y-auto">
          <button
            v-for="s in sessions"
            :key="s.id"
            class="w-full text-left px-3 py-2 rounded-lg border transition-colors"
            :class="sessionDetail?.id === s.id
              ? 'border-ink-900 bg-ink-50'
              : 'border-ink-100 hover:border-ink-300'"
            @click="openSession(s.id)"
          >
            <div class="flex items-center gap-2">
              <span class="text-xs font-medium text-ink-900 truncate">{{ s.title || $t('aiMemory.未命名条_1n867t') }}</span>
              <span class="ml-auto text-[10px] text-ink-400 shrink-0">{{ s.turn_count }} {{ $t('aiMemory.条_kf5') }}</span>
            </div>
            <div class="text-[11px] text-ink-500 truncate mt-0.5">
              <span class="text-ink-400">{{ s.last_kind }}</span> · {{ s.last_content }}
            </div>
            <div class="text-[10px] text-ink-300 mt-0.5">{{ fmtTime(s.updated_at) }}</div>
          </button>
        </div>
      </div>

      <div class="card">
        <div v-if="!sessionDetail" class="text-xs text-ink-400 py-16 text-center">
          {{ $t('aiMemory.左边选一_glph9g') }}
        </div>

        <div v-else>
          <div class="flex items-center gap-3 mb-1">
            <h2 class="text-sm font-semibold text-ink-900 truncate">{{ sessionDetail.title || $t('aiMemory.未命名条_1n867t') }}</h2>
            <span class="px-1.5 py-0.5 rounded bg-ink-100 text-ink-600 text-[10px] shrink-0">
              {{ sessionDetail.turns.length }} {{ $t('aiMemory.条记录_ftebq') }}
            </span>
            <button
              class="ml-auto text-xs text-ink-400 hover:text-red-600 shrink-0"
              :disabled="!!sessionBusy"
              @click="removeSession({ id: sessionDetail.id, entry_id: sessionDetail.entry_id, title: sessionDetail.title, turn_count: sessionDetail.turn_count, last_kind: '', last_content: '' })"
            >{{ $t('aiMemory.删除会话_azbkg7') }}</button>
          </div>
          <p class="text-[11px] text-ink-400 mb-4">
            {{ $t('aiMemory.最近_ib4h') }} {{ 8 }} {{ $t('aiMemory.条会压成_eov1yz') }}
          </p>

          <div class="space-y-2 mb-4">
            <div
              v-for="t in sessionDetail.turns"
              :key="t.id"
              class="flex items-start gap-3 rounded-lg border px-3 py-2.5"
              :class="t.role === 'user'
                ? 'border-amber-200 bg-amber-50/60'
                : 'border-ink-100 bg-white'"
            >
              <span
                class="px-1.5 py-0.5 rounded text-[10px] shrink-0 mt-0.5"
                :class="t.role === 'user'
                  ? 'bg-amber-100 text-amber-700'
                  : 'bg-ink-100 text-ink-600'"
              >{{ t.role === 'user' ? $t('aiMemory.人_fju') : 'AI' }} · {{ t.kind_label }}</span>
              <div class="flex-1 min-w-0">
                <div class="text-xs text-ink-800 leading-relaxed break-words">{{ t.content }}</div>
                <div class="text-[10px] text-ink-300 mt-1">{{ fmtTime(t.created_at) }}</div>
              </div>
              <button
                class="text-[11px] text-ink-300 hover:text-red-600 shrink-0"
                :disabled="!!sessionBusy"
                @click="removeTurn(t)"
              >{{ $t('aiMemory.删_g80') }}</button>
            </div>
          </div>

          <div class="rounded-lg border border-ink-200 p-3">
            <div class="text-xs font-medium text-ink-800 mb-2">
              {{ $t('aiMemory.给这篇加_gzs123') }}
              <span class="text-[11px] font-normal text-ink-400 ml-1">
                {{ $t('aiMemory.只对这篇_x6854s') }}
              </span>
            </div>
            <textarea
              v-model="noteText"
              rows="2"
              maxlength="1000"
              :placeholder="$t('aiMemory.例_173a0h')"
              class="w-full text-xs rounded-lg border border-ink-200 px-3 py-2 outline-none focus:border-ink-400"
            />
            <div class="flex items-center gap-2 mt-2">
              <span class="text-[10px] text-ink-300">{{ noteText.length }}/1000</span>
              <button
                class="ml-auto px-3 py-1.5 text-xs rounded-lg bg-ink-900 text-white hover:bg-ink-800 disabled:opacity-50"
                :disabled="!noteText.trim() || !!sessionBusy"
                @click="addNote"
              >{{ sessionBusy === 'note' ? $t('aiMemory.写入中_amssxx') : $t('aiMemory.写入备注_amv2jx') }}</button>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- 编辑弹窗 -->
    <div
      v-if="editorOpen"
      class="fixed inset-0 z-50 bg-black/40 flex items-start justify-center p-4 overflow-y-auto"
      @click.self="editorOpen = false"
    >
      <div class="bg-white rounded-xl w-full max-w-[600px] my-10 shadow-xl">
        <div class="flex items-center gap-3 px-5 py-3.5 border-b border-ink-100">
          <h2 class="font-semibold text-ink-900 text-sm">{{ draft.id ? $t('aiMemory.编辑记忆_gmr2c1') : $t('aiMemory.新增记忆_d7dmro') }}</h2>
          <span class="text-xs text-ink-400">{{ SCOPE_HINT[draft.scope] }}</span>
          <button class="ml-auto text-ink-400 hover:text-ink-700 text-xl leading-none" @click="editorOpen = false">×</button>
        </div>

        <div class="p-5 space-y-3">
          <label class="block text-xs text-ink-600">
            {{ $t('aiMemory.分类_emut') }}
            <select
              v-model="draft.scope"
              class="mt-1 w-full px-2.5 py-1.5 text-sm rounded-lg border border-ink-200 bg-white focus:outline-none focus:ring-2 focus:ring-ink-900/10"
            >
              <option v-for="s in scopes" :key="s.value" :value="s.value">{{ s.label }}</option>
            </select>
          </label>

          <label v-if="draft.scope === 'term' || draft.scope === 'ban'" class="block text-xs text-ink-600">
            {{ draft.scope === 'term' ? $t('aiMemory.规范写法_hx4s4b') : $t('aiMemory.要禁用的_1k8lcy') }}
            <input
              v-model="draft.key"
              class="mt-1 w-full px-2.5 py-1.5 text-sm rounded-lg border border-ink-200 focus:outline-none focus:ring-2 focus:ring-ink-900/10"
              :placeholder="draft.scope === 'term' ? 'MES' : '赋能'"
            />
          </label>

          <label class="block text-xs text-ink-600">
            {{ draft.scope === 'term' ? $t('aiMemory.说明_1296cw') : draft.scope === 'ban' ? $t('aiMemory.原因_3qvfor') : $t('aiMemory.内容_edas') }}
            <textarea
              v-model="draft.content"
              rows="4"
              class="mt-1 w-full px-2.5 py-1.5 text-sm rounded-lg border border-ink-200 focus:outline-none focus:ring-2 focus:ring-ink-900/10 resize-y"
              :placeholder="
                draft.scope === 'brand'
                  ? '本站是面向制造业管理者的实战内容站，所有结论要有案例或数据支撑'
                  : draft.scope === 'audience'
                    ? '读者是中小制造企业的信息化负责人，懂业务但不熟悉 AI'
                    : '一句话写清规范'
              "
            />
          </label>

          <label class="block text-xs text-ink-600">
            {{ $t('aiMemory.权重_1j0o85') }}
            <div class="flex items-center gap-3 mt-1">
              <input v-model.number="draft.weight" type="range" min="0" max="100" step="5" class="flex-1" />
              <span class="w-8 text-sm text-ink-900 tabular-nums text-right">{{ draft.weight }}</span>
            </div>
            <span class="block mt-1 text-[11px] text-ink-400">
              {{ $t('aiMemory.预算有限_ty9sx4') }}
            </span>
          </label>

          <div class="flex items-center gap-2 pt-1">
            <button
              class="px-3 py-1.5 text-sm rounded-lg bg-ink-900 text-white hover:bg-ink-800 disabled:opacity-50"
              :disabled="busy === 'save'"
              @click="saveMemory"
            >{{ $t('aiMemory.保存_e32z') }}</button>
            <button
              class="px-3 py-1.5 text-sm rounded-lg border border-ink-200 text-ink-600 hover:bg-ink-50"
              @click="editorOpen = false"
            >{{ $t('aiMemory.取消_ev02') }}</button>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>
