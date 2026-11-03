<script setup lang="ts">
/**
 * 第三方登录回调页。
 *
 * 后端 OAuth 回调完成后会跳到 /auth/sso/callback?ticket=xxx，这里拿 ticket
 * 换真正的 JWT。为什么绕这一步而不直接把 token 放 URL：
 * URL 会进浏览器历史、Nginx access log、Referer 头，token 泄露一次就等于
 * 账号被接管。ticket 只有 2 分钟且一次性，泄露了也用不掉。
 */
import { onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { useAuthStore } from '@/stores/auth'
import { api } from '@/lib/api'

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()
const { t } = useI18n()

const status = ref<'working' | 'error' | 'bound'>('working')
const message = ref('')

onMounted(async () => {
  const q = route.query

  // 1) 后端在回调里直接判定失败，会带 error + message 过来
  if (q.error) {
    status.value = 'error'
    message.value = String(q.message || t('login.ssoFailed'))
    return
  }

  // 2) 绑定模式：已登录用户在个人中心点了「绑定微信」，这里只是回执
  if (q.bound) {
    status.value = 'bound'
    message.value = `${q.provider_name || q.bound} ${t('login.ssoBound')}`
    // 1.2 秒后回个人中心，让用户能看见「已绑定」那一行
    setTimeout(() => router.replace('/profile'), 1200)
    return
  }

  // 3) 登录模式：用 ticket 换 token
  const ticket = String(q.ticket || '')
  if (!ticket) {
    status.value = 'error'
    message.value = t('login.ssoNoTicket')
    return
  }

  try {
    const { data } = await api.post('/api/v1/public/sso/exchange', { ticket })
    auth.setSession(data.access_token, data.refresh_token, data.user)
    const redirect = typeof q.redirect === 'string' && q.redirect.startsWith('/') ? q.redirect : '/'
    router.replace(redirect)
  } catch (e: any) {
    status.value = 'error'
    message.value = e?.response?.data?.detail || t('login.ssoFailed')
  }
})
</script>

<template>
  <div class="min-h-screen flex items-center justify-center bg-slate-50 px-4">
    <div class="w-full max-w-md bg-white rounded-2xl shadow-sm border p-8 text-center space-y-4">
      <template v-if="status === 'working'">
        <div class="text-3xl">🔄</div>
        <p class="text-slate-600">{{ t('login.ssoProcessing') }}</p>
      </template>

      <template v-else-if="status === 'bound'">
        <div class="text-3xl">✅</div>
        <p class="text-slate-700">{{ message }}</p>
      </template>

      <template v-else>
        <div class="text-3xl">⚠️</div>
        <p class="text-slate-700">{{ message }}</p>
        <router-link to="/login" class="inline-block text-sm text-slate-500 hover:text-slate-900 underline">
          {{ t('login.backToLogin') }}
        </router-link>
      </template>
    </div>
  </div>
</template>
