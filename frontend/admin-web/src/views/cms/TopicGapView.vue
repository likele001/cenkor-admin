<script setup lang="ts">
/**
 * 选题 Gap 分析页。
 *
 * 定位：给内容团队一张「下周写什么」的清单，不是一份分析报告。
 * 所以每条缺口都要带一个**能直接开工的标题** + 一个「去起草」按钮 ——
 * 看完就能进编辑器，中间不需要再翻译一次。
 *
 * 两种数据源刻意分开，因为它们回答的不是同一个问题：
 *   · 语义反推（模型看「库里已有什么」判断「还缺什么主题」）—— 有洞察，但是推断；
 *   · 真实搜索词（读者实际打的字，尤其是搜了没结果的）—— 没有洞察，但是事实。
 * 先看事实补空白，再用推断找结构性问题。
 */
import { onMounted, ref } from 'vue'
import { api } from '@/lib/api'

interface Gap {
  topic: string
  intent: 'awareness' | 'consideration' | 'decision' | 'retention'
  intent_label: string
  why_gap: string
  suggested_title: string
  keywords: string[]
  priority: 'high' | 'medium' | 'low'
  related_existing: string[]
}

interface GapReport {
  coverage_summary: string
  gaps: Gap[]
  total_entries: number
  sampled_entries?: number
  content_types: { key: string; count: number }[]
  intent_distribution: Record<string, number>
  refs_dropped?: number
  generated_at: string
  warning?: string | null
}

interface SearchTerm {
  query: string
  query_norm: string
  hits: number
  zero_hits: number
  visitors: number
  gap_rate: number
  last_seen: string | null
}

interface SearchSummary {
  days: number
  total: number
  zero_result: number
  zero_rate: number
  distinct_terms: number
  visitors: number
}

type Mode = 'semantic' | 'search'

const mode = ref<Mode>('semantic')

const loading = ref(false)
const elapsed = ref(0)
const errorMsg = ref('')
const report = ref<GapReport | null>(null)
const limit = ref(8)
const ctKey = ref('')

// ---- 真实搜索词 ----
const terms = ref<SearchTerm[]>([])
const termSummary = ref<SearchSummary | null>(null)
const termLoading = ref(false)
const termError = ref('')
const termOrder = ref<'hits' | 'zero' | 'gap'>('zero')
const termDays = ref(30)
const onlyZero = ref(true)

const priorityText: Record<string, string> = { high: '优先做', medium: '可以做', low: '候补' }
const priorityClass: Record<string, string> = {
  high: 'bg-red-50 text-red-700 border-red-200',
  medium: 'bg-amber-50 text-amber-700 border-amber-200',
  low: 'bg-ink-100 text-ink-600 border-ink-200',
}
const intentClass: Record<string, string> = {
  awareness: 'bg-sky-50 text-sky-700',
  consideration: 'bg-violet-50 text-violet-700',
  decision: 'bg-emerald-50 text-emerald-700',
  retention: 'bg-ink-100 text-ink-600',
}

const INTENTS: Array<{ key: string; label: string }> = [
  { key: 'awareness', label: '认知' },
  { key: 'consideration', label: '比较' },
  { key: 'decision', label: '决策' },
  { key: 'retention', label: '留存' },
]

const intentView = ref(INTENTS.map((r) => ({ ...r, count: 0 })))
const totalGaps = ref(0)

async function analyze() {
  loading.value = true
  errorMsg.value = ''
  const t0 = Date.now()
  const timer = window.setInterval(() => {
    elapsed.value = Math.round((Date.now() - t0) / 1000)
  }, 500)
  try {
    const params: Record<string, string | number> = { limit: limit.value }
    if (ctKey.value.trim()) params.content_type_key = ctKey.value.trim()
    const { data } = await api.get('/api/v1/cms/ai/topic-gaps', { params, timeout: 300000 })
    report.value = data as GapReport
    const d = (data as GapReport)?.intent_distribution || {}
    intentView.value = INTENTS.map((r) => ({ ...r, count: d[r.key] || 0 }))
    totalGaps.value = (data as GapReport)?.gaps?.length || 0
  } catch (e: any) {
    errorMsg.value = e?.response?.data?.detail || e?.message || '分析失败'
  } finally {
    window.clearInterval(timer)
    elapsed.value = Math.round((Date.now() - t0) / 1000)
    loading.value = false
  }
}

async function loadTerms() {
  termLoading.value = true
  termError.value = ''
  try {
    const { data } = await api.get('/api/v1/cms/ai/search-terms', {
      params: {
        days: termDays.value,
        limit: 50,
        order: termOrder.value,
        only_zero: onlyZero.value,
      },
    })
    terms.value = data.items || []
    termSummary.value = data.summary || null
  } catch (e: any) {
    termError.value = e?.response?.data?.detail || e?.message || '加载搜索词失败'
  } finally {
    termLoading.value = false
  }
}

function switchMode(m: Mode) {
  mode.value = m
  // 懒加载：没切过来就不打接口，语义分析本身已经够慢
  if (m === 'search' && !termSummary.value && !termLoading.value) loadTerms()
}

function startDraft(title: string) {
  const q: Record<string, string> = { title }
  if (ctKey.value.trim()) q.ct = ctKey.value.trim()
  window.location.href = `/cms/entries/new?${new URLSearchParams(q).toString()}`
}

function startDraftGap(g: Gap) {
  startDraft(g.suggested_title)
}

function copyTitle(text: string) {
  navigator.clipboard?.writeText(text)
}

function pct(v: number) {
  return `${Math.round((v || 0) * 100)}%`
}

onMounted(analyze)
</script>

<template>
  <div class="min-h-screen bg-ink-50">
    <header class="bg-white border-b border-ink-200">
      <div class="max-w-6xl mx-auto px-6 h-14 flex items-center gap-4">
        <router-link to="/cms/ai" class="text-sm text-ink-500 hover:text-ink-900">← AI 驾驶舱</router-link>
        <span class="font-semibold">选题缺口</span>
        <span class="text-xs text-ink-400">该写什么，两种问法</span>
      </div>
    </header>

    <main class="max-w-6xl mx-auto px-6 py-8">
      <!-- 数据源切换 -->
      <div class="flex gap-1 mb-5 p-1 bg-white border border-ink-200 rounded-xl w-fit text-sm">
        <button
          class="px-4 py-1.5 rounded-lg transition-colors"
          :class="mode === 'semantic' ? 'bg-ink-900 text-white' : 'text-ink-600 hover:bg-ink-50'"
          @click="switchMode('semantic')"
        >
          语义反推
        </button>
        <button
          class="px-4 py-1.5 rounded-lg transition-colors"
          :class="mode === 'search' ? 'bg-ink-900 text-white' : 'text-ink-600 hover:bg-ink-50'"
          @click="switchMode('search')"
        >
          真实搜索词
        </button>
      </div>

      <template v-if="mode === 'semantic'">
        <p v-if="errorMsg" class="mb-4 text-sm text-red-600 bg-red-50 border border-red-200 rounded-xl px-4 py-2.5">
          {{ errorMsg }}
        </p>

        <div class="card mb-6 flex flex-wrap items-end gap-4">
          <label class="text-sm text-ink-600">
            内容类型 key（可空）
            <input
              v-model="ctKey"
              placeholder="article"
              class="ml-2 w-32 px-2 py-1 border border-ink-200 rounded-lg text-sm"
            />
          </label>
          <label class="text-sm text-ink-600">
            缺口数量
            <input
              v-model.number="limit"
              type="number"
              min="1"
              max="20"
              class="ml-2 w-16 px-2 py-1 border border-ink-200 rounded-lg text-sm"
            />
          </label>
          <button
            class="ml-auto px-4 py-2 text-sm rounded-lg bg-ink-900 text-white hover:bg-ink-800 disabled:opacity-50"
            :disabled="loading"
            @click="analyze"
          >
            {{ loading ? `分析中… ${elapsed}s` : '重新分析' }}
          </button>
        </div>

        <div v-if="loading && !report" class="card text-sm text-ink-500">
          正在读取内容库并让模型判断覆盖缺口，通常 20~60 秒。
        </div>

        <template v-if="report">
          <div class="grid gap-4 md:grid-cols-3 mb-6">
            <div class="card md:col-span-2">
              <p class="text-xs text-ink-400 mb-2">覆盖概况</p>
              <p class="text-sm leading-relaxed text-ink-800">{{ report.coverage_summary || '—' }}</p>
              <p class="mt-3 text-xs text-ink-400">
                已发布 {{ report.total_entries }} 篇 ·
                采样 {{ report.sampled_entries ?? '—' }} 篇 ·
                缺口 {{ totalGaps }} 条
                <span v-if="report.refs_dropped"> · 已剔除 {{ report.refs_dropped }} 条虚构引用</span>
              </p>
            </div>
            <div class="card">
              <p class="text-xs text-ink-400 mb-2">决策阶段分布</p>
              <ul class="space-y-1.5">
                <li v-for="r in intentView" :key="r.key" class="flex items-center justify-between text-sm">
                  <span class="text-ink-600">{{ r.label }}</span>
                  <span :class="r.count > 0 ? 'text-ink-900 font-medium' : 'text-ink-300'">{{ r.count }}</span>
                </li>
              </ul>
              <p class="mt-3 text-xs text-ink-400 leading-relaxed">
                B2B 常见病：认知层一堆，决策层（报价/交期/验收）空白。
              </p>
            </div>
          </div>

          <p v-if="!report.gaps.length" class="card text-sm text-ink-500">
            {{ report.warning || '没有识别出明显缺口。' }}
          </p>

          <div class="space-y-3">
            <div v-for="(g, i) in report.gaps" :key="i" class="card">
              <div class="flex items-start gap-3">
                <div class="flex-1 min-w-0">
                  <div class="flex flex-wrap items-center gap-2 mb-2">
                    <span class="px-2 py-0.5 text-xs rounded-full border" :class="priorityClass[g.priority]">
                      {{ priorityText[g.priority] }}
                    </span>
                    <span class="px-2 py-0.5 text-xs rounded-full" :class="intentClass[g.intent]">
                      {{ g.intent_label }}
                    </span>
                    <span class="text-xs text-ink-400">{{ g.topic }}</span>
                  </div>

                  <p class="text-base font-medium text-ink-900 leading-snug">{{ g.suggested_title }}</p>
                  <p class="mt-1.5 text-sm text-ink-600">{{ g.why_gap }}</p>

                  <div class="mt-2 flex flex-wrap gap-1.5">
                    <span
                      v-for="k in g.keywords"
                      :key="k"
                      class="px-2 py-0.5 text-xs bg-ink-100 text-ink-600 rounded"
                    >{{ k }}</span>
                  </div>

                  <p class="mt-2 text-xs text-ink-400">
                    <template v-if="g.related_existing.length">
                      已有相关：{{ g.related_existing.join('、') }}
                    </template>
                    <template v-else>站内无相关文章</template>
                  </p>
                </div>

                <div class="flex flex-col gap-2 shrink-0">
                  <button
                    class="px-3 py-1.5 text-xs rounded-lg bg-ink-900 text-white hover:bg-ink-800"
                    @click="startDraftGap(g)"
                  >去起草</button>
                  <button
                    class="px-3 py-1.5 text-xs rounded-lg border border-ink-200 text-ink-600 hover:bg-ink-50"
                    @click="copyTitle(g.suggested_title)"
                  >复制标题</button>
                </div>
              </div>
            </div>
          </div>
        </template>
      </template>

      <template v-else>
        <p class="mb-4 text-xs text-ink-500 leading-relaxed">
          读者在搜索框里真正打的字。「搜了没结果」是最便宜的选题清单 ——
          它不需要模型判断，需求已经写在问题里了。
        </p>

        <p v-if="termError" class="mb-4 text-sm text-red-600 bg-red-50 border border-red-200 rounded-xl px-4 py-2.5">
          {{ termError }}
        </p>

        <div class="card mb-6 flex flex-wrap items-end gap-4">
          <label class="text-sm text-ink-600">
            回看天数
            <input
              v-model.number="termDays"
              type="number"
              min="1"
              max="365"
              class="ml-2 w-20 px-2 py-1 border border-ink-200 rounded-lg text-sm"
            />
          </label>
          <label class="text-sm text-ink-600">
            排序
            <select v-model="termOrder" class="ml-2 px-2 py-1 border border-ink-200 rounded-lg text-sm">
              <option value="zero">零结果最多</option>
              <option value="gap">零结果占比高</option>
              <option value="hits">搜得最多</option>
            </select>
          </label>
          <label class="flex items-center gap-1.5 text-sm text-ink-600">
            <input v-model="onlyZero" type="checkbox" class="w-3.5 h-3.5" />
            只看没搜到的
          </label>
          <button
            class="ml-auto px-4 py-2 text-sm rounded-lg bg-ink-900 text-white hover:bg-ink-800 disabled:opacity-50"
            :disabled="termLoading"
            @click="loadTerms"
          >
            {{ termLoading ? '加载中…' : '刷新' }}
          </button>
        </div>

        <div v-if="termSummary" class="grid gap-4 md:grid-cols-4 mb-6">
          <div class="card">
            <p class="text-xs text-ink-400 mb-1">搜索次数</p>
            <p class="text-2xl font-medium text-ink-900">{{ termSummary.total }}</p>
          </div>
          <div class="card">
            <p class="text-xs text-ink-400 mb-1">零结果</p>
            <p class="text-2xl font-medium text-ink-900">{{ termSummary.zero_result }}</p>
            <p class="text-xs text-ink-400 mt-1">占 {{ pct(termSummary.zero_rate) }}</p>
          </div>
          <div class="card">
            <p class="text-xs text-ink-400 mb-1">不同词</p>
            <p class="text-2xl font-medium text-ink-900">{{ termSummary.distinct_terms }}</p>
          </div>
          <div class="card">
            <p class="text-xs text-ink-400 mb-1">访客</p>
            <p class="text-2xl font-medium text-ink-900">{{ termSummary.visitors }}</p>
            <p class="text-xs text-ink-400 mt-1">近 {{ termSummary.days }} 天</p>
          </div>
        </div>

        <div v-if="termLoading && !terms.length" class="card text-sm text-ink-500">加载中…</div>

        <div v-else-if="terms.length" class="card p-0 overflow-hidden">
          <table class="w-full text-sm">
            <thead class="bg-ink-50 text-xs text-ink-500">
              <tr>
                <th class="text-left px-4 py-2 font-normal">搜索词</th>
                <th class="text-right px-3 py-2 font-normal w-20">次数</th>
                <th class="text-right px-3 py-2 font-normal w-20">零结果</th>
                <th class="text-right px-3 py-2 font-normal w-20">占比</th>
                <th class="text-right px-3 py-2 font-normal w-28">最近</th>
                <th class="px-4 py-2 w-32"></th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="t in terms" :key="t.query_norm" class="border-t border-ink-100">
                <td class="px-4 py-2 text-ink-900">{{ t.query }}</td>
                <td class="px-3 py-2 text-right text-ink-600">{{ t.hits }}</td>
                <td class="px-3 py-2 text-right" :class="t.zero_hits ? 'text-red-600 font-medium' : 'text-ink-300'">
                  {{ t.zero_hits }}
                </td>
                <td class="px-3 py-2 text-right" :class="t.gap_rate >= 0.8 ? 'text-red-600' : 'text-ink-500'">
                  {{ pct(t.gap_rate) }}
                </td>
                <td class="px-3 py-2 text-right text-xs text-ink-400">{{ t.last_seen || '—' }}</td>
                <td class="px-4 py-2 text-right">
                  <button
                    class="px-2.5 py-1 text-xs rounded-lg bg-ink-900 text-white hover:bg-ink-800"
                    @click="startDraft(t.query)"
                  >去起草</button>
                </td>
              </tr>
            </tbody>
          </table>
        </div>

        <p v-else class="card text-sm text-ink-500">
          还没有搜索记录。访问公开站的搜索页（/search?q=…）就会开始积累；
          数据从今天起攒，越早开越早有得看。
        </p>
      </template>
    </main>
  </div>
</template>
