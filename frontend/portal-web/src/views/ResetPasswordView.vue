<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { api } from '@/lib/api'

const route = useRoute()
const router = useRouter()
const { t } = useI18n()
const token = ref('')
const newPassword = ref('')
const confirm = ref('')
const error = ref('')
const loading = ref(false)
const done = ref(false)

onMounted(() => {
  const t = route.query.token
  if (typeof t === 'string') token.value = t
  if (!token.value) error.value = t ? '' : 'missing-token'
})

async function submit() {
  if (newPassword.value.length < 8) {
    error.value = t('error.passwordMin8')
    return
  }
  if (newPassword.value !== confirm.value) {
    error.value = t('error.passwordMismatch')
    return
  }
  loading.value = true
  error.value = ''
  try {
    await api.post('/api/v1/public/portal/auth/reset-password', {
      token: token.value,
      new_password: newPassword.value,
    })
    done.value = true
    setTimeout(() => router.push('/login'), 2000)
  } catch (e: any) {
    error.value = e?.response?.data?.detail || t('error.resetFailed')
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div class="min-h-screen flex items-center justify-center bg-slate-50 px-4">
    <form class="w-full max-w-md bg-white rounded-2xl shadow-sm border p-8 space-y-4" @submit.prevent="submit">
      <h1 class="text-2xl font-semibold">{{ t('resetPassword.title') }}</h1>
      <p v-if="!token && !done" class="text-sm text-red-600">{{ t('error.missingToken') }}</p>
      <div v-if="!done && token">
        <input v-model="newPassword" type="password" required minlength="8" class="input" :placeholder="t('resetPassword.newPassword')" />
        <input v-model="confirm" type="password" required minlength="8" class="input mt-3" :placeholder="t('resetPassword.confirmPassword')" />
        <p v-if="error" class="text-sm text-red-600 mt-2">{{ error }}</p>
        <button class="btn w-full mt-3" :disabled="loading || !token">
          {{ loading ? t('error.submitting') : t('resetPassword.submit') }}
        </button>
      </div>
      <div v-else-if="done" class="rounded-lg bg-emerald-50 border border-emerald-200 p-4 text-sm text-emerald-700">
        {{ t('error.resetOk') }}
      </div>
    </form>
  </div>
</template>

<style scoped>
.input { @apply w-full border rounded-lg px-3 py-2; }
.btn { @apply bg-slate-900 text-white rounded-lg py-2 font-medium; }
</style>