<script setup lang="ts">
import { useI18n } from 'vue-i18n'
const { t } = useI18n()
import { ref, onMounted, computed } from 'vue'
import { useRoute } from 'vue-router'
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
  id: number; key: string; name: string; icon: string | null
  field_groups: FieldGroup[]; field_definitions: FieldDef[]
}

const FIELD_TYPES = [
  'text', 'longtext', 'richtext', 'markdown', 'number', 'boolean',
  'date', 'datetime', 'url', 'email', 'phone', 'image', 'images',
  'file', 'files', 'select', 'multiselect', 'color', 'json',
  'repeater', 'relation',
]
const FIELD_TYPE_LABELS: Record<string, string> = {
  text: 't("fieldDefinitions.单行文本")', longtext: 't("fieldDefinitions.多行文本")', richtext: 't("fieldDefinitions.富文本")', markdown: 'Markdown',
  number: 't("fieldDefinitions.数字")', boolean: 't("fieldDefinitions.布尔")', date: 't("fieldDefinitions.date")', datetime: 't("fieldDefinitions.日期时间")',
  url: 'URL', email: 'Email', phone: 't("fieldDefinitions.电话")', image: 't("fieldDefinitions.单图")', images: 't("fieldDefinitions.多图")',
  file: 't("fieldDefinitions.单文件")', files: 't("fieldDefinitions.多文件")', select: 't("fieldDefinitions.单选")', multiselect: 't("fieldDefinitions.多选")',
  color: 't("tags.颜色_qo9i")', json: 'JSON', repeater: 't("fieldDefinitions.重复子项")', relation: 't("fieldDefinitions.关联")',
}
const NEEDS_OPTIONS = new Set(['select', 'multiselect'])

const route = useRoute()
const ctId = computed(() => Number(route.params.id))

const ct = ref<ContentType | null>(null)
const loading = ref(true)
const error = ref('')
const showFieldModal = ref(false)
const showGroupModal = ref(false)
const saving = ref(false)
const editingField = ref<FieldDef | null>(null)
const editingGroup = ref<FieldGroup | null>(null)
const activeGroup = ref<string>('all')

const fieldForm = ref({
  field_key: '', label: '', field_type: 'text', required: false,
  default_value: '', group_id: null as number | null, sort: 0, status: 'active',
  newOptions: [] as { value: string; label: string; color: string }[],
})
const groupForm = ref({ key: '', label: '', sort: 0, icon: '' })

const filteredFields = computed(() => {
  if (!ct.value) return []
  if (activeGroup.value === 'all') return ct.value.field_definitions
  if (activeGroup.value === 'ungrouped') return ct.value.field_definitions.filter(f => !f.group_id)
  return ct.value.field_definitions.filter(f => String(f.group_id) === activeGroup.value)
})

async function load() {
  loading.value = true
  error.value = ''
  try {
    const { data } = await api.get(`/api/v1/cms/content-types/${ctId.value}`)
    ct.value = data
  } catch (e: any) {
    error.value = e?.response?.data?.detail || 't("caseEdit.loadFailed")'
  } finally {
    loading.value = false
  }
}

function openCreateField() {
  editingField.value = null
  fieldForm.value = {
    field_key: '', label: '', field_type: 'text', required: false,
    default_value: '', group_id: null, sort: ct.value?.field_definitions?.length || 0,
    status: 'active', newOptions: [],
  }
  showFieldModal.value = true
}

function openEditField(fd: FieldDef) {
  editingField.value = fd
  fieldForm.value = {
    field_key: fd.field_key, label: fd.label, field_type: fd.field_type,
    required: fd.required, default_value: fd.default_value || '',
    group_id: fd.group_id, sort: fd.sort, status: fd.status,
    newOptions: fd.field_options?.map(o => ({ value: o.value, label: o.label, color: o.color || '' })) || [],
  }
  showFieldModal.value = true
}

function openCreateGroup() {
  editingGroup.value = null
  groupForm.value = { key: '', label: '', sort: ct.value?.field_groups?.length || 0, icon: '' }
  showGroupModal.value = true
}

function openEditGroup(fg: FieldGroup) {
  editingGroup.value = fg
  groupForm.value = { key: fg.key, label: fg.label, sort: fg.sort, icon: fg.icon || '' }
  showGroupModal.value = true
}

function addOption() {
  fieldForm.value.newOptions.push({ value: '', label: '', color: '' })
}

function removeOption(idx: number) {
  fieldForm.value.newOptions.splice(idx, 1)
}

async function saveField() {
  saving.value = true
  try {
    const payload: any = {
      field_key: fieldForm.value.field_key,
      label: fieldForm.value.label,
      field_type: fieldForm.value.field_type,
      required: fieldForm.value.required,
      default_value: fieldForm.value.default_value || null,
      group_id: fieldForm.value.group_id,
      sort: fieldForm.value.sort,
      status: fieldForm.value.status,
    }
    if (editingField.value) {
      await api.patch(`/api/v1/cms/field-definitions/${editingField.value.id}`, payload)
    } else {
      await api.post(`/api/v1/cms/content-types/${ctId.value}/field-definitions`, payload)
    }
    showFieldModal.value = false
    await load()
  } catch (e: any) {
    alert(e?.response?.data?.detail || 't("caseEdit.saveFailed")')
  } finally {
    saving.value = false
  }
}

async function deleteField(fd: FieldDef) {
  if (!confirm(`确定删除字段「${fd.label}」？`)) return
  try {
    await api.delete(`/api/v1/cms/field-definitions/${fd.id}`)
    await load()
  } catch (e: any) {
    alert(e?.response?.data?.detail || 't("categories.删除失败")')
  }
}

async function saveGroup() {
  saving.value = true
  try {
    const payload = {
      key: groupForm.value.key, label: groupForm.value.label,
      sort: groupForm.value.sort, icon: groupForm.value.icon || null,
    }
    if (editingGroup.value) {
      await api.patch(`/api/v1/cms/content-types/${ctId.value}/field-groups/${editingGroup.value.id}`, payload)
    } else {
      await api.post(`/api/v1/cms/content-types/${ctId.value}/field-groups`, payload)
    }
    showGroupModal.value = false
    await load()
  } catch (e: any) {
    alert(e?.response?.data?.detail || 't("caseEdit.saveFailed")')
  } finally {
    saving.value = false
  }
}

async function deleteGroup(fg: FieldGroup) {
  if (!confirm(`确定删除分组「${fg.label}」？字段不会被删除，但会变成未分组。`)) return
  try {
    await api.delete(`/api/v1/cms/content-types/${ctId.value}/field-groups/${fg.id}`)
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
        <div class="flex items-center gap-2 mb-1">
          <router-link to="/cms/content-types" class="text-ink-400 hover:text-ink-600 text-sm">{{ t('fieldDefinitions.text_1aztzu') }}</router-link>
        </div>
        <h1 class="text-2xl font-semibold tracking-tight">
          {{ ct?.icon || '📦' }} {{ ct?.name || '...' }} — 字段管理
        </h1>
        <p class="text-ink-500 text-sm">key: <code>{{ ct?.key }}</code></p>
      </div>
      <div class="flex gap-2">
        <button class="btn-ghost" @click="openCreateGroup">{{ t('fieldDefinitions.text_16rgz') }}</button>
        <button class="btn-primary" @click="openCreateField">{{ t('fieldDefinitions.text_188r7') }}</button>
      </div>
    </div>

    <div v-if="loading" class="card text-ink-500">{{ t('usersList.加载中_b0k5km') }}</div>
    <div v-else-if="error" class="card text-red-600">{{ error }}</div>
    <div v-else>
      <!-- Group Tabs -->
      <div class="flex gap-1 mb-4 border-b pb-2">
        <button
          class="px-3 py-1 text-sm rounded-t"
          :class="activeGroup === 'all' ? 'bg-ink-900 text-white' : 'hover:bg-ink-50'"
          @click="activeGroup = 'all'"
        >{{ t('media.全部_en40') }}</button>
        <button
          v-for="fg in ct?.field_groups || []"
          :key="fg.id"
          class="px-3 py-1 text-sm rounded-t flex items-center gap-1"
          :class="String(fg.id) === activeGroup ? 'bg-ink-900 text-white' : 'hover:bg-ink-50'"
          @click="activeGroup = String(fg.id)"
        >
          {{ fg.label }}
          <span class="text-xs opacity-60" @click.stop="openEditGroup(fg)">✏</span>
          <span class="text-xs opacity-60" @click.stop="deleteGroup(fg)">✕</span>
        </button>
        <button
          class="px-3 py-1 text-sm rounded-t"
          :class="activeGroup === 'ungrouped' ? 'bg-ink-900 text-white' : 'hover:bg-ink-50'"
          @click="activeGroup = 'ungrouped'"
        >{{ t('fieldDefinitions.未分组_fimnc') }}</button>
      </div>

      <!-- Field List -->
      <div class="space-y-2">
        <div v-if="filteredFields.length === 0" class="card text-ink-400 text-center py-8">
          {{ t('fieldDefinitions.暂无字段点击右上角字段添加') }}
        </div>
        <div
          v-for="fd in filteredFields"
          :key="fd.id"
          class="card flex items-center gap-4 py-3"
        >
          <div class="flex-1 min-w-0">
            <div class="flex items-center gap-2">
              <span class="font-medium">{{ fd.label }}</span>
              <code class="text-xs text-ink-400">{{ fd.field_key }}</code>
              <span class="text-xs px-1.5 py-0.5 bg-ink-100 rounded">{{ FIELD_TYPE_LABELS[fd.field_type] || fd.field_type }}</span>
              <span v-if="fd.required" class="text-xs px-1.5 py-0.5 bg-red-50 text-red-600 rounded">{{ t('fieldDefinitions.必填_grwm') }}</span>
              <span v-if="fd.status === 'hidden'" class="text-xs px-1.5 py-0.5 bg-yellow-50 text-yellow-600 rounded">{{ t('fieldDefinitions.隐藏_qce7') }}</span>
            </div>
            <div v-if="fd.field_options?.length" class="flex flex-wrap gap-1 mt-1">
              <span
                v-for="opt in fd.field_options"
                :key="opt.id"
                class="text-xs px-1.5 py-0.5 rounded border"
                :style="opt.color ? `border-color: ${opt.color}; color: ${opt.color}` : ''"
              >{{ opt.label }}</span>
            </div>
          </div>
          <div class="flex gap-1">
            <button class="btn-ghost text-sm" @click="openEditField(fd)">{{ t('usersList.编辑_mekb') }}</button>
            <button class="btn-ghost text-sm text-red-600" @click="deleteField(fd)">{{ t('usersList.删除_eslg') }}</button>
          </div>
        </div>
      </div>
    </div>

    <!-- Field Modal -->
    <div v-if="showFieldModal" class="fixed inset-0 bg-black/40 flex items-center justify-center z-50" @click.self="showFieldModal = false">
      <div class="bg-white rounded-lg shadow-xl w-full max-w-lg p-6 max-h-[90vh] overflow-y-auto">
        <h2 class="text-lg font-semibold mb-4">{{ editingField ? '编辑字段' : '新建字段' }}</h2>
        <div class="space-y-3">
          <div class="grid grid-cols-2 gap-3">
            <div>
              <label class="block text-sm font-medium mb-1">{{ t('fieldDefinitions.字段_1ket27') }}</label>
              <input v-model="fieldForm.field_key" class="input" placeholder="price" :disabled="!!editingField" />
            </div>
            <div>
              <label class="block text-sm font-medium mb-1">{{ t('fieldDefinitions.显示标签_deic5v') }}</label>
              <input v-model="fieldForm.label" class="input" :placeholder="t('fieldDefinitions.价格_e04l')" />
            </div>
          </div>
          <div class="grid grid-cols-2 gap-3">
            <div>
              <label class="block text-sm font-medium mb-1">{{ t('fieldDefinitions.字段类型_bz47ji') }}</label>
              <select v-model="fieldForm.field_type" class="input">
                <option v-for="ft in FIELD_TYPES" :key="ft" :value="ft">{{ FIELD_TYPE_LABELS[ft] || ft }}</option>
              </select>
            </div>
            <div>
              <label class="block text-sm font-medium mb-1">{{ t('fieldDefinitions.所属分组_cs1v6k') }}</label>
              <select v-model="fieldForm.group_id" class="input">
                <option :value="null">{{ t('fieldDefinitions.text_1qwx61') }}</option>
                <option v-for="fg in ct?.field_groups || []" :key="fg.id" :value="fg.id">{{ fg.label }}</option>
              </select>
            </div>
          </div>
          <div class="grid grid-cols-3 gap-3">
            <div>
              <label class="block text-sm font-medium mb-1">{{ t('fieldDefinitions.默认值_nxrsg') }}</label>
              <input v-model="fieldForm.default_value" class="input" :placeholder="t('fieldDefinitions.可选_f2ey')" />
            </div>
            <div>
              <label class="block text-sm font-medium mb-1">{{ t('productEdit.排序_hge5') }}</label>
              <input v-model.number="fieldForm.sort" type="number" class="input" />
            </div>
            <div>
              <label class="block text-sm font-medium mb-1">{{ t('usersList.状态_k1e3') }}</label>
              <select v-model="fieldForm.status" class="input">
                <option value="active">{{ t('tasks.启用_eymx') }}</option>
                <option value="hidden">{{ t('fieldDefinitions.隐藏_qce7') }}</option>
              </select>
            </div>
          </div>
          <label class="flex items-center gap-2">
            <input type="checkbox" v-model="fieldForm.required" />
            <span class="text-sm">{{ t('fieldDefinitions.必填_grwm') }}</span>
          </label>
          <!-- Options for select/multiselect -->
          <div v-if="NEEDS_OPTIONS.has(fieldForm.field_type)">
            <label class="block text-sm font-medium mb-1">{{ t('fieldDefinitions.选项_pc40') }}</label>
            <div v-for="(opt, idx) in fieldForm.newOptions" :key="idx" class="flex gap-2 mb-1">
              <input v-model="opt.value" class="input flex-1" :placeholder="t('fieldDefinitions.值_fuk')" />
              <input v-model="opt.label" class="input flex-1" :placeholder="t('productsList.标签_idef')" />
              <input v-model="opt.color" class="input w-20" :placeholder="t('tags.颜色_qo9i')" />
              <button class="text-red-400 hover:text-red-600" @click="removeOption(idx)">✕</button>
            </div>
            <button class="btn-ghost text-sm" @click="addOption">{{ t('fieldDefinitions.text_z2pu7e') }}</button>
          </div>
        </div>
        <div class="flex justify-end gap-2 mt-6">
          <button class="btn-ghost" @click="showFieldModal = false">{{ t('usersList.取消_ev02') }}</button>
          <button class="btn-primary" :disabled="saving" @click="saveField">{{ saving ? '保存中…' : '保存' }}</button>
        </div>
      </div>
    </div>

    <!-- Group Modal -->
    <div v-if="showGroupModal" class="fixed inset-0 bg-black/40 flex items-center justify-center z-50" @click.self="showGroupModal = false">
      <div class="bg-white rounded-lg shadow-xl w-full max-w-sm p-6">
        <h2 class="text-lg font-semibold mb-4">{{ editingGroup ? '编辑分组' : '新建分组' }}</h2>
        <div class="space-y-3">
          <div>
            <label class="block text-sm font-medium mb-1">Key</label>
            <input v-model="groupForm.key" class="input" placeholder="basic" :disabled="!!editingGroup" />
          </div>
          <div>
            <label class="block text-sm font-medium mb-1">{{ t('productsList.标签_idef') }}</label>
            <input v-model="groupForm.label" class="input" :placeholder="t('productEdit.基础信息_blh1h0')" />
          </div>
          <div class="grid grid-cols-2 gap-3">
            <div>
              <label class="block text-sm font-medium mb-1">{{ t('productEdit.排序_hge5') }}</label>
              <input v-model.number="groupForm.sort" type="number" class="input" />
            </div>
            <div>
              <label class="block text-sm font-medium mb-1">{{ t('fieldDefinitions.图标_fd8p') }}</label>
              <input v-model="groupForm.icon" class="input" placeholder="📋" />
            </div>
          </div>
        </div>
        <div class="flex justify-end gap-2 mt-6">
          <button class="btn-ghost" @click="showGroupModal = false">{{ t('usersList.取消_ev02') }}</button>
          <button class="btn-primary" :disabled="saving" @click="saveGroup">{{ saving ? '保存中…' : '保存' }}</button>
        </div>
      </div>
    </div>
  </div>
</template>
