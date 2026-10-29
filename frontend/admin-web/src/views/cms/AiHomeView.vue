<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { api } from '@/lib/api'

/** 驾驶舱只陈述事实，不编造指标 —— 所有数字都来自 /ai/dashboard 的真实聚合 */

interface Capability {
  key: string
  label: string
  hint: string
  wired: boolean
  ready: boolean
  configured_only: boolean
  model: string
  provider: string
  source: string
  dims: number | null
}

interface Dashboard {
  site: { id: number; name: string; key: string }
  capabilities: Capability[]
  health: { chat_ready: boolean; embedding_ready: boolean; ready_count: number; total_count: number }
  output: {
    today: number
    week: number
    month: number
    total: number
    by_origin: { origin: string; count: number }[]
    trend: { date: string; count: number }[]
  }
  coverage: {
    ai_entries: number
    all_entries: number
    ai_ratio: number
    month_ai: number
    month_all: number
    month_ratio: number
  }
  usage: {
    today_calls: number
    today_tokens: number
    month_calls: number
    month_tokens: number
    avg_latency_ms: number
    by_kind: { kind: string; calls: number; tokens_in: number; tokens_out: number; avg_latency_ms: number }[]
  }
  vectors: { entries: number; embedded: number; ratio: number; dim: number | null }
  recent: {
    id: number
    kind: string
    target: string
    model: string
    tokens_in: number
    tokens_out: number
    latency_ms: number
    status: string
    error: string | null
    created_at: string | null
    entry_id: number | null
  }[]
  batches: { id: number; name: string; status: string; total: number; succeeded: number; failed: number; skipped: number }[]
  prompts: { keys: number; modified: number }
  generated_at: string
}

const data = ref<Dashboard | null>(null)
const loading = ref(true)
const error = ref('')

const KIND_LABEL: Record<string, string> = {
  entry_draft: '起草',
  translate: '翻译',
  seo: 'SEO 建议',
  content_type_from_nl: '建模',
  rewrite: '改写',
  embedding: '向量化',
}

const ORIGIN_LABEL: Record<string, string> = {
  draft: '起草',
  rewrite: '改写',
  translate: '翻译',
}

const BATCH_STATUS: Record<string, { label: string; cls: string }> = {
  running: { label: '进行中', cls: 'bg-blue-50 text-blue-700' },
  paused: { label: '已暂停', cls: 'bg-amber-50 text-amber-700' },
  done: { label: '已完成', cls: 'bg-emerald-50 text-emerald-700' },
  cancelled: { label: '已取消', cls: 'bg-red-50 text-red-700' },
}

/** 有活跃批次时 15s 轮询一次；纯浏览页面，没批次就完全静默 */
let pollTimer: ReturnType<typeof setTimeout> | null = null

const hasActiveBatch = computed(() =>
  (data.value?.batches ?? []).some((b) => b.status === 'running'),
)

function schedulePoll() {
  if (pollTimer) {
    clearTimeout(pollTimer)
    pollTimer = null
  }
  if (!hasActiveBatch.value) return
  pollTimer = setTimeout(load, 15_000)
}

async function load() {
  try {
    const { data: d } = await api.get<Dashboard>('/api/v1/cms/ai/dashboard')
    data.value = d
    error.value = ''
  } catch (e: any) {
    error.value = e?.response?.data?.detail || e?.message || '加载失败'
  } finally {
    loading.value = false
    schedulePoll()
  }
}

// ---------- 向量补建 ----------
// 覆盖率不满时，用户只能干看着 —— 这里给一个能点的按钮，一次最多补 50 条。
const vectorBusy = ref(false)
const vectorMsg = ref('')

async function rebuildVectors() {
  if (vectorBusy.value) return
  vectorBusy.value = true
  vectorMsg.value = ''
  try {
    const { data: r } = await api.post('/api/v1/cms/ai/vectors/rebuild', { limit: 50 })
    const processed = Number(r?.processed ?? 0)
    const scanned = Number(r?.scanned ?? 0)
    const created = Number(r?.created ?? 0)
    const calls = Number(r?.api_calls ?? 0)
    // processed 是「处理成功条数」，不等于「补出来几条」——已有最新向量的也计入。
    // 所以文案分三档，避免把「扫了 25 条」说成「补了 25 条」，让用户以为白花了 25 次钱。
    if (processed === 0) {
      vectorMsg.value = scanned
        ? `扫描 ${scanned} 条但没处理成功任何一条，检查嵌入模型配置`
        : '没有需要补建的条目'
    } else if (calls === 0) {
      vectorMsg.value = `检查了 ${processed} 条，向量都是最新的，无需重建`
    } else if (created > 0) {
      vectorMsg.value = `新补 ${created} 条向量（共处理 ${processed} 条，嵌入调用 ${calls} 次）`
    } else {
      vectorMsg.value = `重算 ${processed} 条（内容有改动），嵌入调用 ${calls} 次`
    }
    await load()
  } catch (e: any) {
    vectorMsg.value = e?.response?.data?.detail || e?.message || '补建失败'
  } finally {
    vectorBusy.value = false
  }
}

onMounted(load)
onUnmounted(() => {
  if (pollTimer) clearTimeout(pollTimer)
})

// ---------- 展示辅助 ----------

const trendMax = computed(() => Math.max(1, ...(data.value?.output.trend ?? []).map((t) => t.count)))

/** 一万 token 以上缩写成 1.2万，大数卡片放不下也读不清 */
function fmtTokens(n: number) {
  if (n >= 10_000) return `${(n / 10_000).toFixed(1)}万`
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}k`
  return String(n)
}

function fmtPct(r: number) {
  return `${(r * 100).toFixed(1)}%`
}

function fmtTime(s: string | null) {
  if (!s) return ''
  return new Date(s).toLocaleString('zh-CN', {
    hour12: false,
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  })
}

function kindLabel(k: string) {
  return KIND_LABEL[k] ?? k
}

function originLabel(o: string) {
  return ORIGIN_LABEL[o] ?? o
}

function batchStatus(s: string) {
  return BATCH_STATUS[s] ?? { label: s, cls: 'bg-ink-100 text-ink-600' }
}

/** 嵌入维度优先显示库里真实维度 —— 建索引认的是它，不是配置 */
const vectorDimText = computed(() => {
  const v = data.value?.vectors
  if (!v || v.dim == null) return ''
  return `${v.dim} 维`
})
</script>

<template>
  <div class="p-6 max-w-[1200px] mx-auto space-y-6">
    <!-- 页头 -->
    <div class="flex items-center gap-3">
      <div>
        <h1 class="text-xl font-semibold text-ink-900">AI 驾驶舱</h1>
        <p v-if="data" class="text-xs text-ink-500 mt-0.5">
          {{ data.site.name }} · 数字来自真实调用记录，更新于 {{ fmtTime(data.generated_at) }}
        </p>
      </div>
      <div class="ml-auto flex items-center gap-3">
        <router-link to="/cms/ai-workbench" class="btn-outline">AI 起草</router-link>
        <router-link to="/cms/ai-batch" class="btn-primary">批量生产</router-link>
      </div>
    </div>

    <div v-if="error" class="text-sm text-red-600 bg-red-50 border border-red-200 rounded-lg px-3 py-2">
      {{ error }}
    </div>

    <div v-if="loading && !data" class="text-sm text-ink-400 py-12 text-center">加载中…</div>

    <template v-if="data">
      <!-- 四个大数 -->
      <div class="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <div class="card !p-5">
          <div class="text-xs text-ink-500">今日出稿</div>
          <div class="text-3xl font-semibold text-ink-900 mt-1">{{ data.output.today }}</div>
          <div class="text-xs text-ink-400 mt-1">本周 {{ data.output.week }} 篇</div>
        </div>
        <div class="card !p-5">
          <div class="text-xs text-ink-500">本月出稿</div>
          <div class="text-3xl font-semibold text-ink-900 mt-1">{{ data.output.month }}</div>
          <div class="text-xs text-ink-400 mt-1">累计 {{ data.output.total }} 篇</div>
        </div>
        <div class="card !p-5">
          <div class="text-xs text-ink-500">本月 token 消耗</div>
          <div class="text-3xl font-semibold text-ink-900 mt-1">{{ fmtTokens(data.usage.month_tokens) }}</div>
          <div class="text-xs text-ink-400 mt-1">{{ data.usage.month_calls }} 次调用</div>
        </div>
        <div class="card !p-5">
          <div class="text-xs text-ink-500">AI 产出占比（本月）</div>
          <div class="text-3xl font-semibold text-ink-900 mt-1">{{ fmtPct(data.coverage.month_ratio) }}</div>
          <div class="text-xs text-ink-400 mt-1">
            {{ data.coverage.month_ai }} / {{ data.coverage.month_all }} 篇
          </div>
        </div>
      </div>

      <div class="grid grid-cols-1 lg:grid-cols-5 gap-6">
        <!-- 近 7 天出稿 -->
        <div class="card lg:col-span-2">
          <h3 class="text-sm font-semibold text-ink-900">近 7 天 AI 出稿</h3>
          <div class="mt-4 flex items-end gap-2 h-32">
            <div
              v-for="t in data.output.trend"
              :key="t.date"
              class="flex-1 flex flex-col items-center gap-1"
              :title="`${t.date}：${t.count} 篇`"
            >
              <span class="text-[10px] text-ink-400">{{ t.count || '' }}</span>
              <div
                class="w-full rounded-t bg-ink-900/80 min-h-[2px] transition-all"
                :style="{ height: `${Math.max(2, (t.count / trendMax) * 100)}%` }"
                :class="t.count ? '' : '!bg-ink-100'"
              ></div>
              <span class="text-[10px] text-ink-400">{{ t.date.slice(5) }}</span>
            </div>
          </div>
          <div v-if="data.output.by_origin.length" class="mt-3 flex flex-wrap gap-2">
            <span
              v-for="o in data.output.by_origin"
              :key="o.origin"
              class="text-xs px-2 py-0.5 rounded-full bg-ink-100 text-ink-600"
            >
              {{ originLabel(o.origin) }} {{ o.count }}
            </span>
          </div>
        </div>

        <!-- 能力矩阵 -->
        <div class="card lg:col-span-3">
          <div class="flex items-center">
            <h3 class="text-sm font-semibold text-ink-900">AI 能力</h3>
            <span class="ml-auto text-xs text-ink-400">
              就绪 {{ data.health.ready_count }} / {{ data.health.total_count }}
            </span>
            <router-link to="/cms/ai-settings" class="ml-3 text-xs text-ink-500 hover:text-ink-900 underline underline-offset-4">
              配置 →
            </router-link>
          </div>
          <div class="mt-4 grid grid-cols-1 sm:grid-cols-2 gap-2">
            <div
              v-for="c in data.capabilities"
              :key="c.key"
              class="flex items-center gap-3 rounded-xl border px-3 py-2.5"
              :class="c.ready ? 'border-emerald-200 bg-emerald-50/40' : 'border-ink-100 bg-ink-50/50'"
            >
              <span
                class="w-2 h-2 rounded-full shrink-0"
                :class="c.ready ? 'bg-emerald-500' : c.configured_only ? 'bg-amber-400' : 'bg-ink-200'"
              ></span>
              <div class="min-w-0">
                <div class="text-sm text-ink-900 font-medium leading-tight">
                  {{ c.label }}
                  <span v-if="c.key === 'embedding' && vectorDimText" class="text-xs text-ink-400 font-normal ml-1">
                    {{ vectorDimText }}
                  </span>
                </div>
                <div class="text-xs text-ink-400 truncate">
                  {{ c.ready ? `${c.provider} · ${c.model}` : c.configured_only ? '已配置，未接入调用' : '未配置' }}
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>

      <div class="grid grid-cols-1 lg:grid-cols-5 gap-6">
        <!-- 进行中批次 -->
        <div class="card lg:col-span-2">
          <div class="flex items-center">
            <h3 class="text-sm font-semibold text-ink-900">批量生产</h3>
            <router-link to="/cms/ai-batch" class="ml-auto text-xs text-ink-500 hover:text-ink-900 underline underline-offset-4">
              管理 →
            </router-link>
          </div>
          <div v-if="!data.batches.length" class="text-xs text-ink-400 mt-3">
            还没有批次。粘贴一批选题，AI 按顺序逐篇起草。
          </div>
          <div v-else class="mt-3 space-y-2.5">
            <div v-for="b in data.batches" :key="b.id" class="text-sm">
              <div class="flex items-center gap-2">
                <span class="text-ink-700 truncate">#{{ b.id }} {{ b.name }}</span>
                <span class="text-xs px-1.5 py-0.5 rounded-full shrink-0" :class="batchStatus(b.status).cls">
                  {{ batchStatus(b.status).label }}
                </span>
                <span class="ml-auto text-xs text-ink-400 shrink-0">
                  {{ b.succeeded }}/{{ b.total }}<template v-if="b.failed"> · 失败 {{ b.failed }}</template>
                </span>
              </div>
              <div class="mt-1 h-1.5 rounded-full bg-ink-100 overflow-hidden">
                <div
                  class="h-full bg-ink-900 transition-all"
                  :style="{ width: `${b.total ? Math.round(((b.succeeded + b.failed + b.skipped) / b.total) * 100) : 0}%` }"
                ></div>
              </div>
            </div>
          </div>
        </div>

        <!-- 语义检索覆盖 -->
        <div class="card lg:col-span-3">
          <div class="flex items-center">
            <h3 class="text-sm font-semibold text-ink-900">语义检索覆盖</h3>
            <button
              v-if="data.vectors.ratio < 1"
              class="ml-auto px-2.5 py-1 text-xs rounded-lg border border-ink-200 hover:bg-ink-50 disabled:opacity-50"
              :disabled="vectorBusy"
              @click="rebuildVectors"
            >{{ vectorBusy ? '补建中…' : '补齐向量' }}</button>
            <!-- 覆盖率满时按钮不消失而是置灰：能力在哪、为什么不能点，都要看得见 -->
            <span
              v-else
              class="ml-auto px-2.5 py-1 text-xs rounded-lg border border-ink-100 text-ink-300 cursor-default"
              title="所有条目都已有向量"
            >向量已齐</span>
          </div>
          <div class="mt-3 flex items-center gap-4">
            <div class="flex-1 h-2 rounded-full bg-ink-100 overflow-hidden">
              <div class="h-full bg-emerald-500 transition-all" :style="{ width: `${data.vectors.ratio * 100}%` }"></div>
            </div>
            <span class="text-sm text-ink-700 shrink-0">
              {{ data.vectors.embedded }} / {{ data.vectors.entries }}
              <template v-if="vectorDimText"> · {{ vectorDimText }}</template>
            </span>
          </div>
          <p v-if="vectorMsg" class="text-xs mt-2" :class="vectorMsg.includes('失败') ? 'text-red-600' : 'text-emerald-600'">
            {{ vectorMsg }}
          </p>
          <p v-if="data.vectors.ratio < 1" class="text-xs text-ink-400 mt-2">
            有条目还没建向量，语义检索和「找相似」会漏掉它们。点「补齐向量」一次最多补 50 条，不够再点。
          </p>
          <p v-else class="text-xs text-ink-400 mt-2">全部条目已建立向量索引。</p>
        </div>
      </div>

      <!-- 最近 AI 调用 -->
      <div class="card">
        <div class="flex items-center">
          <h3 class="text-sm font-semibold text-ink-900">最近 AI 调用</h3>
          <span class="ml-auto text-xs text-ink-400">{{ data.usage.today_calls }} 次今日</span>
        </div>
        <div v-if="!data.recent.length" class="text-xs text-ink-400 mt-3">还没有调用记录。</div>
        <div v-else class="mt-3 overflow-x-auto">
          <table class="w-full text-sm">
            <thead>
              <tr class="text-left text-xs text-ink-400 border-b border-ink-100">
                <th class="py-2 pr-4 font-normal">类型</th>
                <th class="py-2 pr-4 font-normal">模型</th>
                <th class="py-2 pr-4 font-normal text-right">token</th>
                <th class="py-2 pr-4 font-normal text-right">耗时</th>
                <th class="py-2 pr-4 font-normal">结果</th>
                <th class="py-2 pr-4 font-normal">时间</th>
                <th class="py-2 font-normal"></th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="g in data.recent" :key="g.id" class="border-b border-ink-50 last:border-0">
                <td class="py-2 pr-4 text-ink-900">{{ kindLabel(g.kind) }}</td>
                <td class="py-2 pr-4 text-ink-500 text-xs">{{ g.model }}</td>
                <td class="py-2 pr-4 text-right text-ink-500 text-xs">
                  {{ fmtTokens(g.tokens_in + g.tokens_out) }}
                </td>
                <td class="py-2 pr-4 text-right text-ink-500 text-xs">
                  {{ (g.latency_ms / 1000).toFixed(1) }}s
                </td>
                <td class="py-2 pr-4">
                  <span
                    class="text-xs px-1.5 py-0.5 rounded-full"
                    :class="g.status === 'ok' ? 'bg-emerald-50 text-emerald-700' : 'bg-red-50 text-red-700'"
                  >
                    {{ g.status === 'ok' ? '成功' : '失败' }}
                  </span>
                  <span v-if="g.error" class="text-xs text-red-500 ml-1" :title="g.error">!</span>
                </td>
                <td class="py-2 pr-4 text-ink-400 text-xs whitespace-nowrap">{{ fmtTime(g.created_at) }}</td>
                <td class="py-2 text-right">
                  <router-link
                    v-if="g.entry_id"
                    :to="`/cms/entries/${g.entry_id}`"
                    class="text-xs text-ink-500 hover:text-ink-900 underline underline-offset-4 whitespace-nowrap"
                  >
                    打开草稿 →
                  </router-link>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </template>
  </div>
</template>
