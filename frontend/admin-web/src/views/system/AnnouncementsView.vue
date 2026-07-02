<script setup lang="ts">
import { useI18n } from 'vue-i18n'
const { t } = useI18n()
import { ref, onMounted } from 'vue'
import { api } from '@/lib/api'

interface Announcement {
  id: number; title: string; summary: string | null; content: string
  category: string; priority: string
  is_pinned: boolean; is_published: boolean
  publish_at: string | null; expire_at: string | null
  view_count: number; author_id: number | null
  created_at: string | null
}

const items = ref<Announcement[]>([])
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
const form = ref({ id: 0, title: '', content: '', summary: '' as string | null, category: 'general', priority: 'normal', is_pinned: false, is_published: false })

async function load() {
  loading.value = true
  error.value = ''
  try {
    const params = new URLSearchParams({ page: String(page.value), page_size: String(pageSize) })
    if (search.value) params.set('search', search.value)
    if (categoryFilter.value) params.set('category', categoryFilter.value)
    const { data } = await api.get(`/api/v1/announcements?${params}`)
    items.value = data.items
    total.value = data.total
  } catch (e: any) {
    error.value = e?.response?.data?.detail || '加载失败'
  } finally { loading.value = false }
}

function openNew() {
  isNew.value = true
  form.value = { id: 0, title: '', content: '', summary: null, category: 'general', priority: 'normal', is_pinned: false, is_published: false }
  showEdit.value = true
}

function openEdit(item: Announcement) {
  isNew.value = false
  form.value = { ...item }
  showEdit.value = true
}

async function save() {
  saving.value = true
  try {
    if (isNew.value) {
      await api.post('/api/v1/announcements', form.value)
    } else {
      await api.patch(`/api/v1/announcements/${form.value.id}`, form.value)
    }
    showEdit.value = false
    await load()
  } catch (e: any) {
    alert(e?.response?.data?.detail || '保存失败')
  } finally { saving.value = false }
}

async function del(item: Announcement) {
  if (!confirm(`确定删除「${item.title}」？`)) return
  try {
    await api.delete(`/api/v1/announcements/${item.id}`)
    await load()
  } catch (e: any) {
    alert(e?.response?.data?.detail || '删除失败')
  }
}

const totalPages = Math.max(1, Math.ceil(total.value / pageSize))

const priorityLabel: Record<string, string> = { low: '低', normal: '普通', high: '高', urgent: '紧急' }
const priorityClass: Record<string, string> = { low: 'bg-ink-100 text-ink-600', normal: 'bg-blue-50 text-blue-600', high: 'bg-amber-50 text-amber-600', urgent: 'bg-red-50 text-red-600' }
const categoryLabel: Record<string, string> = { general: '通用', system: '系统', urgent: '紧急' }

onMounted(load)
</script>

<template>
  <div>
    <div class="flex items-center justify-between mb-6">
      <div>
        <h1 class="text-2xl font-semibold tracking-tight">公告管理</h1>
        <p class="text-ink-500">发布和管理企业内部公告</p>
      </div>
      <button class="btn-primary" @click="openNew">新建公告</button>
    </div>

    <div class="card mb-4 flex flex-wrap gap-3 items-center">
      <input v-model="search" type="text" class="input w-60" placeholder="搜索标题/内容..." @keyup.enter="load" />
      <select v-model="categoryFilter" class="input w-32" @change="load">
        <option value="">全部分类</option>
        <option value="general">通用</option>
        <option value="system">系统</option>
        <option value="urgent">紧急</option>
      </select>
      <button class="btn-ghost" @click="load">搜索</button>
    </div>

    <div v-if="loading" class="card text-ink-500">加载中...</div>
    <div v-else-if="error" class="card text-red-600">{{ error }}</div>
    <div v-else class="card overflow-hidden p-0">
      <table class="w-full text-sm">
        <thead class="bg-ink-50 border-b border-ink-200">
          <tr class="text-left text-ink-500">
            <th class="px-4 py-3 font-medium">标题</th>
            <th class="px-4 py-3 font-medium">分类</th>
            <th class="px-4 py-3 font-medium">优先级</th>
            <th class="px-4 py-3 font-medium">状态</th>
            <th class="px-4 py-3 font-medium">浏览</th>
            <th class="px-4 py-3 font-medium">创建时间</th>
            <th class="px-4 py-3 font-medium text-right">操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-if="items.length === 0">
            <td colspan="7" class="px-4 py-12 text-center text-ink-400">暂无公告</td>
          </tr>
          <tr v-for="item in items" :key="item.id" class="border-b border-ink-100 last:border-0 hover:bg-ink-50">
            <td class="px-4 py-3 font-medium">
              <span v-if="item.is_pinned" class="text-amber-500 mr-1">📌</span>
              {{ item.title }}
            </td>
            <td class="px-4 py-3 text-xs">{{ categoryLabel[item.category] || item.category }}</td>
            <td class="px-4 py-3">
              <span class="text-xs px-1.5 py-0.5 rounded" :class="priorityClass[item.priority]">{{ priorityLabel[item.priority] || item.priority }}</span>
            </td>
            <td class="px-4 py-3">
              <span class="text-xs px-1.5 py-0.5 rounded-full" :class="item.is_published ? 'bg-green-50 text-green-700' : 'bg-ink-100 text-ink-500'">
                {{ item.is_published ? '已发布' : '草稿' }}
              </span>
            </td>
            <td class="px-4 py-3 text-ink-500">{{ item.view_count }}</td>
            <td class="px-4 py-3 text-ink-500 text-xs">{{ item.created_at?.slice(0, 10) }}</td>
            <td class="px-4 py-3 text-right space-x-2">
              <button class="text-sm text-ink-600 hover:text-ink-900" @click="openEdit(item)">编辑</button>
              <button class="text-sm text-red-600 hover:underline" @click="del(item)">删除</button>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <!-- Edit Modal -->
    <div v-if="showEdit" class="fixed inset-0 z-50 flex items-center justify-center p-4 bg-ink-900/40" @click.self="showEdit = false">
      <div class="bg-white rounded-2xl w-full max-w-2xl p-6 max-h-[90vh] overflow-y-auto">
        <h2 class="text-lg font-semibold mb-4">{{ isNew ? '新建公告' : '编辑公告' }}</h2>
        <form @submit.prevent="save" class="space-y-4">
          <div>
            <label class="block text-sm font-medium mb-1.5">标题</label>
            <input v-model="form.title" required class="input" />
          </div>
          <div class="grid grid-cols-2 gap-4">
            <div>
              <label class="block text-sm font-medium mb-1.5">分类</label>
              <select v-model="form.category" class="input">
                <option value="general">通用</option>
                <option value="system">系统</option>
                <option value="urgent">紧急</option>
              </select>
            </div>
            <div>
              <label class="block text-sm font-medium mb-1.5">优先级</label>
              <select v-model="form.priority" class="input">
                <option value="low">低</option>
                <option value="normal">普通</option>
                <option value="high">高</option>
                <option value="urgent">紧急</option>
              </select>
            </div>
          </div>
          <div>
            <label class="block text-sm font-medium mb-1.5">摘要</label>
            <input v-model="form.summary" class="input" placeholder="可选" />
          </div>
          <div>
            <label class="block text-sm font-medium mb-1.5">内容</label>
            <textarea v-model="form.content" required rows="8" class="input"></textarea>
          </div>
          <div class="flex gap-4">
            <label class="flex items-center gap-2 text-sm">
              <input v-model="form.is_pinned" type="checkbox" class="rounded" /> 置顶
            </label>
            <label class="flex items-center gap-2 text-sm">
              <input v-model="form.is_published" type="checkbox" class="rounded" /> 发布
            </label>
          </div>
          <div class="flex gap-3 pt-2">
            <button type="submit" :disabled="saving" class="btn-primary flex-1">{{ saving ? '保存中...' : '保存' }}</button>
            <button type="button" @click="showEdit = false" class="btn-ghost">取消</button>
          </div>
        </form>
      </div>
    </div>
  </div>
</template>
