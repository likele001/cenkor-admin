<script setup lang="ts">
import { useI18n } from 'vue-i18n'
const { t } = useI18n()
import { ref, computed, onMounted } from 'vue'
import { api } from '@/lib/api'

interface SiteConfigItem {
  key: string
  value: unknown
  description: string | null
  updated_at: string | null
}

interface ConfigGroup {
  id: string
  label: string
  hint: string
  items: SiteConfigItem[]
}

const items = ref<SiteConfigItem[]>([])
const loading = ref(true)
const error = ref('')
const saving = ref<string | null>(null)
const savedKey = ref<string | null>(null)
const search = ref('')
const editValues = ref<Record<string, string>>({})

const GROUP_DEFS: { id: string; label: string; hint: string }[] = [
  { id: 'web', label: '官网文案', hint: 'www.cenkor.cn 静态站的标题、导语、按钮与页面固定文案。改完约 5 分钟内自动同步到官网；留空或保持默认值则不改动页面。' },
  { id: 'brand', label: '品牌信息', hint: '品牌名称、标语与简介，页脚与首页主视觉会用到。' },
  { id: 'contact', label: '联系方式', hint: '页脚、联系页与落地页的邮箱、电话、微信。' },
  { id: 'seo', label: 'SEO 默认值', hint: '站点级 meta 默认值，产品可单独覆盖。' },
  { id: 'url', label: 'URL 规则', hint: '站内链接历史规则，通常不需要改动。' },
  { id: 'other', label: '其他', hint: '' },
]

function groupOf(key: string): string {
  const prefix = key.split('.')[0]
  const known = ['web', 'brand', 'contact', 'seo', 'url']
  return known.includes(prefix) ? prefix : 'other'
}

const groups = computed<ConfigGroup[]>(() => {
  const q = search.value.trim().toLowerCase()
  const matched = items.value.filter((item) => {
    if (!q) return true
    return (
      item.key.toLowerCase().includes(q) ||
      (item.description || '').toLowerCase().includes(q) ||
      String(item.value ?? '').toLowerCase().includes(q)
    )
  })
  return GROUP_DEFS.map((def) => ({
    ...def,
    items: matched
      .filter((item) => groupOf(item.key) === def.id)
      .sort((a, b) => a.key.localeCompare(b.key)),
  })).filter((g) => g.items.length > 0)
})

const totalMatched = computed(() => groups.value.reduce((n, g) => n + g.items.length, 0))

async function load() {
  loading.value = true
  error.value = ''
  try {
    const { data } = await api.get('/api/v1/cms/site-config')
    items.value = data.items
    for (const item of data.items) {
      editValues.value[item.key] =
        typeof item.value === 'string' ? item.value : JSON.stringify(item.value, null, 2)
    }
  } catch (e: any) {
    error.value = e?.response?.data?.detail || 't("caseEdit.loadFailed")'
  } finally {
    loading.value = false
  }
}

function parseValue(raw: string): unknown {
  const trimmed = raw.trim()
  if (trimmed.startsWith('{') || trimmed.startsWith('[')) {
    return JSON.parse(trimmed)
  }
  if (trimmed === 'true') return true
  if (trimmed === 'false') return false
  if (/^-?\d+$/.test(trimmed)) return Number(trimmed)
  return raw
}

async function save(item: SiteConfigItem) {
  saving.value = item.key
  error.value = ''
  savedKey.value = null
  try {
    const value = parseValue(editValues.value[item.key] ?? '')
    await api.put(`/api/v1/cms/site-config/${item.key}`, {
      value,
      description: item.description,
    })
    await load()
    savedKey.value = item.key
    window.setTimeout(() => {
      if (savedKey.value === item.key) savedKey.value = null
    }, 3000)
  } catch (e: any) {
    error.value = e?.response?.data?.detail || 't("caseEdit.saveFailed")'
  } finally {
    saving.value = null
  }
}

onMounted(load)
</script>

<template>
  <div>
    <h1 class="text-2xl font-semibold tracking-tight mb-2">{{ t('siteConfig.站点配置_fz0r7l') }}</h1>
    <p class="text-ink-500 mb-6">{{ t('siteConfig.管理官网_1nkjj0') }}</p>

    <div v-if="loading" class="card text-ink-500">{{ t('usersList.加载中_b0k5km') }}</div>
    <div v-else-if="error" class="card text-red-600">⚠️ {{ error }}</div>
    <div v-else>
      <div class="flex flex-wrap items-center gap-3 mb-5">
        <label for="site-config-search" class="text-sm font-medium">搜索配置项</label>
        <input
          id="site-config-search"
          v-model="search"
          class="input max-w-md"
          type="search"
          placeholder="输入 key 或说明，如 hero、主标题、邮箱"
        />
        <span class="text-sm text-ink-400">共 {{ totalMatched }} 项</span>
      </div>

      <div v-if="items.length === 0" class="card text-center text-ink-400 py-12">{{ t('siteConfig.暂无配置_1n3u3j') }}</div>
      <div v-else-if="totalMatched === 0" class="card text-center text-ink-400 py-12">没有匹配的配置项，换个关键词试试。</div>

      <section v-for="g in groups" :key="g.id" class="mb-8">
        <h2 class="text-lg font-semibold mb-1">
          {{ g.label }} <span class="text-sm font-normal text-ink-400">（{{ g.items.length }}）</span>
        </h2>
        <p v-if="g.hint" class="text-sm text-ink-500 mb-3">{{ g.hint }}</p>
        <div class="space-y-3">
          <div v-for="item in g.items" :key="item.key" class="card">
            <div class="flex items-start justify-between gap-4 mb-3">
              <div class="min-w-0">
                <code class="text-sm font-medium">{{ item.key }}</code>
                <p v-if="item.description" class="text-sm text-ink-500 mt-1">{{ item.description }}</p>
              </div>
              <span v-if="item.updated_at" class="text-xs text-ink-400 shrink-0">{{ item.updated_at.slice(0, 10) }}</span>
            </div>
            <label class="sr-only" :for="`cfg-${item.key}`">{{ item.key }} 的值</label>
            <textarea :id="`cfg-${item.key}`" v-model="editValues[item.key]" rows="2" class="input font-mono text-sm" />
            <div class="mt-3 flex items-center gap-3">
              <button
                class="btn-primary"
                :disabled="saving === item.key"
                @click="save(item)"
              >
                {{ saving === item.key ? '保存中…' : '保存' }}
              </button>
              <span v-if="savedKey === item.key" class="text-sm text-emerald-600" role="status">已保存，官网将自动同步</span>
            </div>
          </div>
        </div>
      </section>
    </div>
  </div>
</template>
