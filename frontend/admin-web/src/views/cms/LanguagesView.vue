<script setup lang="ts">
import { useI18n } from 'vue-i18n'
const { t } = useI18n()
import { ref, onMounted } from 'vue'
import { api } from '@/lib/api'

interface Language {
  id: number; code: string; name: string; flag: string | null
  is_default: boolean; enabled: boolean; sort: number
}

const items = ref<Language[]>([])
const loading = ref(false)
const showModal = ref(false)
const editing = ref<Language | null>(null)
const form = ref({ code: '', name: '', flag: '', is_default: false, enabled: true, sort: 0 })

async function load() {
  loading.value = true
  try {
    const { data } = await api.get('/api/v1/cms/languages')
    items.value = data.items || []
  } catch (e: any) {
    alert(e?.response?.data?.detail || t("dashboard.loadFailed"))
  } finally {
    loading.value = false
  }
}

function openCreate() {
  editing.value = null
  form.value = { code: '', name: '', flag: '', is_default: false, enabled: true, sort: 0 }
  showModal.value = true
}

function openEdit(l: Language) {
  editing.value = l
  form.value = {
    code: l.code, name: l.name, flag: l.flag || '',
    is_default: l.is_default, enabled: l.enabled, sort: l.sort,
  }
  showModal.value = true
}

async function save() {
  try {
    if (editing.value) {
      await api.patch(`/api/v1/cms/languages/${editing.value.code}`, {
        name: form.value.name, flag: form.value.flag || null,
        is_default: form.value.is_default, enabled: form.value.enabled, sort: form.value.sort,
      })
    } else {
      await api.post('/api/v1/cms/languages', {
        code: form.value.code, name: form.value.name, flag: form.value.flag || null,
        is_default: form.value.is_default, enabled: form.value.enabled, sort: form.value.sort,
      })
    }
    showModal.value = false
    await load()
  } catch (e: any) {
    alert(e?.response?.data?.detail || t("aiMemory.saveFailed"))
  }
}

async function remove(l: Language) {
  if (!window.confirm(`确认删除语言 ${l.code}？相关翻译将一并清理。`)) return
  await api.delete(`/api/v1/cms/languages/${l.code}`)
  await load()
}

onMounted(load)
</script>

<template>
  <div>
    <div class="flex items-center justify-between mb-6">
      <div class="flex items-center gap-2">
        <h1 class="text-2xl font-semibold tracking-tight">{{ t("languages.text_13sgpm") }}</h1>
        <span class="text-sm text-ink-400">{{ t("languages.内容多语_vu37kp") }}</span>
      </div>
      <button class="btn-primary" @click="openCreate">{{ t("languages.新增语言_d7dwkh") }}</button>
    </div>

    <div class="card overflow-hidden">
      <div v-if="loading" class="text-ink-500 p-6">{{ t("apiKeys.加载中_b0k5km") }}</div>
      <table v-else class="w-full text-sm">
        <thead>
          <tr class="text-left text-ink-400 border-b">
            <th class="p-3">{{ t("languages.语言_ok37") }}</th>
            <th class="p-3">{{ t("languages.代码_e2ri") }}</th>
            <th class="p-3">{{ t("languages.默认_rs98") }}</th>
            <th class="p-3">{{ t("languages.enable") }}</th>
            <th class="p-3">{{ t("languages.排序_hge5") }}</th>
            <th class="p-3 text-right">{{ t("languages.actions") }}</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="l in items" :key="l.code" class="border-b last:border-0">
            <td class="p-3 font-medium">{{ l.flag || '🌍' }} {{ l.name }}</td>
            <td class="p-3"><code class="text-ink-400">{{ l.code }}</code></td>
            <td class="p-3">
              <span v-if="l.is_default" class="text-xs px-1.5 py-0.5 bg-blue-50 text-blue-600 rounded">{{ t("languages.默认_rs98") }}</span>
              <span v-else class="text-ink-300">—</span>
            </td>
            <td class="p-3">
              <span :class="l.enabled ? 'text-green-600' : 'text-ink-300'">{{ l.enabled ? '启用' : '停用' }}</span>
            </td>
            <td class="p-3 text-ink-400">{{ l.sort }}</td>
            <td class="p-3 text-right space-x-2">
              <button class="btn-ghost text-sm" @click="openEdit(l)">{{ t("languages.edit") }}</button>
              <button v-if="!l.is_default" class="btn-ghost text-sm text-red-600" @click="remove(l)">{{ t("languages.delete") }}</button>
            </td>
          </tr>
          <tr v-if="!items.length">
            <td colspan="6" class="p-6 text-center text-ink-400">{{ t("languages.暂无语言_98twxd") }}</td>
          </tr>
        </tbody>
      </table>
    </div>

    <!-- Modal -->
    <div v-if="showModal" class="fixed inset-0 bg-black/40 flex items-center justify-center z-50" @click.self="showModal = false">
      <div class="bg-white rounded-lg shadow-xl w-full max-w-md p-6">
        <h2 class="text-lg font-semibold mb-4">{{ editing ? '编辑语言' : '新增语言' }}</h2>
        <div class="space-y-3">
          <div v-if="!editing">
            <label class="block text-sm font-medium mb-1">{{ t("languages.代码_e2ri") }}</label>
            <input v-model="form.code" class="input" :placeholder="t('languages.如_1nmqez')" />
          </div>
          <div>
            <label class="block text-sm font-medium mb-1">{{ t("languages.name") }}</label>
            <input v-model="form.name" class="input" :placeholder="t('languages.如_1rw6yw')" />
          </div>
          <div>
            <label class="block text-sm font-medium mb-1">{{ t("languages.旗帜_19jcdq") }}</label>
            <input v-model="form.flag" class="input" placeholder="🇺🇸" />
          </div>
          <div class="flex gap-4">
            <label class="flex items-center gap-2">
              <input type="checkbox" v-model="form.is_default" />
              <span class="text-sm">{{ t("languages.设为默认_4102bf") }}</span>
            </label>
            <label class="flex items-center gap-2">
              <input type="checkbox" v-model="form.enabled" />
              <span class="text-sm">{{ t("languages.enable") }}</span>
            </label>
          </div>
          <div>
            <label class="block text-sm font-medium mb-1">{{ t("languages.排序_hge5") }}</label>
            <input v-model.number="form.sort" type="number" class="input" />
          </div>
        </div>
        <div class="flex justify-end gap-2 mt-6">
          <button class="btn-ghost" @click="showModal = false">{{ t("languages.cancel") }}</button>
          <button class="btn-primary" @click="save">{{ t("languages.保存_e32z") }}</button>
        </div>
      </div>
    </div>
  </div>
</template>
