<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { api } from '@/lib/api'
import SliderCaptcha from '@/components/SliderCaptcha.vue'

const router = useRouter()
const form = ref({ username: '', password: '' })
const loading = ref(false)
const error = ref('')
const captchaRef = ref<InstanceType<typeof SliderCaptcha> | null>(null)
const captchaVerified = ref(false)
const captchaToken = ref('')

function onCaptchaUpdate(verified: boolean) {
  captchaVerified.value = verified
  captchaToken.value = verified ? (captchaRef.value?.token() || '') : ''
}

async function login() {
  if (!captchaVerified.value) {
    error.value = '请先完成滑动验证'
    return
  }
  loading.value = true
  error.value = ''
  try {
    const { data } = await api.post('/api/v1/public/portal/auth/login', {
      username: form.value.username,
      password: form.value.password,
      captcha_token: captchaToken.value,
    })
    localStorage.setItem('dev_token', data.access_token)
    localStorage.setItem('dev_user', JSON.stringify(data.user))
    router.push('/dashboard')
  } catch (e: any) {
    error.value = e?.response?.data?.detail || '登录失败'
    captchaRef.value?.refresh()
    captchaVerified.value = false
  } finally { loading.value = false }
}
</script>

<template>
  <div class="min-h-screen bg-ink-50 flex items-center justify-center p-4">
    <div class="bg-white rounded-2xl shadow-xl w-full max-w-md p-8">
      <div class="text-center mb-8">
        <img src="/logo.svg" class="w-10 h-10 rounded-lg mx-auto mb-3" width="40" height="40">
        <h1 class="text-xl font-semibold">开发者登录</h1>
        <p class="text-sm text-ink-500 mt-1">登录开发者中心管理你的应用</p>
      </div>
      <form @submit.prevent="login" class="space-y-4">
        <div>
          <label class="block text-sm font-medium mb-1.5">邮箱 / 用户名</label>
          <input v-model="form.username" type="text" required class="input" placeholder="请输入邮箱或用户名" />
        </div>
        <div>
          <label class="block text-sm font-medium mb-1.5">密码</label>
          <input v-model="form.password" type="password" required class="input" placeholder="请输入密码" />
        </div>
        <div>
          <label class="block text-sm font-medium mb-1.5">滑动验证</label>
          <SliderCaptcha ref="captchaRef" @update:verified="onCaptchaUpdate" />
        </div>
        <div v-if="error" class="text-sm text-red-600">{{ error }}</div>
        <button type="submit" :disabled="loading" class="btn-primary w-full">
          {{ loading ? '登录中...' : '登录' }}
        </button>
      </form>
      <div class="text-center mt-6 text-sm text-ink-500">
        还没有账号？ <router-link to="/register" class="text-ink-900 hover:underline">注册开发者</router-link>
      </div>
    </div>
  </div>
</template>
