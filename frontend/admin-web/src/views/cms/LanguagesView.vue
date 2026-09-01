<script setup lang="ts">
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
    alert(e?.response?.data?.detail || '加载失败')
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
    alert(e?.response?.data?.detail || '保存失败')
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
        <h1 class="text-2xl font-semibold tracking-tight">🌐 语言管理</h1>
        <span class="text-sm text-ink-400">内容多语言 i18n（M1·P0）</span>
      </div>
      <button class="btn-primary" @click="openCreate">新增语言</button>
    </div>

    <div class="card overflow-hidden">
      <div v-if="loading" class="text-ink-500 p-6">加载中…</div>
      <table v-else class="w-full text-sm">
        <thead>
          <tr class="text-left text-ink-400 border-b">
            <th class="p-3">语言</th>
            <th class="p-3">代码</th>
            <th class="p-3">默认</th>
            <th class="p-3">启用</th>
            <th class="p-3">排序</th>
            <th class="p-3 text-right">操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="l in items" :key="l.code" class="border-b last:border-0">
            <td class="p-3 font-medium">{{ l.flag || '🌍' }} {{ l.name }}</td>
            <td class="p-3"><code class="text-ink-400">{{ l.code }}</code></td>
            <td class="p-3">
              <span v-if="l.is_default" class="text-xs px-1.5 py-0.5 bg-blue-50 text-blue-600 rounded">默认</span>
              <span v-else class="text-ink-300">—</span>
            </td>
            <td class="p-3">
              <span :class="l.enabled ? 'text-green-600' : 'text-ink-300'">{{ l.enabled ? '启用' : '停用' }}</span>
            </td>
            <td class="p-3 text-ink-400">{{ l.sort }}</td>
            <td class="p-3 text-right space-x-2">
              <button class="btn-ghost text-sm" @click="openEdit(l)">编辑</button>
              <button v-if="!l.is_default" class="btn-ghost text-sm text-red-600" @click="remove(l)">删除</button>
            </td>
          </tr>
          <tr v-if="!items.length">
            <td colspan="6" class="p-6 text-center text-ink-400">暂无语言，点击「新增语言」添加（示例：zh-CN / en-US）</td>
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
            <label class="block text-sm font-medium mb-1">代码</label>
            <input v-model="form.code" class="input" placeholder="如 en-US / ja-JP" />
          </div>
          <div>
            <label class="block text-sm font-medium mb-1">名称</label>
            <input v-model="form.name" class="input" placeholder="如 English / 日本語" />
          </div>
          <div>
            <label class="block text-sm font-medium mb-1">旗帜 emoji</label>
            <input v-model="form.flag" class="input" placeholder="🇺🇸" />
          </div>
          <div class="flex gap-4">
            <label class="flex items-center gap-2">
              <input type="checkbox" v-model="form.is_default" />
              <span class="text-sm">设为默认语言</span>
            </label>
            <label class="flex items-center gap-2">
              <input type="checkbox" v-model="form.enabled" />
              <span class="text-sm">启用</span>
            </label>
          </div>
          <div>
            <label class="block text-sm font-medium mb-1">排序</label>
            <input v-model.number="form.sort" type="number" class="input" />
          </div>
        </div>
        <div class="flex justify-end gap-2 mt-6">
          <button class="btn-ghost" @click="showModal = false">取消</button>
          <button class="btn-primary" @click="save">保存</button>
        </div>
      </div>
    </div>
  </div>
</template>
