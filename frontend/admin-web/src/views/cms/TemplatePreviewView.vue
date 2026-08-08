<script setup lang="ts">
import { useI18n } from 'vue-i18n'
const { t } = useI18n()
import { ref, onMounted, computed } from 'vue'
import { api } from '@/lib/api'

interface FieldDef {
  field_key: string; label: string; field_type: string;
  field_options: { value: string; label: string; color: string | null }[]
}

const contentTypes = ref<any[]>([])
const selectedCtKey = ref('product')
const templates = ref<any[]>([])
const fields = ref<FieldDef[]>([])
const form = ref({ name: '', desc: '' })
const template = ref('{{ name | upcase }}')
const rendered = ref('')
const error = ref('')
const valid = ref(true)
const saving = ref(false)

const defaultTemplates: Record<string, string> = {
  product: `{% for p in entries %}
## {{ p.title }}
{{ p.content.tagline | default: '' }}
**价格**: {{ p.custom_fields.price | format_price | default: 't("templatePreview.面议")' }}
{% if p.content.features %}- 特性: {{ p.content.features | join: ', ' }}
{% endif %}
---
{% endfor %}`,
  case: `{% for c in entries %}
- **{{ c.title }}** ({{ c.content.industry | default: 't("templatePreview.通用")' }})
  {{ c.content.desc | default: '' }}
{% endfor %}`,
  news: `{% for n in entries %}
# {{ n.title }}
{{ n.content.excerpt | default: '' }}
发布日期: {{ n.published_at | date: '%Y-%m-%d' | default: 't("productEdit.草稿_n02e")' }}
{% endfor %}`,
}

async function loadContentTypes() {
  const { data } = await api.get('/api/v1/cms/content-types')
  contentTypes.value = data.items
}

async function loadFields() {
  if (!selectedCtKey.value) return
  const { data } = await api.get(`/api/v1/cms/content-types?page=1&page_size=200`)
  const ct = data.items.find((c: any) => c.key === selectedCtKey.value)
  if (ct) {
    const detail = await api.get(`/api/v1/cms/content-types/${ct.id}`)
    fields.value = detail.data.field_definitions
  }
}

async function loadEntries() {
  const { data } = await api.get(`/api/v1/cms/entries?content_type_key=${selectedCtKey.value}&page=1&page_size=5`)
  return data.items
}

async function render() {
  error.value = ''
  try {
    const entries = await loadEntries()
    const data = { entries, name: form.value.name || 't("templatePreview.示例")', now: new Date().toISOString() }
    const r = await api.post('/api/v1/cms/templates/render', { template: template.value, data })
    rendered.value = r.data.rendered
  } catch (e: any) {
    error.value = e?.response?.data?.detail || 't("templatePreview.渲染失败")'
    rendered.value = ''
  }
}

async function validate() {
  const r = await api.post('/api/v1/cms/templates/validate', { template: template.value })
  valid.value = r.data.valid
  error.value = r.data.error
}

function setDefaultTemplate() {
  if (defaultTemplates[selectedCtKey.value]) {
    template.value = defaultTemplates[selectedCtKey.value]
  }
}

function insertSnippet(snippet: string) {
  template.value += snippet
}

const templateSnippets = [
  { label: 't("templatePreview.变量")', text: '{{ variable_name }}' },
  { label: 'if', text: '{% if condition %}...{% endif %}' },
  { label: 'for', text: '{% for item in collection %}{{ item }}{% endfor %}' },
  { label: 'upcase', text: ' | upcase' },
  { label: 'date', text: ' | date: "%Y-%m-%d"' },
  { label: 'format_price', text: ' | format_price' },
  { label: 'markdown', text: ' | markdown' },
  { label: 'truncate', text: ' | truncate: 100' },
]

onMounted(async () => {
  await loadContentTypes()
  await loadFields()
  setDefaultTemplate()
})
</script>

<template>
  <div>
    <div class="mb-4">
      <h1 class="text-2xl font-semibold tracking-tight">{{ t('templatePreview.模板预览_dtsi4i') }}</h1>
      <p class="text-ink-500">{{ t('templatePreview.使用_1mk1ub') }}</p>
    </div>

    <div class="grid grid-cols-1 sm:grid-cols-2 gap-4">
      <!-- Left: editor -->
      <div class="space-y-3">
        <div class="card">
          <label class="block text-sm font-medium mb-1">{{ t('templatePreview.内容类型_ao6o90') }}</label>
          <select v-model="selectedCtKey" class="input" @change="loadFields">
            <option v-for="ct in contentTypes" :key="ct.key" :value="ct.key">{{ ct.icon }} {{ ct.name }}</option>
          </select>
          <button class="btn-ghost text-sm mt-2" @click="setDefaultTemplate">{{ t('templatePreview.使用默认_rz06dv') }}</button>
        </div>

        <div class="card">
          <div class="flex items-center justify-between mb-1">
            <label class="block text-sm font-medium">{{ t('templatePreview.模板_1nve5c') }}</label>
            <span v-if="valid" class="text-xs text-green-600">{{ t('templatePreview.text_1upoog') }}</span>
            <span v-else class="text-xs text-red-600">✗ {{ error }}</span>
          </div>
          <textarea v-model="template" class="input font-mono text-xs min-h-[400px]" @input="validate" />
          <div class="flex flex-wrap gap-1 mt-2">
            <button v-for="s in templateSnippets" :key="s.label" class="text-xs px-2 py-0.5 bg-ink-50 hover:bg-ink-100 rounded" @click="insertSnippet(s.text)">
              + {{ s.label }}
            </button>
          </div>
        </div>

        <div class="card">
          <label class="block text-sm font-medium mb-1">{{ t('templatePreview.测试数据_ed8ep4') }}</label>
          <input v-model="form.name" class="input" placeholder="name" />
          <textarea v-model="form.desc" class="input mt-2" placeholder="desc" />
          <button class="btn-primary mt-2" @click="render">{{ t('templatePreview.渲染_jba9') }}</button>
        </div>
      </div>

      <!-- Right: preview -->
      <div class="card">
        <h3 class="font-medium text-sm mb-2">{{ t('templatePreview.渲染结果_jsth5o') }}</h3>
        <div v-if="error" class="text-red-600 text-sm">{{ error }}</div>
        <pre v-else class="whitespace-pre-wrap text-sm bg-ink-50 p-3 rounded font-mono">{{ rendered || '（点击「渲染」按钮查看效果）' }}</pre>

        <h3 class="font-medium text-sm mt-4 mb-2">{{ t('templatePreview.字段定义_3y0ez1') }}</h3>
        <div v-if="fields.length" class="text-xs space-y-1">
          <div v-for="f in fields" :key="f.field_key" class="flex gap-2">
            <code class="bg-ink-50 px-1 rounded">{{ f.field_key }}</code>
            <span class="text-ink-500">{{ f.label }} ({{ f.field_type }})</span>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>
