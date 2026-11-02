<script setup lang="ts">
// URL 伪静态规则输入组件（对齐老 CMS 体验）：
// 1. 变量 chip 点击即插入到光标位置（不用手抄 {xxx}）
// 2. 预设规则下拉（选择即填入）
// 3. 解析校验：必须包含至少一个必备变量，否则前台无法反解
// 4. 示例预览：按样例值实时算出最终地址
import { ref, computed } from 'vue'

export interface RuleVar { name: string; desc: string }
export interface RulePreset { label: string; pattern: string }

const props = withDefaults(defineProps<{
  modelValue: string
  vars: RuleVar[]
  presets?: RulePreset[]
  /** 至少要出现其中之一，否则无法解析；不传 = vars 里全部名字 */
  requiredVars?: string[]
  /** 是否显示示例预览（已有服务端预览的页面可关掉） */
  showExample?: boolean
  placeholder?: string
}>(), {
  presets: () => [],
  requiredVars: undefined,
  showExample: true,
  placeholder: '',
})

const emit = defineEmits<{ (e: 'update:modelValue', v: string): void }>()

const inputEl = ref<HTMLInputElement | null>(null)

// 变量样例值：用于示例预览。没给样例的变量按原样保留。
const SAMPLES: Record<string, string> = {
  type: 'article',
  catdir: 'mes-system/flow',
  cat: 'flow',
  parent: 'mes-system',
  slug: 'my-post',
  id: '123',
  n: '2',
  key: 'hot',
  name: '标签名',
  YYYY: '2026', MM: '11', DD: '02', HH: '09', II: '30',
}

function update(v: string) { emit('update:modelValue', v) }

function onInput(e: Event) {
  update((e.target as HTMLInputElement).value)
}

function onPresetChange(e: Event) {
  const sel = e.target as HTMLSelectElement
  const p = props.presets[Number(sel.value)]
  if (p) applyPreset(p)
  sel.value = ''
}

/** 在光标处插入 {token}，插完保持焦点并移动光标到插入文本之后 */
function insertVar(name: string) {
  const token = '{' + name + '}'
  const el = inputEl.value
  const cur = props.modelValue
  if (!el) { update(cur + token); return }
  const start = el.selectionStart ?? cur.length
  const end = el.selectionEnd ?? cur.length
  const next = cur.slice(0, start) + token + cur.slice(end)
  update(next)
  requestAnimationFrame(() => {
    el.focus()
    const pos = start + token.length
    el.setSelectionRange(pos, pos)
  })
}

function applyPreset(p: RulePreset) {
  update(p.pattern)
}

/** 解析校验：非空但不含任何必备变量 → 无法解析 */
const missingRequired = computed(() => {
  const v = props.modelValue.trim()
  if (!v) return false
  const required = props.requiredVars ?? props.vars.map(x => x.name)
  if (!required.length) return false
  return !required.some(name => v.includes('{' + name + '}'))
})

/** 同一变量出现两次：地址歧义，后端保存时也会拒 */
const dupVars = computed(() => {
  const names = (props.modelValue.match(/\{([A-Za-z_@x0-9]+)\}/g) || []).map(t => t.slice(1, -1))
  return [...new Set(names.filter((n, i) => names.indexOf(n) !== i))]
})

/** 相邻变量之间没有任何字面分隔符（如 {catdir}{slug}）：拼出来的地址无法反解 */
const adjacentVars = computed(() => /\}\{/.test(props.modelValue))

/** 写了不认识的变量 → 提示可能拼错 */
const unknownVars = computed(() => {
  const known = new Set(props.vars.map(v => v.name))
  const found = props.modelValue.match(/\{([A-Za-z_@x0-9]+)\}/g) || []
  return found
    .map(t => t.slice(1, -1))
    .filter(n => !known.has(n))
})

/** 示例地址：把认识的变量换成样例值 */
const exampleUrl = computed(() => {
  const v = props.modelValue.trim()
  if (!v) return ''
  return v.replace(/\{([A-Za-z_@x0-9]+)\}/g, (m, name: string) =>
    SAMPLES[name] !== undefined ? SAMPLES[name] : m
  )
})

const varNames = computed(() => props.vars.map(v => '{' + v.name + '}'))

/** 校验提示的「其中之一」文案 */
const requiredHint = computed(() =>
  (props.requiredVars ?? props.vars.map(x => x.name)).map(n => '{' + n + '}').join(' ')
)
</script>

<template>
  <div>
    <div class="flex gap-2">
      <input
        ref="inputEl"
        :value="modelValue"
        class="input font-mono text-sm flex-1"
        :placeholder="placeholder"
        @input="onInput"
      />
      <div v-if="presets.length" class="relative">
        <select
          class="input w-24 text-sm h-full cursor-pointer bg-white"
          value=""
          title="选择常用规则模板"
          @change="onPresetChange"
        >
          <option value="" disabled>选择 ▾</option>
          <option v-for="(p, i) in presets" :key="p.pattern" :value="i">{{ p.label }}</option>
        </select>
      </div>
    </div>

    <!-- 变量 chips：点击插入到光标位置 -->
    <div class="mt-2 flex flex-wrap gap-1.5 items-center">
      <span class="text-xs text-ink-400">点变量插入：</span>
      <button
        v-for="v in vars"
        :key="v.name"
        type="button"
        class="text-xs px-2 py-0.5 rounded bg-ink-100 text-ink-600 hover:bg-blue-100 hover:text-blue-700 active:scale-95 transition-colors"
        :title="`${v.desc}（点击插入）`"
        @click="insertVar(v.name)"
      ><code>{{ '{' + v.name + '}' }}</code></button>
    </div>

    <!-- 校验提示：从重到轻依次展示 -->
    <p v-if="missingRequired" class="text-xs text-red-600 mt-1.5">
      ⚠️ 规则里必须包含 {{ requiredHint }} 其中之一，否则前台将无法解析这个地址
    </p>
    <p v-else-if="dupVars.length" class="text-xs text-red-600 mt-1.5">
      ⚠️ 变量重复出现：{{ dupVars.map(n => '{' + n + '}').join(' ') }}，同一变量用两次会让地址产生歧义
    </p>
    <p v-else-if="adjacentVars" class="text-xs text-red-600 mt-1.5">
      ⚠️ 相邻变量之间要加分隔符（/ - _ 等），比如 <code>{'{catdir}/{slug}'}</code>，直接连写 <code>{'{catdir}{slug}'}</code> 无法反解
    </p>
    <p v-else-if="unknownVars.length" class="text-xs text-amber-600 mt-1.5">
      ⚠️ 不认识的变量：{{ unknownVars.map(n => '{' + n + '}').join(' ') }}，请检查是否拼写有误
    </p>
    <p v-else-if="exampleUrl && showExample" class="text-xs text-ink-500 mt-1.5">
      示例：<code class="text-green-700">{{ exampleUrl }}</code>
    </p>
    <slot />
  </div>
</template>
