<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { api } from '@/lib/api'

const router = useRouter()
const route = useRoute()
const form = ref({ app_key: '', name: '', version: '', description: '', category: 'productivity' })
const file = ref<File | null>(null)
const uploading = ref(false)
const error = ref('')
const success = ref(false)

onMounted(() => {
  const key = route.query.app_key as string | undefined
  if (key) form.value.app_key = key
})

function onFileChange(e: Event) {
  const input = e.target as HTMLInputElement
  file.value = input.files?.[0] || null
}

async function submit() {
  if (!file.value || !form.value.app_key || !form.value.name || !form.value.version) {
    error.value = '请填写所有必填项并上传 ZIP 文件'
    return
  }
  uploading.value = true
  error.value = ''
  try {
    const fd = new FormData()
    fd.append('file', file.value)
    fd.append('app_key', form.value.app_key)
    fd.append('name', form.value.name)
    fd.append('version', form.value.version)
    fd.append('description', form.value.description)
    fd.append('category', form.value.category)
    await api.post('/api/v1/store/submissions', fd)
    success.value = true
  } catch (e: any) {
    error.value = e?.response?.data?.detail || '上传失败'
  } finally { uploading.value = false }
}
</script>

<template>
  <div>
    <div v-if="success" class="card p-8 text-center">
      <div class="text-4xl mb-4">✅</div>
      <h2 class="text-xl font-semibold mb-2">提交成功</h2>
      <p class="text-ink-500 mb-6">你的应用已提交审核，通常 1-3 个工作日内完成审核。</p>
      <div class="flex justify-center gap-3">
        <router-link to="/dashboard/my-apps" class="btn-primary">查看我的应用</router-link>
        <button class="btn-ghost" @click="success = false; form = { app_key: '', name: '', version: '', description: '', category: 'productivity' }; file = null">继续提交</button>
      </div>
    </div>

    <div v-else class="card p-6">
      <h2 class="text-lg font-semibold mb-4">提交应用</h2>
      <form @submit.prevent="submit" class="space-y-4 max-w-xl">
        <div class="grid grid-cols-2 gap-4">
          <div>
            <label class="block text-sm font-medium mb-1.5">App Key <span class="text-red-500">*</span></label>
            <input v-model="form.app_key" required class="input" placeholder="my_app（小写英文+下划线/连字符）" pattern="[a-z][a-z0-9\-_]{1,49}" />
            <p class="text-xs text-ink-400 mt-1">小写字母开头，2-50位，只含小写字母/数字/连字符</p>
          </div>
          <div>
            <label class="block text-sm font-medium mb-1.5">版本号 <span class="text-red-500">*</span></label>
            <input v-model="form.version" required class="input" placeholder="1.0.0" />
          </div>
        </div>
        <div>
          <label class="block text-sm font-medium mb-1.5">应用名称 <span class="text-red-500">*</span></label>
          <input v-model="form.name" required class="input" placeholder="我的应用" />
        </div>
        <div>
          <label class="block text-sm font-medium mb-1.5">分类</label>
          <select v-model="form.category" class="input">
            <option value="content">内容管理</option>
            <option value="productivity">效率工具</option>
            <option value="system">系统扩展</option>
            <option value="ai">AI 应用</option>
          </select>
        </div>
        <div>
          <label class="block text-sm font-medium mb-1.5">描述</label>
          <textarea v-model="form.description" rows="3" class="input" placeholder="应用描述（可选）"></textarea>
        </div>
        <div>
          <label class="block text-sm font-medium mb-1.5">ZIP 文件 <span class="text-red-500">*</span></label>
          <input type="file" accept=".zip" @change="onFileChange" class="input" />
          <p class="text-xs text-ink-400 mt-1">必须包含 manifest.py 和 __init__.py</p>
        </div>
        <div v-if="error" class="text-sm text-red-600">{{ error }}</div>
        <button type="submit" :disabled="uploading" class="btn-primary">
          {{ uploading ? '上传中...' : '提交审核' }}
        </button>
      </form>
    </div>
  </div>
</template>
