<script setup lang="ts">
/**
 * 问答自测页（内部用）。
 *
 * 为什么运营需要这个：公开问答上线后，最大的风险不是「答不出」，
 * 是**答得一本正经但库里没有**。这个页面就是给内容团队一个「我这么问，
 * 它会怎么答」的沙盘 —— 发布前自己先问一遍最难的问题。
 *
 * 正文渲染刻意不用 v-html：把 [n] 切成片段用模板拼，
 * 这样模型输出的任何 HTML 都进不了 DOM。
 */
import { computed, ref } from 'vue'
import { api } from '@/lib/api'

interface Citation {
  index: number
  title: string | null
  heading_path: string | null
  source_url: string | null
  snippet: string
  score: number
}

interface AskResult {
  question: string
  answer: string
  citations: Citation[]
  no_answer: boolean
  reason: string | null
  followups: string[]
  llm_used: boolean
  warning: string | null
}

interface Seg {
  text: string
  cite?: number
}

const question = ref('')
const loading = ref(false)
const elapsed = ref(0)
const errorMsg = ref('')
const result = ref<AskResult | null>(null)
const activeCite = ref<number | null>(null)

const SUGGESTIONS = [
  '取向硅钢的磁滞损耗受哪些因素影响？',
  '你们能提供哪些牌号？',
  '怎么判断供应商的资质？',
]

const segments = computed<Seg[]>(() => {
  const a = result.value?.answer || ''
  if (!a) return []
  const out: Seg[] = []
  const re = /\[(\d+)\]/g
  let last = 0
  let m: RegExpExecArray | null = re.exec(a)
  while (m !== null) {
    if (m.index > last) out.push({ text: a.slice(last, m.index) })
    out.push({ text: m[1], cite: Number(m[1]) })
    last = m.index + m[0].length
    m = re.exec(a)
  }
  if (last < a.length) out.push({ text: a.slice(last) })
  return out
})

async function submit(q?: string) {
  const text = (q ?? question.value).trim()
  if (!text || loading.value) return
  question.value = text
  loading.value = true
  errorMsg.value = ''
  result.value = null
  activeCite.value = null
  const t0 = Date.now()
  const timer = window.setInterval(() => {
    elapsed.value = Math.round((Date.now() - t0) / 1000)
  }, 500)
  try {
    const { data } = await api.post(
      '/api/v1/cms/ai/ask',
      { question: text, top_k: 5 },
      { timeout: 180000 },
    )
    result.value = data as AskResult
  } catch (e: any) {
    errorMsg.value = e?.response?.data?.detail || e?.message || '提问失败'
  } finally {
    window.clearInterval(timer)
    elapsed.value = Math.round((Date.now() - t0) / 1000)
    loading.value = false
  }
}

function jump(c: Citation) {
  activeCite.value = c.index
  if (c.source_url) window.open(c.source_url, '_blank')
}

function jumpByIndex(i: number) {
  const hit = result.value?.citations.find((c) => c.index === i)
  if (hit) jump(hit)
}
</script>

<template>
  <div class="min-h-screen bg-ink-50">
    <header class="bg-white border-b border-ink-200">
      <div class="max-w-4xl mx-auto px-6 h-14 flex items-center gap-4">
        <router-link to="/cms/ai" class="text-sm text-ink-500 hover:text-ink-900">← AI 驾驶舱</router-link>
        <span class="font-semibold">问答自测</span>
        <span class="text-xs text-ink-400">访客这么问，我们答得上来吗</span>
      </div>
    </header>

    <main class="max-w-4xl mx-auto px-6 py-8">
      <div class="card mb-4">
        <div class="flex gap-2">
          <input
            v-model="question"
            placeholder="输入一个访客可能问的问题…"
            class="flex-1 px-3 py-2 border border-ink-200 rounded-lg text-sm focus:outline-none focus:border-ink-400"
            @keydown.enter="submit()"
          />
          <button
            class="px-4 py-2 text-sm rounded-lg bg-ink-900 text-white hover:bg-ink-800 disabled:opacity-50"
            :disabled="loading || !question.trim()"
            @click="submit()"
          >
            {{ loading ? `思考中 ${elapsed}s` : '提问' }}
          </button>
        </div>

        <div class="mt-2 flex flex-wrap gap-2">
          <button
            v-for="s in SUGGESTIONS"
            :key="s"
            class="px-2.5 py-1 text-xs text-ink-500 bg-ink-100 rounded hover:bg-ink-200"
            :disabled="loading"
            @click="submit(s)"
          >{{ s }}</button>
        </div>

        <p class="mt-3 text-xs text-ink-400 leading-relaxed">
          只检索已发布内容。查不到会明确返回「站内暂无相关内容」——这是设计，不是故障。
          回答里的每个 <span class="text-ink-600">[n]</span> 都能点回原文核对。
        </p>
      </div>

      <p v-if="errorMsg" class="mb-4 text-sm text-red-600 bg-red-50 border border-red-200 rounded-xl px-4 py-2.5">
        {{ errorMsg }}
      </p>

      <template v-if="result">
        <div class="card mb-4">
          <div class="flex items-center gap-2 mb-3">
            <span class="text-xs text-ink-400">问</span>
            <span class="text-sm font-medium text-ink-900">{{ result.question }}</span>
          </div>

          <div
            v-if="result.no_answer"
            class="rounded-xl bg-amber-50 border border-amber-200 px-4 py-3"
          >
            <p class="text-sm text-amber-800 font-medium">站内暂无相关内容</p>
            <p v-if="result.reason" class="mt-1 text-xs text-amber-700">{{ result.reason }}</p>
            <p class="mt-2 text-xs text-amber-600">
              这就是正确答案。要么补一篇对应内容，要么这个提问本身不是我们的战场。
            </p>
          </div>

          <div v-else class="text-sm leading-7 text-ink-800">
            <template v-for="(seg, i) in segments" :key="i">
              <span v-if="seg.cite === undefined">{{ seg.text }}</span>
              <sup v-else>
                <button
                  class="text-[11px] px-1 rounded text-sky-700 bg-sky-50 hover:bg-sky-100 align-super"
                  @click="jumpByIndex(seg.cite)"
                >{{ seg.text }}</button>
              </sup>
            </template>
          </div>

          <p v-if="result.warning" class="mt-3 text-xs text-amber-600">{{ result.warning }}</p>

          <div class="mt-3 pt-3 border-t border-ink-100 flex flex-wrap gap-3 text-xs text-ink-400">
            <span>{{ elapsed }}s</span>
            <span v-if="!result.llm_used">未调用模型（检索降级）</span>
            <span>{{ result.citations.length }} 条出处</span>
          </div>
        </div>

        <div v-if="result.citations.length" class="card mb-4">
          <p class="text-xs text-ink-400 mb-2">出处</p>
          <ul class="space-y-2">
            <li
              v-for="c in result.citations"
              :key="c.index"
              class="rounded-lg border px-3 py-2 cursor-pointer transition-colors"
              :class="activeCite === c.index ? 'border-sky-300 bg-sky-50' : 'border-ink-200 hover:bg-ink-50'"
              @click="jump(c)"
            >
              <div class="flex items-start gap-2">
                <span class="shrink-0 text-xs text-sky-700 font-medium">[{{ c.index }}]</span>
                <div class="min-w-0">
                  <p class="text-sm text-ink-900 truncate">{{ c.title || '未命名' }}</p>
                  <p v-if="c.heading_path" class="text-xs text-ink-500 truncate">{{ c.heading_path }}</p>
                  <p class="mt-1 text-xs text-ink-400" style="display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden">{{ c.snippet }}</p>
                </div>
              </div>
            </li>
          </ul>
        </div>

        <div v-if="result.followups.length" class="card">
          <p class="text-xs text-ink-400 mb-2">访客可能接着问</p>
          <div class="flex flex-wrap gap-2">
            <button
              v-for="f in result.followups"
              :key="f"
              class="px-3 py-1.5 text-xs rounded-lg border border-ink-200 text-ink-600 hover:bg-ink-50"
              @click="submit(f)"
            >{{ f }}</button>
          </div>
        </div>
      </template>

      <div v-else-if="loading" class="card text-sm text-ink-500">
        正在检索站内内容并作答，通常 10~40 秒。
      </div>
    </main>
  </div>
</template>
