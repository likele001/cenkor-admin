<script setup lang="ts">
/**
 * AI 批量生产 · 一次起草 N 篇
 *
 * 单篇起草只能演示，「这个月 20 篇」才是真需求。这里把一批选题丢进队列，
 * 后台逐篇起草并落成草稿，中途可暂停、可取消、可只重试失败项。
 *
 * 两个刻意的产品决定：
 * 1. AI 产出永远是 draft，绝不直接发布 —— 批量出错的代价比单篇大得多
 * 2. 一个站点同时只能跑一个批次（后端唯一索引保证），前端提前给出提示，
 *    而不是让用户点了 start 才吃 409
 */
import { computed, onUnmounted, ref, watch } from 'vue'
import { api } from '@/lib/api'
import { useAuthStore } from '@/stores/auth'

interface Job {
  id: number
  site_id: number
  name: string
  content_type_id: number
  content_type_key: string
  status: string
  lang: string
  total: number
  succeeded: number
  failed: number
  skipped: number
  concurrency: number
  last_error: string | null
  created_at: string | null
  started_at: string | null
  finished_at: string | null
}

interface Item {
  id: number
  seq: number
  brief: string
  status: string
  entry_id: number | null
  title: string | null
  error: string | null
  attempts: number
  tokens_in: number
  tokens_out: number
}

interface Detail extends Job {
  items: Item[]
  live: boolean
}

interface Stats {
  jobs: number
  topics: number
  succeeded: number
  failed: number
  running: number
}

const auth = useAuthStore()
const canManage = computed(() => auth.hasPermission('cms:ai:manage'))

const jobs = ref<Job[]>([])
const detail = ref<Detail | null>(null)
const stats = ref<Stats | null>(null)
const contentTypes = ref<{ id: number; key: string; name: string }[]>([])

const error = ref('')
const toast = ref('')
const busy = ref(false)
const loading = ref(false)

// 新建表单
const showForm = ref(false)
const formCtId = ref<number | null>(null)
const formName = ref('')
const formTopics = ref('')
const formConcurrency = ref(1)

let pollTimer: ReturnType<typeof setTimeout> | null = null

const topicsParsed = computed(() => {
  const seen = new Set<string>()
  const out: string[] = []
  for (const raw of formTopics.value.split('\n')) {
    const t = raw.trim()
    if (!t || seen.has(t)) continue
    seen.add(t)
    out.push(t)
  }
  return out
})

function errText(e: any): string {
  const d = e?.response?.data?.detail
  if (typeof d === 'string') return d
  if (Array.isArray(d)) return d.map((x: any) => x.msg ?? JSON.stringify(x)).join('; ')
  return e?.message || '请求失败'
}

function flash(msg: string) {
  toast.value = msg
  setTimeout(() => (toast.value = ''), 2600)
}

const STATUS_META: Record<string, { label: string; cls: string }> = {
  pending: { label: '待开始', cls: 'bg-ink-100 text-ink-600' },
  running: { label: '进行中', cls: 'bg-blue-50 text-blue-700' },
  paused: { label: '已暂停', cls: 'bg-amber-50 text-amber-700' },
  done: { label: '已完成', cls: 'bg-emerald-50 text-emerald-700' },
  cancelled: { label: '已取消', cls: 'bg-red-50 text-red-700' },
}

const ITEM_META: Record<string, { label: string; cls: string }> = {
  pending: { label: '排队中', cls: 'text-ink-400' },
  running: { label: '起草中', cls: 'text-blue-600' },
  done: { label: '已生成', cls: 'text-emerald-700' },
  failed: { label: '失败', cls: 'text-red-600' },
  skipped: { label: '已跳过', cls: 'text-ink-400' },
}

function statusMeta(s: string) {
  return STATUS_META[s] ?? { label: s, cls: 'bg-ink-100 text-ink-600' }
}

function itemMeta(s: string) {
  return ITEM_META[s] ?? { label: s, cls: 'text-ink-500' }
}

function pct(j: Job) {
  if (!j.total) return 0
  return Math.min(100, Math.round(((j.succeeded + j.failed + j.skipped) / j.total) * 100))
}

function fmtTime(s: string | null) {
  if (!s) return ''
  return new Date(s).toLocaleString('zh-CN', { hour12: false, month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' })
}

async function loadJobs() {
  const { data } = await api.get<Job[]>('/api/v1/cms/ai/batch')
  jobs.value = data
}

async function loadStats() {
  const { data } = await api.get<Stats>('/api/v1/cms/ai/batch-stats')
  stats.value = data
}

async function loadContentTypes() {
  const { data } = await api.get('/api/v1/cms/content-types')
  const items = (data.items || data || []).filter((c: any) => c.status !== 'archived')
  contentTypes.value = items
  if (items.length && !formCtId.value) formCtId.value = items[0].id
}

async function selectJob(id: number) {
  const { data } = await api.get<Detail>(`/api/v1/cms/ai/batch/${id}`)
  detail.value = data
  schedulePoll()
}

/** running 时每 2s 拉一次；一旦不是 running 就停，避免无意义请求。 */
function schedulePoll() {
  if (pollTimer) {
    clearTimeout(pollTimer)
    pollTimer = null
  }
  const d = detail.value
  if (!d || d.status !== 'running') return
  pollTimer = setTimeout(async () => {
    try {
      const st = d.status
      await loadJobs()
      await loadStats()
      if (detail.value) await selectJob(detail.value.id)
      if (st !== 'running') return
    } catch {
      /* 轮询失败不打断界面，下一轮再来 */
    }
  }, 2000)
}

watch(
  () => detail.value?.status,
  () => schedulePoll()
)

async function refreshAll() {
  await Promise.all([loadJobs(), loadStats()])
  if (detail.value) await selectJob(detail.value.id)
}

async function createJob() {
  if (!canManage.value) return
  error.value = ''
  if (!formCtId.value) {
    error.value = '请选择内容类型'
    return
  }
  const topics = topicsParsed.value
  if (!topics.length) {
    error.value = '至少要有一个选题'
    return
  }
  busy.value = true
  try {
    const { data } = await api.post<Detail>('/api/v1/cms/ai/batch', {
      name: formName.value.trim() || null,
      content_type_id: formCtId.value,
      topics,
      concurrency: formConcurrency.value,
    })
    showForm.value = false
    formName.value = ''
    formTopics.value = ''
    flash(`已建批次：${data.total} 篇`)
    await refreshAll()
    await selectJob(data.id)
  } catch (e: any) {
    error.value = errText(e)
  } finally {
    busy.value = false
  }
}

async function act(path: string, okText: string, confirmText?: string) {
  if (!canManage.value || !detail.value) return
  if (confirmText && !window.confirm(confirmText)) return
  busy.value = true
  error.value = ''
  try {
    await api.post(`/api/v1/cms/ai/batch/${detail.value.id}/${path}`)
    flash(okText)
    await refreshAll()
  } catch (e: any) {
    error.value = errText(e)
  } finally {
    busy.value = false
  }
}

async function removeJob() {
  if (!canManage.value || !detail.value) return
  if (!window.confirm('删除这个批次记录？已生成的草稿条目会保留，不会被删掉。')) return
  busy.value = true
  try {
    const id = detail.value.id
    await api.delete(`/api/v1/cms/ai/batch/${id}`)
    detail.value = null
    flash('批次记录已删除')
    await refreshAll()
  } catch (e: any) {
    error.value = errText(e)
  } finally {
    busy.value = false
  }
}

onUnmounted(() => {
  if (pollTimer) clearTimeout(pollTimer)
})

// 初始加载
;(async () => {
  loading.value = true
  try {
    await Promise.all([loadJobs(), loadStats(), loadContentTypes()])
    if (jobs.value.length) await selectJob(jobs.value[0].id)
  } catch (e: any) {
    error.value = errText(e)
  } finally {
    loading.value = false
  }
})()
</script>

<template>
  <div class="min-h-screen bg-ink-50">
    <header class="bg-white border-b border-ink-200">
      <div class="max-w-7xl mx-auto px-6 h-14 flex items-center gap-4">
        <router-link to="/cms/ai-settings" class="text-sm text-ink-500 hover:text-ink-900">
          ← AI 设置
        </router-link>
        <span class="font-semibold">批量生产</span>
        <span class="text-xs text-ink-400">一次起草 N 篇，全部落成草稿</span>
      </div>
    </header>

    <main class="max-w-7xl mx-auto px-6 py-8 space-y-5">
      <p v-if="error" class="text-sm text-red-600 bg-red-50 border border-red-200 rounded-lg px-3 py-2">
        {{ error }}
      </p>
      <p
        v-if="toast"
        class="text-sm text-emerald-700 bg-emerald-50 border border-emerald-200 rounded-lg px-3 py-2"
      >
        {{ toast }}
      </p>

      <!-- 统计 -->
      <div v-if="stats" class="grid grid-cols-2 md:grid-cols-4 gap-3">
        <div class="card !py-3">
          <div class="text-xs text-ink-400">历史批次</div>
          <div class="mt-1 text-xl font-semibold text-ink-900">{{ stats.jobs }}</div>
        </div>
        <div class="card !py-3">
          <div class="text-xs text-ink-400">累计选题</div>
          <div class="mt-1 text-xl font-semibold text-ink-900">{{ stats.topics }}</div>
        </div>
        <div class="card !py-3">
          <div class="text-xs text-ink-400">已产出草稿</div>
          <div class="mt-1 text-xl font-semibold text-emerald-700">{{ stats.succeeded }}</div>
        </div>
        <div class="card !py-3">
          <div class="text-xs text-ink-400">正在跑</div>
          <div class="mt-1 text-xl font-semibold" :class="stats.running ? 'text-blue-700' : 'text-ink-900'">
            {{ stats.running }}
          </div>
        </div>
      </div>

      <div class="grid grid-cols-1 lg:grid-cols-[360px_1fr] gap-5 items-start">
        <!-- 左：批次列表 -->
        <aside class="card !p-0 overflow-hidden">
          <div class="px-4 py-3 border-b border-ink-100 flex items-center justify-between">
            <span class="text-sm font-semibold text-ink-900">批次</span>
            <button
              class="text-xs px-2 py-1 rounded border border-ink-200 text-ink-600 hover:border-ink-900 disabled:opacity-40"
              :disabled="!canManage"
              @click="showForm = true"
            >
              + 新建
            </button>
          </div>

          <div v-if="loading" class="p-4 text-sm text-ink-400">加载中…</div>
          <div v-else-if="!jobs.length" class="p-4 text-sm text-ink-400">
            还没有批次。点「新建」，粘贴一批选题就能开始。
          </div>
          <ul v-else class="divide-y divide-ink-100 max-h-[62vh] overflow-y-auto">
            <li v-for="j in jobs" :key="j.id">
              <button
                class="w-full text-left px-4 py-3 hover:bg-ink-50 transition-colors"
                :class="detail?.id === j.id ? 'bg-ink-50' : ''"
                @click="selectJob(j.id)"
              >
                <div class="flex items-center justify-between gap-2">
                  <span class="text-sm font-medium text-ink-900 truncate">{{ j.name }}</span>
                  <span class="text-[11px] px-1.5 py-0.5 rounded shrink-0" :class="statusMeta(j.status).cls">
                    {{ statusMeta(j.status).label }}
                  </span>
                </div>
                <div class="mt-1.5 flex items-center gap-2">
                  <div class="flex-1 h-1 rounded-full bg-ink-100 overflow-hidden">
                    <div
                      class="h-full rounded-full transition-all"
                      :class="j.failed ? 'bg-amber-500' : 'bg-emerald-500'"
                      :style="{ width: pct(j) + '%' }"
                    ></div>
                  </div>
                  <span class="text-[11px] text-ink-400 font-mono shrink-0">
                    {{ j.succeeded }}/{{ j.total }}
                  </span>
                </div>
                <div class="mt-1 text-[11px] text-ink-400">
                  {{ j.content_type_key }} · {{ fmtTime(j.created_at) }}
                </div>
              </button>
            </li>
          </ul>
        </aside>

        <!-- 右：新建 / 详情 -->
        <section class="space-y-5">
          <!-- 新建表单 -->
          <div v-if="showForm" class="card">
            <div class="flex items-center justify-between mb-3">
              <h2 class="text-base font-semibold text-ink-900">新建批次</h2>
              <button class="text-xs text-ink-500 hover:text-ink-900" @click="showForm = false">
                收起
              </button>
            </div>

            <div class="grid grid-cols-1 md:grid-cols-3 gap-3">
              <label class="block">
                <span class="text-xs text-ink-500">内容类型</span>
                <select
                  v-model.number="formCtId"
                  class="mt-1 w-full text-sm rounded-lg border border-ink-200 px-3 py-2 focus:outline-none focus:border-ink-900"
                >
                  <option v-for="c in contentTypes" :key="c.id" :value="c.id">
                    {{ c.name }}（{{ c.key }}）
                  </option>
                </select>
              </label>
              <label class="block">
                <span class="text-xs text-ink-500">批次名称（选填）</span>
                <input
                  v-model="formName"
                  placeholder="默认用「类型 · 时间」"
                  class="mt-1 w-full text-sm rounded-lg border border-ink-200 px-3 py-2 focus:outline-none focus:border-ink-900"
                />
              </label>
              <label class="block">
                <span class="text-xs text-ink-500">并发数</span>
                <select
                  v-model.number="formConcurrency"
                  class="mt-1 w-full text-sm rounded-lg border border-ink-200 px-3 py-2 focus:outline-none focus:border-ink-900"
                >
                  <option :value="1">1（稳，推荐）</option>
                  <option :value="2">2</option>
                  <option :value="3">3</option>
                  <option :value="4">4（快，易被限流）</option>
                </select>
              </label>
            </div>

            <label class="block mt-3">
              <span class="text-xs text-ink-500">
                选题 / 素材 · 一行一条（空行自动忽略，重复自动去重）
              </span>
              <textarea
                v-model="formTopics"
                rows="9"
                spellcheck="false"
                placeholder="春季新品上市：主打轻量便携，面向通勤人群&#10;老客户回访：设备保养的 5 个关键点&#10;行业观察：2026 年内容营销的三个变化"
                class="mt-1 w-full font-mono text-[13px] leading-relaxed rounded-lg border border-ink-200 px-3 py-2.5 focus:outline-none focus:border-ink-900 resize-y"
              ></textarea>
            </label>

            <div class="mt-3 flex flex-wrap items-center gap-2">
              <span class="text-xs text-ink-400">
                有效 <span class="font-semibold text-ink-900">{{ topicsParsed.length }}</span> 条
                <span v-if="topicsParsed.length > 200" class="text-red-600">（超过 200，会被拒）</span>
              </span>
              <div class="flex-1"></div>
              <button
                class="px-3 py-2 text-sm rounded-lg border border-ink-200 text-ink-600 hover:border-ink-400"
                @click="formTopics = ''; formName = ''"
              >
                清空
              </button>
              <button
                class="px-4 py-2 text-sm rounded-lg bg-ink-900 text-white font-medium disabled:opacity-40"
                :disabled="busy || !topicsParsed.length || !canManage"
                @click="createJob"
              >
                创建批次
              </button>
            </div>
            <p class="mt-2 text-xs text-ink-400">
              创建后需要点「开始」才会真正跑。AI 产出一律是草稿，不会自动发布。
            </p>
          </div>

          <!-- 详情 -->
          <div v-if="detail" class="space-y-5">
            <div class="card">
              <div class="flex flex-wrap items-start justify-between gap-3">
                <div class="min-w-0">
                  <div class="flex items-center gap-2">
                    <h2 class="text-base font-semibold text-ink-900 truncate">{{ detail.name }}</h2>
                    <span
                      class="text-[11px] px-1.5 py-0.5 rounded shrink-0"
                      :class="statusMeta(detail.status).cls"
                    >
                      {{ statusMeta(detail.status).label }}
                    </span>
                  </div>
                  <p class="mt-1 text-xs text-ink-400">
                    {{ detail.content_type_key }} · 共 {{ detail.total }} 篇 · 并发
                    {{ detail.concurrency }} · 创建于 {{ fmtTime(detail.created_at) }}
                    <span v-if="detail.started_at"> · 开始 {{ fmtTime(detail.started_at) }}</span>
                    <span v-if="detail.finished_at"> · 结束 {{ fmtTime(detail.finished_at) }}</span>
                  </p>
                </div>

                <div class="flex flex-wrap items-center gap-2">
                  <button
                    v-if="detail.status !== 'running' && detail.status !== 'done' && detail.status !== 'cancelled'"
                    class="px-3 py-1.5 text-sm rounded-lg bg-ink-900 text-white disabled:opacity-40"
                    :disabled="busy || !canManage"
                    @click="act('start', '已开始')"
                  >
                    {{ detail.status === 'paused' ? '继续' : '开始' }}
                  </button>
                  <button
                    v-if="detail.status === 'running'"
                    class="px-3 py-1.5 text-sm rounded-lg border border-ink-200 text-ink-700 hover:border-ink-400 disabled:opacity-40"
                    :disabled="busy || !canManage"
                    @click="act('pause', '已暂停，跑完当前这篇就停')"
                  >
                    暂停
                  </button>
                  <button
                    v-if="detail.failed > 0 && detail.status !== 'running'"
                    class="px-3 py-1.5 text-sm rounded-lg border border-amber-300 text-amber-700 hover:border-amber-500 disabled:opacity-40"
                    :disabled="busy || !canManage"
                    @click="act('retry-failed', '失败项已重新入队')"
                  >
                    重试失败 {{ detail.failed }}
                  </button>
                  <button
                    v-if="detail.status === 'running' || detail.status === 'paused' || detail.status === 'pending'"
                    class="px-3 py-1.5 text-sm rounded-lg border border-ink-200 text-ink-600 hover:border-red-400 hover:text-red-600 disabled:opacity-40"
                    :disabled="busy || !canManage"
                    @click="act('cancel', '已取消', '取消后未跑的条目会标记为已跳过，且无法恢复。继续？')"
                  >
                    取消
                  </button>
                  <button
                    v-if="detail.status !== 'running'"
                    class="px-3 py-1.5 text-sm rounded-lg border border-ink-200 text-ink-500 hover:border-red-400 hover:text-red-600 disabled:opacity-40"
                    :disabled="busy || !canManage"
                    @click="removeJob"
                  >
                    删除
                  </button>
                </div>
              </div>

              <div class="mt-4">
                <div class="flex items-center justify-between text-xs text-ink-500 mb-1.5">
                  <span>
                    成功 {{ detail.succeeded }} ·
                    失败 <span :class="detail.failed ? 'text-red-600 font-medium' : ''">{{ detail.failed }}</span> ·
                    跳过 {{ detail.skipped }} · 共 {{ detail.total }}
                  </span>
                  <span class="font-mono">{{ pct(detail) }}%</span>
                </div>
                <div class="h-2 rounded-full bg-ink-100 overflow-hidden flex">
                  <div
                    class="h-full bg-emerald-500 transition-all"
                    :style="{ width: (detail.total ? (detail.succeeded / detail.total) * 100 : 0) + '%' }"
                  ></div>
                  <div
                    class="h-full bg-red-500 transition-all"
                    :style="{ width: (detail.total ? (detail.failed / detail.total) * 100 : 0) + '%' }"
                  ></div>
                  <div
                    class="h-full bg-ink-300 transition-all"
                    :style="{ width: (detail.total ? (detail.skipped / detail.total) * 100 : 0) + '%' }"
                  ></div>
                </div>
              </div>

              <p v-if="detail.last_error" class="mt-3 text-xs text-red-600 bg-red-50 border border-red-200 rounded px-2 py-1.5">
                执行器报错：{{ detail.last_error }}
              </p>
              <p v-if="!canManage" class="mt-3 text-xs text-amber-800 bg-amber-50 border border-amber-200 rounded px-2 py-1.5">
                你当前是只读权限（缺 <span class="font-mono">cms:ai:manage</span>），可以看进度但不能操作。
              </p>
            </div>

            <!-- 逐篇 -->
            <div class="card !p-0 overflow-hidden">
              <div class="px-4 py-3 border-b border-ink-100 flex items-center justify-between">
                <span class="text-sm font-semibold text-ink-900">逐篇状态</span>
                <span v-if="detail.status === 'running'" class="text-[11px] text-blue-600">
                  每 2 秒自动刷新
                </span>
              </div>
              <ul class="divide-y divide-ink-100 max-h-[55vh] overflow-y-auto">
                <li v-for="it in detail.items" :key="it.id" class="px-4 py-2.5 flex items-start gap-3">
                  <span class="text-[11px] font-mono text-ink-300 w-7 pt-0.5 shrink-0">
                    {{ String(it.seq).padStart(2, '0') }}
                  </span>
                  <div class="min-w-0 flex-1">
                    <div class="flex items-center gap-2">
                      <span class="text-sm text-ink-800 truncate">
                        {{ it.title || it.brief }}
                      </span>
                      <span class="text-[11px] shrink-0" :class="itemMeta(it.status).cls">
                        {{ itemMeta(it.status).label }}
                      </span>
                      <span
                        v-if="it.attempts > 1"
                        class="text-[11px] text-amber-600 shrink-0"
                        :title="`尝试了 ${it.attempts} 次`"
                      >
                        ×{{ it.attempts }}
                      </span>
                    </div>
                    <div v-if="it.title && it.title !== it.brief" class="mt-0.5 text-[11px] text-ink-400 truncate">
                      {{ it.brief }}
                    </div>
                    <div v-if="it.error" class="mt-1 text-[11px] text-red-600 break-all">
                      {{ it.error }}
                    </div>
                  </div>
                  <a
                    v-if="it.entry_id"
                    :href="`/cms/entries/${it.entry_id}`"
                    target="_blank"
                    class="text-[11px] text-ink-500 hover:text-ink-900 shrink-0 pt-0.5"
                  >
                    打开草稿 →
                  </a>
                </li>
              </ul>
            </div>
          </div>

          <div v-else-if="!showForm" class="card text-sm text-ink-400">
            左侧选一个批次看详情，或点「新建」开一批。
          </div>
        </section>
      </div>
    </main>
  </div>
</template>
