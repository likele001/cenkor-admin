<script setup lang="ts">
/**
 * 内容体检报告页。
 *
 * 定位：不是「另一个列表页」，而是**修哪里**的清单。
 * 所以默认按分数升序（最烂的在最上面），每条直接给跳编辑的入口，
 * 检查项按严重度配色 —— 运营打开就能干活，不用先学会读报告。
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
  issues: Issue[]
  chars: number
  has_image: boolean
  inbound_links: number
  outbound_links: number
  updated_at?: string | null
  public_url?: string
}

interface Report {
  scanned: number
  truncated: boolean
  score: number
  level: 'critical' | 'warning' | 'healthy'
  problem_count: number
  generated_at: string
  check_summary: Record<string, { label: string; severity: string; hit: number }>
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

const checkRows = computed(() => {
  const cs = report.value?.check_summary || {}
  return Object.entries(cs)
    .map(([key, v]) => ({ key, ...v }))
    .sort((a, b) => b.hit - a.hit)
})

const activeChecks = computed(() => checkRows.value.filter((r) => r.hit > 0))

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
        <span class="text-xs text-ink-400">过期 · 死链 · 过薄 · SEO · 孤岛 · 缺图 · 陈旧</span>
      </div>
    </header>

    <main class="max-w-7xl mx-auto px-6 py-8">
      <p v-if="errorMsg" class="mb-4 text-sm text-red-600 bg-red-50 border border-red-200 rounded-xl px-4 py-2.5">
        {{ errorMsg }}
      </p>

      <!-- 参数 + 刷新 -->
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
            class="ml-2 w-20 px-2 py-1 border border-ink-200 rounded-lg text-sm"
          />
        </label>
        <label class="text-sm text-ink-600 flex items-center gap-2">
          <input v-model="includeDrafts" type="checkbox" class="rounded border-ink-300" />
          连同草稿一起体检
        </label>
        <button
          class="ml-auto px-4 py-2 text-sm rounded-lg bg-ink-900 text-white hover:bg-ink-800 disabled:opacity-50"
          :disabled="loading"
          @click="load"
        >
          {{ loading ? '体检中…' : '重新体检' }}
        </button>
      </div>

      <!-- 总览 -->
      <div v-if="report" class="grid gap-4 md:grid-cols-4 mb-6">
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

        <div class="card md:col-span-2">
          <p class="text-xs text-ink-400 mb-2">检查项命中分布</p>
          <div class="flex flex-wrap gap-2">
            <span
              v-for="row in checkRows"
              :key="row.key"
              class="px-2.5 py-1 text-xs rounded-lg border"
              :class="row.hit > 0
                ? (row.severity === 'critical' ? 'bg-red-50 text-red-700 border-red-200' : 'bg-amber-50 text-amber-700 border-amber-200')
                : 'bg-ink-50 text-ink-400 border-ink-200'"
            >
              {{ row.label }} {{ row.hit }}
            </span>
          </div>
          <p v-if="!activeChecks.length" class="mt-3 text-xs text-emerald-600">
            本次体检没有发现任何问题项。
          </p>
        </div>
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

                <ul v-if="expanded.has(item.entry_id)" class="mt-2 space-y-1 text-xs text-ink-600 bg-ink-50 rounded-lg p-3">
                  <li v-for="(is_, idx) in item.issues" :key="idx">
                    <span class="font-medium">{{ is_.label }}：</span>{{ is_.message }}
                    <div v-if="is_.hrefs?.length" class="mt-1 text-ink-400 break-all">
                      死链：{{ is_.hrefs.join(' , ') }}
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
