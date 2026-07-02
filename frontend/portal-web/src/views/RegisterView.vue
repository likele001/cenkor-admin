<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { useAuthStore } from '@/stores/auth'
import { api } from '@/lib/api'
import SliderCaptcha from '@/components/SliderCaptcha.vue'

const router = useRouter()
const auth = useAuthStore()
const { t } = useI18n()
const form = ref({ username: '', email: '', password: '', nickname: '' })
const error = ref('')
const loading = ref(false)
const captchaRef = ref<InstanceType<typeof SliderCaptcha> | null>(null)
const captchaToken = ref('')
const captchaVerified = ref(false)

function onCaptchaUpdate(v: boolean) {
  captchaVerified.value = v
  captchaToken.value = v ? captchaRef.value?.token() || '' : ''
}

async function submit() {
  if (!captchaVerified.value) {
    error.value = t('error.captchaRequired')
    return
  }
  loading.value = true
  error.value = ''
  try {
    const { data } = await api.post('/api/v1/public/portal/auth/register', {
      ...form.value,
      captcha_token: captchaToken.value,
    })
    auth.setSession(data.access_token, data.refresh_token, data.user)
    router.push('/')
  } catch (e: any) {
    error.value = e?.response?.data?.detail || t('error.registerFailed')
    captchaRef.value?.refresh()
    captchaVerified.value = false
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div class="min-h-screen flex items-center justify-center bg-slate-50 px-4">
    <form class="w-full max-w-md bg-white rounded-2xl shadow-sm border p-8 space-y-4" @submit.prevent="submit">
      <h1 class="text-2xl font-semibold">{{ t('register.title') }}</h1>
      <input v-model="form.username" required class="input" :placeholder="t('register.username')" />
      <input v-model="form.email" type="email" required class="input" :placeholder="t('register.email')" />
      <input v-model="form.nickname" class="input" :placeholder="t('register.nicknameOptional')" />
      <input v-model="form.password" type="password" required minlength="8" class="input" :placeholder="t('register.passwordHint')" />
      <div>
        <label class="block text-sm font-medium mb-1.5">{{ t('register.captcha') }}</label>
        <SliderCaptcha ref="captchaRef" @update:verified="onCaptchaUpdate" />
      </div>
      <p v-if="error" class="text-sm text-red-600">{{ error }}</p>
      <button class="btn w-full" :disabled="loading">
        {{ loading ? t('error.submitting') : t('register.submit') }}
      </button>
      <router-link to="/login" class="block text-center text-sm text-slate-500">{{ t('login.haveAccount') }}</router-link>
    </form>
  </div>
</template>

<style scoped>
.input { @apply w-full border rounded-lg px-3 py-2; }
.btn { @apply bg-slate-900 text-white rounded-lg py-2 font-medium; }
</style>