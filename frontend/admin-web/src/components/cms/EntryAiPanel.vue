<script setup lang="ts">
/**
 * 编辑页侧栏 AI 面板：摘要 / SEO / 翻译 / 内链建议 / 多渠道再分发
 *
 * 五件事都在条目级，都需要「已有内容」：
 *  - 摘要：用当前表单正文（不落库也算），生成后可一键填进摘要字段
 *  - SEO：需要已保存的条目 id（后端要读库里的完整条目）
 *  - 翻译：需要已保存的条目 id，写 cms_entry_translations（状态 draft）
 *  - 内链建议：需要已保存的条目 id（后端用条目向量召回相似内容，LLM 精选）
 *  - 再分发：需要已保存的条目 id，只产出各渠道成品文本，不推送平台
 *
 * 所有结果先展示，由用户决定是否应用；不自动覆盖任何已有内容。
 */
import { computed, onUnmounted, ref } from 'vue'
import { api } from '@/lib/api'

interface Lang {
  code: string
  name: string
  flag?: string | null
}

type RedistChannel = 'wechat' | 'xiaohongshu' | 'linkedin'

interface RedistResult {
  channel: RedistChannel
  channel_label: string
  title: string
  hook: string
  body: string
  tags: string[]
  notes: string
  chars: number
  limit: number
  over_limit: boolean
  too_short: boolean
  full_text: string
}

interface Illustration {
  media_id: number
  url: string
  mime: string
  width: number | null
  height: number | null
  size: number
  alt: string
  prompt: string
  applied: string
  model: string
  latency_ms: number
}

/** 视频任务。status 由后端归一：queued / running / succeeded / failed / canceled */
interface VideoJob {
  id: number
  entry_id: number | null
  mode: string
  mode_label: string
  status: string
  model: string
  prompt: string
  duration: number | null
  ratio: string | null
  error: string | null
  media_id: number | null
  url: string | null
  mime: string | null
  size: number | null
  width: number | null
  height: number | null
  cover_url: string | null
  og_image: string | null
}

interface LinkSuggestion {
  entry_id: number
  title: string
  slug?: string | null
  anchor_text: string
  reason: string
  insert_after: string
  source_url: string
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
  (e: 'apply-link', v: { anchorText: string; url: string; title: string }): void
}>()

const busy = ref('')
const errorMsg = ref('')
const notice = ref('')
const aiUnavailable = ref(false)

const summary = ref('')
const seo = ref<Record<string, any> | null>(null)
const targetLangs = ref<string[]>([])
const linkSuggestions = ref<LinkSuggestion[]>([])
const appliedLinks = ref<Record<number, boolean>>({})

const REDIST_CHANNELS: { key: RedistChannel; label: string; hint: string }[] = [
  { key: 'wechat', label: '公众号', hint: '长文 + 小标题' },
  { key: 'xiaohongshu', label: '小红书', hint: '短句 + 话题标签' },
  { key: 'linkedin', label: 'LinkedIn', hint: '专业视角' },
]
const redistChannel = ref<RedistChannel>('wechat')
const redistResult = ref<RedistResult | null>(null)
const copied = ref(false)

// 配图：一次生成、多次决策。生图按张计价，不该为了「试试看」反复重生
const ILL_ASPECTS = [
  { key: 'wide', label: '横图' },
  { key: 'square', label: '方图' },
  { key: 'portrait', label: '竖图' },
] as const
const ILL_STYLES = [
  { key: 'photo', label: '写实' },
  { key: 'render', label: '渲染' },
  { key: 'flat', label: '插画' },
] as const
const illAspect = ref<string>('wide')
const illStyle = ref<string>('photo')
const illustration = ref<Illustration | null>(null)
const illAttached = ref<string>('')

// 视频：提交后要轮询 1~3 分钟，所以不放在 busy 里等 —— busy 一挂整个面板就锁死，
// 用户连别的按钮都点不了。视频自己的状态用 vidBusy 单独表达。
const VID_MODES = [
  { key: 't2v', label: '文生' },
  { key: 'i2v', label: '图生' },
] as const
const VID_RATIOS = [
  { key: '16:9', label: '横屏' },
  { key: '9:16', label: '竖屏' },
  { key: '1:1', label: '方图' },
] as const
const VID_DURATIONS = [5, 10] as const
const vidMode = ref<string>('t2v')
const vidRatio = ref<string>('16:9')
const vidDuration = ref<number>(5)
const videoJob = ref<VideoJob | null>(null)
const vidAttached = ref<string>('')
let vidTimer: number | null = null

const vidRunning = computed(
  () => !!videoJob.value && ['queued', 'running'].includes(videoJob.value.status),
)
const vidStatusText = computed(() => {
  switch (videoJob.value?.status) {
    case 'queued':
      return '已提交，服务商排队中'
    case 'running':
      return '生成中，通常 1~3 分钟'
    case 'succeeded':
      return '已完成，可以挂到文章上'
    case 'failed':
      return '生成失败'
    case 'canceled':
      return '已取消'
    default:
      return ''
  }
})

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

async function makeLinkSuggestions() {
  if (!canEntryOp.value) return
  reset()
  busy.value = 'link'
  linkSuggestions.value = []
  try {
    const { data } = await api.get(
      `/api/v1/cms/ai/entries/${props.entryId}/link-suggestions`,
      { params: { max_links: 3, candidates: 8 } },
    )
    linkSuggestions.value = (data.links || []) as LinkSuggestion[]
    if (data.warning) notice.value = data.warning
    if (!linkSuggestions.value.length) {
      notice.value = data.warning || '没有值得互链的内容'
    }
  } catch (e: any) {
    errorMsg.value = errText(e)
  } finally {
    busy.value = ''
  }
}

async function makeRedist() {
  if (!canEntryOp.value) return
  reset()
  busy.value = 'redist'
  redistResult.value = null
  copied.value = false
  try {
    // 公众号长文在推理模型下要 30~60s，axios 默认超时撑不住
    const { data } = await api.post(
      `/api/v1/cms/ai/entries/${props.entryId}/redistribute`,
      { channel: redistChannel.value, lang: props.lang || 'zh-CN' },
      { timeout: 300000 },
    )
    redistResult.value = data as RedistResult
    if (data.over_limit) notice.value = `超出该渠道字数上限（${data.chars}/${data.limit}），建议精简后再用`
    else if (data.too_short) notice.value = '产物偏短，可再生成一次或手工补充'
  } catch (e: any) {
    errorMsg.value = errText(e)
  } finally {
    busy.value = ''
  }
}

async function makeIllustration() {
  if (!canEntryOp.value) return
  reset()
  busy.value = 'illustration'
  illustration.value = null
  illAttached.value = ''
  try {
    // 一次生图 + 一次图 prompt 提炼，实测 15~40s；默认不应用，先让人看
    const { data } = await api.post(
      `/api/v1/cms/ai/entries/${props.entryId}/illustration`,
      { aspect: illAspect.value, style: illStyle.value, apply: 'none' },
      { timeout: 300000 },
    )
    illustration.value = data as Illustration
  } catch (e: any) {
    errorMsg.value = errText(e)
  } finally {
    busy.value = ''
  }
}

async function attachIllustration(mode: 'og_image' | 'body_head') {
  if (!illustration.value || !props.entryId) return
  reset()
  busy.value = 'attach'
  try {
    await api.post(`/api/v1/cms/ai/media/${illustration.value.media_id}/attach`, {
      entry_id: props.entryId,
      mode,
    })
    illAttached.value = mode
    notice.value =
      mode === 'og_image'
        ? '已设为分享图（og_image），记得保存条目'
        : '已插入正文首图，记得保存条目'
  } catch (e: any) {
    errorMsg.value = errText(e)
  } finally {
    busy.value = ''
  }
}

async function makeVideo() {
  if (!canEntryOp.value) return
  reset()
  stopVidPoll()
  videoJob.value = null
  vidAttached.value = ''
  // 图生视频的首帧就取刚生成的那张配图 —— 不让人再上传一次，
  // 也不让后端凭空猜用哪张，链路最短且意图明确
  if (vidMode.value === 'i2v' && !illustration.value) {
    errorMsg.value = '图生视频需要先在上面生成一张配图当首帧'
    return
  }
  busy.value = 'video'
  try {
    const body: Record<string, any> = {
      mode: vidMode.value,
      ratio: vidRatio.value,
      duration: vidDuration.value,
    }
    if (vidMode.value === 'i2v' && illustration.value) {
      body.source_media_id = illustration.value.media_id
    }
    // 只负责提交，几秒内就返回；产物靠下面的轮询去取
    const { data } = await api.post(
      `/api/v1/cms/ai/entries/${props.entryId}/video`,
      body,
      { timeout: 120000 },
    )
    videoJob.value = data as VideoJob
    if (videoJob.value.status === 'failed') {
      errorMsg.value = videoJob.value.error || '提交失败'
    } else {
      startVidPoll()
    }
  } catch (e: any) {
    errorMsg.value = errText(e)
  } finally {
    busy.value = ''
  }
}

function startVidPoll() {
  stopVidPoll()
  vidTimer = window.setInterval(async () => {
    if (!videoJob.value) {
      stopVidPoll()
      return
    }
    try {
      const { data } = await api.get(`/api/v1/cms/ai/video/jobs/${videoJob.value.id}`)
      videoJob.value = data as VideoJob
      if (!['queued', 'running'].includes(videoJob.value.status)) {
        stopVidPoll()
        if (videoJob.value.status === 'failed') {
          errorMsg.value = videoJob.value.error || '生成失败'
        }
      }
    } catch {
      // 单次查询失败不该中断轮询：网络抖一下而已，下一个 tick 继续
    }
  }, 5000)
}

function stopVidPoll() {
  if (vidTimer !== null) {
    window.clearInterval(vidTimer)
    vidTimer = null
  }
}

// 面板关闭后不能还在后台每 5 秒打一次接口
onUnmounted(stopVidPoll)

async function attachVideo(mode: 'og_image' | 'body_head') {
  if (!videoJob.value || !props.entryId) return
  reset()
  busy.value = 'video-attach'
  try {
    await api.post(`/api/v1/cms/ai/video/jobs/${videoJob.value.id}/attach`, {
      entry_id: props.entryId,
      mode,
    })
    vidAttached.value = mode
    notice.value =
      mode === 'og_image'
        ? '已用封面帧设为分享图，记得保存条目'
        : '已插入正文视频，记得保存条目'
  } catch (e: any) {
    errorMsg.value = errText(e)
  } finally {
    busy.value = ''
  }
}

async function copyRedist() {
  if (!redistResult.value) return
  try {    await navigator.clipboard.writeText(redistResult.value.full_text)
    copied.value = true
    setTimeout(() => (copied.value = false), 2000)
  } catch {
    notice.value = '复制失败，请手动全选复制'
  }
}

function applyLink(s: LinkSuggestion) {
  emit('apply-link', {
    anchorText: s.anchor_text,
    url: s.source_url,
    title: s.title,
  })
  appliedLinks.value = { ...appliedLinks.value, [s.entry_id]: true }
  notice.value = `已在正文末尾追加「${s.anchor_text}」链接，可自行调整位置`
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

    <!-- 内链建议 -->
    <div class="border-t border-ink-100 pt-3">
      <div class="flex items-center justify-between">
        <span class="text-xs font-medium text-ink-700">内链建议</span>
        <button
          class="text-xs text-violet-600 hover:text-violet-800 disabled:text-ink-300"
          :disabled="!canEntryOp"
          aria-label="生成内链建议"
          title="生成内链建议"
          @click="makeLinkSuggestions"
        >
          {{ busy === 'link' ? '分析中…' : '分析' }}
        </button>
      </div>
      <p v-if="!entryId" class="mt-1 text-xs text-ink-400">先保存一次，再分析内链</p>
      <p v-else-if="!linkSuggestions.length" class="mt-1 text-xs text-ink-400">
        找出该互相链接的内容，给出可直接插入的锚文本
      </p>
      <div v-if="linkSuggestions.length" class="mt-1.5 space-y-2">
        <div
          v-for="s in linkSuggestions"
          :key="s.entry_id"
          class="text-xs border border-ink-200 rounded-lg px-2.5 py-2 bg-ink-50"
        >
          <div class="flex items-start justify-between gap-2">
            <div class="min-w-0">
              <div class="text-ink-800 font-medium truncate">《{{ s.title }}》</div>
              <div class="text-ink-500 mt-0.5">
                锚文本：<span class="text-violet-700">{{ s.anchor_text }}</span>
              </div>
            </div>
            <button
              v-if="!appliedLinks[s.entry_id]"
              class="btn-ghost text-xs px-2 py-0.5 shrink-0"
              @click="applyLink(s)"
            >
              插入
            </button>
            <span v-else class="text-xs text-emerald-600 shrink-0">已插入</span>
          </div>
          <div v-if="s.reason" class="text-ink-500 mt-1 leading-relaxed">{{ s.reason }}</div>
        </div>
        <p class="text-ink-400">插入会追加到正文末尾的「相关阅读」段落，位置可自行调整</p>
      </div>
    </div>

    <!-- 多渠道再分发 -->
    <div class="border-t border-ink-200 pt-3 mt-3">
      <div class="flex items-center justify-between gap-2">
        <span class="text-xs font-medium text-ink-700">多渠道再分发</span>
        <div class="flex gap-1">
          <button
            v-for="ch in REDIST_CHANNELS"
            :key="ch.key"
            class="px-2 py-0.5 text-xs rounded-md border transition-colors"
            :class="redistChannel === ch.key
              ? 'bg-ink-900 text-white border-ink-900'
              : 'bg-white text-ink-600 border-ink-200 hover:border-ink-400'"
            :title="ch.hint"
            @click="redistChannel = ch.key"
          >{{ ch.label }}</button>
        </div>
        <button
          class="btn-ghost text-xs px-2 py-0.5"
          :disabled="!canEntryOp"
          aria-label="生成渠道稿"
          @click="makeRedist"
        >
          {{ busy === 'redist' ? '改写中…' : '生成' }}
        </button>
      </div>

      <p v-if="!entryId" class="mt-1 text-xs text-ink-400">先保存一次，再改写</p>
      <p v-else-if="!redistResult" class="mt-1 text-xs text-ink-400">
        改写成各渠道体裁，只产出文本不自动发布 —— 平台发布由你确认
      </p>
      <p v-if="busy === 'redist'" class="mt-1 text-xs text-ink-400">
        公众号长文需 30~60 秒（模型推理开销），请稍等
      </p>

      <div v-if="redistResult" class="mt-2 text-xs border border-ink-200 rounded-lg p-2.5 bg-ink-50">
        <div class="flex items-start justify-between gap-2">
          <div class="min-w-0">
            <div class="text-ink-800 font-medium break-words">{{ redistResult.title }}</div>
            <div class="text-ink-400 mt-0.5">
              {{ redistResult.channel_label }} · {{ redistResult.chars }} 字 / 上限 {{ redistResult.limit }}
            </div>
          </div>
          <button class="btn-ghost text-xs px-2 py-0.5 shrink-0" @click="copyRedist">
            {{ copied ? '已复制' : '复制全文' }}
          </button>
        </div>

        <p v-if="redistResult.over_limit" class="mt-1.5 text-red-600">
          超出字数上限，平台会截断，建议精简
        </p>

        <div class="mt-1.5 max-h-56 overflow-auto whitespace-pre-wrap break-words text-ink-700 leading-relaxed">
          {{ redistResult.body }}
        </div>

        <div v-if="redistResult.tags.length" class="mt-1.5 flex flex-wrap gap-1">
          <span
            v-for="t in redistResult.tags"
            :key="t"
            class="px-1.5 py-0.5 rounded bg-white border border-ink-200 text-ink-600"
          >#{{ t }}</span>
        </div>

        <p v-if="redistResult.notes" class="mt-1.5 text-ink-500 leading-relaxed">
          改动说明：{{ redistResult.notes }}
        </p>
      </div>
    </div>

    <!-- AI 配图 -->
    <div class="border-t border-ink-200 pt-3 mt-3">
      <div class="flex items-center justify-between gap-2">
        <span class="text-xs font-medium text-ink-700">AI 配图</span>
        <div class="flex gap-1">
          <button
            v-for="a in ILL_ASPECTS"
            :key="a.key"
            class="px-2 py-0.5 text-xs rounded-md border transition-colors"
            :class="illAspect === a.key
              ? 'bg-ink-900 text-white border-ink-900'
              : 'bg-white text-ink-600 border-ink-200 hover:border-ink-400'"
            @click="illAspect = a.key"
          >{{ a.label }}</button>
        </div>
        <div class="flex gap-1">
          <button
            v-for="st in ILL_STYLES"
            :key="st.key"
            class="px-2 py-0.5 text-xs rounded-md border transition-colors"
            :class="illStyle === st.key
              ? 'bg-ink-900 text-white border-ink-900'
              : 'bg-white text-ink-600 border-ink-200 hover:border-ink-400'"
            @click="illStyle = st.key"
          >{{ st.label }}</button>
        </div>
        <button
          class="btn-ghost text-xs px-2 py-0.5"
          :disabled="!canEntryOp"
          aria-label="生成配图"
          @click="makeIllustration"
        >
          {{ busy === 'illustration' ? '生成中…' : '生成' }}
        </button>
      </div>

      <p v-if="!entryId" class="mt-1 text-xs text-ink-400">先保存一次，再配图</p>
      <p v-else-if="!illustration" class="mt-1 text-xs text-ink-400">
        读正文语义出图并落媒体库，不自动插入 —— 满意再挂上去
      </p>
      <p v-if="busy === 'illustration'" class="mt-1 text-xs text-ink-400">
        生图约 15~40 秒，请稍等
      </p>

      <div v-if="illustration" class="mt-2 text-xs border border-ink-200 rounded-lg p-2.5 bg-ink-50">
        <img :src="illustration.url" :alt="illustration.alt"
             class="w-full rounded-md border border-ink-200 mb-2" />
        <div class="text-ink-400">
          {{ illustration.width }}×{{ illustration.height }} ·
          {{ Math.round(illustration.size / 1024) }} KB · {{ illustration.model }}
        </div>
        <div class="mt-1 text-ink-600 break-words">alt：{{ illustration.alt }}</div>
        <div class="mt-2 flex flex-wrap gap-1">
          <button class="btn-ghost text-xs px-2 py-0.5" :disabled="busy === 'attach'"
                  @click="attachIllustration('og_image')">
            {{ illAttached === 'og_image' ? '已设为分享图' : '设为分享图' }}
          </button>
          <button class="btn-ghost text-xs px-2 py-0.5" :disabled="busy === 'attach'"
                  @click="attachIllustration('body_head')">
            {{ illAttached === 'body_head' ? '已插入正文' : '插入正文首图' }}
          </button>
          <a :href="illustration.url" target="_blank" class="btn-ghost text-xs px-2 py-0.5">看原图</a>
        </div>
      </div>
    </div>
    <!-- AI 视频 -->
    <div class="border-t border-ink-200 pt-3 mt-3">
      <div class="flex items-center justify-between gap-2">
        <span class="text-xs font-medium text-ink-700">AI 视频</span>
        <div class="flex gap-1">
          <button
            v-for="m in VID_MODES"
            :key="m.key"
            class="px-2 py-0.5 text-xs rounded-md border transition-colors"
            :class="vidMode === m.key
              ? 'bg-ink-900 text-white border-ink-900'
              : 'bg-white text-ink-600 border-ink-200 hover:border-ink-400'"
            @click="vidMode = m.key"
          >{{ m.label }}</button>
        </div>
      </div>

      <div class="flex items-center gap-1 mt-1.5">
        <button
          v-for="r in VID_RATIOS"
          :key="r.key"
          class="px-2 py-0.5 text-xs rounded-md border transition-colors"
          :class="vidRatio === r.key
            ? 'bg-ink-900 text-white border-ink-900'
            : 'bg-white text-ink-600 border-ink-200 hover:border-ink-400'"
          @click="vidRatio = r.key"
        >{{ r.label }}</button>
        <span class="text-xs text-ink-300 mx-0.5">|</span>
        <button
          v-for="d in VID_DURATIONS"
          :key="d"
          class="px-2 py-0.5 text-xs rounded-md border transition-colors"
          :class="vidDuration === d
            ? 'bg-ink-900 text-white border-ink-900'
            : 'bg-white text-ink-600 border-ink-200 hover:border-ink-400'"
          @click="vidDuration = d"
        >{{ d }}s</button>
        <button
          class="btn-ghost text-xs px-2 py-0.5 ml-auto"
          :disabled="!canEntryOp"
          aria-label="生成视频"
          @click="makeVideo"
        >
          {{ busy === 'video' ? '提交中…' : '生成' }}
        </button>
      </div>

      <p v-if="!entryId" class="mt-1 text-xs text-ink-400">先保存一次，再生成视频</p>
      <p v-else-if="!videoJob" class="mt-1 text-xs text-ink-400">
        {{ vidMode === 'i2v'
          ? '拿上面那张配图当首帧，做 3~10 秒镜头运动'
          : '按正文语义直接出片，不自动插入 —— 满意再挂上去' }}
      </p>
      <p v-if="vidRunning" class="mt-1 text-xs text-ink-400">
        {{ vidStatusText }}，页面可以关，回来再查也一样
      </p>

      <div v-if="videoJob" class="mt-2 text-xs border border-ink-200 rounded-lg p-2.5 bg-ink-50">
        <video
          v-if="videoJob.url"
          :src="videoJob.url"
          :poster="videoJob.cover_url || undefined"
          controls
          preload="metadata"
          class="w-full rounded-md border border-ink-200 mb-2"
        ></video>
        <div class="text-ink-400">
          {{ videoJob.mode_label }}
          <template v-if="videoJob.ratio"> · {{ videoJob.ratio }}</template>
          <template v-if="videoJob.duration"> · {{ videoJob.duration }}s</template>
          <template v-if="videoJob.size"> · {{ Math.round(videoJob.size / 1024) }} KB</template>
          <template v-if="videoJob.status !== 'succeeded'"> · {{ vidStatusText }}</template>
        </div>
        <div v-if="videoJob.error" class="mt-1 text-red-600 break-words">
          {{ videoJob.error }}
        </div>
        <div v-if="videoJob.status === 'succeeded'" class="mt-2 flex flex-wrap gap-1">
          <button
            class="btn-ghost text-xs px-2 py-0.5"
            :disabled="busy === 'video-attach' || !videoJob.cover_url"
            @click="attachVideo('og_image')"
          >
            {{ vidAttached === 'og_image' ? '已设为分享图' : '设为分享图' }}
          </button>
          <button
            class="btn-ghost text-xs px-2 py-0.5"
            :disabled="busy === 'video-attach'"
            @click="attachVideo('body_head')"
          >
            {{ vidAttached === 'body_head' ? '已插入正文' : '插入正文' }}
          </button>
          <a
            v-if="videoJob.url"
            :href="videoJob.url"
            target="_blank"
            class="btn-ghost text-xs px-2 py-0.5"
          >看原片</a>
        </div>
      </div>
    </div>
  </div>
</template>
