<script setup lang="ts">
/**
 * 事实核验弹层（P0-B AI 事实溯源的前端）
 *
 * 要解决的问题：AI 写的稿子读起来最像真的地方，恰恰是它最可能编的地方 ——
 * 「提升 37%」「服务 1200 家客户」「兼容 GPT-4o」这类具体说法。
 * 质检的 accuracy 只给一个分数，编辑拿着 72 分只能全篇重读。
 *
 * 这里把「哪句话没有依据」直接指出来，并附上它能查到的出处。
 *
 * 三个取舍：
 * 1. 结论只展示、不阻断。核验本身有误判空间（模型常识、行业公知、纯观点稿），
 *    拿它硬卡发布，编辑第一周就会把功能关掉。先让人看见，再谈卡不卡。
 * 2. 句子里的具体值（数字/专名）单独高亮 —— 编辑要改的往往就是那几个字，
 *    整句涂红只会让人重新读一遍。
 * 3. 证据只给「标题 + 跳转」，不内联全文。内联会让弹窗变成另一篇文章，
 *    反而没人看判定结果。
 */
import { computed, ref, watch } from 'vue'
import { api } from '@/lib/api'

interface EvidenceTrace {
  id: number
  kind: 'material' | 'kb' | 'entry' | string
  title: string
  url: string | null
  entry_id: number | null
}

interface FactItem {
  index: number
  sentence: string
  verdict: 'supported' | 'unsupported' | 'uncertain' | string
  facts: string[]
  note: string
  by: 'rule' | 'model' | string
  evidence: EvidenceTrace[]
}

interface FactSummary {
  claims: number
  supported: number
  unsupported: number
  uncertain: number
  support_rate: number
  /** 能被判定的句数（supported + unsupported），不含 uncertain —— 支撑率的分母 */
  judged: number
  level: 'ok' | 'warn' | 'risk' | string
  evidence_count: number
  evidence_sources: Record<string, number>
  truncated: boolean
}

interface FactPayload {
  entry_id: number | null
  title: string
  summary: FactSummary
  items: FactItem[]
  traces: EvidenceTrace[]
  degraded: boolean
  degraded_reason: string
}

const props = defineProps<{
  open: boolean
  entryId: number
  /** 草稿未落库时传空：此时只能核验已保存内容 */
  materials?: string[]
}>()

const emit = defineEmits<{ (e: 'update:open', v: boolean): void }>()

const loading = ref(false)
const error = ref('')
const data = ref<FactPayload | null>(null)

const LEVEL_STYLE: Record<string, { label: string; cls: string; tip: string }> = {
  ok: { label: '基本可信', cls: 'bg-emerald-50 text-emerald-700 border-emerald-200', tip: '具体说法基本都能在依据里找到' },
  warn: { label: '需要复核', cls: 'bg-amber-50 text-amber-700 border-amber-200', tip: '部分说法没找到依据，建议逐条确认' },
  risk: { label: '风险较高', cls: 'bg-red-50 text-red-700 border-red-200', tip: '多数说法缺乏依据，发布前务必核实' },
}

const level = computed(() => LEVEL_STYLE[data.value?.summary.level || 'ok'] || LEVEL_STYLE.ok)
const ratePercent = computed(() => {
  const rate = data.value?.summary.support_rate
  return rate === undefined ? '—' : `${Math.round(rate * 100)}%`
})

/**
 * 两类问题要分开看，混在一列里等于没分优先级：
 * 「查无依据」是编辑必须处理的（要么补素材、要么改稿），
 * 「无法确认」多数是站外事实（新闻原报道、行业公知），本来就核不了。
 * 默认只看前者，后者折叠起来不占屏。
 */
const tab = ref<'bad' | 'unsure'>('bad')
const badItems = computed(() => (data.value?.items || []).filter((i) => i.verdict === 'unsupported'))
const unsureItems = computed(() => (data.value?.items || []).filter((i) => i.verdict !== 'unsupported'))
const shownItems = computed(() => (tab.value === 'bad' ? badItems.value : unsureItems.value))

const sourceLine = computed(() => {
  const src = data.value?.summary.evidence_sources || {}
  const parts: string[] = []
  if (src.material) parts.push(`素材 ${src.material}`)
  if (src.kb) parts.push(`知识库 ${src.kb}`)
  if (src.entry) parts.push(`站内内容 ${src.entry}`)
  return parts.length ? parts.join(' · ') : '无任何依据来源'
})

const verdictStyle: Record<string, { label: string; cls: string }> = {
  unsupported: { label: '查无依据', cls: 'bg-red-50 text-red-700 border-red-200' },
  uncertain: { label: '无法确认', cls: 'bg-amber-50 text-amber-700 border-amber-200' },
  supported: { label: '有依据', cls: 'bg-emerald-50 text-emerald-700 border-emerald-200' },
}

function escapeRe(raw: string): string {
  return raw.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
}

/**
 * 把句子切成 [普通文本, 命中事实] 片段，供模板渲染。
 * 长词优先，避免 "37%" 被更短的 "7%" 先切走。
 */
function segments(text: string, facts: string[]): { text: string; hit: boolean }[] {
  const words = [...new Set((facts || []).filter(Boolean))].sort((a, b) => b.length - a.length)
  if (!words.length) return [{ text, hit: false }]
  const re = new RegExp(`(${words.map(escapeRe).join('|')})`, 'g')
  return text
    .split(re)
    .filter((piece) => piece !== '')
    .map((piece) => ({ text: piece, hit: words.includes(piece) }))
}

async function load() {
  if (!props.entryId) {
    error.value = '内容还没保存，先保存再核验'
    return
  }
  loading.value = true
  error.value = ''
  data.value = null
  try {
    const payload: any = await api.post(`/cms/ai/entries/${props.entryId}/fact-check`, {
      materials: props.materials || [],
    })
    data.value = payload as FactPayload
  } catch (e: any) {
    error.value = e?.message || '核验失败'
  } finally {
    loading.value = false
  }
}

function close() {
  emit('update:open', false)
}

function openTrace(trace: EvidenceTrace) {
  if (trace.url) window.open(trace.url, '_blank', 'noopener')
}

watch(
  () => props.open,
  (v) => {
    if (v) load()
  },
)
</script>

<template>
  <div
    v-if="open"
    class="fixed inset-0 bg-black/40 z-50 flex items-center justify-center p-4"
    @click.self="close"
  >
    <div class="bg-white rounded-lg shadow-xl w-full max-w-4xl max-h-[88vh] flex flex-col">
      <!-- 头部 -->
      <div class="flex items-center justify-between gap-3 px-5 py-3 border-b">
        <div class="flex items-center gap-2">
          <h3 class="font-medium text-sm">事实核验</h3>
          <span
            v-if="data"
            class="px-2 py-0.5 rounded border text-xs"
            :class="level.cls"
            :title="level.tip"
          >{{ level.label }}</span>
        </div>
        <div class="flex items-center gap-2 text-xs">
          <button v-if="data || error" class="btn-ghost px-2 py-1" :disabled="loading" @click="load">
            重新核验
          </button>
          <button class="text-ink-400 hover:text-ink-600 text-lg leading-none px-1" @click="close">✕</button>
        </div>
      </div>

      <!-- 加载 / 错误 -->
      <div v-if="loading" class="flex-1 flex items-center justify-center text-xs text-ink-400 p-12 text-center">
        <div>
          正在核验正文里的具体说法…
          <div class="text-[11px] mt-1 text-ink-300">逐句交给模型判定，通常需要 20~60 秒</div>
        </div>
      </div>
      <div v-else-if="error" class="flex-1 flex items-center justify-center text-xs text-red-600 p-12">
        {{ error }}
      </div>

      <template v-else-if="data">
        <!-- 概览 -->
        <div class="px-5 py-3 border-b bg-ink-50/50">
          <div class="flex items-end gap-6">
            <div>
              <div class="text-2xl font-semibold leading-none" :class="{
                'text-emerald-600': data.summary.level === 'ok',
                'text-amber-600': data.summary.level === 'warn',
                'text-red-600': data.summary.level === 'risk',
              }">{{ ratePercent }}</div>
              <div class="text-[11px] text-ink-400 mt-1">有依据占比（只算能判定的）</div>
            </div>
            <div class="flex gap-4 text-xs text-ink-600">
              <div><span class="font-semibold text-ink-800">{{ data.summary.claims }}</span> 处具体说法</div>
              <div><span class="font-semibold text-emerald-600">{{ data.summary.supported }}</span> 有依据</div>
              <div><span class="font-semibold text-red-600">{{ data.summary.unsupported }}</span> 查无依据</div>
              <div><span class="font-semibold text-amber-600">{{ data.summary.uncertain }}</span> 无法确认</div>
            </div>
          </div>
          <div class="text-[11px] text-ink-400 mt-2">
            依据来源：{{ sourceLine }}
            <span v-if="data.summary.truncated" class="text-amber-600 ml-2">（正文超长，仅核验前 12000 字）</span>
          </div>
          <div
            v-if="data.degraded && data.degraded_reason"
            class="mt-2 text-[11px] text-amber-700 bg-amber-50 border border-amber-200 rounded px-2 py-1"
          >
            {{ data.degraded_reason }}
          </div>
        </div>

        <!-- 分类 tab：查无依据要处理，无法确认多半是站外事实 -->
        <div v-if="data.items.length" class="flex gap-1 px-5 pt-2 border-b text-xs">
          <button
            class="px-3 py-1.5 rounded-t"
            :class="tab === 'bad' ? 'bg-white border border-b-white -mb-px text-ink-800 font-medium' : 'text-ink-400 hover:text-ink-600'"
            @click="tab = 'bad'"
          >
            查无依据 {{ badItems.length }}
          </button>
          <button
            class="px-3 py-1.5 rounded-t"
            :class="tab === 'unsure' ? 'bg-white border border-b-white -mb-px text-ink-800 font-medium' : 'text-ink-400 hover:text-ink-600'"
            @click="tab = 'unsure'"
          >
            无法确认 {{ unsureItems.length }}
          </button>
        </div>

        <!-- 明细 -->
        <div class="flex-1 overflow-y-auto px-5 py-3 space-y-2">
          <div v-if="!shownItems.length" class="text-xs text-ink-400 py-8 text-center">
            <template v-if="!data.summary.claims">
              正文里没有可核验的数字、日期或专名，属于纯描述内容，无需核验。
            </template>
            <template v-else-if="tab === 'bad'">没有「查无依据」的说法，这篇稿子的具体说法都站得住。</template>
            <template v-else>没有「无法确认」的句子。</template>
          </div>

          <div
            v-for="item in shownItems"
            :key="item.index"
            class="border rounded p-3 space-y-1.5"
            :class="item.verdict === 'unsupported' ? 'border-red-200 bg-red-50/30' : 'border-amber-200 bg-amber-50/20'"
          >
            <div class="flex items-start gap-2">
              <span
                class="shrink-0 px-1.5 py-0.5 rounded border text-[11px]"
                :class="(verdictStyle[item.verdict] || verdictStyle.uncertain).cls"
              >{{ (verdictStyle[item.verdict] || verdictStyle.uncertain).label }}</span>
              <p class="text-xs leading-relaxed text-ink-700">
                <template v-for="(seg, i) in segments(item.sentence, item.facts)" :key="i">
                  <mark v-if="seg.hit" class="bg-yellow-100 text-ink-900 rounded px-0.5">{{ seg.text }}</mark>
                  <span v-else>{{ seg.text }}</span>
                </template>
              </p>
            </div>

            <div v-if="item.note" class="text-[11px] text-ink-500 pl-1">{{ item.note }}</div>

            <div class="flex flex-wrap items-center gap-1 pl-1">
              <span v-if="item.by === 'rule'" class="text-[10px] text-ink-400">规则比对</span>
              <span v-else class="text-[10px] text-ink-400">模型判定</span>
              <button
                v-for="ev in item.evidence"
                :key="ev.id"
                class="px-1.5 py-0.5 rounded border text-[11px] bg-white border-ink-200 hover:border-blue-300"
                :class="ev.url ? 'cursor-pointer text-blue-600' : 'text-ink-600 cursor-default'"
                @click="openTrace(ev)"
              >
                [{{ ev.id }}] {{ ev.title }}
              </button>
              <span v-if="!item.evidence.length" class="text-[10px] text-ink-400">未引用任何依据</span>
            </div>
          </div>
        </div>

        <!-- 底部提示 -->
        <div class="px-5 py-2 border-t text-[11px] text-ink-400 leading-relaxed">
          核验只做提示，不阻断发布。依据来自起草素材、企业知识库与站内已发布内容；
          站外事实（新闻原报道、行业公知）本来就核不了，判为「查无依据」属正常，请以人工核实为准。
        </div>
      </template>
    </div>
  </div>
</template>
