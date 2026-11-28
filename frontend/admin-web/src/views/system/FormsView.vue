<script setup lang="ts">
import { useI18n } from 'vue-i18n'
const { t } = useI18n()
import { ref, onMounted } from 'vue'
import { api } from '@/lib/api'

interface FormItem { id: number; key: string; title: string; description: string | null; fields: any[]; enabled: boolean; submissions: number }

const items = ref<FormItem[]>([])
const showModal = ref(false)
const editing = ref<FormItem | null>(null)
const form = ref({ key: '', title: '', description: '', fields: '', enabled: true, success_message: '' })
const showSubs = ref(false)
const subs = ref<any[]>([])
const activeForm = ref<FormItem | null>(null)

async function load() {
  try {
    const { data } = await api.get('/api/v1/forms')
    items.value = data.items || []
  } catch (e: any) { alert(e?.response?.data?.detail || t("dashboard.loadFailed")) }
}
function openCreate() { editing.value = null; form.value = { key: '', title: '', description: '', fields: '', enabled: true, success_message: '' }; showModal.value = true }
function openEdit(f: FormItem) {
  editing.value = f
  form.value = {
    key: f.key, title: f.title, description: f.description || '',
    fields: JSON.stringify(f.fields || [], null, 2), enabled: f.enabled,
    success_message: (f as any).success_message || '',
  }
  showModal.value = true
}
async function save() {
  let fields: any[] = []
  if (form.value.fields.trim()) {
    try { fields = JSON.parse(form.value.fields) } catch { return alert('字段 JSON 格式错误') }
  }
  try {
    const payload = { key: form.value.key, title: form.value.title, description: form.value.description || null, fields, enabled: form.value.enabled, success_message: form.value.success_message || null }
    if (editing.value) await api.patch(`/api/v1/forms/${editing.value.id}`, payload)
    else await api.post('/api/v1/forms', payload)
    showModal.value = false
    await load()
  } catch (e: any) { alert(e?.response?.data?.detail || t("aiMemory.saveFailed")) }
}
async function remove(f: FormItem) {
  if (!window.confirm(t("forms.确认删除_dp1yrm"))) return
  await api.delete(`/api/v1/forms/${f.id}`)
  await load()
}
async function openSubmissions(f: FormItem) {
  activeForm.value = f
  const { data } = await api.get(`/api/v1/forms/${f.id}/submissions`)
  subs.value = data.items || []
  showSubs.value = true
}
function downloadCsv(f: FormItem) {
  window.open(`/api/v1/forms/${f.id}/submissions/export`, '_blank')
}
onMounted(load)
</script>

<template>
  <div>
    <div class="flex items-center justify-between mb-6">
      <div class="flex items-center gap-2">
        <h1 class="text-2xl font-semibold tracking-tight">{{ t("forms.text_1340ly") }}</h1>
        <span class="text-sm text-ink-400">M4·P3</span>
      </div>
      <button class="btn-primary" @click="openCreate">{{ t("forms.新增表单_d7d07v") }}</button>
    </div>

    <div class="card overflow-hidden">
      <table class="w-full text-sm">
        <thead>
          <tr class="text-left text-ink-400 border-b">
            <th class="p-3">{{ t("forms.表单_nnql") }}</th><th class="p-3">Key</th><th class="p-3">{{ t("forms.提交数_f08po") }}</th><th class="p-3">{{ t("forms.status") }}</th><th class="p-3 text-right">{{ t("forms.actions") }}</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="f in items" :key="f.id" class="border-b last:border-0">
            <td class="p-3 font-medium">{{ f.title }}</td>
            <td class="p-3"><code class="text-xs text-ink-400">{{ f.key }}</code></td>
            <td class="p-3">{{ f.submissions }}</td>
            <td class="p-3"><span :class="f.enabled ? 'text-green-600' : 'text-ink-300'">{{ f.enabled ? '启用' : '停用' }}</span></td>
            <td class="p-3 text-right space-x-2 whitespace-nowrap">
              <button class="btn-ghost text-sm" @click="openSubmissions(f)">{{ t("forms.提交记录_cxej5l") }}</button>
              <button class="btn-ghost text-sm" @click="downloadCsv(f)">{{ t("forms.export") }}</button>
              <button class="btn-ghost text-sm" @click="openEdit(f)">{{ t("forms.edit") }}</button>
              <button class="btn-ghost text-sm text-red-600" @click="remove(f)">{{ t("forms.delete") }}</button>
            </td>
          </tr>
          <tr v-if="!items.length"><td colspan="5" class="p-6 text-center text-ink-400">{{ t("forms.暂无表单_dd105n") }}</td></tr>
        </tbody>
      </table>
    </div>

    <!-- 编辑弹窗 -->
    <div v-if="showModal" class="fixed inset-0 bg-black/40 flex items-center justify-center z-50" @click.self="showModal = false">
      <div class="bg-white rounded-lg shadow-xl w-full max-w-lg p-6">
        <h2 class="text-lg font-semibold mb-4">{{ editing ? '编辑表单' : '新增表单' }}</h2>
        <div class="space-y-3">
          <div v-if="!editing">
            <label class="block text-sm font-medium mb-1">Key</label>
            <input v-model="form.key" class="input" placeholder="contact" />
          </div>
          <div>
            <label class="block text-sm font-medium mb-1">{{ t("forms.title") }}</label>
            <input v-model="form.title" class="input" />
          </div>
          <div>
            <label class="block text-sm font-medium mb-1">{{ t("forms.description") }}</label>
            <input v-model="form.description" class="input" />
          </div>
          <div>
            <label class="block text-sm font-medium mb-1">{{ t("forms.字段定义_11xni8") }}</label>
            <textarea v-model="form.fields" rows="6" class="input font-mono text-xs" placeholder='[{"key":"name","label":"姓名","type":"text","required":true}]' />
          </div>
          <div>
            <label class="block text-sm font-medium mb-1">{{ t("forms.成功提示_cputkp") }}</label>
            <input v-model="form.success_message" class="input" :placeholder="t('forms.提交成功_cx7dr7')" />
          </div>
          <label class="flex items-center gap-2">
            <input type="checkbox" v-model="form.enabled" /><span class="text-sm">{{ t("forms.enable") }}</span>
          </label>
        </div>
        <div class="flex justify-end gap-2 mt-6">
          <button class="btn-ghost" @click="showModal = false">{{ t("forms.cancel") }}</button>
          <button class="btn-primary" @click="save">{{ t("forms.保存_e32z") }}</button>
        </div>
      </div>
    </div>

    <!-- 提交记录抽屉 -->
    <div v-if="showSubs" class="fixed inset-0 bg-black/40 z-50 flex justify-end" @click.self="showSubs = false">
      <div class="bg-white h-full w-full max-w-lg overflow-auto p-6">
        <div class="flex items-center justify-between mb-4">
          <h2 class="text-lg font-semibold">提交记录 · {{ activeForm?.title }}</h2>
          <button @click="showSubs = false" class="text-ink-400 hover:text-ink-600">✕</button>
        </div>
        <div v-if="!subs.length" class="text-ink-400 text-sm">{{ t("forms.暂无提交_dcur5e") }}</div>
        <div v-for="s in subs" :key="s.id" class="border rounded p-3 mb-3 text-sm">
          <div class="text-xs text-ink-400 mb-1">#{{ s.id }} · {{ s.created_at ? new Date(s.created_at).toLocaleString() : '' }}</div>
          <pre class="whitespace-pre-wrap bg-ink-50 rounded p-2 text-xs">{{ JSON.stringify(s.data, null, 2) }}</pre>
        </div>
      </div>
    </div>
  </div>
</template>
