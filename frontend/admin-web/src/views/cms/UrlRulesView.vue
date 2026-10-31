<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import { api } from '@/lib/api'

interface RuleVar { name: string; desc: string }

interface DefaultRule {
  kind: string
  label: string
  config_key: string
  pattern: string
  builtin: string
  source: 'default' | 'custom' | 'invalid'
  vars: RuleVar[]
}

interface OverrideItem {
  id: number
  name: string
  slug: string
  url_pattern: string | null
}

interface HistoryItem { kind: string; pattern: string }

interface Conflict {
  sample: string
  severity: 'block' | 'warn'
  reason: string
  other_source: string
  other_pattern: string
}

interface PreviewResult {
  ok: boolean
  pattern: string
  samples: string[]
  conflicts: Conflict[]
  message: string
}

const defaults = ref<DefaultRule[]>([])
const categories = ref<OverrideItem[]>([])
const tags = ref<OverrideItem[]>([])
const history = ref<HistoryItem[]>([])

const loading = ref(true)
// 加载失败（页面整体错误）与保存失败（只影响单条规则）要分开。
// 用同一个状态的话，保存一失败整页规则列表就被错误卡片顶掉了 ——
// 用户改到一半的草稿全丢，只能重新来。
const loadError = ref('')
const saveError = ref('')
// 每类规则的编辑框内容：kind -> 草稿 pattern
const drafts = ref<Record<string, string>>({})
// 每类规则的预览结果：kind -> 预览
const previews = ref<Record<string, PreviewResult | null>>({})
const previewing = ref<string | null>(null)
const saving = ref<string | null>(null)

const overriddenCategories = computed(() => categories.value.filter(c => !!c.url_pattern))
const overriddenTags = computed(() => tags.value.filter(t => !!t.url_pattern))

const sourceLabel: Record<string, string> = {
  default: '内置默认',
  custom: '已自定义',
  invalid: '规则非法',
}

async function load() {
  loading.value = true
  loadError.value = ''
  try {
    const { data } = await api.get('/api/v1/cms/url-rules')
    defaults.value = data.defaults || []
    categories.value = data.categories || []
    tags.value = data.tags || []
    history.value = data.history || []
    const next: Record<string, string> = {}
    for (const r of defaults.value) next[r.kind] = r.pattern
    drafts.value = next
  } catch (e: any) {
    loadError.value = e?.response?.data?.detail || '规则加载失败'
  } finally {
    loading.value = false
  }
}

/** 预览一条规则：校验合法性 + 看示例地址 + 看冲突。 */
async function preview(rule: DefaultRule) {
  previewing.value = rule.kind
  try {
    const { data } = await api.post('/api/v1/cms/url-rules/preview', {
      kind: rule.kind,
      pattern: drafts.value[rule.kind] ?? '',
    })
    previews.value = { ...previews.value, [rule.kind]: data }
  } catch (e: any) {
    previews.value = {
      ...previews.value,
      [rule.kind]: {
        ok: false,
        pattern: drafts.value[rule.kind] ?? '',
        samples: [],
        conflicts: [],
        message: e?.response?.data?.detail || '预览失败',
      },
    }
  } finally {
    previewing.value = null
  }
}

/** 保存一条站点默认规则。传空串 = 恢复内置默认。 */
async function save(rule: DefaultRule) {
  saving.value = rule.kind
  saveError.value = ''
  try {
    await api.post('/api/v1/cms/url-rules/save', {
      kind: rule.kind,
      pattern: drafts.value[rule.kind] ?? '',
    })
    await load()
  } catch (e: any) {
    // 失败只提示，不重载页面：草稿要留着，用户改一版就能再试
    saveError.value = `「${rule.label}」保存失败：${e?.response?.data?.detail || '未知错误'}`
  } finally {
    saving.value = null
  }
}

function resetDraft(rule: DefaultRule) {
  drafts.value = { ...drafts.value, [rule.kind]: rule.builtin }
}

onMounted(load)
</script>

<template>
  <div>
    <div class="mb-6">
      <h1 class="text-2xl font-semibold tracking-tight">URL 伪静态规则</h1>
      <p class="text-ink-500">
        控制内容在前台的访问地址。规则改动后，老地址会自动 301 到新地址，不会变成 404。
      </p>
    </div>

    <!-- 优先级说明：三层规则，改哪一层决定谁说了算 -->
    <div class="card mb-6 bg-ink-50 border-ink-200">
      <h2 class="text-sm font-semibold mb-3">规则优先级（从上到下，覆盖前面的）</h2>
      <ol class="space-y-1.5 text-sm text-ink-700 list-decimal list-inside">
        <li>单条内容自定义地址 —— 在文章编辑页填「自定义地址」，优先级最高，规则再改也不动它</li>
        <li>栏目 / 标签覆盖 —— 在「分类管理」「标签管理」里单独设置，只对那一个栏目或标签生效</li>
        <li>站点默认规则 —— 就是本页下面这几条，全站通用</li>
      </ol>
      <p class="text-xs text-ink-500 mt-3">
        注意：栏目级规则只决定「栏目页自己的地址」，不管该栏目下文章的地址 ——
        文章地址看站点默认规则里有没有用 <code>{catdir}</code>。
      </p>
    </div>

    <div v-if="loading" class="card text-ink-500">加载中…</div>
    <div v-else-if="loadError" class="card mb-4 text-red-600">⚠️ {{ loadError }}</div>

    <template v-else>
      <!-- 保存失败：只提示，不清空列表和草稿 -->
      <div v-if="saveError" class="card mb-4 text-red-600">⚠️ {{ saveError }}</div>
      <!-- 站点默认规则 -->
      <h2 class="text-lg font-semibold mb-3">站点默认规则</h2>
      <div class="space-y-4 mb-8">
        <div v-for="rule in defaults" :key="rule.kind" class="card">
          <div class="flex items-start justify-between gap-4 mb-3">
            <div>
              <div class="flex items-center gap-2">
                <span class="font-medium">{{ rule.label }}</span>
                <code class="text-xs text-ink-400">{{ rule.config_key }}</code>
                <span
                  class="text-xs px-2 py-0.5 rounded-full"
                  :class="{
                    'bg-ink-100 text-ink-600': rule.source === 'default',
                    'bg-green-100 text-green-700': rule.source === 'custom',
                    'bg-red-100 text-red-700': rule.source === 'invalid',
                  }"
                >{{ sourceLabel[rule.source] || rule.source }}</span>
              </div>
              <p class="text-xs text-ink-500 mt-1">
                内置默认：<code class="text-ink-700">{{ rule.builtin }}</code>
              </p>
            </div>
          </div>

          <input
            v-model="drafts[rule.kind]"
            class="input font-mono text-sm"
            :placeholder="rule.builtin"
          />

          <!-- 可用变量提示：让用户知道能填什么，而不是靠猜 -->
          <div class="mt-2 flex flex-wrap gap-1.5">
            <span
              v-for="v in rule.vars"
              :key="v.name"
              class="text-xs px-2 py-0.5 rounded bg-ink-100 text-ink-600 cursor-help"
              :title="v.desc"
            ><code>{{ '{' + v.name + '}' }}</code></span>
          </div>

          <div class="mt-3 flex flex-wrap gap-2">
            <button class="btn-outline" :disabled="previewing === rule.kind" @click="preview(rule)">
              {{ previewing === rule.kind ? '预览中…' : '预览' }}
            </button>
            <button class="btn-primary" :disabled="saving === rule.kind" @click="save(rule)">
              {{ saving === rule.kind ? '保存中…' : '保存' }}
            </button>
            <button class="btn-ghost" @click="resetDraft(rule)">填回默认值</button>
          </div>

          <!-- 预览结果：示例地址 + 冲突 -->
          <div v-if="previews[rule.kind]" class="mt-4 border-t border-ink-200 pt-3">
            <div
              class="text-sm mb-2"
              :class="previews[rule.kind]!.ok ? 'text-green-700' : 'text-red-600'"
            >
              {{ previews[rule.kind]!.ok ? '✓' : '✕' }} {{ previews[rule.kind]!.message }}
            </div>
            <div v-if="previews[rule.kind]!.samples.length" class="text-sm">
              <span class="text-ink-500">示例地址：</span>
              <code
                v-for="s in previews[rule.kind]!.samples"
                :key="s"
                class="block text-ink-800 bg-ink-50 px-2 py-1 rounded mt-1"
              >{{ s }}</code>
            </div>
            <div v-if="previews[rule.kind]!.conflicts.length" class="mt-3 space-y-2">
              <div
                v-for="(c, i) in previews[rule.kind]!.conflicts"
                :key="i"
                class="text-sm rounded px-3 py-2"
                :class="c.severity === 'block' ? 'bg-red-50 text-red-700' : 'bg-amber-50 text-amber-700'"
              >
                <div class="font-medium">
                  {{ c.severity === 'block' ? '冲突' : '重叠' }}：{{ c.sample }}
                </div>
                <div>{{ c.reason }}</div>
                <div class="text-xs opacity-75">
                  对方规则：{{ c.other_source }} · <code>{{ c.other_pattern }}</code>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- 栏目覆盖概览 -->
      <h2 class="text-lg font-semibold mb-3">栏目覆盖（{{ overriddenCategories.length }}）</h2>
      <div class="card mb-8">
        <p class="text-sm text-ink-500 mb-3">
          栏目级规则只管栏目页自己的地址。修改请到「分类管理」里编辑对应栏目。
        </p>
        <div v-if="!overriddenCategories.length" class="text-sm text-ink-400">暂无栏目自定义规则</div>
        <div
          v-for="c in overriddenCategories"
          :key="c.id"
          class="flex items-center gap-3 py-2 border-b border-ink-100 last:border-0"
        >
          <span class="font-medium text-sm">{{ c.name }}</span>
          <code class="text-xs text-ink-400">{{ c.slug }}</code>
          <code class="text-xs text-ink-700 ml-auto">{{ c.url_pattern }}</code>
        </div>
      </div>

      <!-- 标签覆盖概览 -->
      <h2 class="text-lg font-semibold mb-3">标签覆盖（{{ overriddenTags.length }}）</h2>
      <div class="card mb-8">
        <p class="text-sm text-ink-500 mb-3">
          标签页对 SEO 最友好，建议用短 slug。修改请到「标签管理」里编辑对应标签。
        </p>
        <div v-if="!overriddenTags.length" class="text-sm text-ink-400">暂无标签自定义规则</div>
        <div
          v-for="t in overriddenTags"
          :key="t.id"
          class="flex items-center gap-3 py-2 border-b border-ink-100 last:border-0"
        >
          <span class="font-medium text-sm">{{ t.name }}</span>
          <code class="text-xs text-ink-400">{{ t.slug }}</code>
          <code class="text-xs text-ink-700 ml-auto">{{ t.url_pattern }}</code>
        </div>
      </div>

      <!-- 变更存档 -->
      <h2 class="text-lg font-semibold mb-3">历史规则存档（{{ history.length }}）</h2>
      <div class="card">
        <p class="text-sm text-ink-500 mb-3">
          每次保存前的旧规则会存到这里，用来把老地址 301 到新地址。最多保留 50 条。
        </p>
        <div v-if="!history.length" class="text-sm text-ink-400">暂无历史存档</div>
        <div
          v-for="(h, i) in history.slice().reverse()"
          :key="i"
          class="flex items-center gap-3 py-2 border-b border-ink-100 last:border-0"
        >
          <code class="text-xs text-ink-400">{{ h.kind }}</code>
          <code class="text-xs text-ink-700">{{ h.pattern }}</code>
        </div>
      </div>
    </template>
  </div>
</template>
