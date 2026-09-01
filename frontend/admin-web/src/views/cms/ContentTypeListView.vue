<script setup lang="ts">
import { useI18n } from 'vue-i18n'
const { t } = useI18n()
import { ref, onMounted } from 'vue'
import { api } from '@/lib/api'

interface FieldOption { id: number; value: string; label: string; color: string | null; sort: number }
interface FieldDef {
  id: number; content_type_id: number; field_key: string; label: string
  field_type: string; required: boolean; default_value: string | null
  options: Record<string, any> | null; validation: Record<string, any> | null
  group_id: number | null; sort: number; status: string
  field_options: FieldOption[]
}
interface FieldGroup { id: number; key: string; label: string; sort: number; icon: string | null }
interface ContentType {
  id: number; key: string; name: string; description: string | null; icon: string | null
  supports_category: boolean; supports_tags: boolean
  translatable?: boolean
  default_list_template: string | null; default_detail_template: string | null
  created_at: string; updated_at: string; deleted_at: string | null
  field_groups: FieldGroup[]; field_definitions: FieldDef[]
}

const contentTypes = ref<ContentType[]>([])
const loading = ref(true)
const error = ref('')
const showModal = ref(false)
const editing = ref<ContentType | null>(null)
const saving = ref(false)
const form = ref({ key: '', name: '', description: '', icon: '', supports_category: true, supports_tags: true, translatable: false })

async function load() {
  loading.value = true
  error.value = ''
  try {
    const { data } = await api.get('/api/v1/cms/content-types')
    contentTypes.value = data.items
  } catch (e: any) {
    error.value = e?.response?.data?.detail || 't("caseEdit.loadFailed")'
  } finally {
    loading.value = false
  }
}

function openCreate() {
  editing.value = null
  form.value = { key: '', name: '', description: '', icon: '', supports_category: true, supports_tags: true, translatable: false }
  showModal.value = true
}

function openEdit(ct: ContentType) {
  editing.value = ct
  form.value = {
    key: ct.key, name: ct.name, description: ct.description || '',
    icon: ct.icon || '', supports_category: ct.supports_category, supports_tags: ct.supports_tags,
    translatable: !!ct.translatable,
  }
  showModal.value = true
}

async function save() {
  saving.value = true
  try {
    if (editing.value) {
      await api.patch(`/api/v1/cms/content-types/${editing.value.id}`, {
        name: form.value.name, description: form.value.description || null,
        icon: form.value.icon || null, supports_category: form.value.supports_category,
        supports_tags: form.value.supports_tags, translatable: form.value.translatable,
      })
    } else {
      await api.post('/api/v1/cms/content-types', {
        key: form.value.key, name: form.value.name, description: form.value.description || null,
        icon: form.value.icon || null, supports_category: form.value.supports_category,
        supports_tags: form.value.supports_tags, translatable: form.value.translatable,
      })
    }
    showModal.value = false
    await load()
  } catch (e: any) {
    alert(e?.response?.data?.detail || 't("caseEdit.saveFailed")')
  } finally {
    saving.value = false
  }
}

async function remove(ct: ContentType) {
  if (!confirm(`确定删除内容类型「${ct.name}」？`)) return
  try {
    await api.delete(`/api/v1/cms/content-types/${ct.id}`)
    await load()
  } catch (e: any) {
    alert(e?.response?.data?.detail || 't("categories.删除失败")')
  }
}

onMounted(load)
</script>

<template>
  <div>
    <div class="flex items-center justify-between mb-6">
      <div>
        <h1 class="text-2xl font-semibold tracking-tight">{{ t('templatePreview.内容类型_ao6o90') }}</h1>
        <p class="text-ink-500">{{ t('contentTypeList.定义内容_ij3unb') }}</p>
      </div>
      <button class="btn-primary" @click="openCreate">{{ t('contentTypeList.text_y2rp5b') }}</button>
    </div>

    <div v-if="loading" class="card text-ink-500">{{ t('usersList.加载中_b0k5km') }}</div>
    <div v-else-if="error" class="card text-red-600">{{ error }}</div>
    <div v-else class="grid md:grid-cols-2 lg:grid-cols-3 gap-4">
      <div v-for="ct in contentTypes" :key="ct.id" class="card hover:shadow-md transition-shadow">
        <div class="flex items-start gap-3">
          <span class="text-2xl">{{ ct.icon || '📦' }}</span>
          <div class="flex-1 min-w-0">
            <h3 class="font-semibold truncate">{{ ct.name }}</h3>
            <code class="text-xs text-ink-400">{{ ct.key }}</code>
            <p v-if="ct.description" class="text-sm text-ink-600 mt-1 truncate">{{ ct.description }}</p>
            <div class="flex flex-wrap gap-1 mt-2">
              <span v-if="ct.supports_category" class="text-xs px-1.5 py-0.5 bg-blue-50 text-blue-600 rounded">{{ t('entryList.分类_emut') }}</span>
              <span v-if="ct.supports_tags" class="text-xs px-1.5 py-0.5 bg-green-50 text-green-600 rounded">{{ t('productsList.标签_idef') }}</span>
              <span v-if="ct.translatable" class="text-xs px-1.5 py-0.5 bg-purple-50 text-purple-600 rounded">🌐 多语言</span>
              <span class="text-xs px-1.5 py-0.5 bg-ink-50 text-ink-500 rounded">{{ ct.field_definitions?.length || 0 }} 字段</span>
              <span class="text-xs px-1.5 py-0.5 bg-ink-50 text-ink-500 rounded">{{ ct.field_groups?.length || 0 }} 分组</span>
            </div>
          </div>
        </div>
        <div class="mt-3 flex gap-2 border-t pt-3">
          <router-link :to="`/cms/content-types/${ct.id}/fields`" class="btn-ghost text-sm">{{ t('contentTypeList.字段管理_bz47yb') }}</router-link>
          <button class="btn-ghost text-sm" @click="openEdit(ct)">{{ t('usersList.编辑_mekb') }}</button>
          <button class="btn-ghost text-sm text-red-600" @click="remove(ct)">{{ t('usersList.删除_eslg') }}</button>
        </div>
      </div>
    </div>

    <!-- Modal -->
    <div v-if="showModal" class="fixed inset-0 bg-black/40 flex items-center justify-center z-50" @click.self="showModal = false">
      <div class="bg-white rounded-lg shadow-xl w-full max-w-md p-6">
        <h2 class="text-lg font-semibold mb-4">{{ editing ? '编辑内容类型' : '新建内容类型' }}</h2>
        <div class="space-y-3">
          <div v-if="!editing">
            <label class="block text-sm font-medium mb-1">Key</label>
            <input v-model="form.key" class="input" placeholder="product" :disabled="!!editing" />
          </div>
          <div>
            <label class="block text-sm font-medium mb-1">{{ t('tags.名称_eyrn') }}</label>
            <input v-model="form.name" class="input" :placeholder="t('dashboard.产品_dud6')" />
          </div>
          <div>
            <label class="block text-sm font-medium mb-1">{{ t('tasks.描述_hrlt') }}</label>
            <input v-model="form.description" class="input" :placeholder="t('fieldDefinitions.可选_f2ey')" />
          </div>
          <div>
            <label class="block text-sm font-medium mb-1">{{ t('fieldDefinitions.图标_fd8p') }}</label>
            <input v-model="form.icon" class="input" placeholder="📦" />
          </div>
          <div class="flex gap-4">
            <label class="flex items-center gap-2">
              <input type="checkbox" v-model="form.supports_category" />
              <span class="text-sm">{{ t('contentTypeList.支持分类_d6cdpj') }}</span>
            </label>
            <label class="flex items-center gap-2">
              <input type="checkbox" v-model="form.supports_tags" />
              <span class="text-sm">{{ t('contentTypeList.支持标签_d6g495') }}</span>
            </label>
            <label class="flex items-center gap-2">
              <input type="checkbox" v-model="form.translatable" />
              <span class="text-sm">🌐 多语言</span>
            </label>
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
