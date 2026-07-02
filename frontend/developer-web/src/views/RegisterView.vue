<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { api } from '@/lib/api'
import SliderCaptcha from '@/components/SliderCaptcha.vue'

const router = useRouter()
const form = ref({ username: '', email: '', password: '', display_name: '' })
const loading = ref(false)
const error = ref('')
const captchaRef = ref<InstanceType<typeof SliderCaptcha> | null>(null)
const captchaVerified = ref(false)
const captchaToken = ref('')

function onCaptchaUpdate(verified: boolean) {
  captchaVerified.value = verified
  captchaToken.value = verified ? (captchaRef.value?.token() || '') : ''
}

async function register() {
  if (!captchaVerified.value) {
    error.value = '请先完成滑动验证'
    return
  }
  loading.value = true
  error.value = ''
  try {
    const payload: Record<string, any> = {
      username: form.value.username,
      password: form.value.password,
      captcha_token: captchaToken.value,
    }
    if (form.value.email) payload.email = form.value.email
    const { data } = await api.post('/api/v1/public/portal/auth/register', payload)
    localStorage.setItem('dev_token', data.access_token)
    localStorage.setItem('dev_user', JSON.stringify(data.user))
    await api.post('/api/v1/store/developers', {
      display_name: form.value.display_name || form.value.username,
    })
    router.push('/dashboard')
  } catch (e: any) {
    const detail = e?.response?.data?.detail || ''
    if (detail.includes('已存在')) {
      error.value = '账号已存在，请直接登录'
    } else {
      error.value = detail || '注册失败'
    }
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
        <h1 class="text-xl font-semibold">注册开发者</h1>
        <p class="text-sm text-ink-500 mt-1">创建开发者账号，发布你的应用</p>
      </div>
      <form @submit.prevent="register" class="space-y-4">
        <div>
          <label class="block text-sm font-medium mb-1.5">用户名</label>
          <input v-model="form.username" required class="input" placeholder="小写字母开头" />
        </div>
        <div>
          <label class="block text-sm font-medium mb-1.5">邮箱</label>
          <input v-model="form.email" type="email" required class="input" />
        </div>
        <div>
          <label class="block text-sm font-medium mb-1.5">密码</label>
          <input v-model="form.password" type="password" required minlength="8" class="input" placeholder="至少 8 位" />
        </div>
        <div>
          <label class="block text-sm font-medium mb-1.5">开发者名称</label>
          <input v-model="form.display_name" class="input" placeholder="显示在应用商店的名称" />
        </div>
        <div>
          <label class="block text-sm font-medium mb-1.5">滑动验证</label>
          <SliderCaptcha ref="captchaRef" @update:verified="onCaptchaUpdate" />
        </div>
        <div v-if="error" class="text-sm text-red-600">{{ error }}</div>
        <button type="submit" :disabled="loading" class="btn-primary w-full">
          {{ loading ? '注册中...' : '注册' }}
        </button>
      </form>
      <div class="text-center mt-6 text-sm text-ink-500">
        已有账号？ <router-link to="/login" class="text-ink-900 hover:underline">登录</router-link>
      </div>
    </div>
  </div>
</template>
