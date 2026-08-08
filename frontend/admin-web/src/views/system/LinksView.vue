<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import RichTextEditor from '@/components/RichTextEditor.vue'
const { t } = useI18n()
import { ref, onMounted } from 'vue'
import { api } from '@/lib/api'

interface Link {
  id: number; url: string; title: string; description: string | null
  category: string; favicon: string | null
  is_favorite: boolean; click_count: number; creator_id: number
  created_at: string | null
}

const items = ref<Link[]>([])
const loading = ref(true)
const error = ref('')
const search = ref('')
const categoryFilter = ref('')
const total = ref(0)
const page = ref(1)
const pageSize = 20
const showEdit = ref(false)
const isNew = ref(true)
const saving = ref(false)
const form = ref({ id: 0, url: '', title: '', description: '' as string | null, category: 'general', is_favorite: false })

async function load() {
  loading.value = true
  error.value = ''
  try {
    const params = new URLSearchParams({ page: String(page.value), page_size: String(pageSize) })
    if (search.value) params.set('search', search.value)
    if (categoryFilter.value) params.set('category', categoryFilter.value)
    const { data } = await api.get(`/api/v1/links?${params}`)
    items.value = data.items
    total.value = data.total
  } catch (e: any) {
    error.value = e?.response?.data?.detail || '加载失败'
  } finally { loading.value = false }
}

function openNew() {
  isNew.value = true
  form.value = { id: 0, url: '', title: '', description: '', category: 'general', is_favorite: false }
  showEdit.value = true
}

function openEdit(item: Link) {
  isNew.value = false
  form.value = { ...item }
  showEdit.value = true
}

async function save() {
  saving.value = true
  try {
    if (isNew.value) {
      await api.post('/api/v1/links', form.value)
    } else {
      await api.patch(`/api/v1/links/${form.value.id}`, form.value)
    }
    showEdit.value = false
    await load()
  } catch (e: any) {
    alert(e?.response?.data?.detail || '保存失败')
  } finally { saving.value = false }
}

async function del(item: Link) {
  if (!confirm(`确定删除「${item.title}」？`)) return
  try {
    await api.delete(`/api/v1/links/${item.id}`)
    await load()
  } catch (e: any) {
    alert(e?.response?.data?.detail || '删除失败')
  }
}

async function toggleFav(item: Link) {
  try {
    await api.patch(`/api/v1/links/${item.id}`, { is_favorite: !item.is_favorite })
    await load()
  } catch { /* ignore */ }
}

const totalPages = Math.max(1, Math.ceil(total.value / pageSize))

const categoryLabel: Record<string, string> = { general: '通用', dev: '开发', design: '设计', docs: '文档', tool: '工具' }
const categoryClass: Record<string, string> = { general: 'bg-ink-100 text-ink-600', dev: 'bg-blue-50 text-blue-600', design: 'bg-purple-50 text-purple-600', docs: 'bg-green-50 text-green-600', tool: 'bg-amber-50 text-amber-600' }

onMounted(load)
</script>

<template>
  <div>
    <div class="flex items-center justify-between mb-6">
      <div>
        <h1 class="text-2xl font-semibold tracking-tight">链接收藏</h1>
        <p class="text-ink-500">书签与外部链接收集管理</p>
      </div>
      <button class="btn-primary" @click="openNew">添加链接</button>
    </div>

    <div class="card mb-4 flex flex-wrap gap-3 items-center">
      <input v-model="search" type="text" class="input w-full sm:w-60" placeholder="搜索标题/URL..." @keyup.enter="load" />
      <select v-model="categoryFilter" class="input w-full sm:w-32" @change="load">
        <option value="">全部分类</option>
        <option value="general">通用</option>
        <option value="dev">开发</option>
        <option value="design">设计</option>
        <option value="docs">文档</option>
        <option value="tool">工具</option>
      </select>
      <button class="btn-ghost" @click="load">搜索</button>
    </div>

    <div v-if="loading" class="card text-ink-500">加载中...</div>
    <div v-else-if="error" class="card text-red-600">{{ error }}</div>
    <div v-else class="card overflow-hidden p-0">
      <div class="overflow-x-auto"><table class="w-full text-sm">
        <thead class="bg-ink-50 border-b border-ink-200">
          <tr class="text-left text-ink-500">
            <th class="px-4 py-3 font-medium w-8"></th>
            <th class="px-4 py-3 font-medium">标题</th>
            <th class="px-4 py-3 font-medium">URL</th>
            <th class="px-4 py-3 font-medium">分类</th>
            <th class="px-4 py-3 font-medium">访问</th>
            <th class="px-4 py-3 font-medium">添加时间</th>
            <th class="px-4 py-3 font-medium text-right">操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-if="items.length === 0">
            <td colspan="7" class="px-4 py-12 text-center text-ink-400">暂无链接</td>
          </tr>
          <tr v-for="item in items" :key="item.id" class="border-b border-ink-100 last:border-0 hover:bg-ink-50">
            <td class="px-4 py-3">
              <button @click="toggleFav(item)" class="text-lg" :class="item.is_favorite ? 'text-amber-500' : 'text-ink-300 hover:text-amber-400'">
                {{ item.is_favorite ? '★' : '☆' }}
              </button>
            </td>
            <td class="px-4 py-3 font-medium">{{ item.title }}</td>
            <td class="px-4 py-3 text-ink-500 text-xs max-w-[200px] truncate">
              <a :href="item.url" target="_blank" class="hover:underline">{{ item.url }}</a>
            </td>
            <td class="px-4 py-3">
              <span class="text-xs px-1.5 py-0.5 rounded" :class="categoryClass[item.category]">{{ categoryLabel[item.category] || item.category }}</span>
            </td>
            <td class="px-4 py-3 text-ink-500">{{ item.click_count }}</td>
            <td class="px-4 py-3 text-ink-500 text-xs">{{ item.created_at?.slice(0, 10) }}</td>
            <td class="px-4 py-3 text-right space-x-2">
              <button class="text-sm text-ink-600 hover:text-ink-900" @click="openEdit(item)">编辑</button>
              <button class="text-sm text-red-600 hover:underline" @click="del(item)">删除</button>
            </td>
          </tr>
        </tbody>
      </table></div>
    </div>

    <!-- Edit Modal -->
    <div v-if="showEdit" class="fixed inset-0 z-50 flex items-center justify-center p-4 bg-ink-900/40" @click.self="showEdit = false">
      <div class="bg-white rounded-2xl w-full max-w-lg p-6 max-h-[90vh] overflow-y-auto">
        <h2 class="text-lg font-semibold mb-4">{{ isNew ? '添加链接' : '编辑链接' }}</h2>
        <form @submit.prevent="save" class="space-y-4">
          <div>
            <label class="block text-sm font-medium mb-1.5">URL</label>
            <input v-model="form.url" required class="input" placeholder="https://..." />
          </div>
          <div>
            <label class="block text-sm font-medium mb-1.5">标题</label>
            <input v-model="form.title" class="input" placeholder="可选，默认用 URL" />
          </div>
          <div>
            <label class="block text-sm font-medium mb-1.5">分类</label>
            <select v-model="form.category" class="input">
              <option value="general">通用</option>
              <option value="dev">开发</option>
              <option value="design">设计</option>
              <option value="docs">文档</option>
              <option value="tool">工具</option>
            </select>
          </div>
          <div>
            <label class="block text-sm font-medium mb-1.5">描述</label>
            <RichTextEditor v-model="form.description" />
          </div>
          <label class="flex items-center gap-2 text-sm">
            <input v-model="form.is_favorite" type="checkbox" class="rounded" /> 收藏
          </label>
          <div class="flex gap-3 pt-2">
            <button type="submit" :disabled="saving" class="btn-primary flex-1">{{ saving ? '保存中...' : '保存' }}</button>
            <button type="button" @click="showEdit = false" class="btn-ghost">取消</button>
          </div>
        </form>
      </div>
    </div>
  </div>
</template>
