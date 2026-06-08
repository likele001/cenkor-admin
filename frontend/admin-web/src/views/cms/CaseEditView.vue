<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { api } from '@/lib/api'

const route = useRoute()
const router = useRouter()
const isNew = !route.params.id
const loading = ref(!isNew)
const saving = ref(false)
const error = ref('')

const form = ref({
  industry: '',
  name: '',
  desc: '',
  tag: '',
  href: '',
  sort: 0,
  status: 'published',
})

onMounted(async () => {
  if (isNew) return
  try {
    const { data } = await api.get(`/api/v1/cms/cases/${route.params.id}`)
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
      const { data } = await api.post('/api/v1/cms/cases', form.value)
      router.push(`/cms/cases/${data.id}`)
    } else {
      await api.patch(`/api/v1/cms/cases/${route.params.id}`, form.value)
    }
    // 简单跳转
    setTimeout(() => router.push('/cms/cases'), 500)
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
        <router-link to="/cms/cases" class="text-sm text-ink-500 hover:text-ink-900">← 案例列表</router-link>
        <span class="font-semibold">{{ isNew ? '新建案例' : '编辑案例' }}</span>
      </div>
    </header>

    <main class="max-w-4xl mx-auto px-6 py-10">
      <div v-if="loading" class="card text-ink-500">加载中…</div>
      <form v-else @submit.prevent="save" class="card space-y-4">
        <div class="grid sm:grid-cols-2 gap-4">
          <div>
            <label class="block text-sm font-medium mb-1.5">行业 *</label>
            <input v-model="form.industry" required class="input" placeholder="智能制造" />
          </div>
          <div>
            <label class="block text-sm font-medium mb-1.5">客户名 *</label>
            <input v-model="form.name" required class="input" placeholder="某精密机加工企业" />
          </div>
        </div>
        <div>
          <label class="block text-sm font-medium mb-1.5">描述 *</label>
          <textarea v-model="form.desc" required rows="3" class="input"></textarea>
        </div>
        <div class="grid sm:grid-cols-2 gap-4">
          <div>
            <label class="block text-sm font-medium mb-1.5">标签 *</label>
            <input v-model="form.tag" required class="input" placeholder="LightMes" />
          </div>
          <div>
            <label class="block text-sm font-medium mb-1.5">外链 URL</label>
            <input v-model="form.href" class="input" placeholder="https://..." />
          </div>
        </div>
        <div class="grid sm:grid-cols-2 gap-4">
          <div>
            <label class="block text-sm font-medium mb-1.5">排序</label>
            <input v-model.number="form.sort" type="number" class="input" />
          </div>
          <div>
            <label class="block text-sm font-medium mb-1.5">状态</label>
            <select v-model="form.status" class="input">
              <option value="published">已发布</option>
              <option value="draft">草稿</option>
            </select>
          </div>
        </div>
        <div v-if="error" class="text-sm text-red-600">{{ error }}</div>
        <div class="flex gap-3">
          <button type="submit" :disabled="saving" class="btn-primary">
            {{ saving ? '保存中…' : isNew ? '创建案例' : '保存修改' }}
          </button>
          <router-link to="/cms/cases" class="btn-ghost">取消</router-link>
        </div>
      </form>
    </main>
  </div>
</template>
