<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { api } from '@/lib/api'

const router = useRouter()
const auth = useAuthStore()
const form = ref({ username: '', email: '', password: '', nickname: '' })
const error = ref('')
const loading = ref(false)

async function submit() {
  loading.value = true
  error.value = ''
  try {
    const { data } = await api.post('/api/v1/auth/register', form.value)
    auth.setSession(data.access_token, data.user)
    router.push('/')
  } catch (e: any) {
    error.value = e?.response?.data?.detail || '注册失败'
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div class="min-h-screen flex items-center justify-center bg-slate-50 px-4">
    <form class="w-full max-w-md bg-white rounded-2xl shadow-sm border p-8 space-y-4" @submit.prevent="submit">
      <h1 class="text-2xl font-semibold">注册账号</h1>
      <input v-model="form.username" required class="input" placeholder="用户名" />
      <input v-model="form.email" type="email" required class="input" placeholder="邮箱" />
      <input v-model="form.nickname" class="input" placeholder="昵称（可选）" />
      <input v-model="form.password" type="password" required minlength="8" class="input" placeholder="密码（至少8位）" />
      <p v-if="error" class="text-sm text-red-600">{{ error }}</p>
      <button class="btn w-full" :disabled="loading">{{ loading ? '提交中…' : '注册' }}</button>
      <router-link to="/login" class="block text-center text-sm text-slate-500">已有账号？登录</router-link>
    </form>
  </div>
</template>

<style scoped>
.input { @apply w-full border rounded-lg px-3 py-2; }
.btn { @apply bg-slate-900 text-white rounded-lg py-2 font-medium; }
</style>
