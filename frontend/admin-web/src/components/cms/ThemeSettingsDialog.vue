<script setup lang="ts">
/**
 * 主题配置弹窗 —— 表单不是写死的，是 theme.json 的 settings 声明长出来的。
 *
 * ## 为什么要有这个
 *
 * 站长装完模板最烦的不是安装，是「想改个主色得去翻 HTML 找 #2563eb」。
 * 有了 settings 声明，作者只要写清楚有哪些项、什么类型、默认值是多少，
 * 这个弹窗就自动出对应的控件 —— 加一个主题不用写一行前端代码。
 *
 * ## 几个刻意的取舍
 *
 * 1. **不即时预览**。颜色每动一下都重新渲染整页，输入框会跳、光标会丢。
 *    改成「保存后生效」，保存完自动关窗并让父组件提示去前台刷新。
 * 2. **按 group 分组、组内保序**。设置项多起来（企业站有 10 个）之后，
 *    平铺一列很难找。分组顺序跟 manifest 里第一次出现的顺序走，
 *    作者写 manifest 的顺序就是表单的顺序。
 * 3. **只提交改过的项**。全量提交会让「后来有人改了 manifest 的默认值」
 *    这件事永远失效 —— 老站点的值都被钉死成旧默认。
 * 4. **恢复默认走 reset 而不是写默认值**。写值等于把默认值固化进 DB，
 *    以后作者调默认值同样不生效。
 */
import { computed, ref, watch } from 'vue'
import { api } from '@/lib/api'

interface SettingItem {
  key: string
  type: 'color' | 'select' | 'bool' | 'text' | 'textarea' | 'number' | 'range' | 'image' | string
  label: string
  default: any
  group: string
  help?: string
  options?: any[]
  minimum?: number
  maximum?: number
  step?: number
}

interface SettingGroup {
  name: string
  items: SettingItem[]
}

interface Payload {
  theme: string
  supports_settings: boolean
  groups: SettingGroup[]
  values: Record<string, any>
  defaults: Record<string, any>
  changed: string[]
  manifest: {
    name: string
    version: string | null
    icon: string
    description: string
    author?: Record<string, any>
    license?: string
    tags?: string[]
  }
}

const props = withDefaults(
  defineProps<{ open: boolean; theme: string; siteId?: number }>(),
  { siteId: 1 },
)
const emit = defineEmits<{ (e: 'close'): void; (e: 'saved', theme: string): void }>()

const BASE = '/api/v1/cms/templates'
const loading = ref(false)
const saving = ref(false)
const data = ref<Payload | null>(null)
const draft = ref<Record<string, any>>({})
const error = ref('')

const dirtyKeys = computed(() => {
  if (!data.value) return []
  return Object.keys(draft.value).filter((k) => draft.value[k] !== data.value!.values[k])
})
const hasDirty = computed(() => dirtyKeys.value.length > 0)

/** 某个值相对「当前已保存值」被改过 —— 用它点亮「恢复默认」小按钮 */
function isChanged(key: string): boolean {
  return data.value ? draft.value[key] !== data.value.values[key] : false
}

/** 某个值当前不等于 manifest 默认值 —— 用它标「已改」小圆点 */
function diffFromDefault(key: string): boolean {
  return data.value ? draft.value[key] !== data.value.defaults[key] : false
}

async function load() {
  if (!props.theme) return
  loading.value = true
  error.value = ''
  try {
    const { data: res } = await api.get(`${BASE}/themes/${props.theme}/settings`, {
      params: { site_id: props.siteId },
    })
    data.value = res
    draft.value = { ...res.values }
  } catch (e: any) {
    error.value = e?.response?.data?.detail || '读取主题配置失败'
  } finally {
    loading.value = false
  }
}

watch(
  () => [props.open, props.theme],
  ([open]) => {
    if (open) load()
  },
  { immediate: true },
)

// ---------------- 控件取值的两个小助手：template 里不写类型断言

function textOf(e: Event): string {
  return (e.target as HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement).value
}
function numOf(e: Event): number {
  const v = Number((e.target as HTMLInputElement).value)
  return Number.isFinite(v) ? v : 0
}
function boolOf(e: Event): boolean {
  return (e.target as HTMLInputElement).checked
}

function setValue(key: string, v: any) {
  draft.value = { ...draft.value, [key]: v }
}

function resetOne(key: string) {
  if (!data.value) return
  setValue(key, data.value.defaults[key])
}

function resetAll() {
  if (!data.value) return
  draft.value = { ...data.value.defaults }
}

async function save() {
  if (!data.value || saving.value) return
  saving.value = true
  error.value = ''
  try {
    // 只提交改过的项 + 与默认值相同的项走 reset，其余不动
    const values: Record<string, any> = {}
    const reset: string[] = []
    for (const key of new Set([...dirtyKeys.value, ...data.value.changed])) {
      const next = draft.value[key]
      if (next === data.value.defaults[key]) reset.push(key)
      else if (next !== data.value.values[key]) values[key] = next
    }
    const { data: res } = await api.put(`${BASE}/themes/${props.theme}/settings`, {
      site_id: props.siteId,
      values,
      reset,
    })
    data.value = res
    draft.value = { ...res.values }
    emit('saved', props.theme)
    emit('close')
  } catch (e: any) {
    error.value = e?.response?.data?.detail || '保存失败'
  } finally {
    saving.value = false
  }
}

function close() {
  if (saving.value) return
  emit('close')
}
</script>

<template>
  <div v-if="open" class="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4" @click.self="close">
    <div class="flex max-h-[88vh] w-full max-w-2xl flex-col rounded-lg bg-white shadow-xl">
      <!-- 头部 -->
      <div class="flex items-start justify-between gap-3 border-b px-5 py-3">
        <div class="min-w-0">
          <h3 class="flex items-center gap-2 text-sm font-medium">
            <span v-if="data?.manifest.icon" class="text-base">{{ data.manifest.icon }}</span>
            <span>{{ data?.manifest.name || theme }}</span>
            <span v-if="data?.manifest.version" class="rounded bg-ink-50 px-1.5 py-0.5 font-mono text-[11px] text-ink-500">
              v{{ data.manifest.version }}
            </span>
            <span v-if="data?.changed.length" class="rounded bg-amber-50 px-1.5 py-0.5 text-[11px] text-amber-700">
              已改 {{ data.changed.length }} 项
            </span>
          </h3>
          <p v-if="data?.manifest.description" class="mt-1 truncate text-xs text-ink-500">
            {{ data.manifest.description }}
          </p>
        </div>
        <button class="px-1 text-lg leading-none text-ink-400 hover:text-ink-600" @click="close">✕</button>
      </div>

      <!-- 内容 -->
      <div class="min-h-0 flex-1 overflow-auto px-5 py-4">
        <div v-if="loading" class="py-12 text-center text-sm text-ink-400">读取中…</div>

        <div v-else-if="error && !data" class="rounded bg-red-50 px-3 py-2 text-sm text-red-700">{{ error }}</div>

        <div v-else-if="data && !data.supports_settings" class="py-10 text-center text-sm text-ink-500">
          <p>这个主题没有声明可配置项。</p>
          <p class="mt-2 text-xs text-ink-400">
            作者可以在 <code class="rounded bg-ink-50 px-1">theme.json</code> 的
            <code class="rounded bg-ink-50 px-1">settings</code> 里声明主色、字号这类选项，
            声明之后这里会自动出现表单。
          </p>
        </div>

        <div v-else-if="data">
          <section v-for="group in data.groups" :key="group.name" class="mb-5 last:mb-0">
            <h4 class="mb-2 text-[11px] font-semibold uppercase tracking-wide text-ink-400">
              {{ group.name }}
            </h4>
            <div class="space-y-3">
              <div
                v-for="item in group.items"
                :key="item.key"
                class="flex items-start gap-3 rounded border border-ink-100 px-3 py-2.5"
              >
                <div class="min-w-0 flex-1">
                  <label class="flex items-center gap-1.5 text-sm">
                    {{ item.label }}
                    <span
                      v-if="diffFromDefault(item.key)"
                      class="h-1.5 w-1.5 rounded-full bg-amber-500"
                      title="已从默认值改动"
                    />
                  </label>
                  <p v-if="item.help" class="mt-0.5 text-xs text-ink-400">{{ item.help }}</p>
                  <p class="mt-0.5 font-mono text-[10px] text-ink-300">{{ item.key }}</p>
                </div>

                <div class="flex shrink-0 items-center gap-2">
                  <!-- 颜色 -->
                  <template v-if="item.type === 'color'">
                    <input
                      type="color"
                      class="h-8 w-10 cursor-pointer rounded border border-ink-200 bg-white p-0.5"
                      :value="draft[item.key]"
                      @input="setValue(item.key, textOf($event))"
                    />
                    <input
                      class="input w-24 font-mono text-xs"
                      :value="draft[item.key]"
                      @change="setValue(item.key, textOf($event))"
                    />
                  </template>

                  <!-- 下拉 -->
                  <select
                    v-else-if="item.type === 'select'"
                    class="input w-40 text-sm"
                    :value="draft[item.key]"
                    @change="setValue(item.key, textOf($event))"
                  >
                    <option v-for="opt in item.options" :key="String(opt)" :value="opt">{{ opt }}</option>
                  </select>

                  <!-- 开关 -->
                  <label v-else-if="item.type === 'bool'" class="inline-flex cursor-pointer items-center gap-2">
                    <input
                      type="checkbox"
                      class="h-4 w-4 rounded border-ink-300"
                      :checked="draft[item.key]"
                      @change="setValue(item.key, boolOf($event))"
                    />
                    <span class="text-xs text-ink-500">{{ draft[item.key] ? '开' : '关' }}</span>
                  </label>

                  <!-- 滑杆 -->
                  <template v-else-if="item.type === 'range'">
                    <input
                      type="range"
                      class="w-32"
                      :min="item.minimum ?? 0"
                      :max="item.maximum ?? 100"
                      :step="item.step ?? 1"
                      :value="draft[item.key]"
                      @input="setValue(item.key, numOf($event))"
                    />
                    <span class="w-14 text-right font-mono text-xs">{{ draft[item.key] }}</span>
                  </template>

                  <!-- 数字 -->
                  <input
                    v-else-if="item.type === 'number'"
                    type="number"
                    class="input w-24 text-sm"
                    :min="item.minimum"
                    :max="item.maximum"
                    :step="item.step"
                    :value="draft[item.key]"
                    @change="setValue(item.key, numOf($event))"
                  />

                  <!-- 多行文本 -->
                  <textarea
                    v-else-if="item.type === 'textarea'"
                    class="input w-64 text-sm"
                    rows="2"
                    :value="draft[item.key]"
                    @change="setValue(item.key, textOf($event))"
                  />

                  <!-- 文本 / 图片地址 -->
                  <input
                    v-else
                    class="text-sm"
                    :class="item.type === 'image' ? 'input w-64' : 'input w-56'"
                    :placeholder="item.type === 'image' ? 'https://… 或 /path' : ''"
                    :value="draft[item.key]"
                    @change="setValue(item.key, textOf($event))"
                  />

                  <button
                    class="text-[11px] text-ink-400 hover:text-ink-700 disabled:opacity-30"
                    :disabled="!isChanged(item.key)"
                    title="恢复此项的默认值"
                    @click="resetOne(item.key)"
                  >
                    默认
                  </button>
                </div>
              </div>
            </div>
          </section>
        </div>

        <div v-if="error && data" class="mt-3 rounded bg-red-50 px-3 py-2 text-sm text-red-700">{{ error }}</div>
      </div>

      <!-- 底部 -->
      <div class="flex items-center gap-2 border-t px-5 py-3">
        <button
          v-if="hasDirty || (data && data.changed.length)"
          class="btn-ghost text-xs"
          :disabled="saving"
          @click="resetAll"
        >
          全部恢复默认
        </button>
        <span class="ml-auto text-xs text-ink-400">
          {{ hasDirty ? `${dirtyKeys.length} 项待保存` : '改动保存后前台刷新即生效' }}
        </span>
        <button class="btn-ghost text-sm" :disabled="saving" @click="close">取消</button>
        <button class="btn-primary text-sm" :disabled="saving || !hasDirty" @click="save">
          {{ saving ? '保存中…' : '保存' }}
        </button>
      </div>
    </div>
  </div>
</template>
