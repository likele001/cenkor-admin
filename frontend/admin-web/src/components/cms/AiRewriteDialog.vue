<script setup lang="ts">
/**
 * 字段级 AI 改写弹层（编辑页内嵌）
 *
 * 两种模式：
 *  - 纯文本（标题 / slug / 摘要字段）：整段送整段回
 *  - HTML（富文本正文）：前端把 DOM 拆成文本节点 → 模型只回文本块 →
 *    前端按序回填。**模型永远不产出 HTML**，所以标签结构不会被模型破坏，
 *    也没有半截标签或 XSS 的口子。
 *
 * 铁律：不自动覆盖。结果先给人看，点「应用」才写回表单，且表单未保存前可放弃。
 */
import { computed, ref, watch } from 'vue'
import { api } from '@/lib/api'

interface Preset {
  key: string
  label: string
}

const props = withDefaults(
  defineProps<{
    open: boolean
    value: string
    html?: boolean
    lang?: string
    context?: string
    title?: string
    presets?: Preset[]
  }>(),
  {
    html: false,
    lang: 'zh-CN',
    context: '',
    title: 'AI 改写',
    presets: () => [
      { key: 'polish', label: '润色' },
      { key: 'shorten', label: '精简' },
      { key: 'expand', label: '扩写' },
      { key: 'formal', label: '正式' },
      { key: 'plain', label: '口语' },
      { key: 'custom', label: '自定义' },
    ],
  },
)

const emit = defineEmits<{
  (e: 'update:open', v: boolean): void
  (e: 'apply', v: string): void
}>()

// 默认动作取 presets 的第一个：标题弹层的第一个是「拟标题」。
// 写死 polish 的话，点标题旁的 ✨ 会去「润色标题」——对一句 6 字标题
// 几乎改不出东西，模型常常原样返回，用户以为坏了。
const action = ref(props.presets?.[0]?.key || 'polish')
const instruction = ref('')
const busy = ref(false)
const errorMsg = ref('')
const result = ref('')
const resultPlain = ref('')
const originalPlain = ref('')
const aiUnavailable = ref(false)
const ran = ref(false)
const showOriginal = ref(false)

const canApply = computed(() => !!result.value && !busy.value)
const needInstruction = computed(() => action.value === 'custom')
// 结果和原文一致（去掉空白差异后比较）：模型没改，需要给用户一个解释
const unchanged = computed(() => {
  if (!result.value || !originalPlain.value) return false
  const norm = (s: string) => s.replace(/\s+/g, '').trim()
  return norm(resultPlain.value || result.value) === norm(originalPlain.value)
})

interface TextBlock {
  node: Text
  lead: string
  trail: string
  core: string
}

/** 把 HTML 拆成「可送模型的文本块」，返回 DOM 引用以便原样回填 */
function splitHtml(html: string): { root: HTMLElement; items: TextBlock[] } | null {
  const doc = new DOMParser().parseFromString(`<div id="__airoot">${html}</div>`, 'text/html')
  const root = doc.getElementById('__airoot') as HTMLElement | null
  if (!root) return null
  // 富文本里不该有脚本，见到就摘掉，别让它们混进改写结果
  root.querySelectorAll('script,style,noscript,iframe').forEach((el) => el.remove())

  const items: TextBlock[] = []
  const walker = doc.createTreeWalker(root, NodeFilter.SHOW_TEXT)
  let n = walker.nextNode()
  while (n) {
    const raw = n.nodeValue || ''
    if (raw.trim()) {
      items.push({
        node: n as Text,
        lead: /^\s*/.exec(raw)?.[0] || '',
        trail: /\s*$/.exec(raw)?.[0] || '',
        core: raw.trim(),
      })
    }
    n = walker.nextNode()
  }
  return { root, items }
}

/** 按序把文本块塞回原节点，保留首尾空白与全部标签结构 */
function fillHtml(root: HTMLElement, items: TextBlock[], blocks: unknown[]): string {
  items.forEach((it, i) => {
    const v = blocks[i]
    if (typeof v === 'string' && v.trim()) it.node.nodeValue = it.lead + v.trim() + it.trail
  })
  return root.innerHTML
}

function plainOf(html: string): string {
  const doc = new DOMParser().parseFromString(`<div>${html}</div>`, 'text/html')
  return (doc.body.textContent || '').replace(/\s+/g, ' ').trim()
}

function errText(e: any): string {
  if (e?.response?.status === 503) {
    aiUnavailable.value = true
    return e.response?.data?.detail || 'AI 未配置'
  }
  if (e?.response?.status === 404) {
    return 'AI 改写接口不可用，确认后端已重启到最新版本'
  }
  const d = e?.response?.data?.detail
  if (Array.isArray(d)) return d.map((x: any) => x.msg || JSON.stringify(x)).join('; ')
  return d || e?.message || '改写失败'
}

async function run(nextAction?: string) {
  if (nextAction) action.value = nextAction
  const src = (props.value || '').trim()
  result.value = ''
  resultPlain.value = ''
  errorMsg.value = ''
  ran.value = true

  if (!src) {
    errorMsg.value = '这里还没有内容可改'
    return
  }
  if (needInstruction.value && !instruction.value.trim()) {
    errorMsg.value = '自定义改写需要先写清楚要求'
    return
  }

  busy.value = true
  try {
    if (props.html) {
      const parsed = splitHtml(src)
      if (!parsed) throw new Error('无法解析富文本内容')
      if (!parsed.items.length) {
        errorMsg.value = '这段正文还没有可改写的文字'
        return
      }
      originalPlain.value = plainOf(src)
      const { data } = await api.post('/api/v1/cms/ai/text/rewrite', {
        blocks: parsed.items.map((i) => i.core),
        action: action.value,
        instruction: instruction.value.trim() || undefined,
        lang: props.lang,
        context: props.context || undefined,
      })
      const merged = fillHtml(parsed.root, parsed.items, data.blocks || [])
      result.value = merged
      resultPlain.value = plainOf(merged)
    } else {
      originalPlain.value = src
      const { data } = await api.post('/api/v1/cms/ai/text/rewrite', {
        text: src,
        action: action.value,
        instruction: instruction.value.trim() || undefined,
        lang: props.lang,
        context: props.context || undefined,
      })
      result.value = data.text || ''
      resultPlain.value = result.value
    }
    if (!result.value) errorMsg.value = '模型没有返回内容，换个动作或再试一次'
  } catch (e: any) {
    errorMsg.value = errText(e)
  } finally {
    busy.value = false
  }
}

function apply() {
  if (!canApply.value) return
  emit('apply', result.value)
  emit('update:open', false)
}

function close() {
  emit('update:open', false)
}

watch(
  () => props.open,
  (v) => {
    if (!v) return
    result.value = ''
    resultPlain.value = ''
    errorMsg.value = ''
    showOriginal.value = false
    aiUnavailable.value = false
    // 每次打开都回到默认动作：上次可能切到了「精简」，重开还停在精简
    // 会让「点 ✨ 就是干默认那件事」的预期落空
    action.value = props.presets?.[0]?.key || 'polish'
    instruction.value = ''
    // 点 ✨ 的意图就是「帮我改」，直接跑默认动作，少一次点击
    void run()
  },
)
</script>

<template>
  <div
    v-if="open"
    class="fixed inset-0 z-[60] flex items-center justify-center bg-black/40 p-4"
    @click.self="close"
  >
    <div class="bg-white rounded-xl shadow-xl w-full max-w-3xl max-h-[86vh] flex flex-col overflow-hidden">
      <header class="px-5 py-3 border-b border-ink-200 flex items-center justify-between shrink-0">
        <div class="flex items-center gap-2">
          <span class="text-base">✨</span>
          <h3 class="font-medium text-ink-900">{{ title }}</h3>
          <span class="text-xs text-ink-400">{{ html ? '正文按段落改写，格式保持不变' : '整段改写' }}</span>
        </div>
        <button class="text-ink-400 hover:text-ink-700 text-lg leading-none" @click="close">✕</button>
      </header>

      <div class="px-5 py-3 border-b border-ink-200 shrink-0">
        <div class="flex flex-wrap items-center gap-2">
          <button
            v-for="p in presets"
            :key="p.key"
            class="px-3 py-1.5 rounded-lg text-xs border transition-colors"
            :class="
              action === p.key
                ? 'bg-ink-900 text-white border-ink-900'
                : 'bg-white text-ink-700 border-ink-200 hover:border-ink-400'
            "
            :disabled="busy"
            @click="run(p.key)"
          >
            {{ p.label }}
          </button>
          <button class="btn-ghost text-xs ml-auto" :disabled="busy" @click="run()">
            {{ busy ? '改写中…' : '再来一次' }}
          </button>
        </div>

        <div v-if="needInstruction" class="mt-2">
          <input
            v-model="instruction"
            class="input text-xs"
            placeholder="想要什么效果？例如：改成小红书口吻、突出性价比、控制在 60 字以内"
            @keyup.enter="run()"
          />
        </div>

        <p v-if="aiUnavailable" class="mt-2 text-xs text-amber-800 bg-amber-50 border border-amber-200 rounded-lg px-3 py-2">
          AI 尚未配置。
          <router-link to="/cms/ai-settings" class="font-medium underline">去 AI 设置绑定服务商与密钥 →</router-link>
        </p>
        <p v-else-if="errorMsg" class="mt-2 text-xs text-red-600 bg-red-50 border border-red-200 rounded-lg px-3 py-2">
          {{ errorMsg }}
        </p>
      </div>

      <div class="flex-1 overflow-auto px-5 py-4">
        <div v-if="busy" class="py-16 text-center text-sm text-ink-400">正在改写…</div>

        <div v-else-if="!result" class="py-16 text-center text-xs text-ink-400">
          {{ ran ? '上面选个动作试试' : '选择一个改写动作' }}
        </div>

        <div v-else :class="html ? 'space-y-4' : 'grid grid-cols-1 md:grid-cols-2 gap-4'">
          <section v-if="html" class="border border-ink-200 rounded-lg overflow-hidden">
            <div class="px-3 py-1.5 bg-ink-50 border-b border-ink-200 text-xs font-medium text-ink-600">
              改写结果
            </div>
            <div class="px-3 py-2 text-sm text-ink-800 leading-relaxed prose-sm" v-html="result"></div>
          </section>

          <template v-else>
            <section class="border border-ink-200 rounded-lg overflow-hidden">
              <div class="px-3 py-1.5 bg-ink-50 border-b border-ink-200 text-xs font-medium text-ink-600">改写结果</div>
              <div class="px-3 py-2 text-sm text-ink-800 leading-relaxed whitespace-pre-wrap break-words">{{ resultPlain }}</div>
            </section>
            <section class="border border-ink-200 rounded-lg overflow-hidden">
              <div class="px-3 py-1.5 bg-ink-50 border-b border-ink-200 text-xs font-medium text-ink-500">修改前</div>
              <div class="px-3 py-2 text-sm text-ink-500 leading-relaxed whitespace-pre-wrap break-words">
                {{ originalPlain }}
              </div>
            </section>
          </template>
        </div>

        <div v-if="html && result" class="mt-4">
          <button class="text-xs text-ink-500 hover:text-ink-800" @click="showOriginal = !showOriginal">
            {{ showOriginal ? '收起修改前' : '查看修改前' }}
          </button>
          <div
            v-if="showOriginal"
            class="mt-2 px-3 py-2 text-xs text-ink-500 leading-relaxed bg-ink-50 border border-ink-200 rounded-lg whitespace-pre-wrap break-words"
          >
            {{ originalPlain }}
          </div>
        </div>

        <!-- 模型有时会原样返回（内容太短、或它认为无需改动）。
             不说明的话，用户只看到两栏一模一样，会以为是坏了。 -->
        <p
          v-if="result && !busy && unchanged"
          class="mt-3 text-xs text-amber-700 bg-amber-50 border border-amber-200 rounded-lg px-3 py-2"
        >
          模型这次没有做出改动——可能是这段内容太短，或它认为无需调整。换个动作、补一句要求，或点「再来一次」。
        </p>
      </div>

      <footer class="px-5 py-3 border-t border-ink-200 flex items-center gap-3 shrink-0">
        <button
          class="btn-primary disabled:opacity-40 disabled:cursor-not-allowed"
          :disabled="!canApply"
          @click="apply"
        >应用到当前字段</button>
        <button class="btn-ghost" @click="close">取消</button>
        <span class="ml-auto text-xs text-ink-400">应用只改表单，保存后才落库</span>
      </footer>
    </div>
  </div>
</template>
