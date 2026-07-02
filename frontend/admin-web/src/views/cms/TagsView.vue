<script setup lang="ts">
import { useI18n } from 'vue-i18n'
const { t } = useI18n()
import { ref, onMounted } from 'vue'
import { api } from '@/lib/api'

interface Tag { id: number; content_type_id: number; slug: string; name: string; color: string | null }
interface ContentType { id: number; key: string; name: string; icon: string | null }

const contentTypes = ref<ContentType[]>([])
const selectedCtKey = ref('')
const tags = ref<Tag[]>([])
const loading = ref(true)
const saving = ref(false)
const showModal = ref(false)
const editing = ref<Tag | null>(null)
const search = ref('')
const form = ref({ name: '', slug: '', color: '#6366f1' })

const COLORS = [
  '#ef4444', '#f97316', '#f59e0b', '#eab308', '#84cc16', '#22c55e',
  '#14b8a6', '#06b6d4', '#0ea5e9', '#3b82f6', '#6366f1', '#8b5cf6',
  '#a855f7', '#d946ef', '#ec4899', '#f43f5e',
]

async function loadContentTypes() {
  try {
    const { data } = await api.get('/api/v1/cms/content-types')
    contentTypes.value = data.items
    if (data.items.length && !selectedCtKey.value) selectedCtKey.value = data.items[0].key
  } catch { /* ignore */ }
}

async function loadTags() {
  if (!selectedCtKey.value) return
  loading.value = true
  try {
    const params = new URLSearchParams({ content_type_key: selectedCtKey.value })
    if (search.value) params.set('search', search.value)
    const { data } = await api.get(`/api/v1/cms/tags?${params}`)
    tags.value = data.items || []
  } catch { /* ignore */ }
  finally { loading.value = false }
}

function openCreate() {
  editing.value = null
  form.value = { name: '', slug: '', color: COLORS[Math.floor(Math.random() * COLORS.length)] }
  showModal.value = true
}

function openEdit(tag: Tag) {
  editing.value = tag
  form.value = { name: tag.name, slug: tag.slug, color: tag.color || '#6366f1' }
  showModal.value = true
}

async function save() {
  saving.value = true
  try {
    if (editing.value) {
      await api.patch(`/api/v1/cms/tags/${editing.value.id}`, {
        name: form.value.name, slug: form.value.slug, color: form.value.color,
      })
    } else {
      await api.post('/api/v1/cms/tags', {
        content_type_key: selectedCtKey.value,
        name: form.value.name, slug: form.value.slug, color: form.value.color,
      })
    }
    showModal.value = false
    await loadTags()
  } catch (e: any) {
    alert(e?.response?.data?.detail || 't("caseEdit.saveFailed")')
  } finally { saving.value = false }
}

async function remove(tag: Tag) {
  if (!confirm(`确定删除标签「${tag.name}」？`)) return
  try {
    await api.delete(`/api/v1/cms/tags/${tag.id}`)
    await loadTags()
  } catch (e: any) {
    alert(e?.response?.data?.detail || 't("categories.删除失败")')
  }
}

function onCtChange() { loadTags() }

onMounted(async () => {
  await loadContentTypes()
  await loadTags()
})
</script>

<template>
  <div>
    <div class="flex items-center justify-between mb-6">
      <div>
        <h1 class="text-2xl font-semibold tracking-tight">{{ t('tags.标签管理_dn1dss') }}</h1>
        <p class="text-ink-500">{{ t('tags.管理各内_2f5syy') }}</p>
      </div>
      <div class="flex gap-2">
        <select v-model="selectedCtKey" class="input w-40" @change="onCtChange">
          <option v-for="ct in contentTypes" :key="ct.key" :value="ct.key">{{ ct.name }}</option>
        </select>
        <button class="btn-primary" @click="openCreate">{{ t('tags.text_y2of06') }}</button>
      </div>
    </div>

    <div v-if="loading" class="card text-ink-500">{{ t('usersList.加载中_b0k5km') }}</div>
    <div v-else-if="tags.length === 0" class="card text-center text-ink-400 py-12">
      {{ t('tags.暂无标签点击新建标签创建第一个') }}
    </div>
    <div v-else class="flex flex-wrap gap-2">
      <div
        v-for="tag in tags"
        :key="tag.id"
        class="card flex items-center gap-2 py-2 px-3 hover:shadow-md transition-shadow"
      >
        <span class="w-3 h-3 rounded-full shrink-0" :style="{ backgroundColor: tag.color || '#6b7280' }"></span>
        <span class="font-medium">{{ tag.name }}</span>
        <code class="text-xs text-ink-400">{{ tag.slug }}</code>
        <div class="flex gap-1 ml-2">
          <button class="text-ink-400 hover:text-ink-600 text-xs" @click="openEdit(tag)">&#9998;</button>
          <button class="text-ink-400 hover:text-red-600 text-xs" @click="remove(tag)">&times;</button>
        </div>
      </div>
    </div>

    <!-- Modal -->
    <div v-if="showModal" class="fixed inset-0 bg-black/40 flex items-center justify-center z-50" @click.self="showModal = false">
      <div class="bg-white rounded-lg shadow-xl w-full max-w-md p-6">
        <h2 class="text-lg font-semibold mb-4">{{ editing ? '编辑标签' : '新建标签' }}</h2>
        <div class="space-y-3">
          <div>
            <label class="block text-sm font-medium mb-1">{{ t('tags.名称_eyrn') }}</label>
            <input v-model="form.name" class="input" :placeholder="t('tags.标签名称_dmuom2')" />
          </div>
          <div>
            <label class="block text-sm font-medium mb-1">Slug</label>
            <input v-model="form.slug" class="input" placeholder="tag-slug" />
          </div>
          <div>
            <label class="block text-sm font-medium mb-1">{{ t('tags.颜色_qo9i') }}</label>
            <div class="flex flex-wrap gap-2 mb-2">
              <button
                v-for="c in COLORS"
                :key="c"
                class="w-6 h-6 rounded-full border-2 transition-transform"
                :class="form.color === c ? 'border-ink-800 scale-110' : 'border-transparent hover:scale-105'"
                :style="{ backgroundColor: c }"
                @click="form.color = c"
              ></button>
            </div>
            <input v-model="form.color" type="color" class="input h-10 p-1 w-full" />
          </div>
        </div>
        <div class="flex justify-end gap-2 mt-6">
          <button class="btn-ghost" @click="showModal = false">{{ t('usersList.取消_ev02') }}</button>
          <button class="btn-primary" :disabled="saving" @click="save">{{ saving ? '保存中…' : '保存' }}</button>
        </div>
      </div>
    </div>
  </div>
</template>
