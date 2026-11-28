<script setup lang="ts">
import { useI18n } from 'vue-i18n'
const { t } = useI18n()
/**
 * AI 用量与成本页。
 *
 * 驾驶舱只给「今日/本周/本月调用次数」，看不出烧钱速度 —— 一次批量起草几十篇，
 * 次数看着不多，token 可能已经翻了几倍。这里把 token 拆成三段来看：
 *
 *   输入（未命中缓存） + 缓存命中 + 输出
 *
 * 为什么必须拆开：各家的 prompt_tokens 都含缓存命中数，整段显示成一个「输入」
 * 数字，就看不出缓存到底省没省钱。命中率从 0 涨到 95%，成本能差一个数量级，
 * 而面板上如果不拆，这两天的数字看起来几乎一样。
 *
 * 金额按「单价表」折算，单价由管理员自己填采购价。没配单价就明确显示「未配置」，
 * 不给任何假定值 —— 按错误单价算出来的数比不显示更误导人。
 */
import { computed, onMounted, ref } from 'vue'
import { api } from '@/lib/api'

interface ModelCost {
  provider: string
  model: string
  calls: number
  tokens_in: number
  tokens_out: number
  tokens_cache: number
  cost: number | null
  priced: boolean
}

interface UsageItem {
  kind: string
  calls: number
  tokens_in: number
  tokens_out: number
  tokens_cache: number
  cache_hit_rate: number
  avg_tokens_in: number
  avg_tokens_out: number
  avg_latency_ms: number
  cost: number
  cache_saved: number
  priced: boolean
  priced_calls: number
  unpriced_calls: number
  live_calls: number
  models: ModelCost[]
}

interface TrendPoint {
  date: string
  calls: number
  tokens_in: number
  tokens_out: number
  tokens_cache: number
  cost: number
  cache_hit_rate: number
  unpriced_calls: number
}

interface PrevTotal {
  days: number
  calls: number
  tokens_in: number
  tokens_out: number
  tokens_cache: number
  cost: number
  cache_hit_rate: number
  unpriced_calls: number
}

interface Usage {
  days: number
  enabled: boolean
  embed_ready: boolean
  items: UsageItem[]
  trend: TrendPoint[]
  prev: PrevTotal
  total_calls: number
  total_tokens: number
  total_tokens_in: number
  total_tokens_out: number
  total_tokens_cache: number
  cache_hit_rate: number
  total_cache_saved: number
  total_cost: number
  priced: boolean
  priced_calls: number
  unpriced_calls: number
  estimated_calls: number
  estimated: boolean
  unpriced_kinds: string[]
  currency: string
  price_count: number
}

interface PriceRule {
  id: number
  provider: string
  model: string
  kind: string
  unit: string
  input_per_m: number
  output_per_m: number
  cache_per_m: number | null
  currency: string
  enabled: boolean
  note: string
  updated_at?: string | null
}

const KIND_LABEL: Record<string, string> = {
  entry_draft: '起草',
  draft: '起草',
  content_type_from_nl: '自然语言建模',
  rewrite: '字段改写',
  seo: 'SEO 元数据',
  translate: '翻译',
  redistribute: '多渠道再分发',
  auto_tag: '自动打标签',
  dedup: '查重',
  embedding: '向量化',
  embed: '向量化',
  illustration: '配图生成',
  illustration_prompt: '配图提示词',
  image: '配图生成',
  ab_run: '模型 A/B',
  qa_ask: '问答检索',
  topic_gap: '选题缺口',
  video: '视频生成',
  ingest_extract: '素材解析',
  ingest_ocr: '扫描件 OCR',
}

const UNIT_OPTIONS = [
  { v: 'token', t: '按 token 计（每百万 token 单价）' },
  { v: 'image', t: '按张计（每次调用单价）' },
  { v: 'video', t: '按条计（每次调用单价）' },
]

const DAY_OPTIONS = [
  { days: 7, label: '近 7 天' },
  { days: 30, label: '近 30 天' },
  { days: 90, label: '近 90 天' },
  { days: 365, label: '近一年' },
]

const days = ref(30)
const loading = ref(false)
const errorMsg = ref('')
const data = ref<Usage | null>(null)
const sortKey = ref<'tokens' | 'calls' | 'latency' | 'cost' | 'cache'>('tokens')

// ---- 单价设置 ----
const priceOpen = ref(false)
const priceList = ref<PriceRule[]>([])
const priceKinds = ref<string[]>([])
const priceBusy = ref(false)
const priceErr = ref('')
const priceOk = ref('')
const recalcBusy = ref(false)
const draft = ref({
  provider: '',
  model: '',
  kind: '',
  unit: 'token',
  input_per_m: '' as string | number,
  output_per_m: '' as string | number,
  cache_per_m: '' as string | number,
  note: '',
})

function kindLabel(k: string) {
  return KIND_LABEL[k] ?? k
}

/** 一万 token 以上折算成「万」，卡片和表格才放得下 */
function fmt(n: number) {
  if (n >= 100_000_000) return `${(n / 100_000_000).toFixed(2)} 亿`
  if (n >= 10_000) return `${(n / 10_000).toFixed(1)} 万`
  return n.toLocaleString('zh-CN')
}

function fmtMs(ms: number) {
  if (ms >= 1000) return `${(ms / 1000).toFixed(1)}s`
  return `${ms}ms`
}

/**
 * 金额格式化。小额不能直接 toFixed(2) —— 0.0004 元会显示成 0.00，
 * 看起来像「没花钱」，实际是「花得很少」。
 */
function fmtMoney(v: number | null | undefined) {
  if (v === null || v === undefined) return '—'
  if (v === 0) return '0'
  if (v < 0.01) return v.toFixed(4)
  if (v < 1) return v.toFixed(3)
  return v.toFixed(2)
}

function currencySymbol(c: string) {
  if (c === 'mixed') return t("aiUsage.多币种_dihl2")
  if (c === 'USD') return '$'
  if (c === 'EUR') return '€'
  return '¥'
}

function pct(v: number) {
  return `${(v * 100).toFixed(v >= 0.995 ? 0 : 1)}%`
}

/**
 * 环比。上期为 0 时不显示百分比 —— 「+∞%」毫无意义，只说「上期无数据」。
 * 也不按涨跌染色：成本涨可能是业务量涨，掉可能是故障，颜色会替人下结论。
 */
function delta(cur: number, prev: number): string | null {
  if (!prev) return null
  const d = ((cur - prev) / prev) * 100
  if (!Number.isFinite(d)) return null
  return `${d >= 0 ? '+' : ''}${d.toFixed(0)}%`
}

/** 当前所有还没匹配到单价的 (业务功能, provider, model) 组合 */
const unpricedCombos = computed(() => {
  const out: { kind: string; provider: string; model: string; calls: number }[] = []
  for (const it of data.value?.items ?? []) {
    for (const m of it.models ?? []) {
      if (m.cost === null) {
        out.push({ kind: it.kind, provider: m.provider, model: m.model, calls: m.calls })
      }
    }
  }
  return out
})

const rows = computed(() => {
  const list = [...(data.value?.items ?? [])].map((it) => ({
    ...it,
    total_tokens: it.tokens_in + it.tokens_out,
    // 未命中缓存的输入 = 总输入 − 缓存命中（缓存是输入的子集）
    tokens_uncached: Math.max(0, it.tokens_in - it.tokens_cache),
  }))
  const key = sortKey.value
  return list.sort((a, b) => {
    if (key === 'calls') return b.calls - a.calls
    if (key === 'latency') return b.avg_latency_ms - a.avg_latency_ms
    if (key === 'cost') return b.cost - a.cost
    if (key === 'cache') return b.tokens_cache - a.tokens_cache
    return b.total_tokens - a.total_tokens
  })
})

const maxTokens = computed(() => Math.max(1, ...rows.value.map((r) => r.total_tokens)))

/** token 三段构成（未命中输入 / 缓存 / 输出），用于顶部说明 */
const tokenMix = computed(() => {
  const tin = data.value?.total_tokens_in ?? 0
  const cache = data.value?.total_tokens_cache ?? 0
  const tout = data.value?.total_tokens_out ?? 0
  const all = tin + tout
  if (!all) return null
  return {
    uncached: (tin - cache) / all,
    cache: cache / all,
    out: tout / all,
    uncachedAbs: tin - cache,
  }
})

/** 趋势图：三段堆叠的最大值，决定柱高比例 */
const trendMax = computed(() => {
  const list = data.value?.trend ?? []
  return Math.max(1, ...list.map((d) => d.tokens_in + d.tokens_out))
})

const trendHasData = computed(() =>
  (data.value?.trend ?? []).some((d) => d.calls > 0),
)

/** 柱高百分比。有数据但很小时给 1.5% 下限，否则整天看不见像断了 */
function barH(v: number) {
  if (!v) return '0%'
  const p = (v / trendMax.value) * 100
  return `${Math.max(1.5, p)}%`
}

/** 日期标签：只标 4 个位置，30 根柱子全标会糊成一片 */
function showDate(i: number, total: number) {
  if (total <= 8) return true
  const step = Math.ceil(total / 4)
  return i % step === 0 || i === total - 1
}

async function load() {
  loading.value = true
  errorMsg.value = ''
  try {
    const { data: d } = await api.get<Usage>('/api/v1/cms/ai/usage', {
      params: { days: days.value },
    })
    data.value = d
  } catch (e: any) {
    errorMsg.value = e?.response?.data?.detail || e?.message || t("dashboard.loadFailed")
  } finally {
    loading.value = false
  }
}

// ---- 单价维护 ----
async function openPrices() {
  priceOpen.value = true
  priceOk.value = ''
  await loadPrices()
}

async function loadPrices() {
  priceBusy.value = true
  priceErr.value = ''
  try {
    const { data: d } = await api.get('/api/v1/cms/ai/prices')
    priceList.value = d.items ?? []
    priceKinds.value = d.kinds ?? []
  } catch (e: any) {
    priceErr.value = e?.response?.data?.detail || t("aiUsage.加载单价_36y8mr")
  } finally {
    priceBusy.value = false
  }
}

function blankDraft() {
  draft.value = {
    provider: '',
    model: '',
    kind: '',
    unit: 'token',
    input_per_m: '',
    output_per_m: '',
    cache_per_m: '',
    note: '',
  }
}

/** 把「还没定价」的调用一键带进表单，省得手打模型名打错 */
function fillDraft(c: { provider: string; model: string }) {
  blankDraft()
  draft.value.provider = c.provider
  draft.value.model = c.model
  priceErr.value = ''
  priceOk.value = ''
}

function editRule(r: PriceRule) {
  draft.value = {
    provider: r.provider,
    model: r.model,
    kind: r.kind,
    unit: r.unit || 'token',
    input_per_m: r.input_per_m,
    output_per_m: r.output_per_m,
    cache_per_m: r.cache_per_m === null || r.cache_per_m === undefined ? '' : r.cache_per_m,
    note: r.note,
  }
  priceErr.value = ''
  priceOk.value = ''
}

async function savePrice() {
  const isUnit = draft.value.unit !== 'token'
  const tin = Number(draft.value.input_per_m) || 0
  const tout = isUnit ? 0 : Number(draft.value.output_per_m) || 0
  if (tin < 0 || tout < 0) {
    priceErr.value = t("aiUsage.单价不能_1d8h14")
    return
  }
  const rawCache = draft.value.cache_per_m
  const hasCache = rawCache !== '' && rawCache !== null && rawCache !== undefined
  const cache = hasCache ? Number(rawCache) : null
  if (cache !== null && (Number.isNaN(cache) || cache < 0)) {
    priceErr.value = t("aiUsage.缓存单价_5wqta2")
    return
  }
  priceBusy.value = true
  priceErr.value = ''
  priceOk.value = ''
  try {
    await api.put('/api/v1/cms/ai/prices', {
      provider: draft.value.provider.trim(),
      model: draft.value.model.trim(),
      kind: draft.value.kind.trim(),
      unit: draft.value.unit,
      input_per_m: tin,
      output_per_m: tout,
      // 空字符串 = 未配置（缓存按输入价计）；填 0 = 缓存真的免费
      cache_per_m: hasCache ? cache : null,
      note: draft.value.note,
    })
    priceOk.value = '已保存，新调用按新价记账'
    blankDraft()
    await loadPrices()
    await load()
  } catch (e: any) {
    priceErr.value = e?.response?.data?.detail || t("aiMemory.saveFailed")
  } finally {
    priceBusy.value = false
  }
}

async function removePrice(r: PriceRule) {
  priceBusy.value = true
  priceErr.value = ''
  priceOk.value = ''
  try {
    await api.delete(`/api/v1/cms/ai/prices/${r.id}`)
    priceOk.value = t("aiUsage.已删除_e65yu")
    await loadPrices()
    await load()
  } catch (e: any) {
    priceErr.value = e?.response?.data?.detail || t("aiMemory.删除失败_azdahk")
  } finally {
    priceBusy.value = false
  }
}

/**
 * 重算历史成本。只在「单价一开始填错了」时用 —— 平时改价不该动历史，
 * 否则上个月的账单这个月会变，对账没法做。所以做成显式按钮。
 */
async function recalcCosts() {
  if (!confirm(t("aiUsage.用当前单_128dbe"))) {
    return
  }
  recalcBusy.value = true
  priceErr.value = ''
  priceOk.value = ''
  try {
    const { data: d } = await api.post('/api/v1/cms/ai/prices/recalc')
    priceOk.value = `已重算 ${d.updated} 条（扫描 ${d.scanned} 条，${d.unpriced} 条无单价）`
    await load()
  } catch (e: any) {
    priceErr.value = e?.response?.data?.detail || t("aiUsage.重算失败_iwkk5a")
  } finally {
    recalcBusy.value = false
  }
}

function pickDays(d: number) {
  if (days.value === d) return
  days.value = d
  load()
}

onMounted(load)
</script>

<template>
  <div class="p-6 max-w-[1200px] mx-auto space-y-6">
    <div class="flex items-center gap-3 flex-wrap">
      <div>
        <h1 class="text-xl font-semibold text-ink-900">{{ t("aiUsage.text_11mmjj") }}</h1>
        <p class="text-xs text-ink-500 mt-0.5">
          {{ t("aiUsage.调用次数_1gzj7h") }}
        </p>
      </div>
      <div class="ml-auto flex items-center gap-2">
        <button
          class="px-3 py-1.5 text-xs rounded-lg border border-ink-200 bg-white text-ink-600 hover:bg-ink-50"
          @click="openPrices"
        >{{ t("aiUsage.单价设置_aumhpu") }}</button>
        <button
          v-for="o in DAY_OPTIONS"
          :key="o.days"
          class="px-3 py-1.5 text-xs rounded-lg border transition"
          :class="days === o.days
            ? 'bg-ink-900 text-white border-ink-900'
            : 'bg-white text-ink-600 border-ink-200 hover:bg-ink-50'"
          @click="pickDays(o.days)"
        >{{ o.label }}</button>
      </div>
    </div>

    <p v-if="errorMsg" class="text-sm text-red-600 bg-red-50 border border-red-200 rounded-lg px-3 py-2">
      {{ errorMsg }}
    </p>

    <div v-if="loading && !data" class="text-sm text-ink-400 py-12 text-center">{{ t("apiKeys.加载中_b0k5km") }}</div>

    <template v-if="data">
      <p
        v-if="!data.enabled"
        class="text-sm text-amber-700 bg-amber-50 border border-amber-200 rounded-lg px-3 py-2"
      >
        {{ t("aiUsage.当前没有_1bad3k") }}
        <router-link to="/cms/ai-settings" class="underline underline-offset-2">{{ t("aiUsage.text_bal853") }}</router-link>
        {{ t("aiUsage.接一个_cw8z0z") }}
      </p>

      <!-- KPI：token 一律拆成未命中/缓存/输出三段，合成一个数字就看不出缓存效果 -->
      <div class="grid grid-cols-2 lg:grid-cols-3 xl:grid-cols-6 gap-3">
        <div class="card !p-4">
          <div class="text-xs text-ink-500">{{ t("aiUsage.调用次数_i5f6b8") }}</div>
          <div class="text-2xl font-semibold text-ink-900 mt-1 tabular-nums">
            {{ data.total_calls.toLocaleString('zh-CN') }}
          </div>
          <div class="text-[11px] mt-1 flex items-center gap-1.5">
            <span
              v-if="delta(data.total_calls, data.prev.calls)"
              class="px-1 py-px rounded bg-ink-100 text-ink-600 tabular-nums"
            >{{ delta(data.total_calls, data.prev.calls) }}</span>
            <span class="text-ink-400">{{ $t('aiUsage.较上_ou7b') }} {{ data.days }} {{ $t('aiUsage.天_hm1') }}</span>
          </div>
        </div>

        <div class="card !p-4">
          <div class="text-xs text-ink-500">{{ t("aiUsage.输入_riahe3") }}</div>
          <div class="text-2xl font-semibold text-ink-900 mt-1 tabular-nums">
            {{ fmt(data.total_tokens_in - data.total_tokens_cache) }}
          </div>
          <div class="text-[11px] text-ink-400 mt-1">
            {{ $t('aiUsage.全价计费_oz7e6l') }} {{ fmt(data.total_tokens_in) }}
          </div>
        </div>

        <div class="card !p-4">
          <div class="text-xs text-ink-500 flex items-center gap-1">
            {{ t("aiUsage.缓存命中_gesalx") }}
            <span
              v-if="data.total_tokens_cache > 0"
              class="px-1 py-px rounded bg-emerald-100 text-emerald-700 text-[10px] tabular-nums"
            >{{ pct(data.cache_hit_rate) }}</span>
          </div>
          <div class="text-2xl font-semibold mt-1 tabular-nums"
               :class="data.total_tokens_cache > 0 ? 'text-emerald-600' : 'text-ink-900'">
            {{ fmt(data.total_tokens_cache) }}
          </div>
          <div class="text-[11px] mt-1 flex items-center gap-1.5">
            <template v-if="data.total_cache_saved > 0">
              <span class="text-emerald-600">{{ $t('aiUsage.省_ni9') }} {{ currencySymbol(data.currency) }}{{ fmtMoney(data.total_cache_saved) }}</span>
            </template>
            <span v-else class="text-ink-400">
              {{ data.total_tokens_in ? $t('aiUsage.未配缓存_jafssq') : $t('aiUsage.暂无记录_dd1mmb') }}
            </span>
          </div>
        </div>

        <div class="card !p-4">
          <div class="text-xs text-ink-500">{{ t("aiUsage.输出_cix3ds") }}</div>
          <div class="text-2xl font-semibold text-ink-900 mt-1 tabular-nums">
            {{ fmt(data.total_tokens_out) }}
          </div>
          <div class="text-[11px] text-ink-400 mt-1">
            {{ $t('aiUsage.约_p0m') }} {{ data.total_calls ? fmt(Math.round(data.total_tokens_out / data.total_calls)) : 0 }} {{ $t('aiUsage.text_1ks0') }}
          </div>
        </div>

        <!-- 成本必须标清「是否全量定价」：只算出部分金额却显示成总额，比不显示更误导 -->
        <div class="card !p-4">
          <div class="text-xs text-ink-500 flex items-center gap-1">
            {{ t("aiUsage.预估成本_jklcnc") }}
            <span
              v-if="!data.priced"
              class="px-1 py-px rounded bg-amber-100 text-amber-700 text-[10px]"
            >{{ t("aiUsage.部分_p3j2") }}</span>
          </div>
          <div
            class="text-2xl font-semibold mt-1 tabular-nums"
            :class="data.priced ? 'text-ink-900' : 'text-ink-500'"
          >
            <template v-if="data.priced_calls > 0">
              <span class="text-base mr-0.5">{{ currencySymbol(data.currency) }}</span>{{ fmtMoney(data.total_cost) }}
            </template>
            <template v-else>{{ t("aiUsage.未配置_fte97") }}</template>
          </div>
          <div class="text-[11px] mt-1 flex items-center gap-1.5">
            <span
              v-if="delta(data.total_cost, data.prev.cost)"
              class="px-1 py-px rounded bg-ink-100 text-ink-600 tabular-nums"
            >{{ delta(data.total_cost, data.prev.cost) }}</span>
            <span v-if="data.unpriced_calls" class="text-amber-600">
              {{ data.unpriced_calls }} {{ $t('aiUsage.次未定价_dxzj46') }}
            </span>
            <span v-else-if="data.estimated" class="text-ink-400">
              {{ data.estimated_calls }} {{ $t('aiUsage.次按现价_xd5gf5') }}
            </span>
            <span v-else class="text-ink-400">{{ t("aiUsage.已覆盖全_zmcnb") }}</span>
          </div>
        </div>

        <div class="card !p-4">
          <div class="text-xs text-ink-500">{{ t("aiUsage.缓存命中_bildv6") }}</div>
          <div class="text-2xl font-semibold text-ink-900 mt-1 tabular-nums">
            {{ data.total_tokens_in ? pct(data.cache_hit_rate) : '—' }}
          </div>
          <div class="text-[11px] mt-1 flex items-center gap-1.5">
            <span
              v-if="delta(data.cache_hit_rate, data.prev.cache_hit_rate)"
              class="px-1 py-px rounded bg-ink-100 text-ink-600 tabular-nums"
            >{{ delta(data.cache_hit_rate, data.prev.cache_hit_rate) }}</span>
            <span class="text-ink-400">{{ t("aiUsage.占输入_18426q") }}</span>
          </div>
        </div>
      </div>

      <!-- 趋势：三段堆叠柱，一眼看出「哪天花得多、花在哪个环节」 -->
      <div class="card">
        <div class="flex items-center gap-3 flex-wrap mb-3">
          <h2 class="text-sm font-semibold text-ink-900">{{ t("aiUsage.每日用量_e10nj1") }}</h2>
          <div class="flex items-center gap-3 text-[11px] text-ink-500 ml-2">
            <span class="flex items-center gap-1">
              <i class="w-2.5 h-2.5 rounded-sm bg-ink-300 inline-block"></i>{{ t("aiUsage.未命中输_1n7hva") }}
            </span>
            <span class="flex items-center gap-1">
              <i class="w-2.5 h-2.5 rounded-sm bg-emerald-400 inline-block"></i>{{ t("aiUsage.缓存命中_gesalx") }}
            </span>
            <span class="flex items-center gap-1">
              <i class="w-2.5 h-2.5 rounded-sm bg-ink-900 inline-block"></i>{{ t("aiUsage.输出_ovd3") }}
            </span>
          </div>
          <span class="ml-auto text-[11px] text-ink-400">
            {{ t("aiUsage.柱高_52sgf8") }}
          </span>
        </div>

        <div v-if="!trendHasData" class="py-12 text-center text-sm text-ink-400">
          {{ t("aiUsage.这段时间_1opuel") }}
        </div>

        <div v-else>
          <div class="flex items-end gap-px h-36 border-b border-ink-100">
            <div
              v-for="(d, i) in data.trend"
              :key="d.date"
              class="flex-1 flex flex-col justify-end group relative h-full"
              :title="`${d.date}
调用 ${d.calls} 次
输入 ${d.tokens_in.toLocaleString()}（缓存 ${d.tokens_cache.toLocaleString()}，${pct(d.cache_hit_rate)}）
输出 ${d.tokens_out.toLocaleString()}
成本 ${currencySymbol(data.currency)}${fmtMoney(d.cost)}`"
            >
              <div
                class="w-full bg-ink-900 opacity-0 group-hover:opacity-100 transition-opacity absolute inset-0 pointer-events-none"
              ></div>
              <div class="w-full bg-ink-900 group-hover:opacity-90"
                   :style="{ height: barH(d.tokens_out) }"></div>
              <div class="w-full bg-emerald-400 group-hover:opacity-90"
                   :style="{ height: barH(d.tokens_cache) }"></div>
              <div class="w-full bg-ink-300 group-hover:opacity-90"
                   :style="{ height: barH(Math.max(0, d.tokens_in - d.tokens_cache)) }"></div>
            </div>
          </div>
          <div class="flex gap-px mt-1.5">
            <div
              v-for="(d, i) in data.trend"
              :key="`x-${d.date}`"
              class="flex-1 text-[10px] text-ink-400 text-center whitespace-nowrap overflow-visible"
            >
              <span v-if="showDate(i, data.trend.length)">{{ d.date.slice(5) }}</span>
            </div>
          </div>
        </div>
      </div>

      <!-- 明细 -->
      <div class="card">
        <div class="flex items-center gap-3 flex-wrap mb-3">
          <h2 class="text-sm font-semibold text-ink-900">{{ t("aiUsage.按能力类_1coxju") }}</h2>
          <span class="text-xs text-ink-400">{{ $t('aiUsage.共_g35') }} {{ rows.length }} {{ $t('aiUsage.类_ol7') }}</span>
          <div class="ml-auto flex items-center gap-1 text-xs">
            <span class="text-ink-400 mr-1">{{ t("aiUsage.排序_hge5") }}</span>
            <button
              v-for="s in [
                { k: 'tokens', label: 'token' },
                { k: 'cache', label: '缓存' },
                { k: 'calls', label: '调用' },
                { k: 'cost', label: '金额' },
                { k: 'latency', label: '延迟' },
              ]"
              :key="s.k"
              class="px-2 py-1 rounded border transition"
              :class="sortKey === (s.k as any)
                ? 'bg-ink-900 text-white border-ink-900'
                : 'bg-white text-ink-600 border-ink-200 hover:bg-ink-50'"
              @click="sortKey = s.k as any"
            >{{ s.label }}</button>
          </div>
        </div>

        <div v-if="!rows.length" class="py-16 text-center text-sm text-ink-400">
          {{ t("aiUsage.这段时间_15sqkn") }}
        </div>

        <div v-else class="overflow-x-auto">
          <table class="w-full text-sm">
            <thead>
              <tr class="text-xs text-ink-400 border-b border-ink-100">
                <th class="text-left font-normal py-2 pr-3">{{ t("aiUsage.能力_me66") }}</th>
                <th class="text-right font-normal py-2 px-2 whitespace-nowrap">{{ t("aiUsage.调用_oghx") }}</th>
                <th class="text-right font-normal py-2 px-2 whitespace-nowrap">{{ t("aiUsage.输入_riahe3") }}</th>
                <th class="text-right font-normal py-2 px-2 whitespace-nowrap">{{ t("aiUsage.缓存命中_gesalx") }}</th>
                <th class="text-right font-normal py-2 px-2 whitespace-nowrap">{{ t("aiUsage.输出_cix3ds") }}</th>
                <th class="text-right font-normal py-2 px-2 whitespace-nowrap">{{ t("aiUsage.平均延迟_ca41ct") }}</th>
                <th class="text-right font-normal py-2 px-2 whitespace-nowrap">{{ t("aiUsage.金额_pn1o") }}</th>
                <th class="text-left font-normal py-2 pl-2 w-[16%]">{{ t("aiUsage.text_1gsb3s") }}</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="r in rows" :key="r.kind" class="border-b border-ink-50 last:border-0">
                <td class="py-2.5 pr-3">
                  <span class="text-ink-900">{{ kindLabel(r.kind) }}</span>
                  <span v-if="kindLabel(r.kind) !== r.kind" class="ml-1.5 text-[10px] text-ink-300">{{ r.kind }}</span>
                  <div
                    v-if="r.models && r.models.length"
                    class="text-[10px] text-ink-300 truncate max-w-[200px]"
                    :title="r.models.map((m) => `${m.provider}/${m.model || '未记录'}`).join('、')"
                  >
                    {{ r.models.map((m) => m.model || m.provider || $t('aiUsage.未记录_fs9jj')).join(' / ') }}
                  </div>
                </td>
                <td class="py-2.5 px-2 text-right text-ink-700 tabular-nums">
                  {{ r.calls.toLocaleString('zh-CN') }}
                  <div class="text-[10px] text-ink-300 tabular-nums">
                    {{ $t('aiUsage.均_h8n') }} {{ fmt(r.avg_tokens_in) }} in
                  </div>
                </td>
                <td class="py-2.5 px-2 text-right text-ink-700 tabular-nums">
                  {{ fmt(r.tokens_in) }}
                  <div v-if="r.tokens_cache" class="text-[10px] text-ink-300 tabular-nums">
                    {{ $t('aiUsage.全价_ea33') }} {{ fmt(r.tokens_uncached) }}
                  </div>
                </td>
                <td class="py-2.5 px-2 text-right tabular-nums">
                  <template v-if="r.tokens_cache">
                    <span class="text-emerald-600">{{ fmt(r.tokens_cache) }}</span>
                    <div class="text-[10px] text-emerald-500/80">{{ pct(r.cache_hit_rate) }}</div>
                  </template>
                  <span v-else class="text-ink-300">—</span>
                </td>
                <td class="py-2.5 px-2 text-right text-ink-700 tabular-nums">{{ fmt(r.tokens_out) }}</td>
                <td class="py-2.5 px-2 text-right text-ink-500 tabular-nums">
                  {{ r.avg_latency_ms ? fmtMs(r.avg_latency_ms) : '—' }}
                </td>
                <td class="py-2.5 px-2 text-right tabular-nums">
                  <template v-if="r.priced_calls > 0">
                    <span class="text-ink-900">{{ currencySymbol(data.currency) }}{{ fmtMoney(r.cost) }}</span>
                    <div v-if="r.unpriced_calls" class="text-[10px] text-amber-600">
                      {{ r.unpriced_calls }} {{ $t('aiUsage.次未定价_dxzj46') }}
                    </div>
                    <div v-else-if="r.cache_saved > 0" class="text-[10px] text-emerald-600">
                      {{ $t('aiUsage.省_ni9') }} {{ fmtMoney(r.cache_saved) }}
                    </div>
                  </template>
                  <span v-else class="text-[11px] text-ink-300">{{ t("aiUsage.未配置_fte97") }}</span>
                </td>
                <td class="py-2.5 pl-2">
                  <div class="flex items-center gap-1.5">
                    <div class="flex-1 h-1.5 rounded-full bg-ink-100 overflow-hidden">
                      <div
                        class="h-full bg-ink-900"
                        :style="{ width: `${Math.max(2, (r.total_tokens / maxTokens) * 100)}%` }"
                      ></div>
                    </div>
                    <span class="text-[11px] text-ink-400 tabular-nums w-9 text-right">
                      {{ data.total_tokens ? ((r.total_tokens / data.total_tokens) * 100).toFixed(0) : 0 }}%
                    </span>
                  </div>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      <p class="text-xs text-ink-400 leading-relaxed">
        {{ t("aiUsage.金额按_1wsp1t") }}
        <template v-if="tokenMix">
          {{ $t('aiUsage.本期_tk7hbm') }} {{ pct(tokenMix.uncached) }}{{ $t('aiUsage.text_1q1jui') }} {{ pct(tokenMix.cache) }}{{ $t('aiUsage.text_7pzt4') }} {{ pct(tokenMix.out) }}。
        </template>
        {{ t("aiUsage.只统计成_cdlntu") }}<span class="font-mono">status=ok</span>{{ $t('aiUsage.text_ndxm9w') }}
      </p>
    </template>

    <!-- 单价设置 -->
    <div
      v-if="priceOpen"
      class="fixed inset-0 z-50 bg-black/40 flex items-start justify-center p-4 overflow-y-auto"
      @click.self="priceOpen = false"
    >
      <div class="bg-white rounded-xl w-full max-w-[820px] my-8 shadow-xl">
        <div class="flex items-center gap-3 px-5 py-3.5 border-b border-ink-100">
          <h2 class="font-semibold text-ink-900 text-sm">{{ t("aiUsage.text_5iq0bu") }}</h2>
          <span class="text-xs text-ink-400">{{ t("aiUsage.按每百万_gd4fwz") }}</span>
          <button
            class="ml-auto text-ink-400 hover:text-ink-700 text-xl leading-none"
            @click="priceOpen = false"
          >×</button>
        </div>

        <div class="p-5 space-y-4">
          <div v-if="unpricedCombos.length" class="rounded-lg border border-amber-200 bg-amber-50 p-3">
            <div class="text-xs text-amber-800 mb-2">{{ t("aiUsage.这些调用_ri2r6q") }}</div>
            <div class="flex flex-wrap gap-1.5">
              <button
                v-for="c in unpricedCombos"
                :key="`${c.kind}-${c.provider}-${c.model}`"
                class="px-2 py-1 text-xs rounded border border-amber-300 bg-white hover:bg-amber-100"
                @click="fillDraft(c)"
              >{{ c.model || c.provider || $t('aiUsage.未记录_fs9jj') }} · {{ kindLabel(c.kind) }} · {{ c.calls }} {{ $t('aiUsage.次_l5t') }}</button>
            </div>
          </div>

          <div class="grid grid-cols-2 gap-3">
            <label class="text-xs text-ink-600">
              {{ t("aiUsage.服务商_fhwnm") }}
              <input
                v-model="draft.provider"
                class="mt-1 w-full px-2.5 py-1.5 text-sm rounded-lg border border-ink-200 focus:outline-none focus:ring-2 focus:ring-ink-900/10"
                :placeholder="t('aiUsage.留空_17ypxo')"
              />
            </label>
            <label class="text-xs text-ink-600">
              {{ t("aiUsage.模型_ij62") }}
              <input
                v-model="draft.model"
                class="mt-1 w-full px-2.5 py-1.5 text-sm rounded-lg border border-ink-200 focus:outline-none focus:ring-2 focus:ring-ink-900/10"
                placeholder="MiniMax-M3.1-Flash"
              />
            </label>
            <label class="text-xs text-ink-600 col-span-2">
              {{ t("aiUsage.计价单位_hxz1qm") }}
              <select
                v-model="draft.unit"
                class="mt-1 w-full px-2.5 py-1.5 text-sm rounded-lg border border-ink-200 bg-white focus:outline-none focus:ring-2 focus:ring-ink-900/10"
              >
                <option v-for="u in UNIT_OPTIONS" :key="u.v" :value="u.v">{{ u.t }}</option>
              </select>
              <span v-if="draft.unit !== 'token'" class="block mt-1 text-[11px] text-ink-400">
                {{ $t('aiUsage.按_jk9') }}{{ draft.unit === 'image' ? $t('aiUsage.张_isg') : $t('aiUsage.条_kf5') }}{{ $t('aiUsage.计费_1o63k9') }}{{ draft.unit === 'image' ? $t('aiUsage.张_isg') : $t('aiUsage.条_kf5') }}{{ $t('aiUsage.价格_c2dfh') }}
              </span>
            </label>
            <label class="text-xs text-ink-600">
              {{ draft.unit === 'image' ? $t('aiUsage.单张单价_kfx702') : draft.unit === 'video' ? $t('aiUsage.单条单价_178uvz') : $t('aiUsage.输入单价_1gzny6') }}
              <input
                v-model="draft.input_per_m"
                type="number"
                min="0"
                step="0.0001"
                class="mt-1 w-full px-2.5 py-1.5 text-sm rounded-lg border border-ink-200 focus:outline-none focus:ring-2 focus:ring-ink-900/10"
                placeholder="0"
              />
            </label>
            <label v-if="draft.unit === 'token'" class="text-xs text-ink-600">
              {{ t("aiUsage.输出单价_1dchro") }}
              <input
                v-model="draft.output_per_m"
                type="number"
                min="0"
                step="0.0001"
                class="mt-1 w-full px-2.5 py-1.5 text-sm rounded-lg border border-ink-200 focus:outline-none focus:ring-2 focus:ring-ink-900/10"
                placeholder="0"
              />
            </label>
            <label v-if="draft.unit === 'token'" class="text-xs text-ink-600 col-span-2">
              {{ t("aiUsage.缓存命中_nxi8g8") }}
              <input
                v-model="draft.cache_per_m"
                type="number"
                min="0"
                step="0.0001"
                class="mt-1 w-full px-2.5 py-1.5 text-sm rounded-lg border border-ink-200 focus:outline-none focus:ring-2 focus:ring-ink-900/10"
                :placeholder="t('aiUsage.留空_1a991j')"
              />
              <span class="block mt-1 text-[11px] text-ink-400 leading-relaxed">
                {{ $t('aiUsage.留空表示_1vw155') }}
              </span>
            </label>
            <label class="text-xs text-ink-600 col-span-2">
              {{ t("aiUsage.能力类型_1iiak7") }}
              <select
                v-model="draft.kind"
                class="mt-1 w-full px-2.5 py-1.5 text-sm rounded-lg border border-ink-200 bg-white focus:outline-none focus:ring-2 focus:ring-ink-900/10"
              >
                <option value="">{{ t("aiUsage.任意_dyt0") }}</option>
                <option v-for="k in priceKinds" :key="k" :value="k">{{ kindLabel(k) }}（{{ k }}）</option>
              </select>
            </label>
            <label class="text-xs text-ink-600 col-span-2">
              {{ t("aiUsage.备注_fqo1") }}
              <input
                v-model="draft.note"
                class="mt-1 w-full px-2.5 py-1.5 text-sm rounded-lg border border-ink-200 focus:outline-none focus:ring-2 focus:ring-ink-900/10"
                :placeholder="t('aiUsage.如_yio6fi')"
              />
            </label>
          </div>

          <div class="flex items-center gap-2 flex-wrap">
            <button
              class="px-3 py-1.5 text-sm rounded-lg bg-ink-900 text-white hover:bg-ink-800 disabled:opacity-50"
              :disabled="priceBusy"
              @click="savePrice"
            >{{ t("aiUsage.保存_e32z") }}</button>
            <button
              class="px-3 py-1.5 text-sm rounded-lg border border-ink-200 text-ink-600 hover:bg-ink-50 disabled:opacity-50"
              :disabled="recalcBusy"
              @click="recalcCosts"
            >{{ recalcBusy ? $t('aiUsage.重算中_iwi35v') : $t('aiUsage.重算历史_1hngy4') }}</button>
            <span v-if="priceErr" class="text-xs text-red-600">{{ priceErr }}</span>
            <span v-else-if="priceOk" class="text-xs text-emerald-600">{{ priceOk }}</span>
          </div>

          <div class="pt-2 border-t border-ink-100">
            <div class="text-xs text-ink-500 mb-2">{{ $t('aiUsage.已配置_egsab') }} {{ priceList.length }} {{ $t('aiUsage.条规则_fszxy') }}</div>
            <div v-if="!priceList.length" class="text-xs text-ink-400 py-4 text-center">
              {{ t("aiUsage.还没有任_1hjqtp") }}
            </div>
            <table v-else class="w-full text-xs">
              <thead>
                <tr class="text-ink-400 border-b border-ink-100">
                  <th class="text-left font-normal py-1.5">{{ t("aiUsage.匹配_eyb8") }}</th>
                  <th class="text-right font-normal py-1.5 px-2">{{ t("aiUsage.输入_ov8y") }}</th>
                  <th class="text-right font-normal py-1.5 px-2">{{ t("aiUsage.输出_ovd3") }}</th>
                  <th class="text-right font-normal py-1.5 px-2">{{ t("aiUsage.缓存_m46d") }}</th>
                  <th class="text-left font-normal py-1.5 px-2">{{ t("aiUsage.备注_fqo1") }}</th>
                  <th class="py-1.5"></th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="r in priceList" :key="r.id" class="border-b border-ink-50 last:border-0">
                  <td class="py-1.5">
                    <span class="font-mono text-ink-700">{{ r.provider || '*' }} / {{ r.model || '*' }}</span>
                    <span v-if="r.kind" class="ml-1 text-ink-400">@{{ kindLabel(r.kind) }}</span>
                  </td>
                  <td class="py-1.5 px-2 text-right tabular-nums whitespace-nowrap">
                    {{ r.input_per_m }}<span class="text-ink-400 text-[10px] ml-0.5">{{ r.unit === 'token' ? '/M' : r.unit === 'image' ? $t('aiUsage.text_jwx') : $t('aiUsage.text_ljm') }}</span>
                  </td>
                  <td class="py-1.5 px-2 text-right tabular-nums">
                    {{ r.unit === 'token' ? r.output_per_m : '—' }}
                  </td>
                  <td class="py-1.5 px-2 text-right tabular-nums whitespace-nowrap">
                    <span v-if="r.unit !== 'token'" class="text-ink-300">—</span>
                    <span v-else-if="r.cache_per_m === null" class="text-ink-300">{{ t("aiUsage.同输入价_b71u2h") }}</span>
                    <span v-else class="text-emerald-600">{{ r.cache_per_m }}</span>
                  </td>
                  <td class="py-1.5 px-2 text-ink-400">{{ r.note || '—' }}</td>
                  <td class="py-1.5 text-right whitespace-nowrap">
                    <button class="text-ink-500 hover:text-ink-900" @click="editRule(r)">{{ t("aiUsage.改_jzt") }}</button>
                    <button class="ml-2 text-red-500 hover:text-red-700" @click="removePrice(r)">{{ t("aiUsage.删_g80") }}</button>
                  </td>
                </tr>
              </tbody>
            </table>
            <p class="text-[11px] text-ink-400 mt-2 leading-relaxed">
              {{ t("aiUsage.text_1wmped") }}<br />
              {{ t("aiUsage.改价只影_1exrc5") }}<span class="text-ink-600">{{ t("aiUsage.之后_ds0z") }}</span>{{ t("aiUsage.的调用_1j6pzt") }}
            </p>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>
