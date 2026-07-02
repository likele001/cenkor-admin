<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { useAuthStore } from '@/stores/auth'
import { api } from '@/lib/api'

const router = useRouter()
const auth = useAuthStore()
const { t } = useI18n()
const form = ref({ username: '', password: '' })
const error = ref('')
const loading = ref(false)

async function submit() {
  loading.value = true
  error.value = ''
  try {
    const { data } = await api.post('/api/v1/public/portal/auth/login', form.value)
    auth.setSession(data.access_token, data.refresh_token, data.user)
    router.push('/')
  } catch (e: any) {
    error.value = e?.response?.data?.detail || t('error.loginFailed')
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div class="min-h-screen flex items-center justify-center bg-slate-50 px-4">
    <form class="w-full max-w-md bg-white rounded-2xl shadow-sm border p-8 space-y-4" @submit.prevent="submit">
      <h1 class="text-2xl font-semibold">{{ t('login.title') }}</h1>
      <input v-model="form.username" required class="input" :placeholder="t('login.emailOrUsername')" />
      <input v-model="form.password" type="password" required class="input" :placeholder="t('login.password')" />
      <p v-if="error" class="text-sm text-red-600">{{ error }}</p>
      <button class="btn w-full" :disabled="loading">
        {{ loading ? t('common.loading') : t('nav.login') }}
      </button>
      <div class="flex items-center justify-between text-sm">
        <router-link to="/register" class="text-slate-500 hover:text-slate-900">{{ t('login.noAccount') }}</router-link>
        <router-link to="/forgot-password" class="text-slate-500 hover:text-slate-900">{{ t('login.forgotPassword') }}</router-link>
      </div>
    </form>
  </div>
</template>

<style scoped>
.input { @apply w-full border rounded-lg px-3 py-2; }
.btn { @apply bg-slate-900 text-white rounded-lg py-2 font-medium; }
</style>