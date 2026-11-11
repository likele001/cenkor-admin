<script setup lang="ts">
import { computed } from 'vue'

/**
 * 官网内容编辑器（www.cenkor.cn 静态站的产品级文案）
 * 数据存于 cms_products.custom_fields (JSONB)，公开 API 原样返回给构建器。
 * 本组件只负责把嵌套结构摊平成可编辑表单，不直接改 props，全部通过 emit 回传。
 */
const props = defineProps<{ modelValue: Record<string, any> }>()
const emit = defineEmits(['update:modelValue'])

const cf = computed<Record<string, any>>(() => props.modelValue || {})

function setField(key: string, value: any) {
  emit('update:modelValue', { ...cf.value, [key]: value })
}

function val(e: Event): string {
  return (e.target as HTMLInputElement).value
}
function num(e: Event): number {
  const n = Number(val(e))
  return Number.isFinite(n) ? n : 0
}
function list(key: string): any[] {
  return Array.isArray(cf.value[key]) ? cf.value[key] : []
}
function obj(key: string): Record<string, any> {
  const v = cf.value[key]
  return v && typeof v === 'object' && !Array.isArray(v) ? v : {}
}
function itemVal(it: any, k: string): string {
  const v = (it || {})[k]
  return v == null ? '' : String(v)
}
function rangeVal(it: any, which: number): number {
  const r = (it || {}).range
  return Array.isArray(r) ? (Number(r[which]) || 0) : 0
}

function setObjItem(key: string, i: number, field: string, value: any) {
  const next = list(key).map((x, j) => (j === i ? { ...(x || {}), [field]: value } : x))
  setField(key, next)
}
function setObjRange(key: string, i: number, which: number, value: number) {
  const r = [rangeVal(list(key)[i], 0), rangeVal(list(key)[i], 1)]
  r[which] = value
  setObjItem(key, i, 'range', r)
}
function setStrItem(key: string, i: number, value: string) {
  const next = [...list(key)]
  next[i] = value
  setField(key, next)
}
function addItem(key: string, tmpl: any) {
  setField(key, [...list(key), tmpl])
}
function addObjItem(key: string, tmpl: any) {
  addItem(key, { ...tmpl })
}
function removeItem(key: string, i: number) {
  setField(key, list(key).filter((_, j) => j !== i))
}
function moveItem(key: string, i: number, delta: number) {
  const next = [...list(key)]
  const j = i + delta
  if (j < 0 || j >= next.length) return
  ;[next[i], next[j]] = [next[j], next[i]]
  setField(key, next)
}

function setLp(field: string, value: any) {
  setField('lp', { ...obj('lp'), [field]: value })
}
function lpPoints(): string[] {
  const v = obj('lp').points
  return Array.isArray(v) ? v : []
}
function setLpPoint(i: number, value: string) {
  const next = [...lpPoints()]
  next[i] = value
  setLp('points', next)
}
function addLpPoint() {
  setLp('points', [...lpPoints(), ''])
}
function removeLpPoint(i: number) {
  setLp('points', lpPoints().filter((_, j) => j !== i))
}
function moveLpPoint(i: number, delta: number) {
  const next = [...lpPoints()]
  const j = i + delta
  if (j < 0 || j >= next.length) return
  ;[next[i], next[j]] = [next[j], next[i]]
  setLp('points', next)
}

interface FieldDef { k: string; label: string; kind: 'text' | 'textarea' | 'range' }
interface ListDef { key: string; label: string; hint: string; open: boolean; tmpl: any; fields: FieldDef[] }

const OBJ_LISTS: ListDef[] = [
  {
    key: 'intro', label: '正文段落', open: true,
    hint: '产品详情页「它是什么」区的大段正文，按列表顺序展示。官网不再使用「详细描述」框里的内容作为正文。',
    fields: [
      { k: 'h', label: '小标题', kind: 'text' },
      { k: 'p', label: '正文', kind: 'textarea' },
    ],
    tmpl: { h: '', p: '' },
  },
  {
    key: 'groups', label: '能力分组', open: false,
    hint: '把上方「特性列表」按主题分组展示。起止序号指该组覆盖第几条到第几条特性，从 0 开始数。',
    fields: [
      { k: 'title', label: '分组标题', kind: 'text' },
      { k: 'desc', label: '分组说明', kind: 'textarea' },
      { k: 'range', label: '特性序号', kind: 'range' },
    ],
    tmpl: { title: '', desc: '', range: [0, 0] },
  },
  {
    key: 'deploy', label: '交付方式', open: false,
    hint: '产品详情页「怎么交付」区，也是侧栏「交付形态」的取值来源。',
    fields: [
      { k: 't', label: '方式名称', kind: 'text' },
      { k: 'd', label: '说明', kind: 'textarea' },
    ],
    tmpl: { t: '', d: '' },
  },
  {
    key: 'faq', label: '常见问题', open: false,
    hint: '产品详情页「常见问题」区，一问一答；同时进入页面结构化数据。',
    fields: [
      { k: 'q', label: '问题', kind: 'text' },
      { k: 'a', label: '回答', kind: 'textarea' },
    ],
    tmpl: { q: '', a: '' },
  },
]

const STR_LISTS = [
  { key: 'audience', label: '适合谁', hint: '逐条列出适用场景，官网「适合谁」区展示。', open: false },
  { key: 'not_for', label: '不适合谁', hint: '如实列出不适用场景，官网同样会展示。', open: false },
]
</script>

<template>
  <div class="space-y-4">
    <div class="rounded-lg border border-ink-200 bg-ink-50 px-4 py-3 text-sm text-ink-700">
      这里的内容直接渲染到 <strong>www.cenkor.cn</strong> 的产品详情页与落地页。
      改完请点页面底部「保存修改」，官网会自动同步（约 5 分钟内）。
    </div>

    <!-- 一句话摘要 -->
    <div class="card space-y-3">
      <h2 class="font-semibold text-lg">官网内容 · 摘要</h2>
      <div>
        <label for="wc-summary" class="block text-sm font-medium mb-1.5">一句话摘要</label>
        <input
          id="wc-summary"
          class="input"
          :value="cf.summary || ''"
          placeholder="用于首页产品卡与 Hero 面板"
          @input="setField('summary', val($event))"
        />
        <p class="mt-1 text-xs text-ink-400">留空则回退到「一句话标签」。建议 40 字以内。</p>
      </div>
    </div>

    <!-- 对象数组：正文 / 能力分组 / 交付方式 / FAQ -->
    <details
      v-for="sec in OBJ_LISTS"
      :key="sec.key"
      :open="sec.open"
      class="card"
    >
      <summary class="cursor-pointer font-medium text-ink-900">
        {{ sec.label }} <span class="text-sm font-normal text-ink-400">（{{ list(sec.key).length }} 条）</span>
      </summary>
      <p class="mt-2 text-sm text-ink-500">{{ sec.hint }}</p>

      <p v-if="!list(sec.key).length" class="mt-3 text-sm text-ink-400">暂无内容，点下方「新增一条」开始。</p>

      <div
        v-for="(it, i) in list(sec.key)"
        :key="i"
        class="mt-4 rounded-lg border border-ink-200 p-4 space-y-3"
      >
        <div class="flex flex-wrap items-center justify-between gap-2">
          <span class="text-xs font-medium text-ink-500">第 {{ i + 1 }} 条</span>
          <div class="flex flex-wrap gap-2 text-xs">
            <button type="button" class="btn-ghost" :disabled="i === 0" @click="moveItem(sec.key, i, -1)">上移</button>
            <button type="button" class="btn-ghost" :disabled="i === list(sec.key).length - 1" @click="moveItem(sec.key, i, 1)">下移</button>
            <button type="button" class="text-red-600 hover:underline" @click="removeItem(sec.key, i)">删除</button>
          </div>
        </div>

        <template v-for="f in sec.fields" :key="f.k">
          <div v-if="f.kind === 'range'">
            <span class="block text-sm font-medium mb-1.5">特性起止序号（从 0 开始）</span>
            <div class="grid grid-cols-2 gap-3">
              <div>
                <label :for="`wc-${sec.key}-${i}-start`" class="block text-xs text-ink-500 mb-1">起始</label>
                <input
                  :id="`wc-${sec.key}-${i}-start`"
                  class="input"
                  type="number"
                  min="0"
                  :value="rangeVal(it, 0)"
                  @input="setObjRange(sec.key, i, 0, num($event))"
                />
              </div>
              <div>
                <label :for="`wc-${sec.key}-${i}-end`" class="block text-xs text-ink-500 mb-1">结束（不含）</label>
                <input
                  :id="`wc-${sec.key}-${i}-end`"
                  class="input"
                  type="number"
                  min="0"
                  :value="rangeVal(it, 1)"
                  @input="setObjRange(sec.key, i, 1, num($event))"
                />
              </div>
            </div>
          </div>
          <div v-else>
            <label :for="`wc-${sec.key}-${i}-${f.k}`" class="block text-sm font-medium mb-1.5">{{ f.label }}</label>
            <input
              v-if="f.kind === 'text'"
              :id="`wc-${sec.key}-${i}-${f.k}`"
              class="input"
              :value="itemVal(it, f.k)"
              @input="setObjItem(sec.key, i, f.k, val($event))"
            />
            <textarea
              v-else
              :id="`wc-${sec.key}-${i}-${f.k}`"
              class="input"
              rows="3"
              :value="itemVal(it, f.k)"
              @input="setObjItem(sec.key, i, f.k, val($event))"
            />
          </div>
        </template>
      </div>

      <button type="button" class="btn-ghost mt-4" @click="addObjItem(sec.key, sec.tmpl)">＋ 新增一条</button>
    </details>

    <!-- 字符串数组：适合 / 不适合 -->
    <details v-for="sec in STR_LISTS" :key="sec.key" :open="sec.open" class="card">
      <summary class="cursor-pointer font-medium text-ink-900">
        {{ sec.label }} <span class="text-sm font-normal text-ink-400">（{{ list(sec.key).length }} 条）</span>
      </summary>
      <p class="mt-2 text-sm text-ink-500">{{ sec.hint }}</p>
      <p v-if="!list(sec.key).length" class="mt-3 text-sm text-ink-400">暂无内容。</p>
      <div v-for="(it, i) in list(sec.key)" :key="i" class="mt-3 flex items-center gap-2">
        <span class="w-6 shrink-0 text-xs text-ink-400">{{ i + 1 }}</span>
        <input
          class="input flex-1"
          :aria-label="`${sec.label} 第 ${i + 1} 条`"
          :value="String(it ?? '')"
          @input="setStrItem(sec.key, i, val($event))"
        />
        <button type="button" class="btn-ghost shrink-0" :disabled="i === 0" @click="moveItem(sec.key, i, -1)">上移</button>
        <button type="button" class="text-xs text-red-600 hover:underline shrink-0" @click="removeItem(sec.key, i)">删除</button>
      </div>
      <button type="button" class="btn-ghost mt-4" @click="addItem(sec.key, '')">＋ 新增一条</button>
    </details>

    <!-- 落地页 -->
    <details class="card">
      <summary class="cursor-pointer font-medium text-ink-900">
        落地页文案 <span class="text-sm font-normal text-ink-400">（/lp/&lt;slug&gt;/）</span>
      </summary>
      <p class="mt-2 text-sm text-ink-500">
        仅对「官网」字段为空的产品生成落地页；填了官网地址的产品，详情页按钮会直接跳外部站点。
      </p>
      <div class="mt-4 space-y-3">
        <div>
          <label for="wc-lp-headline" class="block text-sm font-medium mb-1.5">主标题</label>
          <input id="wc-lp-headline" class="input" :value="obj('lp').headline || ''" @input="setLp('headline', val($event))" />
        </div>
        <div>
          <label for="wc-lp-sub" class="block text-sm font-medium mb-1.5">副标题</label>
          <textarea id="wc-lp-sub" class="input" rows="2" :value="obj('lp').sub || ''" @input="setLp('sub', val($event))" />
        </div>
        <div>
          <span class="block text-sm font-medium mb-1.5">核心要点</span>
          <p v-if="!lpPoints().length" class="text-sm text-ink-400">暂无要点。</p>
          <div v-for="(pt, i) in lpPoints()" :key="i" class="mt-2 flex items-center gap-2">
            <span class="w-6 shrink-0 text-xs text-ink-400">{{ i + 1 }}</span>
            <input
              class="input flex-1"
              :aria-label="`核心要点 第 ${i + 1} 条`"
              :value="String(pt ?? '')"
              @input="setLpPoint(i, val($event))"
            />
            <button type="button" class="btn-ghost shrink-0" :disabled="i === 0" @click="moveLpPoint(i, -1)">上移</button>
            <button type="button" class="text-xs text-red-600 hover:underline shrink-0" @click="removeLpPoint(i)">删除</button>
          </div>
          <button type="button" class="btn-ghost mt-3" @click="addLpPoint">＋ 新增要点</button>
        </div>
      </div>
    </details>
  </div>
</template>
