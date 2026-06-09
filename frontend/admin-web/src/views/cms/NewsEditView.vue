<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { api } from '@/lib/api'
import VditorEditor from '@/components/VditorEditor.vue'

const route = useRoute()
const router = useRouter()
const isNew = !route.params.id
const loading = ref(!isNew)
const saving = ref(false)
const error = ref('')

const form = ref({
  slug: '',
  title: '',
  excerpt: '',
  content_md: '',
  cover_image: '',
  status: 'draft',
})

onMounted(async () => {
  if (isNew) return
  try {
    const { data } = await api.get(`/api/v1/cms/news/${route.params.id}`)
    Object.assign(form.value, data)
  } catch (e: any) {
    error.value = e?.response?.data?.detail || '加载失败'
  } finally {
    loading.value = false
  }
})

async function save() {
  saving.value = true
  error.value = ''
  try {
    if (isNew) {
      const { data } = await api.post('/api/v1/cms/news', form.value)
      router.push(`/cms/news/${data.id}`)
    } else {
      await api.patch(`/api/v1/cms/news/${route.params.id}`, form.value)
    }
    setTimeout(() => router.push('/cms/news'), 500)
  } catch (e: any) {
    error.value = e?.response?.data?.detail || '保存失败'
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <div class="min-h-screen bg-ink-50">
    <header class="bg-white border-b border-ink-200">
      <div class="max-w-4xl mx-auto px-6 h-14 flex items-center gap-4">
        <router-link to="/cms/news" class="text-sm text-ink-500 hover:text-ink-900">← 新闻列表</router-link>
        <span class="font-semibold">{{ isNew ? '新建新闻' : '编辑新闻' }}</span>
      </div>
    </header>

    <main class="max-w-4xl mx-auto px-6 py-10">
      <div v-if="loading" class="card text-ink-500">加载中…</div>
      <form v-else @submit.prevent="save" class="card space-y-4">
        <div class="grid sm:grid-cols-2 gap-4">
          <div>
            <label class="block text-sm font-medium mb-1.5">标题 *</label>
            <input v-model="form.title" required class="input" />
          </div>
          <div>
            <label class="block text-sm font-medium mb-1.5">Slug *</label>
            <input v-model="form.slug" required :disabled="!isNew" class="input" />
          </div>
        </div>
        <div>
          <label class="block text-sm font-medium mb-1.5">摘要 *</label>
          <input v-model="form.excerpt" required maxlength="500" class="input" />
        </div>
        <div>
          <label class="block text-sm font-medium mb-1.5">封面图 URL</label>
          <input v-model="form.cover_image" class="input" placeholder="https://..." />
        </div>
        <div>
          <label class="block text-sm font-medium mb-1.5">内容 (Markdown) *</label>
          <VditorEditor v-model="form.content_md" :height="520" />
        </div>
        <div>
          <label class="block text-sm font-medium mb-1.5">状态</label>
          <select v-model="form.status" class="input">
            <option value="draft">草稿</option>
            <option value="published">已发布</option>
            <option value="archived">已归档</option>
          </select>
        </div>
        <div v-if="error" class="text-sm text-red-600">{{ error }}</div>
        <div class="flex gap-3">
          <button type="submit" :disabled="saving" class="btn-primary">
            {{ saving ? '保存中…' : isNew ? '发布' : '保存修改' }}
          </button>
          <router-link to="/cms/news" class="btn-ghost">取消</router-link>
        </div>
      </form>
    </main>
  </div>
</template>
