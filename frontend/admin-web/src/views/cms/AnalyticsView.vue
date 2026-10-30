<script setup lang="ts">
/**
 * 内容效果看板。
 *
 * 这一页的存在意义不是「展示好看的图表」，而是让「下一篇写什么」有依据。
 * 所以排序逻辑刻意不按 PV 排，而是按一个复合表现分：
 *
 *   读完率 50% + 停留时长 30% + 转化率 20%
 *
 * 只看 PV 的话标题党永远第一，但它带来的线索可能是零；只看停留时长的话
 * 万字长文永远占优，而客户真正想复制的是「短而有用」。每一项得分下面都
 * 附着人话理由（「读完 87%，停留 2 分 30 秒」），不做黑箱分数。
 *
 * 没有数据时不做假图：直接给出接入指引。埋点没接上的时候，一张全零的
 * 折线图比空白更让人困惑。
 */
import { computed, onMounted, ref } from 'vue'
import { api } from '@/lib/api'

interface Overview {
  days: number
  pv: number
  uv: number
  conversions: number
  entries: number
  bounce_rate: number
  avg_duration_ms: number
  avg_scroll_pct: number
  has_data: boolean
}

interface TrendPoint {
  date: string
  pv: number
  uv: number
  conversions: number
}

interface ChannelRow {
  source: string
  pv: number
  uv: number
  conversions: number
}

interface StorageInfo {
  total: number
  today: number
  oldest: string | null
  today_unlinked: number
  quota_per_ip: number
}

interface PerfRow {
  entry_id: number
  title: string
  slug: string | null
  published_at: string | null
  pv: number
  uv: number
  avg_duration_ms: number
  avg_scroll_pct: number
  bounce_rate: number
  conversions: number
  score: number
  reason: string
}

interface InsightItem {
  entry_id: number
  title: string
  published_at?: string | null
  pv?: number
  avg_scroll_pct?: number
  bounce_rate?: number
  problem?: string
  hint?: string
}

interface TopicRow {
  category: string
  entries: number
  pv: number
  avg_scroll_pct: number
  score: number
  reason: string
}

const days = ref(30)
const loading = ref(false)
const error = ref('')

const overview = ref<Overview | null>(null)
const trend = ref<TrendPoint[]>([])
const channels = ref<ChannelRow[]>([])
const storage = ref<StorageInfo | null>(null)
const rows = ref<PerfRow[]>([])
const lowPerformers = ref<InsightItem[]>([])
const deadContent = ref<InsightItem[]>([])
const topics = ref<TopicRow[]>([])

const setup = ref<{ snippet: string; notes: string[] } | null>(null)
const showSetup = ref(false)

const hasData = computed(() => !!overview.value?.has_data)

const maxTrend = computed(() => Math.max(1, ...trend.value.map((t) => t.pv)))

function pct(v: number | undefined | null) {
  return `${Number(v ?? 0)}%`
}

function dur(ms: number | undefined | null) {
  const s = Math.round(Number(ms ?? 0) / 1000)
  if (s < 60) return `${s}s`
  return `${Math.floor(s / 60)}分${String(s % 60).padStart(2, '0')}秒`
}

function shortDate(d: string) {
  return d.slice(5)
}

function scoreClass(score: number) {
  if (score >= 60) return 'text-emerald-600'
  if (score >= 35) return 'text-amber-600'
  return 'text-red-600'
}

async function load() {
  loading.value = true
  error.value = ''
  try {
    const [ov, ent, ins] = await Promise.all([
      api.get('/api/v1/cms/ai/stats/overview', { params: { days: days.value } }),
      api.get('/api/v1/cms/ai/stats/entries', { params: { days: days.value, limit: 50 } }),
      api.get('/api/v1/cms/ai/stats/insights', { params: { days: days.value } }),
    ])
    overview.value = ov.data.overview
    trend.value = ov.data.trend || []
    channels.value = ov.data.channels || []
    storage.value = ov.data.storage || null
    rows.value = ent.data.items || []
    lowPerformers.value = ins.data.low_performers || []
    deadContent.value = ins.data.dead_content || []
    topics.value = ins.data.topics || []
  } catch (e: unknown) {
    error.value = e instanceof Error ? e.message : '加载失败'
  } finally {
    loading.value = false
  }
}

async function loadSetup() {
  if (setup.value) return
  const { data } = await api.get('/api/v1/cms/ai/stats/tracking-setup')
  setup.value = data
}

async function toggleSetup() {
  showSetup.value = !showSetup.value
  if (showSetup.value) await loadSetup()
}

async function refresh() {
  loading.value = true
  try {
    await api.post('/api/v1/cms/ai/stats/refresh', null, { params: { days: days.value } })
    await load()
  } finally {
    loading.value = false
  }
}

async function copySnippet() {
  if (!setup.value) return
  try {
    await navigator.clipboard.writeText(setup.value.snippet)
  } catch {
    /* 剪贴板无权限时保持静默，下面代码块可以直接手选 */
  }
}

function setDays(d: number) {
  if (days.value === d) return
  days.value = d
  load()
}

onMounted(load)
</script>

<template>
  <div class="space-y-5">
    <div class="flex flex-wrap items-center justify-between gap-3">
      <div>
        <h1 class="text-lg font-medium text-ink-900">内容效果</h1>
        <p class="mt-1 text-[13px] text-ink-500">
          发布之后发生了什么。数据来自埋点，按 Asia/Shanghai 自然日统计。
        </p>
      </div>
      <div class="flex items-center gap-2">
        <div class="flex overflow-hidden rounded-lg border border-ink-200">
          <button
            v-for="d in [7, 30, 90]"
            :key="d"
            class="px-3 py-1.5 text-[13px] transition"
            :class="days === d ? 'bg-ink-900 text-white' : 'bg-white text-ink-600 hover:bg-ink-50'"
            @click="setDays(d)"
          >
            近 {{ d }} 天
          </button>
        </div>
        <button class="btn btn-ghost" :disabled="loading" @click="refresh">重算</button>
        <button class="btn btn-ghost" @click="toggleSetup">接入埋点</button>
      </div>
    </div>

    <div v-if="error" class="card border-red-200 bg-red-50 text-[13px] text-red-700">{{ error }}</div>

    <!-- 没数据时不画空图，直接给接入方式 -->
    <div v-if="!loading && !hasData" class="card space-y-4">
      <div class="text-[15px] font-medium text-ink-900">还没有效果数据</div>
      <p class="text-[13px] leading-relaxed text-ink-600">
        埋点脚本没接入之前，看板不会有任何数字。接入只要一行标签，放在官网模板
        <code class="rounded bg-ink-100 px-1 py-0.5 text-[12px]">&lt;/head&gt;</code> 之前，全站一次即可。
      </p>
      <div v-if="setup" class="space-y-3">
        <div class="relative">
          <pre class="overflow-x-auto rounded-lg bg-ink-900 p-3 text-[12px] leading-relaxed text-ink-50">{{ setup.snippet }}</pre>
          <button class="absolute right-2 top-2 rounded bg-white/15 px-2 py-1 text-[12px] text-white" @click="copySnippet">
            复制
          </button>
        </div>
        <ul class="space-y-1.5">
          <li v-for="(n, i) in setup.notes" :key="i" class="flex gap-2 text-[13px] text-ink-600">
            <span class="text-ink-300">{{ i + 1 }}.</span><span>{{ n }}</span>
          </li>
        </ul>
      </div>
      <div v-else class="text-[13px] text-ink-400">正在读取接入指引…</div>
    </div>

    <template v-else>
      <!-- 指标卡 -->
      <div class="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <div class="card">
          <div class="text-[12px] text-ink-500">浏览量 PV</div>
          <div class="mt-1 text-2xl font-medium text-ink-900">{{ overview?.pv ?? 0 }}</div>
          <div class="mt-1 text-[12px] text-ink-400">{{ overview?.entries ?? 0 }} 篇内容有访问</div>
        </div>
        <div class="card">
          <div class="text-[12px] text-ink-500">独立访客 UV</div>
          <div class="mt-1 text-2xl font-medium text-ink-900">{{ overview?.uv ?? 0 }}</div>
          <div class="mt-1 text-[12px] text-ink-400">
            人均 {{ overview?.uv ? ((overview.pv ?? 0) / overview.uv).toFixed(1) : '0' }} 次
          </div>
        </div>
        <div class="card">
          <div class="text-[12px] text-ink-500">平均读完</div>
          <div class="mt-1 text-2xl font-medium text-ink-900">{{ pct(overview?.avg_scroll_pct) }}</div>
          <div class="mt-1 text-[12px] text-ink-400">停留 {{ dur(overview?.avg_duration_ms) }}</div>
        </div>
        <div class="card">
          <div class="text-[12px] text-ink-500">线索转化</div>
          <div class="mt-1 text-2xl font-medium text-ink-900">{{ overview?.conversions ?? 0 }}</div>
          <div class="mt-1 text-[12px] text-ink-400">跳出率 {{ pct(overview?.bounce_rate) }}</div>
        </div>
      </div>

      <!-- 趋势 -->
      <div class="card">
        <div class="mb-4 flex items-center justify-between">
          <div class="text-[14px] font-medium text-ink-900">访问趋势</div>
          <div class="flex items-center gap-3 text-[12px] text-ink-500">
            <span class="flex items-center gap-1"><i class="inline-block h-2 w-2 rounded-sm bg-ink-800" />PV</span>
            <span class="flex items-center gap-1"><i class="inline-block h-2 w-2 rounded-sm bg-ink-300" />UV</span>
          </div>
        </div>
        <div class="flex h-36 items-end gap-1">
          <div v-for="(p, i) in trend" :key="p.date" class="group flex flex-1 flex-col items-center justify-end gap-0.5">
            <div class="flex w-full items-end justify-center gap-[2px]" :title="`${p.date}  PV ${p.pv} / UV ${p.uv}`">
              <div
                class="w-1/2 rounded-t-sm bg-ink-800"
                :style="{ height: `${Math.max(2, (p.pv / maxTrend) * 100)}px` }"
              />
              <div
                class="w-1/2 rounded-t-sm bg-ink-300"
                :style="{ height: `${Math.max(2, (p.uv / maxTrend) * 100)}px` }"
              />
            </div>
            <span v-if="i % Math.ceil(trend.length / 6) === 0" class="text-[10px] text-ink-400">
              {{ shortDate(p.date) }}
            </span>
          </div>
        </div>
      </div>

      <!-- 内容排行 -->
      <div class="card">
        <div class="mb-3 flex items-center justify-between">
          <div class="text-[14px] font-medium text-ink-900">内容表现排行</div>
          <div class="text-[12px] text-ink-400">按表现分排序，不是按 PV</div>
        </div>
        <div v-if="!rows.length" class="py-6 text-center text-[13px] text-ink-400">这段时间内没有内容被访问</div>
        <div v-else class="overflow-x-auto">
          <table class="w-full text-[13px]">
            <thead>
              <tr class="border-b border-ink-100 text-left text-[12px] text-ink-500">
                <th class="py-2 pr-3 font-normal">内容</th>
                <th class="px-2 py-2 text-right font-normal">PV</th>
                <th class="px-2 py-2 text-right font-normal">读完</th>
                <th class="px-2 py-2 text-right font-normal">停留</th>
                <th class="px-2 py-2 text-right font-normal">跳出</th>
                <th class="px-2 py-2 text-right font-normal">线索</th>
                <th class="px-3 py-2 text-right font-normal">表现分</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="r in rows" :key="r.entry_id" class="border-b border-ink-50 last:border-0 hover:bg-ink-50/60">
                <td class="py-2.5 pr-3">
                  <div class="max-w-[320px] truncate text-ink-900">{{ r.title }}</div>
                  <div class="mt-0.5 truncate text-[12px] text-ink-400">{{ r.reason }}</div>
                </td>
                <td class="px-2 py-2.5 text-right tabular-nums text-ink-700">{{ r.pv }}</td>
                <td class="px-2 py-2.5 text-right tabular-nums text-ink-700">{{ pct(r.avg_scroll_pct) }}</td>
                <td class="px-2 py-2.5 text-right tabular-nums text-ink-700">{{ dur(r.avg_duration_ms) }}</td>
                <td class="px-2 py-2.5 text-right tabular-nums" :class="r.bounce_rate > 70 ? 'text-red-600' : 'text-ink-700'">
                  {{ pct(r.bounce_rate) }}
                </td>
                <td class="px-2 py-2.5 text-right tabular-nums text-ink-700">{{ r.conversions }}</td>
                <td class="px-3 py-2.5 text-right">
                  <span class="font-medium tabular-nums" :class="scoreClass(r.score)">{{ r.score }}</span>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      <!-- 三类洞察 -->
      <div class="grid grid-cols-1 gap-4 xl:grid-cols-3">
        <div class="card">
          <div class="mb-1 text-[14px] font-medium text-ink-900">有流量没读完</div>
          <p class="mb-3 text-[12px] text-ink-400">标题和正文对不上，或者开头太虚</p>
          <div v-if="!lowPerformers.length" class="py-4 text-center text-[13px] text-ink-400">没有明显问题内容</div>
          <ul v-else class="space-y-2.5">
            <li v-for="it in lowPerformers.slice(0, 8)" :key="it.entry_id" class="border-b border-ink-50 pb-2 last:border-0">
              <div class="truncate text-[13px] text-ink-900">{{ it.title }}</div>
              <div class="mt-0.5 text-[12px] text-amber-600">{{ it.problem }} · PV {{ it.pv }}</div>
            </li>
          </ul>
        </div>

        <div class="card">
          <div class="mb-1 text-[14px] font-medium text-ink-900">发布后零访问</div>
          <p class="mb-3 text-[12px] text-ink-400">多半是没分发出去，不是内容问题</p>
          <div v-if="!deadContent.length" class="py-4 text-center text-[13px] text-ink-400">全部内容都有访问</div>
          <ul v-else class="space-y-2.5">
            <li v-for="it in deadContent.slice(0, 8)" :key="it.entry_id" class="border-b border-ink-50 pb-2 last:border-0">
              <div class="truncate text-[13px] text-ink-900">{{ it.title }}</div>
              <div class="mt-0.5 text-[12px] text-ink-500">发布 {{ (it.published_at || '').slice(0, 10) }}</div>
            </li>
          </ul>
        </div>

        <div class="card">
          <div class="mb-1 text-[14px] font-medium text-ink-900">哪类主题值得再写</div>
          <p class="mb-3 text-[12px] text-ink-400">按分类汇总的表现分</p>
          <div v-if="!topics.length" class="py-4 text-center text-[13px] text-ink-400">还没有分类数据</div>
          <ul v-else class="space-y-2.5">
            <li v-for="t in topics.slice(0, 8)" :key="t.category" class="border-b border-ink-50 pb-2 last:border-0">
              <div class="flex items-center justify-between">
                <span class="truncate text-[13px] text-ink-900">{{ t.category }}</span>
                <span class="ml-2 shrink-0 font-medium tabular-nums" :class="scoreClass(t.score)">{{ t.score }}</span>
              </div>
              <div class="mt-0.5 text-[12px] text-ink-500">{{ t.entries }} 篇 · PV {{ t.pv }} · {{ t.reason }}</div>
            </li>
          </ul>
        </div>
      </div>

      <!-- 存储健康度 -->
      <div v-if="storage" class="card flex flex-wrap items-center gap-x-6 gap-y-2 text-[12px] text-ink-500">
        <span>原始事件 {{ storage.total }} 条</span>
        <span>今日 {{ storage.today }} 条</span>
        <span>最早 {{ storage.oldest || '—' }}</span>
        <span :class="storage.today_unlinked ? 'text-amber-600' : ''">
          今日未关联内容 {{ storage.today_unlinked }} 条
        </span>
        <span>单 IP 每日上限 {{ storage.quota_per_ip }}</span>
        <span class="text-ink-400">明细保留 90 天，汇总永久保留</span>
      </div>
    </template>
  </div>
</template>
