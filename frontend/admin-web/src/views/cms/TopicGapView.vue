<script setup lang="ts">
/**
 * 选题 Gap 分析页。
 *
 * 定位：给内容团队一张「下周写什么」的清单，不是一份分析报告。
 * 所以每条缺口都要带一个**能直接开工的标题** + 一个「去起草」按钮 ——
 * 看完就能进编辑器，中间不需要再翻译一次。
 *
 * 三层信息刻意分开呈现：
 *   1. 覆盖概况（一句话判断偏科在哪）
 *   2. 决策阶段分布（B2B 库最常见病：认知层一堆，决策层空白）
 *   3. 缺口清单（按优先级排序，high 在前）
 */
import { computed, onMounted, ref } from 'vue'
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

const loading = ref(false)
const elapsed = ref(0)
const errorMsg = ref('')
const report = ref<GapReport | null>(null)
const limit = ref(8)
const ctKey = ref('')

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

const intentRows = computed(() => {
  const d = report.value?.intent_distribution || {}
  const labels: Record<string, string> = {
    awareness: '认知',
    consideration: '比较',
    decision: '决策',
    retention: '留存',
  }
  return Object.keys(labels).map((k) => ({ key: k, label: labels[k], count: d[k] || 0 }))
})

const totalGaps = computed(() => report.value?.gaps.length || 0)

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
  } catch (e: any) {
    errorMsg.value = e?.response?.data?.detail || e?.message || '分析失败'
  } finally {
    window.clearInterval(timer)
    elapsed.value = Math.round((Date.now() - t0) / 1000)
    loading.value = false
  }
}

function startDraft(g: Gap) {
  const q: Record<string, string> = { title: g.suggested_title }
  if (ctKey.value.trim()) q.ct = ctKey.value.trim()
  window.location.href = `/cms/entries/new?${new URLSearchParams(q).toString()}`
}

function copyTitle(g: Gap) {
  navigator.clipboard?.writeText(g.suggested_title)
}

onMounted(analyze)
</script>

<template>
  <div class="min-h-screen bg-ink-50">
    <header class="bg-white border-b border-ink-200">
      <div class="max-w-6xl mx-auto px-6 h-14 flex items-center gap-4">
        <router-link to="/cms/ai" class="text-sm text-ink-500 hover:text-ink-900">← AI 驾驶舱</router-link>
        <span class="font-semibold">选题缺口</span>
        <span class="text-xs text-ink-400">已有内容 vs 该有的内容</span>
      </div>
    </header>

    <main class="max-w-6xl mx-auto px-6 py-8">
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
              <li v-for="r in intentRows" :key="r.key" class="flex items-center justify-between text-sm">
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
                  @click="startDraft(g)"
                >去起草</button>
                <button
                  class="px-3 py-1.5 text-xs rounded-lg border border-ink-200 text-ink-600 hover:bg-ink-50"
                  @click="copyTitle(g)"
                >复制标题</button>
              </div>
            </div>
          </div>
        </div>
      </template>
    </main>
  </div>
</template>
