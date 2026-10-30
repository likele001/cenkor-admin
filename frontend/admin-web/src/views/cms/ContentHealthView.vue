<script setup lang="ts">
/**
 * 内容体检页。
 *
 * 定位：不是「另一个列表页」，而是**修哪里**的清单。
 * 所以默认按分数升序（最烂的在最上面），每条直接给跳编辑的入口，
 * 检查项按严重度配色 —— 运营打开就能干活，不用先学会读报告。
 *
 * 三块信息的分工：
 *   1. 分数区  —— 现在什么水平（总分 + 三个维度分开看，避免效果差被结构分糊住）
 *   2. 行动区  —— 先改哪几件（按「命中篇数 × 单条扣分」排，带改法）
 *   3. 明细区  —— 具体哪一篇（可重检、可跳编辑）
 *
 * 「导出报告」不是给运营看的，是给客户/老板看的：同一套数据换成
 * 自带口径说明与改法的文档，能直接发出去。
 */
import { computed, onMounted, ref } from 'vue'
import { api } from '@/lib/api'

interface Issue {
  check: string
  label: string
  severity: 'critical' | 'warning'
  deduct: number
  message: string
  problems?: string[]
  hrefs?: string[]
  chars?: number
  days?: number
  rivals?: { entry_id: number; title: string }[]
  shared?: string[]
  pv?: number
  scroll?: number
  age_days?: number
}

interface Dimensions {
  structure: number
  seo: number
  performance: number
}

interface HealthItem {
  entry_id: number
  title: string
  slug?: string | null
  status: string
  content_type_id: number
  content_type_key?: string
  score: number
  level: 'critical' | 'warning' | 'healthy'
  dimensions?: Dimensions
  issues: Issue[]
  chars: number
  has_image: boolean
  inbound_links: number
  outbound_links: number
  updated_at?: string | null
  public_url?: string
  performance?: Record<string, any> | null
}

interface DimensionSummary {
  label: string
  hint: string
  score: number
  enabled: boolean
  checks: { check: string; label: string; hit: number }[]
}

interface Action {
  check: string
  label: string
  dimension: 'structure' | 'seo' | 'performance'
  severity: 'critical' | 'warning'
  hit: number
  impact: number
  remedy: string
  entries: { entry_id: number; title: string }[]
}

interface Report {
  scanned: number
  truncated: boolean
  score: number
  level: 'critical' | 'warning' | 'healthy'
  problem_count: number
  generated_at: string
  check_summary: Record<
    string,
    { label: string; severity: string; dimension?: string; deduct?: number; remedy?: string; hit: number }
  >
  dimension_summary?: Record<string, DimensionSummary>
  actions?: Action[]
  perf_ready?: boolean
  perf_window_days?: number
  entries: HealthItem[]
  thresholds: Record<string, any>
}

const loading = ref(false)
const errorMsg = ref('')
const report = ref<Report | null>(null)

const includeDrafts = ref(false)
const staleDays = ref(365)
const thinChars = ref(300)

const expanded = ref<Set<number>>(new Set())

const levelText: Record<string, string> = {
  critical: '需尽快处理',
  warning: '建议优化',
  healthy: '健康',
}

const levelClass: Record<string, string> = {
  critical: 'bg-red-50 text-red-700 border-red-200',
  warning: 'bg-amber-50 text-amber-700 border-amber-200',
  healthy: 'bg-emerald-50 text-emerald-700 border-emerald-200',
}

const scoreColor = computed(() => {
  const s = report.value?.score ?? 100
  if (s < 60) return 'text-red-600'
  if (s < 85) return 'text-amber-600'
  return 'text-emerald-600'
})

function scoreTone(s: number) {
  if (s < 60) return 'text-red-600'
  if (s < 85) return 'text-amber-600'
  return 'text-emerald-600'
}

const dimensionList = computed(() => {
  const ds = report.value?.dimension_summary || {}
  return (['structure', 'seo', 'performance'] as const)
    .map((k) => ({ key: k, ...(ds[k] || ({} as DimensionSummary)) }))
    .filter((d) => d.label)
})

const checkRows = computed(() => {
  const cs = report.value?.check_summary || {}
  return Object.entries(cs)
    .map(([key, v]) => ({ key, ...v }))
    .sort((a, b) => b.hit - a.hit)
})

const activeChecks = computed(() => checkRows.value.filter((r) => r.hit > 0))

// 检查项按维度分组展示 —— 混在一张清单里会让人先挑好改的改
const checksByDimension = computed(() => {
  const groups: { key: string; label: string; rows: typeof checkRows.value }[] = [
    { key: 'structure', label: '结构', rows: [] },
    { key: 'seo', label: 'SEO', rows: [] },
    { key: 'performance', label: '效果', rows: [] },
  ]
  for (const row of checkRows.value) {
    const dim = row.dimension || 'structure'
    const g = groups.find((x) => x.key === dim)
    if (g) g.rows.push(row)
  }
  return groups.filter((g) => g.rows.length)
})

const actions = computed<Action[]>(() => report.value?.actions || [])

function toggle(id: number) {
  const s = new Set(expanded.value)
  if (s.has(id)) s.delete(id)
  else s.add(id)
  expanded.value = s
}

async function load() {
  loading.value = true
  errorMsg.value = ''
  try {
    const { data } = await api.get('/api/v1/cms/ai/health/report', {
      params: {
        include_drafts: includeDrafts.value,
        stale_days: staleDays.value,
        thin_chars: thinChars.value,
        limit: 200,
      },
    })
    report.value = data
  } catch (e: any) {
    errorMsg.value = e?.response?.data?.detail || e?.message || '体检失败'
  } finally {
    loading.value = false
  }
}

function openEntry(id: number) {
  window.location.href = `/cms/entries/${id}`
}

// ---------- 报告导出 ----------
// 走 blob 而不是直接 <a href>：导出接口要 Authorization 头，
// 导航式下载带不上 token，只会拿到 401。
const exporting = ref<'' | 'html' | 'md'>('')
const exportMsg = ref('')

async function fetchReportBlob(fmt: 'html' | 'md', inline = false) {
  const res = await api.get('/api/v1/cms/ai/health/export', {
    params: {
      format: fmt,
      inline,
      include_drafts: includeDrafts.value,
      stale_days: staleDays.value,
      thin_chars: thinChars.value,
    },
    responseType: 'blob',
  })
  const type = fmt === 'html' ? 'text/html;charset=utf-8' : 'text/markdown;charset=utf-8'
  return new Blob([res.data], { type })
}

async function exportReport(fmt: 'html' | 'md') {
  if (exporting.value) return
  exporting.value = fmt
  exportMsg.value = ''
  try {
    const blob = await fetchReportBlob(fmt)
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    const stamp = new Date().toISOString().slice(0, 10).replace(/-/g, '')
    a.href = url
    a.download = `内容体检报告-${stamp}.${fmt}`
    document.body.appendChild(a)
    a.click()
    a.remove()
    URL.revokeObjectURL(url)
    exportMsg.value = fmt === 'html' ? 'HTML 报告已下载，可直接发客户或打印成 PDF' : 'Markdown 报告已下载'
  } catch (e: any) {
    exportMsg.value = `导出失败：${e?.response?.data?.detail || e?.message || '未知错误'}`
  } finally {
    exporting.value = ''
  }
}

async function previewReport() {
  if (exporting.value) return
  exporting.value = 'html'
  exportMsg.value = ''
  try {
    const blob = await fetchReportBlob('html', true)
    const url = URL.createObjectURL(blob)
    window.open(url, '_blank')
    // 新窗口自己持有 blob URL，等它加载完再回收
    setTimeout(() => URL.revokeObjectURL(url), 60000)
  } catch (e: any) {
    exportMsg.value = `预览失败：${e?.response?.data?.detail || e?.message || '未知错误'}`
  } finally {
    exporting.value = ''
  }
}

// ---------- 单条重检 ----------
// 改完一条内容不必整站重扫（几百条要几十秒）。这里只重检这一条，
// 就地替换该行；全站分是聚合值，仍要整体体检才会变，必须说明白。
const rechecking = ref<Set<number>>(new Set())
const recheckMsg = ref('')

async function recheck(id: number) {
  if (rechecking.value.has(id)) return
  rechecking.value = new Set([...rechecking.value, id])
  recheckMsg.value = ''
  try {
    const { data } = await api.get(`/api/v1/cms/ai/health/entries/${id}`, {
      params: { stale_days: staleDays.value, thin_chars: thinChars.value },
    })
    if (report.value) {
      const idx = report.value.entries.findIndex((e) => e.entry_id === id)
      if (idx >= 0) {
        // 后端单条接口不带 status/updated_at，合并而不是整体替换，避免字段被抹掉
        report.value.entries[idx] = { ...report.value.entries[idx], ...data }
        report.value.entries.sort((a, b) => a.score - b.score)
      }
    }
    recheckMsg.value = `#${id} 已重检（全站健康分需整体重新体检才会更新）`
  } catch (e: any) {
    recheckMsg.value = e?.response?.data?.detail || e?.message || `#${id} 重检失败`
  } finally {
    const s = new Set(rechecking.value)
    s.delete(id)
    rechecking.value = s
  }
}

onMounted(load)
</script>

<template>
  <div class="min-h-screen bg-ink-50">
    <header class="bg-white border-b border-ink-200">
      <div class="max-w-7xl mx-auto px-6 h-14 flex items-center gap-4">
        <router-link to="/cms/ai" class="text-sm text-ink-500 hover:text-ink-900">← AI 驾驶舱</router-link>
        <span class="font-semibold">内容体检</span>
        <span class="text-xs text-ink-400">结构 · SEO · 效果 三个维度</span>
      </div>
    </header>

    <main class="max-w-7xl mx-auto px-6 py-8">
      <p v-if="errorMsg" class="mb-4 text-sm text-red-600 bg-red-50 border border-red-200 rounded-xl px-4 py-2.5">
        {{ errorMsg }}
      </p>

      <!-- 参数 + 刷新 + 导出 -->
      <div class="card mb-6 flex flex-wrap items-end gap-4">
        <label class="text-sm text-ink-600">
          陈旧阈值(天)
          <input
            v-model.number="staleDays"
            type="number"
            min="30"
            max="3650"
            class="ml-2 w-20 px-2 py-1 border border-ink-200 rounded-lg text-sm"
          />
        </label>
        <label class="text-sm text-ink-600">
          过薄阈值(字)
          <input
            v-model.number="thinChars"
            type="number"
            min="50"
            max="5000"
            class="ml-2 w-20 py-1 border border-ink-200 rounded-lg text-sm px-2"
          />
        </label>
        <label class="text-sm text-ink-600 flex items-center gap-2">
          <input v-model="includeDrafts" type="checkbox" class="rounded border-ink-300" />
          连同草稿一起体检
        </label>

        <div class="ml-auto flex items-center gap-2">
          <button
            class="px-3 py-2 text-sm rounded-lg border border-ink-200 hover:bg-ink-50 disabled:opacity-50"
            :disabled="!!exporting || !report"
            @click="previewReport"
          >预览报告</button>
          <button
            class="px-3 py-2 text-sm rounded-lg border border-ink-200 hover:bg-ink-50 disabled:opacity-50"
            :disabled="!!exporting || !report"
            @click="exportReport('md')"
          >{{ exporting === 'md' ? '导出中…' : '导出 MD' }}</button>
          <button
            class="px-3 py-2 text-sm rounded-lg border border-ink-900 bg-white text-ink-900 hover:bg-ink-50 disabled:opacity-50"
            :disabled="!!exporting || !report"
            @click="exportReport('html')"
          >{{ exporting === 'html' ? '导出中…' : '导出报告' }}</button>
          <button
            class="px-4 py-2 text-sm rounded-lg bg-ink-900 text-white hover:bg-ink-800 disabled:opacity-50"
            :disabled="loading"
            @click="load"
          >{{ loading ? '体检中…' : '重新体检' }}</button>
        </div>
      </div>

      <p v-if="exportMsg" class="mb-4 text-xs text-ink-500">{{ exportMsg }}</p>

      <!-- 总览：总分 + 三个维度 -->
      <div v-if="report" class="grid gap-4 md:grid-cols-5 mb-6">
        <div class="card md:col-span-2">
          <p class="text-xs text-ink-400 mb-1">站点健康分</p>
          <div class="flex items-end gap-3">
            <span class="text-5xl font-semibold leading-none" :class="scoreColor">{{ report.score }}</span>
            <span
              class="mb-1 px-2 py-0.5 text-xs rounded-full border"
              :class="levelClass[report.level]"
            >{{ levelText[report.level] }}</span>
          </div>
          <p class="mt-3 text-xs text-ink-400">
            扫描 {{ report.scanned }} 条{{ report.truncated ? '（已截断，超过单次上限）' : '' }} ·
            问题 {{ report.problem_count }} 条 ·
            {{ new Date(report.generated_at).toLocaleString('zh-CN') }}
          </p>
        </div>

        <div
          v-for="d in dimensionList"
          :key="d.key"
          class="card"
        >
          <p class="text-xs text-ink-400 mb-1 flex items-center justify-between">
            <span>{{ d.label }}</span>
            <span v-if="!d.enabled" class="text-[10px] px-1.5 py-0.5 rounded bg-ink-100 text-ink-400">未启用</span>
          </p>
          <p class="text-3xl font-semibold leading-none" :class="d.enabled ? scoreTone(d.score) : 'text-ink-300'">
            {{ d.enabled ? d.score : '—' }}
          </p>
          <p class="mt-2 text-[11px] leading-snug text-ink-400">{{ d.hint }}</p>
        </div>
      </div>

      <!-- 效果维度未启用说明 -->
      <p
        v-if="report && report.perf_ready === false"
        class="mb-6 text-xs rounded-xl px-4 py-3 bg-sky-50 border border-sky-200 text-sky-900"
      >
        效果维度未启用：埋点还没有采集到任何数据，本次不评价「有没有人看」。
        接入埋点后会自动补充零访问、读完率、转化三类问题（窗口 {{ report.perf_window_days || 30 }} 天）。
      </p>

      <!-- 行动清单 -->
      <div v-if="report && actions.length" class="card mb-6">
        <div class="flex items-center justify-between mb-1">
          <h2 class="font-semibold">先改这几件</h2>
          <span class="text-xs text-ink-400">按「命中篇数 × 单条扣分」排序</span>
        </div>
        <ol class="mt-3 space-y-3">
          <li v-for="(a, i) in actions" :key="a.check" class="flex items-start gap-3">
            <span class="mt-0.5 shrink-0 w-5 text-center text-xs font-semibold text-ink-400">{{ i + 1 }}</span>
            <div class="min-w-0 flex-1">
              <div class="flex items-center gap-2 flex-wrap">
                <span class="font-medium text-sm">{{ a.label }}</span>
                <span
                  class="px-1.5 py-0.5 text-[10px] rounded"
                  :class="a.severity === 'critical' ? 'bg-red-50 text-red-700' : 'bg-amber-50 text-amber-700'"
                >{{ a.severity === 'critical' ? '严重' : '一般' }}</span>
                <span class="text-xs text-ink-400">{{ a.hit }} 篇 · 影响面 {{ a.impact }}</span>
              </div>
              <p class="mt-1 text-xs text-ink-500">改法：{{ a.remedy }}</p>
              <p v-if="a.entries.length" class="mt-1 text-[11px] text-ink-400 truncate">
                涉及：{{ a.entries.slice(0, 3).map((e) => e.title).join('；') }}
                <span v-if="a.entries.length > 3"> 等 {{ a.entries.length }} 篇</span>
              </p>
            </div>
          </li>
        </ol>
      </div>

      <!-- 检查项命中分布（按维度分组） -->
      <div v-if="report" class="card mb-6">
        <p class="text-xs text-ink-400 mb-3">检查项命中分布</p>
        <div class="space-y-3">
          <div v-for="g in checksByDimension" :key="g.key">
            <p class="text-[11px] text-ink-400 mb-1.5">{{ g.label }}</p>
            <div class="flex flex-wrap gap-2">
              <span
                v-for="row in g.rows"
                :key="row.key"
                class="px-2.5 py-1 text-xs rounded-lg border"
                :class="row.hit > 0
                  ? (row.severity === 'critical' ? 'bg-red-50 text-red-700 border-red-200' : 'bg-amber-50 text-amber-700 border-amber-200')
                  : 'bg-ink-50 text-ink-400 border-ink-200'"
                :title="row.remedy || ''"
              >
                {{ row.label }} {{ row.hit }}
              </span>
            </div>
          </div>
        </div>
        <p v-if="!activeChecks.length" class="mt-3 text-xs text-emerald-600">
          本次体检没有发现任何问题项。
        </p>
      </div>

      <!-- 问题清单 -->
      <div v-if="report" class="card">
        <div class="flex items-center justify-between mb-3">
          <h2 class="font-semibold">待处理条目</h2>
          <span class="text-xs text-ink-400">按分数升序，最需要修的在前</span>
        </div>

        <p
          v-if="recheckMsg"
          class="mb-3 text-xs rounded-lg px-3 py-2 border"
          :class="recheckMsg.includes('失败') ? 'text-red-600 bg-red-50 border-red-200' : 'text-emerald-700 bg-emerald-50 border-emerald-200'"
        >{{ recheckMsg }}</p>

        <div v-if="!report.entries.length" class="py-16 text-center text-sm text-ink-400">
          没有需要处理的条目。
        </div>

        <ul v-else class="divide-y divide-ink-100">
          <li v-for="item in report.entries" :key="item.entry_id" class="py-3">
            <div class="flex items-start gap-3">
              <span
                class="mt-0.5 shrink-0 w-11 text-center text-sm font-semibold rounded-lg py-1 border"
                :class="levelClass[item.level]"
              >{{ item.score }}</span>

              <div class="min-w-0 flex-1">
                <div class="flex items-center gap-2 flex-wrap">
                  <button class="font-medium text-left hover:underline truncate" @click="toggle(item.entry_id)">
                    {{ item.title || '(无标题)' }}
                  </button>
                  <span class="text-xs text-ink-400">#{{ item.entry_id }}</span>
                  <span v-if="item.status !== 'published'" class="text-xs px-1.5 py-0.5 rounded bg-ink-100 text-ink-500">
                    {{ item.status }}
                  </span>
                  <span class="text-xs text-ink-400">{{ item.chars }} 字</span>
                  <span class="text-xs text-ink-400">链入 {{ item.inbound_links }} / 链出 {{ item.outbound_links }}</span>
                  <span
                    v-if="item.dimensions"
                    class="text-[11px] text-ink-400"
                  >结构 {{ item.dimensions.structure }} · SEO {{ item.dimensions.seo }} · 效果 {{ item.dimensions.performance }}</span>
                </div>

                <div class="mt-1.5 flex flex-wrap gap-1.5">
                  <span
                    v-for="is_ in item.issues"
                    :key="is_.check"
                    class="px-2 py-0.5 text-xs rounded border"
                    :class="is_.severity === 'critical'
                      ? 'bg-red-50 text-red-700 border-red-200'
                      : 'bg-amber-50 text-amber-700 border-amber-200'"
                    :title="is_.message"
                  >{{ is_.label }} −{{ is_.deduct }}</span>
                </div>

                <ul v-if="expanded.has(item.entry_id)" class="mt-2 space-y-1.5 text-xs text-ink-600 bg-ink-50 rounded-lg p-3">
                  <li v-for="(is_, idx) in item.issues" :key="idx">
                    <span class="font-medium">{{ is_.label }}：</span>{{ is_.message }}
                    <div v-if="is_.hrefs?.length" class="mt-1 text-ink-400 break-all">
                      死链：{{ is_.hrefs.join(' , ') }}
                    </div>
                    <div v-if="is_.rivals?.length" class="mt-1 text-ink-400">
                      竞争：{{ is_.rivals.map((r) => `#${r.entry_id} ${r.title}`).join('；') }}
                    </div>
                    <div v-if="is_.shared?.length" class="mt-1 text-ink-400">
                      共用关键词：{{ is_.shared.join('、') }}
                    </div>
                    <div v-if="report.check_summary[is_.check]?.remedy" class="mt-1 text-ink-500">
                      改法：{{ report.check_summary[is_.check].remedy }}
                    </div>
                  </li>
                </ul>
              </div>

              <div class="shrink-0 flex items-center gap-2">
                <button
                  class="px-2.5 py-1 text-xs rounded-lg border border-ink-200 hover:bg-ink-50 disabled:opacity-50"
                  :disabled="rechecking.has(item.entry_id)"
                  @click="recheck(item.entry_id)"
                >{{ rechecking.has(item.entry_id) ? '重检中…' : '重检' }}</button>
                <button
                  class="px-2.5 py-1 text-xs rounded-lg border border-ink-200 hover:bg-ink-50"
                  @click="toggle(item.entry_id)"
                >{{ expanded.has(item.entry_id) ? '收起' : '详情' }}</button>
                <button
                  class="px-2.5 py-1 text-xs rounded-lg bg-ink-900 text-white hover:bg-ink-800"
                  @click="openEntry(item.entry_id)"
                >去修</button>
              </div>
            </div>
          </li>
        </ul>
      </div>
    </main>
  </div>
</template>
