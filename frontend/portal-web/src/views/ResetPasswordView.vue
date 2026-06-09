<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { api } from '@/lib/api'

const route = useRoute()
const router = useRouter()
const token = ref('')
const newPassword = ref('')
const confirm = ref('')
const error = ref('')
const loading = ref(false)
const done = ref(false)

onMounted(() => {
  const t = route.query.token
  if (typeof t === 'string') token.value = t
  if (!token.value) error.value = '缺少重置 token，请通过邮件中的链接进入'
})

async function submit() {
  if (newPassword.value.length < 8) {
    error.value = '新密码至少 8 位'
    return
  }
  if (newPassword.value !== confirm.value) {
    error.value = '两次输入的密码不一致'
    return
  }
  loading.value = true
  error.value = ''
  try {
    await api.post('/api/v1/auth/reset-password', {
      token: token.value,
      new_password: newPassword.value,
    })
    done.value = true
    setTimeout(() => router.push('/login'), 2000)
  } catch (e: any) {
    error.value = e?.response?.data?.detail || '重置失败'
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div class="min-h-screen flex items-center justify-center bg-slate-50 px-4">
    <form class="w-full max-w-md bg-white rounded-2xl shadow-sm border p-8 space-y-4" @submit.prevent="submit">
      <h1 class="text-2xl font-semibold">重置密码</h1>
      <div v-if="!done">
        <input
          v-model="newPassword"
          type="password"
          required
          minlength="8"
          class="input"
          placeholder="新密码（至少 8 位）"
        />
        <input
          v-model="confirm"
          type="password"
          required
          minlength="8"
          class="input mt-3"
          placeholder="确认新密码"
        />
        <p v-if="error" class="text-sm text-red-600 mt-2">{{ error }}</p>
        <button class="btn w-full mt-3" :disabled="loading || !token">
          {{ loading ? '提交中…' : '重置密码' }}
        </button>
      </div>
      <div v-else class="rounded-lg bg-emerald-50 border border-emerald-200 p-4 text-sm text-emerald-700">
        ✅ 密码已重置，2 秒后跳转到登录页。
      </div>
    </form>
  </div>
</template>

<style scoped>
.input { @apply w-full border rounded-lg px-3 py-2; }
.btn { @apply bg-slate-900 text-white rounded-lg py-2 font-medium; }
</style>
