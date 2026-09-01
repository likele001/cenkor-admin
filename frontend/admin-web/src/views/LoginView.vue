<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { api } from '@/lib/api'
import { useAuthStore } from '@/stores/auth'
import SliderCaptcha from '@/components/SliderCaptcha.vue'

const router = useRouter()
const route = useRoute()
const auth = useAuthStore()
const { t } = useI18n()

const username = ref('admin@cenkor.cn')
const password = ref('admin123')
const loading = ref(false)
const error = ref('')
const captchaRef = ref<InstanceType<typeof SliderCaptcha> | null>(null)
const captchaVerified = ref(false)
const captchaToken = ref('')

// 登录页滑块是否启用：默认 true（兜底）；登录前拉取后台开关，false 时隐藏滑块
const captchaRequired = ref(true)

onMounted(async () => {
  try {
    const { data } = await api.get('/api/v1/auth/login-config')
    captchaRequired.value = !!data.captcha_required
  } catch {
    // 接口失败时保留默认 true，保持现有安全行为
  }
})

function onCaptchaUpdate(verified: boolean) {
  captchaVerified.value = verified
  if (verified) {
    captchaToken.value = captchaRef.value?.token() || ''
  } else {
    captchaToken.value = ''
  }
}

async function submit() {
  if (captchaRequired.value && !captchaVerified.value) {
    error.value = t('login.captchaRequired')
    return
  }
  loading.value = true
  error.value = ''
  try {
    const { data } = await api.post('/api/v1/auth/login', {
      username: username.value,
      password: password.value,
      captcha_token: captchaToken.value,
    })
    auth.setToken(data.access_token, data.user)
    auth.setRefresh(data.refresh_token)
    router.push((route.query.redirect as string) || '/')
  } catch (e: any) {
    error.value = e?.response?.data?.detail || t('login.loginFailed')
    captchaRef.value?.refresh()
    captchaVerified.value = false
  } finally {
    loading.value = false
  }
}

function loginFeishu() {
  // 跳到后端 OAuth 端点 → 飞书 → 回调 → 自动登录
  window.location.href = '/api/v1/auth/feishu/authorize'
}
</script>

<template>
  <div class="min-h-screen flex items-center justify-center bg-ink-50 px-4">
    <div class="w-full max-w-sm">
      <div class="text-center mb-8">
        <div class="inline-flex items-center justify-center w-12 h-12 rounded-xl bg-ink-900 text-white text-xl font-bold mb-4">
          {{ t('app.logo', '辰') }}
        </div>
        <h1 class="text-2xl font-semibold tracking-tight">{{ t('app.name') }}</h1>
        <p class="mt-1 text-sm text-ink-500">{{ t('login.title') }}</p>
      </div>

      <form @submit.prevent="submit" class="card space-y-4">
        <div>
          <label for="f-username" class="block text-sm font-medium mb-1.5">{{ t('login.username') }}</label>
          <input
            id="f-username"
            v-model="username"
            type="text"
            autocomplete="username"
            required
            class="input"
          />
        </div>
        <div>
          <label for="f-password" class="block text-sm font-medium mb-1.5">{{ t('login.password') }}</label>
          <input
            id="f-password"
            v-model="password"
            type="password"
            autocomplete="current-password"
            required
            class="input"
          />
        </div>
        <div v-if="captchaRequired">
          <label class="block text-sm font-medium mb-1.5">{{ t('login.captcha') }}</label>
          <SliderCaptcha ref="captchaRef" @update:verified="onCaptchaUpdate" />
        </div>
        <div v-if="error" class="text-sm text-red-600">{{ error }}</div>
        <button type="submit" :disabled="loading" class="btn-primary w-full">
          {{ loading ? t('login.submitting') : t('login.submit') }}
        </button>

        <div class="relative my-2">
          <div class="absolute inset-0 flex items-center"><div class="w-full border-t border-ink-200"></div></div>
          <div class="relative flex justify-center text-xs"><span class="px-2 bg-white text-ink-400">{{ t('login.or') }}</span></div>
        </div>

        <button
          type="button"
          @click="loginFeishu"
          class="w-full inline-flex items-center justify-center gap-2 px-4 py-2.5 rounded-lg border border-ink-200 hover:border-ink-900 hover:bg-ink-50 transition text-sm font-medium"
        >
          <svg class="w-4 h-4" viewBox="0 0 24 24" fill="currentColor"><path d="M3 3h8.5L3 14.5V3zM21 3v11.5L12.5 3H21zM3 21h8.5L3 9.5V21zM21 21V9.5L12.5 21H21z"/></svg>
          {{ t('login.feishu') }}
        </button>

        <p class="text-xs text-ink-400 text-center">
          {{ t('login.defaultHint') }} <code class="px-1.5 py-0.5 rounded bg-ink-100">admin@cenkor.cn</code> /
          <code class="px-1.5 py-0.5 rounded bg-ink-100">admin123</code>
        </p>
      </form>
    </div>
  </div>
</template>