<script setup lang="ts">
import { ref } from 'vue'
import { api } from '@/lib/api'

const email = ref('')
const error = ref('')
const sent = ref(false)
const loading = ref(false)

async function submit() {
  if (!email.value) return
  loading.value = true
  error.value = ''
  try {
    await api.post('/api/v1/auth/forgot-password', {
      email: email.value,
      frontend_base: window.location.origin,
    })
    sent.value = true
  } catch (e: any) {
    error.value = e?.response?.data?.detail || '请求失败'
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div class="min-h-screen flex items-center justify-center bg-slate-50 px-4">
    <form class="w-full max-w-md bg-white rounded-2xl shadow-sm border p-8 space-y-4" @submit.prevent="submit">
      <h1 class="text-2xl font-semibold">忘记密码</h1>
      <p v-if="!sent" class="text-sm text-slate-500">
        输入您注册时使用的邮箱，我们会发送一封密码重置链接。
      </p>
      <template v-if="!sent">
        <input
          v-model="email"
          type="email"
          required
          class="input"
          placeholder="you@example.com"
        />
        <p v-if="error" class="text-sm text-red-600">{{ error }}</p>
        <button class="btn w-full" :disabled="loading">
          {{ loading ? '发送中…' : '发送重置链接' }}
        </button>
      </template>
      <div v-else class="rounded-lg bg-emerald-50 border border-emerald-200 p-4 text-sm text-emerald-700">
        ✅ 重置链接已发送（如该邮箱存在）。
        请检查收件箱（含垃圾邮件）。
      </div>
      <router-link to="/login" class="block text-center text-sm text-slate-500">返回登录</router-link>
    </form>
  </div>
</template>

<style scoped>
.input { @apply w-full border rounded-lg px-3 py-2; }
.btn { @apply bg-slate-900 text-white rounded-lg py-2 font-medium; }
</style>
