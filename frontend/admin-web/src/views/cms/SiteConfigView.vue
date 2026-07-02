<script setup lang="ts">
import { useI18n } from 'vue-i18n'
const { t } = useI18n()
import { ref, onMounted } from 'vue'
import { api } from '@/lib/api'

interface SiteConfigItem {
  key: string
  value: unknown
  description: string | null
  updated_at: string | null
}

const items = ref<SiteConfigItem[]>([])
const loading = ref(true)
const error = ref('')
const saving = ref<string | null>(null)
const editValues = ref<Record<string, string>>({})

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
  try {
    const value = parseValue(editValues.value[item.key] ?? '')
    await api.put(`/api/v1/cms/site-config/${item.key}`, {
      value,
      description: item.description,
    })
    await load()
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
    <div v-else class="space-y-4">
      <div v-for="item in items" :key="item.key" class="card">
        <div class="flex items-start justify-between gap-4 mb-3">
          <div>
            <code class="text-sm font-medium">{{ item.key }}</code>
            <p v-if="item.description" class="text-sm text-ink-500 mt-1">{{ item.description }}</p>
          </div>
          <span v-if="item.updated_at" class="text-xs text-ink-400 shrink-0">{{ item.updated_at.slice(0, 10) }}</span>
        </div>
        <textarea v-model="editValues[item.key]" rows="2" class="input font-mono text-sm" />
        <div class="mt-3">
          <button
            class="btn-primary"
            :disabled="saving === item.key"
            @click="save(item)"
          >
            {{ saving === item.key ? '保存中…' : '保存' }}
          </button>
        </div>
      </div>
      <div v-if="items.length === 0" class="card text-center text-ink-400 py-12">{{ t('siteConfig.暂无配置_1n3u3j') }}</div>
    </div>
  </div>
</template>
