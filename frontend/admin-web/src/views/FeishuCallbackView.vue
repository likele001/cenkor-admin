<script setup lang="ts">
import { useI18n } from 'vue-i18n'
const { t } = useI18n()
import { onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { api } from '@/lib/api'

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()

onMounted(async () => {
  const code = route.query.code as string
  const state = route.query.state as string
  if (!code) {
    router.replace('/login?error=feishu_no_code')
    return
  }
  try {
    const { data } = await api.get('/api/v1/auth/feishu/callback', {
      params: { code, state },
    })
    if (data.access_token) {
      auth.setToken(data.access_token, data.user)
      if (data.refresh_token) auth.setRefresh(data.refresh_token)
      router.replace('/')
    }
  } catch {
    router.replace('/login?error=feishu_failed')
  }
})
</script>

<template>
  <div class="min-h-screen flex items-center justify-center bg-ink-50">
    <p class="text-ink-500">{{ t('feishuCallback.飞书登录_16gozd') }}</p>
  </div>
</template>
