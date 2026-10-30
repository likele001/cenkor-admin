<script setup lang="ts">
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
    errorMsg.value = e?.response?.data?.detail || e?.message || '加载失败'
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
    errorMsg.value = e?.response?.data?.detail || '预览失败'
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
    errorMsg.value = '内容不能为空'
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
    errorMsg.value = e?.response?.data?.detail || '保存失败'
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
    errorMsg.value = e?.response?.data?.detail || '操作失败'
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
    errorMsg.value = e?.response?.data?.detail || '操作失败'
  } finally {
    busy.value = ''
  }
}

async function removeMemory(it: MemoryItem) {
  if (!confirm(`删除这条记忆？\n\n${it.content.slice(0, 80)}`)) return
  busy.value = `d-${it.id}`
  try {
    await api.delete(`/api/v1/cms/ai/memory/${it.id}`)
    okMsg.value = '已删除'
    await load()
    await loadPreview()
  } catch (e: any) {
    errorMsg.value = e?.response?.data?.detail || '删除失败'
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
    errorMsg.value = e?.response?.data?.detail || '操作失败'
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
      errorMsg.value = data.reason || '样本不足'
    } else if (!data.created) {
      okMsg.value = `已分析 ${data.sample} 篇，没有新的可提炼项（已有建议未处理）`
    } else {
      okMsg.value = `已提炼 ${data.created} 条，在下方「待审」里确认后才会生效`
    }
    await load()
  } catch (e: any) {
    errorMsg.value = e?.response?.data?.detail || '提炼失败'
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
    errorMsg.value = e?.response?.data?.detail || '重建失败'
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
    errorMsg.value = e?.response?.data?.detail || '会话加载失败'
  }
}

async function openSession(id: number) {
  sessionBusy.value = 'open'
  try {
    const { data } = await api.get<SessionDetail>(`/api/v1/cms/ai/sessions/${id}`)
    sessionDetail.value = data
    noteText.value = ''
  } catch (e: any) {
    errorMsg.value = e?.response?.data?.detail || '会话详情加载失败'
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
    errorMsg.value = e?.response?.data?.detail || '备注写入失败'
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
  if (!confirm(`删除「${s.title || '未命名'}」的整条会话？时间线将全部清空。`)) return
  sessionBusy.value = `sess-${s.id}`
  try {
    await api.delete(`/api/v1/cms/ai/sessions/${s.id}`)
    if (sessionDetail.value?.id === s.id) sessionDetail.value = null
    await loadSessions()
    okMsg.value = '会话已删除'
  } catch (e: any) {
    errorMsg.value = e?.response?.data?.detail || '删除失败'
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
        <h1 class="text-xl font-semibold text-ink-900">AI 记忆</h1>
        <p class="text-xs text-ink-500 mt-0.5">
          让 AI 记住本站的调性、术语与已经写过的内容 —— 不再是每次从零开始的陌生人
        </p>
      </div>
      <div class="ml-auto flex items-center gap-2">
        <button
          class="px-3 py-1.5 text-xs rounded-lg border border-ink-200 bg-white text-ink-600 hover:bg-ink-50 disabled:opacity-50"
          :disabled="!!busy"
          @click="distill"
        >{{ busy === 'distill' ? '提炼中…' : 'AI 提炼风格' }}</button>
        <button
          class="px-3 py-1.5 text-xs rounded-lg border border-ink-200 bg-white text-ink-600 hover:bg-ink-50 disabled:opacity-50"
          :disabled="!!busy"
          @click="rebuildDigests"
        >{{ busy === 'rebuild' ? '索引中…' : '重建内容索引' }}</button>
        <button
          class="px-3 py-1.5 text-xs rounded-lg bg-ink-900 text-white hover:bg-ink-800"
          @click="openEditor()"
        >新增记忆</button>
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
        <div class="text-xs text-ink-500">生效中的记忆</div>
        <div class="text-2xl font-semibold text-ink-900 mt-1 tabular-nums">{{ stats.approved }}</div>
        <div class="text-[11px] text-ink-400 mt-1">
          {{ stats.by_scope.map((s) => `${s.label}${s.count}`).join(' · ') || '还没有任何记忆' }}
        </div>
      </div>
      <div class="card !p-4">
        <div class="text-xs text-ink-500">待审（AI 提炼）</div>
        <div class="text-2xl font-semibold mt-1 tabular-nums"
             :class="stats.pending ? 'text-amber-600' : 'text-ink-900'">{{ stats.pending }}</div>
        <div class="text-[11px] text-ink-400 mt-1">审核通过后才会注入提示词</div>
      </div>
      <div class="card !p-4">
        <div class="text-xs text-ink-500">内容索引覆盖</div>
        <div class="text-2xl font-semibold text-ink-900 mt-1 tabular-nums">
          {{ stats.digests }}<span class="text-sm text-ink-400"> / {{ stats.entries }}</span>
        </div>
        <div class="text-[11px] text-ink-400 mt-1">
          {{ stats.entries ? `${Math.round(stats.coverage * 100)}% 的条目有摘要` : '暂无条目' }}
        </div>
      </div>
      <div class="card !p-4">
        <div class="text-xs text-ink-500">累计注入</div>
        <div class="text-2xl font-semibold text-ink-900 mt-1 tabular-nums">{{ stats.injection_total }}</div>
        <div class="text-[11px] text-ink-400 mt-1">被写进提示词的次数</div>
      </div>
    </div>

    <!-- 待审区 -->
    <div v-if="pending.length && view === 'memory'" class="card border-amber-200 bg-amber-50/50">
      <div class="flex items-center gap-3 mb-3">
        <h2 class="text-sm font-semibold text-amber-900">AI 提炼的风格建议（{{ pending.length }}）</h2>
        <span class="text-[11px] text-amber-700">
          机器归纳的东西看着像真的、实际经常是编的 —— 确认前不会生效
        </span>
        <button
          class="ml-auto px-2.5 py-1 text-xs rounded-lg bg-amber-600 text-white hover:bg-amber-700 disabled:opacity-50"
          :disabled="!!busy"
          @click="approveAll"
        >全部通过</button>
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
          >通过</button>
          <button
            class="text-xs text-ink-400 hover:text-red-600 shrink-0"
            :disabled="!!busy"
            @click="setStatus(p, 'rejected')"
          >驳回</button>
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
      >站点记忆</button>
      <button
        class="-mb-px px-3 py-2 text-xs border-b-2 transition-colors"
        :class="view === 'session'
          ? 'border-ink-900 text-ink-900 font-medium'
          : 'border-transparent text-ink-500 hover:text-ink-800'"
        @click="switchView('session')"
      >会话记忆
        <span v-if="sessionStats?.sessions" class="ml-1 text-ink-400">{{ sessionStats.sessions }}</span>
      </button>
    </div>

    <div v-show="view === 'memory'" class="grid grid-cols-1 xl:grid-cols-[1fr_400px] gap-5 items-start">
      <!-- 左：记忆条目 -->
      <div class="card">
        <div class="flex items-center gap-3 mb-3">
          <h2 class="text-sm font-semibold text-ink-900">记忆条目</h2>
          <span class="text-xs text-ink-400">权重高的先注入</span>
          <button class="ml-auto text-xs text-ink-500 hover:text-ink-900" @click="toggleDigests">
            {{ digestOpen ? '收起内容索引' : '查看内容索引' }}
          </button>
        </div>

        <div v-if="loading && !items.length" class="py-12 text-center text-sm text-ink-400">加载中…</div>

        <div v-else-if="!approved.length" class="py-14 text-center">
          <p class="text-sm text-ink-500">还没有任何生效中的记忆。</p>
          <p class="text-xs text-ink-400 mt-1.5 max-w-md mx-auto leading-relaxed">
            最小起步只需三条：一条品牌调性（这站是什么调子）、一条目标读者（写给谁看）、
            一组术语（哪些词必须统一写法）。填完起草质量立刻不一样。
          </p>
          <button
            class="mt-4 px-3 py-1.5 text-xs rounded-lg bg-ink-900 text-white hover:bg-ink-800"
            @click="openEditor()"
          >添加第一条</button>
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
              >+ 添加</button>
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
                    权重 {{ it.weight }}
                    · 注入 {{ it.injection_count }} 次
                    <span v-if="it.source === 'ai'" class="text-amber-500">· AI 提炼</span>
                    <span v-if="!it.enabled" class="text-red-400">· 已停用</span>
                  </p>
                </div>
                <div class="flex items-center gap-2 opacity-0 group-hover:opacity-100 transition shrink-0">
                  <button class="text-[11px] text-ink-500 hover:text-ink-900" @click="openEditor(it)">改</button>
                  <button class="text-[11px] text-ink-500 hover:text-ink-900" @click="toggleEnabled(it)">
                    {{ it.enabled ? '停用' : '启用' }}
                  </button>
                  <button class="text-[11px] text-red-400 hover:text-red-700" @click="removeMemory(it)">删</button>
                </div>
              </div>
            </div>
          </div>
        </div>

        <!-- 内容索引 -->
        <div v-if="digestOpen" class="mt-5 pt-4 border-t border-ink-100">
          <div class="flex items-center gap-2 mb-2">
            <h3 class="text-xs font-semibold text-ink-700">内容索引（已发布内容的记忆）</h3>
            <span class="text-[10px] text-ink-400">起草时会带上最近 15 条</span>
          </div>
          <div v-if="!digests.length" class="text-xs text-ink-400 py-6 text-center">
            还没有索引。点右上角「重建内容索引」生成。
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
          <h2 class="text-sm font-semibold text-ink-900">AI 实际吃到的原文</h2>
          <button
            class="ml-auto text-[11px] text-ink-500 hover:text-ink-900 disabled:opacity-50"
            :disabled="previewBusy"
            @click="loadPreview"
          >{{ previewBusy ? '刷新中…' : '刷新' }}</button>
        </div>
        <div class="flex items-center gap-3 mb-3 text-[11px] text-ink-500">
          <label class="flex items-center gap-1">
            预算
            <input
              v-model.number="budget"
              type="number"
              min="200"
              max="8000"
              step="200"
              class="w-16 px-1.5 py-0.5 rounded border border-ink-200 text-ink-700"
              @change="loadPreview"
            />
            字
          </label>
          <label class="flex items-center gap-1">
            <input v-model="withContent" type="checkbox" @change="loadPreview" />
            含内容记忆
          </label>
        </div>

        <div v-if="preview" class="flex items-center gap-1.5 flex-wrap mb-2">
          <span class="px-1.5 py-0.5 rounded bg-ink-100 text-ink-600 text-[10px]">
            注入 {{ preview.injected }} 条
          </span>
          <span v-if="preview.content_memory" class="px-1.5 py-0.5 rounded bg-ink-100 text-ink-600 text-[10px]">
            内容记忆 {{ preview.content_memory }} 篇
          </span>
          <span v-if="preview.truncated" class="px-1.5 py-0.5 rounded bg-amber-100 text-amber-700 text-[10px]">
            {{ preview.truncated }} 条超预算未注入
          </span>
          <span class="px-1.5 py-0.5 rounded bg-ink-100 text-ink-600 text-[10px]">
            {{ preview.chars }} 字
          </span>
        </div>

        <pre
          v-if="preview && preview.block"
          class="text-[11px] leading-relaxed text-ink-700 bg-ink-50 rounded-lg p-3 whitespace-pre-wrap break-words max-h-[520px] overflow-y-auto font-mono"
        >{{ preview.block }}</pre>
        <div v-else class="text-xs text-ink-400 py-10 text-center">
          当前没有可注入的记忆。
        </div>

        <p class="text-[11px] text-ink-400 mt-3 leading-relaxed">
          这段文本会被拼在每次起草的 system prompt <span class="text-ink-600">末尾</span> ——
          固定内容在前、记忆在后，前缀缓存才能命中。放在最前面会让每次请求前缀都不同，缓存全废。
        </p>

        <div v-if="zombie.length" class="mt-3 rounded-lg bg-ink-50 px-3 py-2">
          <p class="text-[11px] text-ink-500 leading-relaxed">
            有 {{ zombie.length }} 条记忆从未被注入过（权重偏低，预算先被别的吃掉了）。
            如果它们很重要，去把权重调高。
          </p>
        </div>
      </div>
    </div>

    <!-- 会话记忆：这一篇稿子的来龙去脉 -->
    <div v-show="view === 'session'" class="grid grid-cols-1 xl:grid-cols-[360px_1fr] gap-5 items-start">
      <div class="card">
        <div class="flex items-center gap-2 mb-3">
          <h2 class="text-sm font-semibold text-ink-900">会话</h2>
          <span class="text-[11px] text-ink-400">
            {{ sessionStats?.sessions ?? 0 }} 篇 / {{ sessionStats?.turns ?? 0 }} 条记录
          </span>
          <button class="ml-auto text-xs text-ink-500 hover:text-ink-900" @click="loadSessions">
            刷新
          </button>
        </div>

        <div v-if="!sessions.length" class="text-xs text-ink-400 py-10 text-center leading-relaxed">
          还没有会话。<br />
          在工作台起草并保存、或对已有内容跑一次 SEO / 翻译，就会自动建一条。
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
              <span class="text-xs font-medium text-ink-900 truncate">{{ s.title || '未命名条目' }}</span>
              <span class="ml-auto text-[10px] text-ink-400 shrink-0">{{ s.turn_count }} 条</span>
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
          左边选一篇，看它被 AI 改过哪些地方
        </div>

        <div v-else>
          <div class="flex items-center gap-3 mb-1">
            <h2 class="text-sm font-semibold text-ink-900 truncate">{{ sessionDetail.title || '未命名条目' }}</h2>
            <span class="px-1.5 py-0.5 rounded bg-ink-100 text-ink-600 text-[10px] shrink-0">
              {{ sessionDetail.turns.length }} 条记录
            </span>
            <button
              class="ml-auto text-xs text-ink-400 hover:text-red-600 shrink-0"
              :disabled="!!sessionBusy"
              @click="removeSession({ id: sessionDetail.id, entry_id: sessionDetail.entry_id, title: sessionDetail.title, turn_count: sessionDetail.turn_count, last_kind: '', last_content: '' })"
            >删除会话</button>
          </div>
          <p class="text-[11px] text-ink-400 mb-4">
            最近 {{ 8 }} 条会压成一段拼进提示词末尾；人工备注原样注入，优先级最高
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
              >{{ t.role === 'user' ? '人' : 'AI' }} · {{ t.kind_label }}</span>
              <div class="flex-1 min-w-0">
                <div class="text-xs text-ink-800 leading-relaxed break-words">{{ t.content }}</div>
                <div class="text-[10px] text-ink-300 mt-1">{{ fmtTime(t.created_at) }}</div>
              </div>
              <button
                class="text-[11px] text-ink-300 hover:text-red-600 shrink-0"
                :disabled="!!sessionBusy"
                @click="removeTurn(t)"
              >删</button>
            </div>
          </div>

          <div class="rounded-lg border border-ink-200 p-3">
            <div class="text-xs font-medium text-ink-800 mb-2">
              给这篇加一条要求
              <span class="text-[11px] font-normal text-ink-400 ml-1">
                只对这篇生效，不会写进全站记忆
              </span>
            </div>
            <textarea
              v-model="noteText"
              rows="2"
              maxlength="1000"
              placeholder="例：结论要落到排产上，不要泛泛谈数字化；不要提竞品参数"
              class="w-full text-xs rounded-lg border border-ink-200 px-3 py-2 outline-none focus:border-ink-400"
            />
            <div class="flex items-center gap-2 mt-2">
              <span class="text-[10px] text-ink-300">{{ noteText.length }}/1000</span>
              <button
                class="ml-auto px-3 py-1.5 text-xs rounded-lg bg-ink-900 text-white hover:bg-ink-800 disabled:opacity-50"
                :disabled="!noteText.trim() || !!sessionBusy"
                @click="addNote"
              >{{ sessionBusy === 'note' ? '写入中…' : '写入备注' }}</button>
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
          <h2 class="font-semibold text-ink-900 text-sm">{{ draft.id ? '编辑记忆' : '新增记忆' }}</h2>
          <span class="text-xs text-ink-400">{{ SCOPE_HINT[draft.scope] }}</span>
          <button class="ml-auto text-ink-400 hover:text-ink-700 text-xl leading-none" @click="editorOpen = false">×</button>
        </div>

        <div class="p-5 space-y-3">
          <label class="block text-xs text-ink-600">
            分类
            <select
              v-model="draft.scope"
              class="mt-1 w-full px-2.5 py-1.5 text-sm rounded-lg border border-ink-200 bg-white focus:outline-none focus:ring-2 focus:ring-ink-900/10"
            >
              <option v-for="s in scopes" :key="s.value" :value="s.value">{{ s.label }}</option>
            </select>
          </label>

          <label v-if="draft.scope === 'term' || draft.scope === 'ban'" class="block text-xs text-ink-600">
            {{ draft.scope === 'term' ? '规范写法' : '要禁用的词' }}
            <input
              v-model="draft.key"
              class="mt-1 w-full px-2.5 py-1.5 text-sm rounded-lg border border-ink-200 focus:outline-none focus:ring-2 focus:ring-ink-900/10"
              :placeholder="draft.scope === 'term' ? 'MES' : '赋能'"
            />
          </label>

          <label class="block text-xs text-ink-600">
            {{ draft.scope === 'term' ? '说明（易错写法 / 全称）' : draft.scope === 'ban' ? '原因 / 该换成什么' : '内容' }}
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
            权重（0-100，越高越先注入）
            <div class="flex items-center gap-3 mt-1">
              <input v-model.number="draft.weight" type="range" min="0" max="100" step="5" class="flex-1" />
              <span class="w-8 text-sm text-ink-900 tabular-nums text-right">{{ draft.weight }}</span>
            </div>
            <span class="block mt-1 text-[11px] text-ink-400">
              预算有限时按权重从高到低装。品牌调性建议 80+，术语 70，冷门事实 30-50。
            </span>
          </label>

          <div class="flex items-center gap-2 pt-1">
            <button
              class="px-3 py-1.5 text-sm rounded-lg bg-ink-900 text-white hover:bg-ink-800 disabled:opacity-50"
              :disabled="busy === 'save'"
              @click="saveMemory"
            >保存</button>
            <button
              class="px-3 py-1.5 text-sm rounded-lg border border-ink-200 text-ink-600 hover:bg-ink-50"
              @click="editorOpen = false"
            >取消</button>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>
