<script setup lang="ts">
import { useI18n } from 'vue-i18n'
const { t } = useI18n()
import { ref, onMounted } from 'vue'
import { api } from '@/lib/api'

interface Redirect { id: number; from_path: string; to_path: string; code: number; enabled: boolean }

const items = ref<Redirect[]>([])
const search = ref('')
const showModal = ref(false)
const editing = ref<Redirect | null>(null)
const form = ref({ from_path: '', to_path: '', code: 301, enabled: true })

async function load() {
  try {
    const { data } = await api.get('/api/v1/system/redirects', { params: search.value ? { search: search.value } : {} })
    items.value = data.items || []
  } catch (e: any) { alert(e?.response?.data?.detail || t("dashboard.loadFailed")) }
}
function openCreate() { editing.value = null; form.value = { from_path: '', to_path: '', code: 301, enabled: true }; showModal.value = true }
function openEdit(r: Redirect) {
  editing.value = r
  form.value = { from_path: r.from_path, to_path: r.to_path, code: r.code, enabled: r.enabled }
  showModal.value = true
}
async function save() {
  if (!form.value.from_path || !form.value.to_path) return alert(t("redirects.起止路径_14dywn"))
  try {
    if (editing.value) await api.patch(`/api/v1/system/redirects/${editing.value.id}`, form.value)
    else await api.post('/api/v1/system/redirects', form.value)
    showModal.value = false
    await load()
  } catch (e: any) { alert(e?.response?.data?.detail || t("aiMemory.saveFailed")) }
}
async function remove(r: Redirect) {
  if (!window.confirm(t("redirects.确认删除_138jsj"))) return
  await api.delete(`/api/v1/system/redirects/${r.id}`)
  await load()
}
onMounted(load)
</script>

<template>
  <div>
    <div class="flex items-center justify-between mb-6">
      <div class="flex items-center gap-2">
        <h1 class="text-2xl font-semibold tracking-tight">{{ t("redirects.text_s59308") }}</h1>
        <span class="text-sm text-ink-400">M3·P2 · 301/302</span>
      </div>
      <div class="flex gap-2">
        <input v-model="search" class="input w-56" :placeholder="t('redirects.搜索路径_1gn6cq')" @keyup.enter="load" />
        <button class="btn-primary" @click="openCreate">{{ t("redirects.新增重定_1i82bh") }}</button>
      </div>
    </div>

    <div class="card overflow-hidden">
      <table class="w-full text-sm">
        <thead>
          <tr class="text-left text-ink-400 border-b">
            <th class="p-3">{{ t("redirects.来源路径_dicrk0") }}</th><th class="p-3">{{ t("redirects.目标路径_ffxpu6") }}</th><th class="p-3">{{ t("redirects.状态码_h9uty") }}</th><th class="p-3">{{ t("redirects.enable") }}</th><th class="p-3 text-right">{{ t("redirects.actions") }}</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="r in items" :key="r.id" class="border-b last:border-0">
            <td class="p-3 font-mono text-xs">{{ r.from_path }}</td>
            <td class="p-3 font-mono text-xs text-blue-600">→ {{ r.to_path }}</td>
            <td class="p-3"><span class="text-xs px-1.5 py-0.5 bg-ink-50 rounded">{{ r.code }}</span></td>
            <td class="p-3"><span :class="r.enabled ? 'text-green-600' : 'text-ink-300'">{{ r.enabled ? $t('redirects.是_k6n') : $t('redirects.否_gme') }}</span></td>
            <td class="p-3 text-right space-x-2">
              <button class="btn-ghost text-sm" @click="openEdit(r)">{{ t("redirects.edit") }}</button>
              <button class="btn-ghost text-sm text-red-600" @click="remove(r)">{{ t("redirects.delete") }}</button>
            </td>
          </tr>
          <tr v-if="!items.length"><td colspan="5" class="p-6 text-center text-ink-400">{{ t("redirects.暂无重定_1n3q9k") }}</td></tr>
        </tbody>
      </table>
    </div>

    <div v-if="showModal" class="fixed inset-0 bg-black/40 flex items-center justify-center z-50" @click.self="showModal = false">
      <div class="bg-white rounded-lg shadow-xl w-full max-w-md p-6">
        <h2 class="text-lg font-semibold mb-4">{{ editing ? $t('redirects.编辑重定_ieem21') : $t('redirects.新增重定_1i82bh') }}</h2>
        <div class="space-y-3">
          <div>
            <label class="block text-sm font-medium mb-1">{{ t("redirects.来源路径_1ody88") }}</label>
            <input v-model="form.from_path" class="input" placeholder="/old-page" />
          </div>
          <div>
            <label class="block text-sm font-medium mb-1">{{ t("redirects.目标路径_bkfgxm") }}</label>
            <input v-model="form.to_path" class="input" placeholder="/new-page" />
          </div>
          <div>
            <label class="block text-sm font-medium mb-1">{{ t("redirects.状态码_h9uty") }}</label>
            <select v-model.number="form.code" class="input">
              <option :value="301">{{ t("redirects.text_nbczrc") }}</option>
              <option :value="302">{{ t("redirects.text_n7mjn8") }}</option>
            </select>
          </div>
          <label class="flex items-center gap-2">
            <input type="checkbox" v-model="form.enabled" /><span class="text-sm">{{ t("redirects.enable") }}</span>
          </label>
        </div>
        <div class="flex justify-end gap-2 mt-6">
          <button class="btn-ghost" @click="showModal = false">{{ t("redirects.cancel") }}</button>
          <button class="btn-primary" @click="save">{{ t("redirects.保存_e32z") }}</button>
        </div>
      </div>
    </div>
  </div>
</template>
