<script setup lang="ts">
/**
 * AI 用量与成本页。
 *
 * 驾驶舱只给「今日/本周/本月调用次数」，看不出烧钱速度 —— 一次批量起草几十篇，
 * 次数看着不多，token 可能已经翻了几倍。这里按能力类型拆开，谁在消耗、消耗在输入
 * 还是输出，一眼能看见。
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
  cost: number | null
}

interface UsageItem {
  kind: string
  calls: number
  tokens_in: number
  tokens_out: number
  avg_latency_ms: number
  cost: number
  priced: boolean
  priced_calls: number
  unpriced_calls: number
  models: ModelCost[]
}

interface Usage {
  days: number
  enabled: boolean
  embed_ready: boolean
  items: UsageItem[]
  total_calls: number
  total_tokens: number
  total_cost: number
  priced: boolean
  priced_calls: number
  unpriced_calls: number
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
  illustration: '配图提示词',
  image: '配图生成',
  ab_run: '模型 A/B',
  qa_ask: '问答检索',
  topic_gap: '选题缺口',
}

const UNIT_OPTIONS = [
  { v: 'token', t: '按 token 计（每百万 token 单价）' },
  { v: 'image', t: '按张计（每次调用单价）' },
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
const sortKey = ref<'tokens' | 'calls' | 'latency'>('tokens')

// ---- 单价设置 ----
const priceOpen = ref(false)
const priceList = ref<PriceRule[]>([])
const priceKinds = ref<string[]>([])
const priceBusy = ref(false)
const priceErr = ref('')
const priceOk = ref('')
const draft = ref({
  provider: '',
  model: '',
  kind: '',
  unit: 'token',
  input_per_m: '' as string | number,
  output_per_m: '' as string | number,
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
  if (c === 'mixed') return '多币种'
  if (c === 'USD') return '$'
  if (c === 'EUR') return '€'
  return '¥'
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
  }))
  const key = sortKey.value
  return list.sort((a, b) => {
    if (key === 'calls') return b.calls - a.calls
    if (key === 'latency') return b.avg_latency_ms - a.avg_latency_ms
    return b.total_tokens - a.total_tokens
  })
})

const maxTokens = computed(() => Math.max(1, ...rows.value.map((r) => r.total_tokens)))

/** 全站平均延迟按调用次数加权，不能对各行 avg 直接取平均 */
const avgLatency = computed(() => {
  const list = data.value?.items ?? []
  const calls = list.reduce((s, r) => s + r.calls, 0)
  if (!calls) return 0
  return Math.round(list.reduce((s, r) => s + r.avg_latency_ms * r.calls, 0) / calls)
})

/** 输入/输出比例：输入 token 一般是提示词（含检索到的上下文），偏高说明检索塞太多 */
const ioRatio = computed(() => {
  const tin = data.value?.items.reduce((s, r) => s + r.tokens_in, 0) ?? 0
  const tout = data.value?.items.reduce((s, r) => s + r.tokens_out, 0) ?? 0
  const all = tin + tout
  if (!all) return null
  return { in: tin / all, out: tout / all, tin, tout }
})

async function load() {
  loading.value = true
  errorMsg.value = ''
  try {
    const { data: d } = await api.get<Usage>('/api/v1/cms/ai/usage', {
      params: { days: days.value },
    })
    data.value = d
  } catch (e: any) {
    errorMsg.value = e?.response?.data?.detail || e?.message || '加载失败'
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
    priceErr.value = e?.response?.data?.detail || '加载单价失败'
  } finally {
    priceBusy.value = false
  }
}

/** 把「还没定价」的调用一键带进表单，省得手打模型名打错 */
function fillDraft(c: { provider: string; model: string }) {
  draft.value = {
    provider: c.provider,
    model: c.model,
    kind: '',
    unit: 'token',
    input_per_m: '',
    output_per_m: '',
    note: '',
  }
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
    note: r.note,
  }
  priceErr.value = ''
  priceOk.value = ''
}

async function savePrice() {
  const isImage = draft.value.unit === 'image'
  const tin = Number(draft.value.input_per_m) || 0
  const tout = isImage ? 0 : Number(draft.value.output_per_m) || 0
  if (tin < 0 || tout < 0) {
    priceErr.value = '单价不能为负'
    return
  }
  if (!tin && !tout) {
    priceErr.value = '至少填一个非零单价，否则金额恒为 0'
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
      note: draft.value.note,
    })
    priceOk.value = '已保存，金额已重算'
    draft.value = {
      provider: '',
      model: '',
      kind: '',
      unit: 'token',
      input_per_m: '',
      output_per_m: '',
      note: '',
    }
    await loadPrices()
    await load() // 金额立刻跟着变，不用手动刷新
  } catch (e: any) {
    priceErr.value = e?.response?.data?.detail || '保存失败'
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
    priceOk.value = '已删除'
    await loadPrices()
    await load()
  } catch (e: any) {
    priceErr.value = e?.response?.data?.detail || '删除失败'
  } finally {
    priceBusy.value = false
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
        <h1 class="text-xl font-semibold text-ink-900">AI 用量</h1>
        <p class="text-xs text-ink-500 mt-0.5">
          按能力类型拆分的调用次数与 token 消耗 · 数据来自真实调用记账
        </p>
      </div>
      <div class="ml-auto flex items-center gap-2">
        <button
          class="px-3 py-1.5 text-xs rounded-lg border border-ink-200 bg-white text-ink-600 hover:bg-ink-50"
          @click="openPrices"
        >单价设置</button>
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

    <div v-if="loading && !data" class="text-sm text-ink-400 py-12 text-center">加载中…</div>

    <template v-if="data">
      <!-- 未配置对话模型时，全零会被误读成「没花过钱」，必须说清楚 -->
      <p
        v-if="!data.enabled"
        class="text-sm text-amber-700 bg-amber-50 border border-amber-200 rounded-lg px-3 py-2"
      >
        当前没有可用的对话模型，所以不会有新的用量记账。去
        <router-link to="/cms/ai-settings" class="underline underline-offset-2">AI 能力配置</router-link>
        接一个。
      </p>

      <div class="grid grid-cols-2 lg:grid-cols-5 gap-4">
        <div class="card !p-5">
          <div class="text-xs text-ink-500">调用次数</div>
          <div class="text-3xl font-semibold text-ink-900 mt-1">{{ data.total_calls.toLocaleString('zh-CN') }}</div>
          <div class="text-xs text-ink-400 mt-1">近 {{ data.days }} 天</div>
        </div>
        <div class="card !p-5">
          <div class="text-xs text-ink-500">总 token</div>
          <div class="text-3xl font-semibold text-ink-900 mt-1">{{ fmt(data.total_tokens) }}</div>
          <div class="text-xs text-ink-400 mt-1">输入 + 输出</div>
        </div>
        <!-- 成本必须标清「是否全量定价」：只算出部分金额却显示成总额，比不显示更误导 -->
        <div class="card !p-5">
          <div class="text-xs text-ink-500 flex items-center gap-1">
            预估成本
            <span
              v-if="!data.priced"
              class="px-1 py-px rounded bg-amber-100 text-amber-700 text-[10px]"
            >部分</span>
          </div>
          <div
            class="text-3xl font-semibold mt-1"
            :class="data.priced ? 'text-ink-900' : 'text-ink-500'"
          >
            <template v-if="data.priced_calls > 0">
              <span class="text-lg mr-0.5">{{ currencySymbol(data.currency) }}</span>{{ fmtMoney(data.total_cost) }}
            </template>
            <template v-else>未配置</template>
          </div>
          <div class="text-xs text-ink-400 mt-1">
            <template v-if="data.priced">已覆盖全部 {{ data.priced_calls }} 次调用</template>
            <template v-else-if="data.unpriced_calls">
              {{ data.unpriced_calls }} 次调用未定价
            </template>
            <template v-else>去「单价设置」填采购价</template>
          </div>
        </div>
        <div class="card !p-5">
          <div class="text-xs text-ink-500">平均延迟</div>
          <div class="text-3xl font-semibold text-ink-900 mt-1">{{ avgLatency ? fmtMs(avgLatency) : '—' }}</div>
          <div class="text-xs text-ink-400 mt-1">按调用次数加权</div>
        </div>
        <div class="card !p-5">
          <div class="text-xs text-ink-500">输入 / 输出</div>
          <div class="text-3xl font-semibold text-ink-900 mt-1">
            <template v-if="ioRatio">{{ Math.round(ioRatio.in * 100) }} / {{ Math.round(ioRatio.out * 100) }}</template>
            <template v-else>—</template>
          </div>
          <div class="text-xs text-ink-400 mt-1">百分比，输入偏高说明上下文塞得多</div>
        </div>
      </div>

      <!-- 明细 -->
      <div class="card">
        <div class="flex items-center gap-3 flex-wrap mb-3">
          <h2 class="text-sm font-semibold text-ink-900">按能力类型</h2>
          <span class="text-xs text-ink-400">共 {{ rows.length }} 类</span>
          <div class="ml-auto flex items-center gap-1 text-xs">
            <span class="text-ink-400 mr-1">排序</span>
            <button
              v-for="s in [
                { k: 'tokens', label: 'token' },
                { k: 'calls', label: '调用' },
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
          这段时间没有任何 AI 调用记录。
        </div>

        <div v-else class="overflow-x-auto">
          <table class="w-full text-sm">
            <thead>
              <tr class="text-xs text-ink-400 border-b border-ink-100">
                <th class="text-left font-normal py-2 pr-3">能力</th>
                <th class="text-right font-normal py-2 px-3 whitespace-nowrap">调用</th>
                <th class="text-right font-normal py-2 px-3 whitespace-nowrap">输入 token</th>
                <th class="text-right font-normal py-2 px-3 whitespace-nowrap">输出 token</th>
                <th class="text-right font-normal py-2 px-3 whitespace-nowrap">平均延迟</th>
                <th class="text-right font-normal py-2 px-3 whitespace-nowrap">金额</th>
                <th class="text-left font-normal py-2 pl-3 w-[22%]">token 占比</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="r in rows" :key="r.kind" class="border-b border-ink-50 last:border-0">
                <td class="py-2.5 pr-3">
                  <span class="text-ink-900">{{ kindLabel(r.kind) }}</span>
                  <span v-if="kindLabel(r.kind) !== r.kind" class="ml-1.5 text-[10px] text-ink-300">{{ r.kind }}</span>
                  <div
                    v-if="r.models && r.models.length"
                    class="text-[10px] text-ink-300 truncate max-w-[220px]"
                    :title="r.models.map((m) => `${m.provider}/${m.model || '未记录'}`).join('、')"
                  >
                    {{ r.models.map((m) => m.model || m.provider || '未记录').join(' / ') }}
                  </div>
                </td>
                <td class="py-2.5 px-3 text-right text-ink-700 tabular-nums">
                  {{ r.calls.toLocaleString('zh-CN') }}
                </td>
                <td class="py-2.5 px-3 text-right text-ink-700 tabular-nums">{{ fmt(r.tokens_in) }}</td>
                <td class="py-2.5 px-3 text-right text-ink-700 tabular-nums">{{ fmt(r.tokens_out) }}</td>
                <td class="py-2.5 px-3 text-right text-ink-500 tabular-nums">
                  {{ r.avg_latency_ms ? fmtMs(r.avg_latency_ms) : '—' }}
                </td>
                <td class="py-2.5 px-3 text-right tabular-nums">
                  <template v-if="r.priced_calls > 0">
                    <span class="text-ink-900">{{ currencySymbol(data.currency) }}{{ fmtMoney(r.cost) }}</span>
                    <div v-if="r.unpriced_calls" class="text-[10px] text-amber-600">
                      {{ r.unpriced_calls }} 次未定价
                    </div>
                  </template>
                  <span v-else class="text-[11px] text-ink-300">未配置</span>
                </td>
                <td class="py-2.5 pl-3">
                  <div class="flex items-center gap-2">
                    <div class="flex-1 h-1.5 rounded-full bg-ink-100 overflow-hidden">
                      <div
                        class="h-full bg-ink-900"
                        :style="{ width: `${Math.max(2, (r.total_tokens / maxTokens) * 100)}%` }"
                      ></div>
                    </div>
                    <span class="text-xs text-ink-400 tabular-nums w-11 text-right">
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
        金额按「单价设置」里填的采购价折算，系统不预置任何单价 —— 按假定单价算出来的数只会误导。
        只统计成功状态（<span class="font-mono">status=ok</span>）的调用，失败请求不计入 token。
        延迟是每次调用的真实耗时；记账改造之前的历史记录该列为 0，显示「—」。
      </p>
    </template>

    <!-- 单价设置 -->
    <div
      v-if="priceOpen"
      class="fixed inset-0 z-50 bg-black/40 flex items-start justify-center p-4 overflow-y-auto"
      @click.self="priceOpen = false"
    >
      <div class="bg-white rounded-xl w-full max-w-[760px] my-8 shadow-xl">
        <div class="flex items-center gap-3 px-5 py-3.5 border-b border-ink-100">
          <h2 class="font-semibold text-ink-900 text-sm">AI 单价设置</h2>
          <span class="text-xs text-ink-400">按每百万 token 的采购价填写</span>
          <button
            class="ml-auto text-ink-400 hover:text-ink-700 text-xl leading-none"
            @click="priceOpen = false"
          >×</button>
        </div>

        <div class="p-5 space-y-4">
          <div v-if="unpricedCombos.length" class="rounded-lg border border-amber-200 bg-amber-50 p-3">
            <div class="text-xs text-amber-800 mb-2">这些调用还没有单价，点一下自动填入模型名：</div>
            <div class="flex flex-wrap gap-1.5">
              <button
                v-for="c in unpricedCombos"
                :key="`${c.kind}-${c.provider}-${c.model}`"
                class="px-2 py-1 text-xs rounded border border-amber-300 bg-white hover:bg-amber-100"
                @click="fillDraft(c)"
              >{{ c.model || c.provider || '未记录' }} · {{ kindLabel(c.kind) }} · {{ c.calls }} 次</button>
            </div>
          </div>

          <div class="grid grid-cols-2 gap-3">
            <label class="text-xs text-ink-600">
              服务商
              <input
                v-model="draft.provider"
                class="mt-1 w-full px-2.5 py-1.5 text-sm rounded-lg border border-ink-200 focus:outline-none focus:ring-2 focus:ring-ink-900/10"
                placeholder="openai"
              />
            </label>
            <label class="text-xs text-ink-600">
              模型
              <input
                v-model="draft.model"
                class="mt-1 w-full px-2.5 py-1.5 text-sm rounded-lg border border-ink-200 focus:outline-none focus:ring-2 focus:ring-ink-900/10"
                placeholder="MiniMax-M3.1-Flash"
              />
            </label>
            <label class="text-xs text-ink-600 col-span-2">
              计价单位
              <select
                v-model="draft.unit"
                class="mt-1 w-full px-2.5 py-1.5 text-sm rounded-lg border border-ink-200 bg-white focus:outline-none focus:ring-2 focus:ring-ink-900/10"
              >
                <option v-for="u in UNIT_OPTIONS" :key="u.v" :value="u.v">{{ u.t }}</option>
              </select>
              <span v-if="draft.unit === 'image'" class="block mt-1 text-[11px] text-ink-400">
                生图按张计费，没有 token，所以只填单张价格。
              </span>
            </label>
            <label class="text-xs text-ink-600">
              {{ draft.unit === 'image' ? '单张单价（元 / 张）' : '输入单价（元 / 百万 token）' }}
              <input
                v-model="draft.input_per_m"
                type="number"
                min="0"
                step="0.0001"
                class="mt-1 w-full px-2.5 py-1.5 text-sm rounded-lg border border-ink-200 focus:outline-none focus:ring-2 focus:ring-ink-900/10"
                placeholder="0"
              />
            </label>
            <label v-if="draft.unit !== 'image'" class="text-xs text-ink-600">
              输出单价（元 / 百万 token）
              <input
                v-model="draft.output_per_m"
                type="number"
                min="0"
                step="0.0001"
                class="mt-1 w-full px-2.5 py-1.5 text-sm rounded-lg border border-ink-200 focus:outline-none focus:ring-2 focus:ring-ink-900/10"
                placeholder="0"
              />
            </label>
            <label class="text-xs text-ink-600 col-span-2">
              能力类型（留空 = 该模型的所有调用，通常留空即可）
              <select
                v-model="draft.kind"
                class="mt-1 w-full px-2.5 py-1.5 text-sm rounded-lg border border-ink-200 bg-white focus:outline-none focus:ring-2 focus:ring-ink-900/10"
              >
                <option value="">任意</option>
                <option v-for="k in priceKinds" :key="k" :value="k">{{ kindLabel(k) }}（{{ k }}）</option>
              </select>
            </label>
            <label class="text-xs text-ink-600 col-span-2">
              备注
              <input
                v-model="draft.note"
                class="mt-1 w-full px-2.5 py-1.5 text-sm rounded-lg border border-ink-200 focus:outline-none focus:ring-2 focus:ring-ink-900/10"
                placeholder="如：2026-10 官网报价"
              />
            </label>
          </div>

          <div class="flex items-center gap-2">
            <button
              class="px-3 py-1.5 text-sm rounded-lg bg-ink-900 text-white hover:bg-ink-800 disabled:opacity-50"
              :disabled="priceBusy"
              @click="savePrice"
            >保存</button>
            <span v-if="priceErr" class="text-xs text-red-600">{{ priceErr }}</span>
            <span v-else-if="priceOk" class="text-xs text-emerald-600">{{ priceOk }}</span>
          </div>

          <div class="pt-2 border-t border-ink-100">
            <div class="text-xs text-ink-500 mb-2">已配置 {{ priceList.length }} 条规则</div>
            <div v-if="!priceList.length" class="text-xs text-ink-400 py-4 text-center">
              还没有任何单价规则，金额会一直显示「未配置」。
            </div>
            <table v-else class="w-full text-xs">
              <thead>
                <tr class="text-ink-400 border-b border-ink-100">
                  <th class="text-left font-normal py-1.5">匹配</th>
                  <th class="text-right font-normal py-1.5 px-2">单价</th>
                  <th class="text-right font-normal py-1.5 px-2">输出</th>
                  <th class="text-left font-normal py-1.5 px-2">备注</th>
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
                    {{ r.input_per_m }}<span class="text-ink-400 text-[10px] ml-0.5">{{ r.unit === 'image' ? '/张' : '/M' }}</span>
                  </td>
                  <td class="py-1.5 px-2 text-right tabular-nums">
                    {{ r.unit === 'image' ? '—' : r.output_per_m }}
                  </td>
                  <td class="py-1.5 px-2 text-ink-400">{{ r.note || '—' }}</td>
                  <td class="py-1.5 text-right whitespace-nowrap">
                    <button class="text-ink-500 hover:text-ink-900" @click="editRule(r)">改</button>
                    <button class="ml-2 text-red-500 hover:text-red-700" @click="removePrice(r)">删</button>
                  </td>
                </tr>
              </tbody>
            </table>
            <p class="text-[11px] text-ink-400 mt-2 leading-relaxed">
              * 表示任意。精确维度越多越优先：模型精确 &gt; 服务商精确 &gt; 能力类型精确。
              删掉规则后，对应调用的金额会立刻变回「未配置」。
            </p>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>
