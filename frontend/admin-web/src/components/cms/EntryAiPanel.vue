<script setup lang="ts">
/**
 * 编辑页侧栏 AI 面板：摘要 / SEO / 翻译
 *
 * 三件事都在条目级，都需要「已有内容」：
 *  - 摘要：用当前表单正文（不落库也算），生成后可一键填进摘要字段
 *  - SEO：需要已保存的条目 id（后端要读库里的完整条目）
 *  - 翻译：需要已保存的条目 id，写 cms_entry_translations（状态 draft）
 *
 * 所有结果先展示，由用户决定是否应用；不自动覆盖任何已有内容。
 */
import { computed, ref } from 'vue'
import { api } from '@/lib/api'

interface Lang {
  code: string
  name: string
  flag?: string | null
}

const props = withDefaults(
  defineProps<{
    entryId: number | null
    title: string
    bodyText: string
    slug: string
    summaryKey?: string | null
    translatableLangs?: Lang[]
    lang?: string
  }>(),
  {
    summaryKey: null,
    translatableLangs: () => [],
    lang: 'zh-CN',
  },
)

const emit = defineEmits<{
  (e: 'apply-slug', v: string): void
  (e: 'apply-summary', v: string): void
  (e: 'translated'): void
}>()

const busy = ref('')
const errorMsg = ref('')
const notice = ref('')
const aiUnavailable = ref(false)

const summary = ref('')
const seo = ref<Record<string, any> | null>(null)
const targetLangs = ref<string[]>([])

const hasBody = computed(() => props.bodyText.trim().length > 20)
const canEntryOp = computed(() => !!props.entryId && !busy.value)

function errText(e: any): string {
  if (e?.response?.status === 503) {
    aiUnavailable.value = true
    return e.response?.data?.detail || 'AI 未配置'
  }
  if (e?.response?.status === 404) {
    return 'AI 接口不可用，确认后端已重启到最新版本'
  }
  const d = e?.response?.data?.detail
  if (Array.isArray(d)) return d.map((x: any) => x.msg || JSON.stringify(x)).join('; ')
  return d || e?.message || '请求失败'
}

function reset() {
  errorMsg.value = ''
  notice.value = ''
}

async function makeSummary() {
  if (!hasBody.value || busy.value) return
  reset()
  busy.value = 'summary'
  summary.value = ''
  try {
    const { data } = await api.post('/api/v1/cms/ai/text/rewrite', {
      text: props.bodyText.slice(0, 6000),
      action: 'summary',
      lang: props.lang,
      context: props.title ? `标题：${props.title}` : undefined,
    })
    summary.value = data.text || ''
    if (!summary.value) errorMsg.value = '没有生成摘要，稍后再试'
  } catch (e: any) {
    errorMsg.value = errText(e)
  } finally {
    busy.value = ''
  }
}

async function makeSeo() {
  if (!canEntryOp.value) return
  reset()
  busy.value = 'seo'
  seo.value = null
  try {
    const { data } = await api.post(`/api/v1/cms/ai/entries/${props.entryId}/seo`, { lang: props.lang })
    seo.value = data.seo || data
  } catch (e: any) {
    errorMsg.value = errText(e)
  } finally {
    busy.value = ''
  }
}

async function doTranslate() {
  if (!canEntryOp.value || !targetLangs.value.length) return
  reset()
  busy.value = 'translate'
  try {
    const { data } = await api.post(`/api/v1/cms/ai/entries/${props.entryId}/translate`, {
      langs: targetLangs.value,
      overwrite: false,
    })
    const results = (data.results || {}) as Record<string, any>
    const ok = Object.values(results).filter((r) => r.ok).length
    const bad = Object.values(results).filter((r) => !r.ok)
    notice.value = `翻译完成 ${ok} 种语言${bad.length ? `，${bad.length} 种失败` : ''}`
    if (bad.length) errorMsg.value = bad.map((b: any) => b.error).filter(Boolean).join('; ').slice(0, 300)
    targetLangs.value = []
    emit('translated')
  } catch (e: any) {
    errorMsg.value = errText(e)
  } finally {
    busy.value = ''
  }
}

function toggleLang(code: string) {
  const i = targetLangs.value.indexOf(code)
  if (i >= 0) targetLangs.value.splice(i, 1)
  else targetLangs.value.push(code)
}

function applySummary() {
  if (!summary.value) return
  emit('apply-summary', summary.value)
  notice.value = '已填入摘要字段，保存后生效'
  summary.value = ''
}

function applySlug() {
  const v = String(seo.value?.title || '').trim()
  if (!v) return
  emit('apply-slug', slugify(v))
  notice.value = '已按 SEO 标题填入 slug，可再手工调整'
}

/** 中文标题也能转出可用 slug：保留字母数字，其余压成连字符 */
function slugify(s: string): string {
  const ascii = s
    .toLowerCase()
    .replace(/[^a-z0-9\u4e00-\u9fa5]+/g, '-')
    .replace(/^-+|-+$/g, '')
  return ascii || props.slug
}
</script>

<template>
  <div class="card space-y-3">
    <div class="flex items-center justify-between">
      <h3 class="font-medium text-sm">✨ AI 助手</h3>
      <span v-if="busy" class="text-xs text-ink-400">处理中…</span>
    </div>

    <p v-if="aiUnavailable" class="text-xs text-amber-800 bg-amber-50 border border-amber-200 rounded-lg px-2.5 py-2">
      AI 尚未配置。
      <router-link to="/cms/ai-settings" class="font-medium underline">去设置 →</router-link>
    </p>
    <p v-if="errorMsg" class="text-xs text-red-600 bg-red-50 border border-red-200 rounded-lg px-2.5 py-2">
      {{ errorMsg }}
    </p>
    <p v-if="notice" class="text-xs text-emerald-700 bg-emerald-50 border border-emerald-200 rounded-lg px-2.5 py-2">
      {{ notice }}
    </p>

    <!-- 摘要 -->
    <div class="border-t border-ink-100 pt-3">
      <div class="flex items-center justify-between">
        <span class="text-xs font-medium text-ink-700">生成摘要</span>
        <button
          class="text-xs text-violet-600 hover:text-violet-800 disabled:text-ink-300"
          :disabled="!hasBody || !!busy"
          aria-label="生成摘要"
          title="生成摘要"
          @click="makeSummary"
        >
          {{ busy === 'summary' ? '生成中…' : '生成' }}
        </button>
      </div>
      <p v-if="!hasBody" class="mt-1 text-xs text-ink-400">正文写下 20 字以上就能生成</p>
      <div v-if="summary" class="mt-1.5 space-y-1.5">
        <p class="text-xs text-ink-700 bg-ink-50 border border-ink-200 rounded-lg px-2.5 py-2 leading-relaxed">
          {{ summary }}
        </p>
        <div class="flex gap-2">
          <button v-if="summaryKey" class="btn-ghost text-xs px-2 py-0.5" @click="applySummary">
            填入 {{ summaryKey }}
          </button>
          <button v-else class="btn-ghost text-xs px-2 py-0.5" @click="applySummary">用作文本字段</button>
          <button class="text-xs text-ink-400 hover:text-ink-700 px-1" @click="summary = ''">丢弃</button>
        </div>
      </div>
    </div>

    <!-- SEO -->
    <div class="border-t border-ink-100 pt-3">
      <div class="flex items-center justify-between">
        <span class="text-xs font-medium text-ink-700">SEO 建议</span>
        <button
          class="text-xs text-violet-600 hover:text-violet-800 disabled:text-ink-300"
          :disabled="!canEntryOp"
          aria-label="生成 SEO 建议"
          title="生成 SEO 建议"
          @click="makeSeo"
        >
          {{ busy === 'seo' ? '生成中…' : '生成' }}
        </button>
      </div>
      <p v-if="!entryId" class="mt-1 text-xs text-ink-400">先保存一次，再生成 SEO</p>
      <div v-if="seo" class="mt-1.5 space-y-2 text-xs">
        <div>
          <div class="text-ink-400">标题</div>
          <div class="text-ink-800 leading-relaxed">{{ seo.title || '—' }}</div>
        </div>
        <div>
          <div class="text-ink-400">描述</div>
          <div class="text-ink-800 leading-relaxed">{{ seo.description || '—' }}</div>
        </div>
        <div v-if="seo.keywords?.length">
          <div class="text-ink-400">关键词</div>
          <div class="mt-1 flex flex-wrap gap-1">
            <span
              v-for="k in seo.keywords"
              :key="k"
              class="px-1.5 py-0.5 rounded bg-ink-100 text-ink-600"
            >{{ k }}</span>
          </div>
        </div>
        <div class="flex gap-2 pt-0.5">
          <button class="btn-ghost text-xs px-2 py-0.5" @click="applySlug">按 SEO 标题生成 slug</button>
          <button class="text-xs text-ink-400 hover:text-ink-700 px-1" @click="seo = null">收起</button>
        </div>
      </div>
    </div>

    <!-- 翻译 -->
    <div v-if="translatableLangs.length" class="border-t border-ink-100 pt-3">
      <div class="flex items-center justify-between">
        <span class="text-xs font-medium text-ink-700">翻译成其他语言</span>
        <button
          class="text-xs text-violet-600 hover:text-violet-800 disabled:text-ink-300"
          :disabled="!canEntryOp || !targetLangs.length"
          aria-label="翻译到选中语言"
          title="翻译到选中语言"
          @click="doTranslate"
        >
          {{ busy === 'translate' ? '翻译中…' : `翻译 ${targetLangs.length || ''}` }}
        </button>
      </div>
      <div class="mt-1.5 flex flex-wrap gap-1.5">
        <button
          v-for="l in translatableLangs"
          :key="l.code"
          class="px-2 py-0.5 rounded text-xs border transition-colors"
          :class="
            targetLangs.includes(l.code)
              ? 'bg-ink-900 text-white border-ink-900'
              : 'bg-white text-ink-600 border-ink-200 hover:border-ink-400'
          "
          @click="toggleLang(l.code)"
        >
          {{ l.flag || '🌍' }} {{ l.name }}
        </button>
      </div>
      <p v-if="!entryId" class="mt-1 text-xs text-ink-400">先保存一次，再翻译</p>
      <p v-else class="mt-1 text-xs text-ink-400">译文写入草稿，不会覆盖已有译文</p>
    </div>
  </div>
</template>
