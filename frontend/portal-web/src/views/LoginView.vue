<script setup lang="ts">
import { onMounted, ref } from 'vue'
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

interface SsoProvider {
  key: string
  name: string
  icon: string
  note: string
  authorize_url: string
}
const ssoProviders = ref<SsoProvider[]>([])

// 渠道列表从后端动态取：后台开关哪个渠道，这里就出现哪个按钮，
// 前端不需要为「加了微信」改一次代码。
// 失败一律静默 —— SSO 接口挂了绝不能让账号密码登录也跟着不可用。
onMounted(async () => {
  try {
    const { data } = await api.get('/api/v1/public/sso/login-config?realm=portal')
    ssoProviders.value = data?.providers ?? []
  } catch {
    ssoProviders.value = []
  }
})

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

// 整页跳转到第三方授权页。用 location 而不是 axios：
// 授权页必须让浏览器自己带过去，XHR 拿不到对方的登录态。
function goSso(p: SsoProvider) {
  window.location.href = p.authorize_url
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

      <!-- 第三方登录：没有可用渠道时整块不渲染，不留一条空白分隔线 -->
      <template v-if="ssoProviders.length">
        <div class="flex items-center gap-3 py-1">
          <span class="h-px flex-1 bg-slate-200"></span>
          <span class="text-xs text-slate-400">{{ t('login.orThirdParty') }}</span>
          <span class="h-px flex-1 bg-slate-200"></span>
        </div>
        <div class="grid grid-cols-2 gap-2">
          <button
            v-for="p in ssoProviders"
            :key="p.key"
            type="button"
            class="sso-btn"
            :title="p.note"
            @click="goSso(p)"
          >
            <span class="text-lg leading-none">{{ p.icon }}</span>
            <span class="truncate">{{ p.name }}</span>
          </button>
        </div>
      </template>

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
.sso-btn {
  @apply flex items-center justify-center gap-2 border rounded-lg py-2 px-3 text-sm
         text-slate-700 bg-white hover:bg-slate-50 hover:border-slate-400 transition;
}
</style>
