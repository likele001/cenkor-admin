<script setup lang="ts">
/**
 * AI 质量台：抽样质检 + 模型 A/B。
 *
 * 定位很明确：这一页不产出内容，只回答两个问题 ——
 *   1. 「最近的 AI 产出到底行不行」（抽样打分 → 曲线）
 *   2. 「该换哪个模型」（同题盲评 → 胜率）
 *
 * 两个刻意的交互选择：
 * - 打分维度不预填 4 分：预填会让所有人一路点提交，曲线就成了一条直线
 * - A/B 生成后**不显示模型名**，只有提交结论才揭晓；否则盲评是假的
 */
import { computed, onMounted, ref } from 'vue'
import { api } from '@/lib/api'

interface Sample {
  entry_id: number
  title: string
  slug: string | null
  status: string
  model: string
  provider: string
  kind: string
  chars: number
  excerpt: string
  has_seo: boolean
  created_at: string | null
}

interface Draft {
  overall: number
  verdict: string
  note: string
  extras: Record<string, number>
}

interface Row extends Sample {
  draft: Draft
}

interface Dimension {
  key: string
  label: string
}

interface CurvePoint {
  week: string
  avg: number
  count: number
  low: number
}

interface ModelStat {
  model: string
  provider: string
  count: number
  overall: number
  accuracy: number | null
  readability: number | null
  pass_rate: number
}

interface Stats {
  curve: CurvePoint[]
  by_model: ModelStat[]
  verdicts: Record<string, number>
  coverage: { total: number; reviewed: number; percent: number }
  ab: { model: string; wins: number; losses: number; ties: number }[]
  weeks: number
}

interface AbSide {
  text: string
  chars: number
  ms: number
  error: string | null
}

interface AbRun {
  id: number
  topic: string
  left: AbSide
  right: AbSide
  reviewable: boolean
  created_at: string | null
}

const TAB_SAMPLE = 'sample'
const TAB_AB = 'ab'

const tab = ref<string>(TAB_SAMPLE)
const loading = ref(false)
const busy = ref('')
const errorMsg = ref('')
const flash = ref('')

const stats = ref<Stats | null>(null)
const dimensions = ref<Dimension[]>([])
const rows = ref<Row[]>([])
const sampleSize = ref(5)

const models = ref<string[]>([])
const abForm = ref({ topic: '', model_a: '', model_b: '', max_tokens: 3000 })
const abRun = ref<AbRun | null>(null)
const abReveal = ref<{ left: string; right: string; won: string } | null>(null)
const abWinner = ref<string>('left')
const abNote = ref('')

const verdictOrder = ['pass', 'needs_fix', 'reject'] as const

const verdictLabels: Record<string, string> = {
  pass: '可直接用',
  needs_fix: '改改能用',
  reject: '不能用',
}

const verdictClass: Record<string, string> = {
  pass: 'bg-emerald-50 text-emerald-700 border-emerald-200',
  needs_fix: 'bg-amber-50 text-amber-700 border-amber-200',
  reject: 'bg-red-50 text-red-700 border-red-200',
}

const dims = computed(() => dimensions.value.filter((d) => d.key !== 'overall'))

const lastPoint = computed<CurvePoint | null>(() => {
  const c = stats.value?.curve ?? []
  return c.length ? c[c.length - 1] : null
})

const avgScore = computed(() => (lastPoint.value ? lastPoint.value.avg.toFixed(1) : '—'))

const verdictRows = computed(() =>
  Object.entries(stats.value?.verdicts ?? {}).map(([key, cnt]) => ({
    key,
    label: verdictLabels[key] ?? key,
    cls: verdictClass[key] ?? 'bg-ink-50 border-ink-200',
    cnt,
  })),
)

function extraVal(row: Row, key: string): number {
  return row.draft.extras[key] ?? 0
}

function setExtra(row: Row, key: string, value: number) {
  row.draft.extras[key] = value
}

async function loadStats() {
  try {
    const { data } = await api.get('/api/v1/cms/ai/quality/stats', { params: { weeks: 12 } })
    stats.value = data as Stats
  } catch (e: any) {
    errorMsg.value = e?.response?.data?.detail || e?.message || '加载统计失败'
  }
}

async function loadModels() {
  try {
    const { data } = await api.get('/api/v1/cms/ai/quality/models')
    const list: string[] = data.models || []
    models.value = list
    if (list.length >= 2) {
      if (!abForm.value.model_a) abForm.value.model_a = list[0]
      if (!abForm.value.model_b) abForm.value.model_b = list[1]
    } else if (list.length === 1) {
      abForm.value.model_a = list[0]
    }
  } catch {
    /* 取不到候选模型不影响抽样质检 */
  }
}

async function draw() {
  loading.value = true
  errorMsg.value = ''
  flash.value = ''
  try {
    const { data } = await api.get('/api/v1/cms/ai/quality/samples', {
      params: { size: sampleSize.value },
    })
    const items = (data.items || []) as Sample[]
    dimensions.value = (data.dimensions || []) as Dimension[]
    rows.value = items.map((s) => ({
      ...s,
      draft: { overall: 0, verdict: 'pass', note: '', extras: {} },
    }))
    if (!items.length) {
      flash.value = '没有可抽的 AI 产出（可能都已评过，或区间内没有 AI 生成的内容）'
    }
  } catch (e: any) {
    errorMsg.value = e?.response?.data?.detail || e?.message || '抽样失败'
  } finally {
    loading.value = false
  }
}

async function submit(row: Row) {
  const scores: Record<string, number> = {}
  if (row.draft.overall) scores.overall = row.draft.overall
  for (const dim of dims.value) {
    const v = extraVal(row, dim.key)
    if (v) scores[dim.key] = v
  }
  if (!Object.keys(scores).length) {
    errorMsg.value = '至少给一个分数再提交'
    return
  }
  busy.value = `review-${row.entry_id}`
  errorMsg.value = ''
  try {
    await api.post('/api/v1/cms/ai/quality/reviews', {
      entry_id: row.entry_id,
      scores,
      verdict: row.draft.verdict,
      note: row.draft.note,
    })
    rows.value = rows.value.filter((r) => r.entry_id !== row.entry_id)
    flash.value = '已记录一条质检'
    await loadStats()
  } catch (e: any) {
    errorMsg.value = e?.response?.data?.detail || e?.message || '提交失败'
  } finally {
    busy.value = ''
  }
}

async function runAb() {
  if (!abForm.value.topic.trim()) {
    errorMsg.value = '先写一个主题'
    return
  }
  if (!abForm.value.model_a || !abForm.value.model_b) {
    errorMsg.value = '两个模型都要选'
    return
  }
  if (abForm.value.model_a === abForm.value.model_b) {
    errorMsg.value = '两个模型相同，没有对比意义'
    return
  }
  busy.value = 'ab'
  errorMsg.value = ''
  flash.value = ''
  abRun.value = null
  abReveal.value = null
  try {
    const { data } = await api.post(
      '/api/v1/cms/ai/quality/ab',
      { ...abForm.value },
      { timeout: 600_000 },
    )
    abRun.value = data as AbRun
  } catch (e: any) {
    errorMsg.value = e?.response?.data?.detail || e?.message || 'A/B 生成失败'
  } finally {
    busy.value = ''
  }
}

async function submitAb() {
  if (!abRun.value) return
  busy.value = 'ab-review'
  try {
    const { data } = await api.post(`/api/v1/cms/ai/quality/ab/${abRun.value.id}/review`, {
      winner: abWinner.value,
      note: abNote.value,
    })
    abReveal.value = data.reveal
    flash.value = '已记录盲评结论'
    await loadStats()
  } catch (e: any) {
    errorMsg.value = e?.response?.data?.detail || e?.message || '提交失败'
  } finally {
    busy.value = ''
  }
}

/** 正文是模型产出的 HTML：只留排版白名单标签，其余一律降级成纯文本。 */
function sanitize(html: string): string {
  const allowed = new Set([
    'P', 'BR', 'H2', 'H3', 'H4', 'UL', 'OL', 'LI',
    'STRONG', 'EM', 'BLOCKQUOTE', 'CODE', 'PRE',
  ])
  const doc = new DOMParser().parseFromString(`<div>${html}</div>`, 'text/html')
  const walk = (node: Element) => {
    for (const child of Array.from(node.children)) {
      if (!allowed.has(child.tagName)) {
        child.replaceWith(document.createTextNode(child.textContent || ''))
        continue
      }
      for (const attr of Array.from(child.attributes)) child.removeAttribute(attr.name)
      walk(child)
    }
  }
  const root = doc.body.firstElementChild
  if (!root) return ''
  walk(root)
  return root.innerHTML
}

onMounted(async () => {
  await Promise.all([loadStats(), loadModels()])
  await draw()
})
</script>

<template>
  <div class="min-h-screen bg-ink-50">
    <header class="bg-white border-b border-ink-200">
      <div class="max-w-7xl mx-auto px-6 h-14 flex items-center gap-4">
        <router-link to="/cms/ai" class="text-sm text-ink-500 hover:text-ink-900">← AI 驾驶舱</router-link>
        <span class="font-semibold">AI 质量台</span>
        <span class="text-xs text-ink-400">抽样质检 · 质量曲线 · 模型 A/B</span>
      </div>
    </header>

    <main class="max-w-7xl mx-auto px-6 py-8">
      <p v-if="errorMsg" class="mb-4 text-sm text-red-600 bg-red-50 border border-red-200 rounded-xl px-4 py-2.5">
        {{ errorMsg }}
      </p>
      <p v-if="flash" class="mb-4 text-sm text-emerald-700 bg-emerald-50 border border-emerald-200 rounded-xl px-4 py-2.5">
        {{ flash }}
      </p>

      <!-- 总览 -->
      <div class="grid gap-4 md:grid-cols-4 mb-6">
        <div class="card">
          <p class="text-xs text-ink-400 mb-1">质检覆盖率</p>
          <p class="text-3xl font-semibold leading-none">
            {{ stats?.coverage.percent ?? 0 }}<span class="text-lg">%</span>
          </p>
          <p class="mt-2 text-xs text-ink-400">
            已评 {{ stats?.coverage.reviewed ?? 0 }} / {{ stats?.coverage.total ?? 0 }} 条 AI 产出
          </p>
        </div>
        <div class="card">
          <p class="text-xs text-ink-400 mb-1">本周均分</p>
          <p class="text-3xl font-semibold leading-none">
            {{ avgScore }}<span class="text-lg text-ink-400">/5</span>
          </p>
          <p class="mt-2 text-xs text-ink-400">本周 {{ lastPoint?.count ?? 0 }} 条评价</p>
        </div>
        <div class="card">
          <p class="text-xs text-ink-400 mb-1">判定分布</p>
          <div class="flex flex-wrap gap-1.5 mt-1">
            <span
              v-for="v in verdictRows"
              :key="v.key"
              class="px-2 py-0.5 text-xs rounded-lg border"
              :class="v.cls"
            >{{ v.label }} {{ v.cnt }}</span>
            <span v-if="!verdictRows.length" class="text-xs text-ink-400">还没有评价</span>
          </div>
        </div>
        <div class="card">
          <p class="text-xs text-ink-400 mb-1">A/B 战绩</p>
          <div v-if="stats?.ab.length" class="space-y-1">
            <div v-for="a in stats?.ab" :key="a.model" class="flex items-center justify-between text-xs gap-2">
              <span class="truncate text-ink-600">{{ a.model }}</span>
              <span class="text-ink-900 font-medium whitespace-nowrap">{{ a.wins }}胜 {{ a.losses }}负 {{ a.ties }}平</span>
            </div>
          </div>
          <p v-else class="text-xs text-ink-400">还没有判定过</p>
        </div>
      </div>

      <!-- 曲线 + 模型对比 -->
      <div class="grid gap-4 md:grid-cols-3 mb-6">
        <div class="card md:col-span-2">
          <p class="text-xs text-ink-400 mb-4">质量曲线（按周，近 {{ stats?.weeks || 12 }} 周）</p>
          <div v-if="stats?.curve.length" class="flex items-end gap-3 h-40">
            <div v-for="w in stats?.curve" :key="w.week" class="flex-1 flex flex-col items-center justify-end gap-1">
              <span class="text-[10px] text-ink-500">{{ w.avg.toFixed(1) }}</span>
              <div
                class="w-full rounded-t-md bg-ink-900/80"
                :style="{ height: Math.max(4, (w.avg / 5) * 120) + 'px' }"
                :title="w.week + ' · ' + w.count + ' 条 · 低于 3 分 ' + w.low + ' 条'"
              ></div>
              <span class="text-[10px] text-ink-400">{{ w.week.slice(5) }}</span>
            </div>
          </div>
          <p v-else class="text-sm text-ink-400 py-10 text-center">还没有质检数据，先从下面抽几条打个分</p>
        </div>

        <div class="card">
          <p class="text-xs text-ink-400 mb-3">按模型对比</p>
          <table v-if="stats?.by_model.length" class="w-full text-xs">
            <thead class="text-ink-400">
              <tr>
                <th class="text-left font-normal pb-2">模型</th>
                <th class="text-right font-normal pb-2">均分</th>
                <th class="text-right font-normal pb-2">条数</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="m in stats?.by_model" :key="m.model" class="border-t border-ink-100">
                <td class="py-2 truncate max-w-[9rem]" :title="m.model">{{ m.model }}</td>
                <td class="py-2 text-right font-medium">{{ m.overall.toFixed(1) }}</td>
                <td class="py-2 text-right text-ink-400">{{ m.count }}</td>
              </tr>
            </tbody>
          </table>
          <p v-else class="text-xs text-ink-400">暂无数据</p>
        </div>
      </div>

      <!-- Tab -->
      <div class="flex gap-2 mb-4">
        <button
          class="px-4 py-2 text-sm rounded-lg border"
          :class="tab === TAB_SAMPLE ? 'bg-ink-900 text-white border-ink-900' : 'bg-white text-ink-600 border-ink-200'"
          @click="tab = TAB_SAMPLE"
        >抽样质检</button>
        <button
          class="px-4 py-2 text-sm rounded-lg border"
          :class="tab === TAB_AB ? 'bg-ink-900 text-white border-ink-900' : 'bg-white text-ink-600 border-ink-200'"
          @click="tab = TAB_AB"
        >模型 A/B</button>
      </div>

      <!-- 抽样 -->
      <section v-if="tab === TAB_SAMPLE">
        <div class="card mb-4 flex flex-wrap items-end gap-4">
          <label class="text-sm text-ink-600">
            抽几条
            <input v-model.number="sampleSize" type="number" min="1" max="20"
              class="ml-2 w-16 px-2 py-1 border border-ink-200 rounded-lg text-sm" />
          </label>
          <button
            class="ml-auto px-4 py-2 text-sm rounded-lg bg-ink-900 text-white hover:bg-ink-800 disabled:opacity-50"
            :disabled="loading" @click="draw"
          >{{ loading ? '抽样中…' : '换一批' }}</button>
        </div>

        <div v-if="rows.length" class="space-y-4">
          <article v-for="row in rows" :key="row.entry_id" class="card">
            <div class="min-w-0">
              <a :href="'/cms/entries/' + row.entry_id" target="_blank"
                 class="font-medium text-ink-900 hover:underline">{{ row.title || '（无标题）' }}</a>
              <p class="mt-1 text-xs text-ink-400">
                {{ row.chars }} 字 · {{ row.model || '模型未知' }} · {{ row.status }}
                · {{ row.has_seo ? 'SEO 已填' : 'SEO 缺失' }}
                <span v-if="row.created_at"> · {{ new Date(row.created_at).toLocaleDateString('zh-CN') }}</span>
              </p>
              <p class="mt-2 text-sm text-ink-600 leading-relaxed">{{ row.excerpt }}</p>
            </div>

            <div class="mt-4 flex flex-wrap items-center gap-x-6 gap-y-3">
              <div class="flex items-center gap-2">
                <span class="text-xs text-ink-500">整体</span>
                <button v-for="n in 5" :key="n" type="button"
                  class="w-8 h-8 rounded-lg border text-sm"
                  :class="row.draft.overall >= n ? 'bg-ink-900 text-white border-ink-900' : 'bg-white text-ink-500 border-ink-200'"
                  @click="row.draft.overall = n">{{ n }}</button>
              </div>
              <div v-for="dim in dims" :key="dim.key" class="flex items-center gap-2">
                <span class="text-xs text-ink-500">{{ dim.label }}</span>
                <button v-for="n in 5" :key="n" type="button"
                  class="w-7 h-7 rounded-md border text-xs"
                  :class="extraVal(row, dim.key) >= n ? 'bg-ink-700 text-white border-ink-700' : 'bg-white text-ink-400 border-ink-200'"
                  @click="setExtra(row, dim.key, n)">{{ n }}</button>
              </div>
            </div>

            <div class="mt-3 flex flex-wrap items-center gap-2">
              <button v-for="key in verdictOrder" :key="key" type="button"
                class="px-3 py-1 text-xs rounded-lg border"
                :class="row.draft.verdict === key ? verdictClass[key] : 'bg-white text-ink-500 border-ink-200'"
                @click="row.draft.verdict = key">{{ verdictLabels[key] }}</button>
              <input v-model="row.draft.note" placeholder="备注（可选）：哪里不好、该怎么改"
                class="flex-1 min-w-[12rem] px-3 py-1.5 text-sm border border-ink-200 rounded-lg" />
              <button
                class="px-4 py-1.5 text-sm rounded-lg bg-emerald-600 text-white hover:bg-emerald-700 disabled:opacity-50"
                :disabled="busy === 'review-' + row.entry_id" @click="submit(row)"
              >{{ busy === 'review-' + row.entry_id ? '提交中…' : '提交评价' }}</button>
            </div>
          </article>
        </div>
        <p v-else class="card text-sm text-ink-400 text-center py-12">点「换一批」抽几条 AI 产出开始打分</p>
      </section>

      <!-- A/B -->
      <section v-else>
        <div class="card mb-4">
          <p class="text-xs text-ink-400 mb-3">
            同一主题、同一参数生成两版，左右随机排序。提交结论后才会揭晓哪边是哪个模型。
          </p>
          <textarea v-model="abForm.topic" rows="2" placeholder="例如：取向硅钢铁损的影响因素与选型建议"
            class="w-full px-3 py-2 text-sm border border-ink-200 rounded-lg mb-3"></textarea>
          <div class="flex flex-wrap items-end gap-4">
            <label class="text-sm text-ink-600">
              模型 ①
              <input v-model="abForm.model_a" list="ab-models"
                class="ml-2 w-56 px-2 py-1.5 border border-ink-200 rounded-lg text-sm" />
            </label>
            <label class="text-sm text-ink-600">
              模型 ②
              <input v-model="abForm.model_b" list="ab-models"
                class="ml-2 w-56 px-2 py-1.5 border border-ink-200 rounded-lg text-sm" />
            </label>
            <datalist id="ab-models">
              <option v-for="m in models" :key="m" :value="m" />
            </datalist>
            <label class="text-sm text-ink-600">
              预算
              <input v-model.number="abForm.max_tokens" type="number" min="500" max="16000" step="500"
                class="ml-2 w-24 px-2 py-1.5 border border-ink-200 rounded-lg text-sm" />
            </label>
            <button
              class="ml-auto px-4 py-2 text-sm rounded-lg bg-ink-900 text-white hover:bg-ink-800 disabled:opacity-50"
              :disabled="busy === 'ab'" @click="runAb"
            >{{ busy === 'ab' ? '两个模型在写…（约 1 分钟）' : '生成两版对比' }}</button>
          </div>
          <p class="mt-2 text-xs text-ink-400">
            提示：推理模型的思考过程与正文共享预算，预算太小会出现「正文为空」——那不是模型不行，是钱没给够。
          </p>
        </div>

        <div v-if="abRun" class="grid gap-4 md:grid-cols-2">
          <article class="card">
            <div class="flex items-center justify-between mb-2">
              <span class="text-sm font-medium">
                左侧
                <span v-if="abReveal" class="ml-2 text-xs text-ink-400">
                  {{ abReveal.left }}
                  <span v-if="abReveal.won === abReveal.left"
                        class="ml-1 px-1.5 py-0.5 rounded bg-emerald-50 text-emerald-700">胜</span>
                </span>
              </span>
              <span class="text-xs text-ink-400">{{ abRun.left.chars }} 字 · {{ (abRun.left.ms / 1000).toFixed(1) }}s</span>
            </div>
            <p v-if="abRun.left.error" class="text-xs text-red-600 bg-red-50 border border-red-200 rounded-lg px-3 py-2">
              {{ abRun.left.error }}
            </p>
            <div v-else class="text-sm text-ink-700 leading-relaxed max-h-[28rem] overflow-auto"
                 v-html="sanitize(abRun.left.text)"></div>
          </article>
          <article class="card">
            <div class="flex items-center justify-between mb-2">
              <span class="text-sm font-medium">
                右侧
                <span v-if="abReveal" class="ml-2 text-xs text-ink-400">
                  {{ abReveal.right }}
                  <span v-if="abReveal.won === abReveal.right"
                        class="ml-1 px-1.5 py-0.5 rounded bg-emerald-50 text-emerald-700">胜</span>
                </span>
              </span>
              <span class="text-xs text-ink-400">{{ abRun.right.chars }} 字 · {{ (abRun.right.ms / 1000).toFixed(1) }}s</span>
            </div>
            <p v-if="abRun.right.error" class="text-xs text-red-600 bg-red-50 border border-red-200 rounded-lg px-3 py-2">
              {{ abRun.right.error }}
            </p>
            <div v-else class="text-sm text-ink-700 leading-relaxed max-h-[28rem] overflow-auto"
                 v-html="sanitize(abRun.right.text)"></div>
          </article>
        </div>

        <div v-if="abRun" class="card mt-4 flex flex-wrap items-center gap-3">
          <template v-if="abRun.reviewable && !abReveal">
            <span class="text-sm text-ink-600">哪一版更好？</span>
            <button type="button" class="px-3 py-1.5 text-sm rounded-lg border"
              :class="abWinner === 'left' ? 'bg-ink-900 text-white border-ink-900' : 'bg-white text-ink-600 border-ink-200'"
              @click="abWinner = 'left'">左侧更好</button>
            <button type="button" class="px-3 py-1.5 text-sm rounded-lg border"
              :class="abWinner === 'right' ? 'bg-ink-900 text-white border-ink-900' : 'bg-white text-ink-600 border-ink-200'"
              @click="abWinner = 'right'">右侧更好</button>
            <button type="button" class="px-3 py-1.5 text-sm rounded-lg border"
              :class="abWinner === 'tie' ? 'bg-ink-900 text-white border-ink-900' : 'bg-white text-ink-600 border-ink-200'"
              @click="abWinner = 'tie'">差不多</button>
            <input v-model="abNote" placeholder="备注（可选）"
              class="flex-1 min-w-[10rem] px-3 py-1.5 text-sm border border-ink-200 rounded-lg" />
            <button class="px-4 py-1.5 text-sm rounded-lg bg-emerald-600 text-white hover:bg-emerald-700 disabled:opacity-50"
              :disabled="busy === 'ab-review'" @click="submitAb">提交并揭晓</button>
          </template>
          <p v-else-if="abReveal" class="text-sm text-ink-700">
            已揭晓：胜出的是 <span class="font-medium">{{ abReveal.won }}</span>
          </p>
          <p v-else class="text-sm text-amber-700">
            这一轮有一侧没写出来，无法评价。把预算调大或换个模型重跑。
          </p>
        </div>
      </section>
    </main>
  </div>
</template>
