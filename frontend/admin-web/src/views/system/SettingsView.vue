<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { api } from '@/lib/api'

interface Setting {
  key: string
  value: any
  description: string | null
  group: string
  updated_by: number | null
  updated_at: string | null
}

const { t } = useI18n()
const items = ref<Setting[]>([])
const loading = ref(true)
const error = ref('')
const editing = ref<string | null>(null)
const draft = ref<{ value: string; description: string }>({ value: '', description: '' })
const saving = ref(false)
const toggling = ref<string | null>(null)

// 布尔型设置直接渲染成开关，点击即时切换保存；其余类型维持原 textarea 编辑。
function isBool(s: Setting): boolean {
  return typeof s.value === 'boolean'
}

async function toggleBool(s: Setting) {
  toggling.value = s.key
  try {
    await api.put(`/api/v1/system/settings/${s.key}`, {
      value: !s.value,
      description: s.description ?? null,
    })
    await load()
  } catch (e: any) {
    alert(t('settings.saveFailed', '保存失败') + '：' + (e?.response?.data?.detail || e.message))
  } finally {
    toggling.value = null
  }
}

async function load() {
  loading.value = true
  error.value = ''
  try {
    const { data } = await api.get('/api/v1/system/settings')
    items.value = data.items
  } catch (e: any) {
    error.value = e?.response?.data?.detail || t('settings.loadFailed', '加载失败')
  } finally {
    loading.value = false
  }
}

const grouped = computed(() => {
  const m: Record<string, Setting[]> = {}
  for (const s of items.value) {
    if (!m[s.group]) m[s.group] = []
    m[s.group].push(s)
  }
  return m
})

function startEdit(s: Setting) {
  editing.value = s.key
  draft.value = {
    value: typeof s.value === 'string' ? s.value : JSON.stringify(s.value, null, 2),
    description: s.description || '',
  }
}

function cancelEdit() {
  editing.value = null
}

async function save(key: string) {
  saving.value = true
  try {
    let parsed: any
    try {
      parsed = JSON.parse(draft.value.value)
    } catch {
      parsed = draft.value.value
    }
    await api.put(`/api/v1/system/settings/${key}`, {
      value: parsed,
      description: draft.value.description || null,
    })
    editing.value = null
    await load()
  } catch (e: any) {
    alert(t('settings.saveFailed', '保存失败') + '：' + (e?.response?.data?.detail || e.message))
  } finally {
    saving.value = false
  }
}

function displayValue(v: any): string {
  if (v == null) return '∅'
  if (typeof v === 'string') return v
  return JSON.stringify(v)
}

onMounted(load)
</script>

<template>
  <div class="min-h-screen bg-ink-50">
    <header class="bg-white border-b border-ink-200">
      <div class="max-w-7xl mx-auto px-6 h-14 flex items-center gap-4">
        <router-link to="/" class="text-sm text-ink-500 hover:text-ink-900">← {{ t('nav.dashboard') }}</router-link>
        <span class="font-semibold">{{ t('settings.title', '系统设置') }}</span>
      </div>
    </header>

    <main class="max-w-5xl mx-auto px-6 py-10">
      <div v-if="loading" class="card text-ink-500">{{ t('app.loading') }}</div>
      <div v-else-if="error" class="card text-red-600">⚠️ {{ error }}</div>
      <div v-else class="space-y-6">
        <section v-for="(group, name) in grouped" :key="name" class="card p-0 overflow-hidden">
          <header class="px-5 py-3 bg-ink-50 border-b border-ink-200">
            <h2 class="text-sm font-semibold uppercase tracking-wide text-ink-500">{{ name }}</h2>
          </header>
          <ul class="divide-y divide-ink-100">
            <li v-for="s in group" :key="s.key" class="px-5 py-4">
              <div class="flex items-start justify-between gap-4">
                <div class="min-w-0 flex-1">
                  <code class="text-sm font-mono text-ink-900">{{ s.key }}</code>
                  <p v-if="s.description" class="mt-1 text-xs text-ink-500">{{ s.description }}</p>
                </div>
                <!-- 布尔型：可视化开关，点击即时切换 -->
                <div v-if="isBool(s)" class="flex items-center gap-3 shrink-0">
                  <span
                    class="text-xs font-medium"
                    :class="s.value ? 'text-brand-600' : 'text-ink-400'"
                  >{{ s.value ? t('settings.enabled', '开启') : t('settings.disabled', '关闭') }}</span>
                  <button
                    type="button"
                    role="switch"
                    :aria-checked="s.value"
                    class="relative inline-flex h-6 w-11 shrink-0 items-center rounded-full transition-colors focus:outline-none focus:ring-2 focus:ring-brand-500/40 disabled:cursor-not-allowed disabled:opacity-50"
                    :class="s.value ? 'bg-brand-600' : 'bg-ink-300'"
                    :disabled="toggling === s.key"
                    @click="toggleBool(s)"
                  >
                    <span
                      class="inline-block h-5 w-5 transform rounded-full bg-white shadow transition-transform"
                      :class="s.value ? 'translate-x-[22px]' : 'translate-x-0.5'"
                    />
                  </button>
                </div>
                <!-- 非布尔：编辑按钮 -->
                <button
                  v-else-if="editing !== s.key"
                  type="button"
                  class="text-sm text-brand-600 hover:underline shrink-0"
                  @click="startEdit(s)"
                >
                  {{ t('app.edit') }}
                </button>
              </div>
              <!-- 非布尔编辑区 -->
              <div v-if="editing === s.key && !isBool(s)" class="mt-3 space-y-3">
                <textarea
                  v-model="draft.value"
                  rows="4"
                  class="input font-mono text-xs"
                  :placeholder="t('settings.jsonPlaceholder', 'JSON 字符串')"
                />
                <input
                  v-model="draft.description"
                  class="input"
                  :placeholder="t('settings.descPlaceholder', '描述（可选）')"
                />
                <div class="flex items-center gap-2">
                  <button
                    type="button"
                    class="btn-primary text-sm"
                    :disabled="saving"
                    @click="save(s.key)"
                  >
                    {{ saving ? t('app.saving', '保存中…') : t('app.save') }}
                  </button>
                  <button type="button" class="btn-ghost text-sm" @click="cancelEdit">{{ t('app.cancel') }}</button>
                </div>
              </div>
              <!-- 非布尔只读展示 -->
              <div v-else-if="!isBool(s)" class="mt-2">
                <pre class="text-xs bg-ink-50 border border-ink-200 rounded-md p-2 overflow-x-auto">{{ displayValue(s.value) }}</pre>
                <p v-if="s.updated_at" class="mt-1 text-[10px] text-ink-400">
                  {{ t('settings.lastUpdated', '上次更新') }}：{{ s.updated_at }} · by user#{{ s.updated_by ?? '?' }}
                </p>
              </div>
            </li>
          </ul>
        </section>
      </div>
    </main>
  </div>
</template>