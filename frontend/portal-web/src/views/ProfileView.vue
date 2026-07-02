<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { useAuthStore } from '@/stores/auth'
import { api } from '@/lib/api'

interface OAuthBinding { id: number; provider: string; open_id: string; created_at: string }

const router = useRouter()
const auth = useAuthStore()
const { t } = useI18n()
const profile = ref({ nickname: '', email: '', avatar: '' })
const pwd = ref({ old_password: '', new_password: '' })
const oauths = ref<OAuthBinding[]>([])
const bindForm = ref({ provider: 'feishu', open_id: '', union_id: '' })
const showBind = ref(false)
const msg = ref('')
const err = ref('')

const PROVIDER_LABELS: Record<string, () => string> = {
  feishu: () => t('profile.feishu'),
  wechat: () => t('profile.wechat'),
  github: () => 'GitHub',
}

async function loadProfile() {
  try {
    const { data } = await api.get('/api/v1/public/portal/me')
    profile.value = {
      nickname: data.nickname || '',
      email: data.email || '',
      avatar: data.avatar || '',
    }
  } catch { /* ignore */ }
}

async function loadOAuth() {
  try {
    const { data } = await api.get('/api/v1/public/portal/me/oauth')
    oauths.value = data || []
  } catch { oauths.value = [] }
}

async function saveProfile() {
  err.value = ''; msg.value = ''
  try {
    await api.patch('/api/v1/public/portal/me/profile', {
      nickname: profile.value.nickname || null,
      email: profile.value.email || null,
      avatar: profile.value.avatar || null,
    })
    msg.value = t('error.saveSuccess')
  } catch (e: any) {
    err.value = e?.response?.data?.detail || t('error.saveFailed')
  }
}

async function changePassword() {
  err.value = ''; msg.value = ''
  try {
    await api.post('/api/v1/public/portal/me/change-password', pwd.value)
    msg.value = t('error.passwordChanged')
    auth.logout()
    router.push('/login')
  } catch (e: any) {
    err.value = e?.response?.data?.detail || t('error.passwordChangeFailed')
  }
}

async function bindOAuth() {
  try {
    await api.post('/api/v1/public/portal/me/oauth/bind', {
      provider: bindForm.value.provider,
      open_id: bindForm.value.open_id,
      union_id: bindForm.value.union_id || undefined,
    })
    showBind.value = false
    bindForm.value = { provider: 'feishu', open_id: '', union_id: '' }
    await loadOAuth()
    msg.value = t('error.bindSuccess')
  } catch (e: any) {
    err.value = e?.response?.data?.detail || t('error.bindFailed')
  }
}

async function unbindOAuth(oauth: OAuthBinding) {
  const label = (PROVIDER_LABELS[oauth.provider]?.() || oauth.provider)
  if (!confirm(t('error.unbindConfirm', { provider: label }))) return
  try {
    await api.delete(`/api/v1/public/portal/me/oauth/${oauth.id}`)
    await loadOAuth()
    msg.value = t('error.unbindSuccess')
  } catch (e: any) {
    err.value = e?.response?.data?.detail || t('error.unbindFailed')
  }
}

function logout() {
  auth.logout()
  router.push('/login')
}

onMounted(async () => {
  await loadProfile()
  await loadOAuth()
})
</script>

<template>
  <div class="min-h-screen bg-slate-50">
    <header class="bg-white border-b">
      <div class="max-w-3xl mx-auto px-6 h-14 flex items-center justify-between">
        <router-link to="/" class="font-semibold">{{ t('profile.title') }}</router-link>
        <button class="text-sm text-slate-500" @click="logout">{{ t('profile.logout') }}</button>
      </div>
    </header>

    <main class="max-w-3xl mx-auto px-6 py-10 space-y-6">
      <!-- 基础资料 -->
      <section class="bg-white rounded-2xl border p-6 space-y-4">
        <h2 class="font-semibold text-lg">{{ t('profile.section.profile') }}</h2>
        <div class="grid grid-cols-3 gap-4">
          <div class="col-span-1">
            <label class="block text-xs text-slate-500 mb-1">{{ t('profile.avatar') }}</label>
            <input v-model="profile.avatar" class="input" placeholder="https://..." />
            <div v-if="profile.avatar" class="mt-2">
              <img :src="profile.avatar" class="w-16 h-16 rounded-full border object-cover" />
            </div>
          </div>
          <div class="col-span-2 space-y-3">
            <div>
              <label class="block text-xs text-slate-500 mb-1">{{ t('profile.nickname') }}</label>
              <input v-model="profile.nickname" class="input" />
            </div>
            <div>
              <label class="block text-xs text-slate-500 mb-1">{{ t('profile.email') }}</label>
              <input v-model="profile.email" type="email" class="input" />
            </div>
          </div>
        </div>
        <button class="btn-primary" @click="saveProfile">{{ t('profile.saveProfile') }}</button>
      </section>

      <!-- 修改密码 -->
      <section class="bg-white rounded-2xl border p-6 space-y-4">
        <h2 class="font-semibold text-lg">{{ t('profile.section.password') }}</h2>
        <input v-model="pwd.old_password" type="password" class="input" :placeholder="t('profile.oldPassword')" />
        <input v-model="pwd.new_password" type="password" class="input" :placeholder="t('profile.newPassword')" />
        <button class="btn-primary" @click="changePassword">{{ t('profile.updatePassword') }}</button>
      </section>

      <!-- OAuth 绑定 -->
      <section class="bg-white rounded-2xl border p-6 space-y-4">
        <div class="flex items-center justify-between">
          <h2 class="font-semibold text-lg">{{ t('profile.section.oauth') }}</h2>
          <button class="btn-ghost text-sm" @click="showBind = !showBind">
            {{ showBind ? t('common.cancel') : '+ ' + t('profile.bind') }}
          </button>
        </div>

        <div v-if="showBind" class="border rounded-lg p-3 space-y-2 bg-slate-50">
          <div class="grid grid-cols-3 gap-2">
            <select v-model="bindForm.provider" class="input">
              <option value="feishu">{{ t('profile.feishu') }}</option>
              <option value="wechat">{{ t('profile.wechat') }}</option>
              <option value="github">GitHub</option>
            </select>
            <input v-model="bindForm.open_id" class="input col-span-2" placeholder="open_id" />
          </div>
          <input v-model="bindForm.union_id" class="input" :placeholder="t('profile.unionIdOptional')" />
          <p class="text-xs text-ink-500">{{ t('profile.oauthHint') }}</p>
          <button class="btn-primary text-sm" @click="bindOAuth">{{ t('profile.bind') }}</button>
        </div>

        <div v-if="oauths.length === 0" class="text-sm text-ink-400 text-center py-4">
          {{ t('error.noBinding') }}
        </div>
        <div v-else class="space-y-2">
          <div v-for="o in oauths" :key="o.id" class="flex items-center justify-between border rounded-lg p-3">
            <div class="flex items-center gap-3">
              <span class="text-2xl">
                {{ { feishu: '🪶', wechat: '💬', github: '🐙' }[o.provider] || '🔗' }}
              </span>
              <div>
                <div class="font-medium text-sm">{{ PROVIDER_LABELS[o.provider]?.() || o.provider }}</div>
                <code class="text-xs text-ink-400">{{ o.open_id.slice(0, 24) }}…</code>
                <div class="text-xs text-ink-400">{{ t('error.bindAt', { date: o.created_at.slice(0, 10) }) }}</div>
              </div>
            </div>
            <button class="text-red-500 text-xs" @click="unbindOAuth(o)">{{ t('profile.unbind') }}</button>
          </div>
        </div>
      </section>

      <p v-if="msg" class="text-emerald-600 text-sm">{{ msg }}</p>
      <p v-if="err" class="text-red-600 text-sm">{{ err }}</p>
    </main>
  </div>
</template>

<style scoped>
.input { @apply w-full border rounded-lg px-3 py-2; }
.btn-primary { @apply bg-slate-900 text-white rounded-lg px-4 py-2 text-sm font-medium; }
.btn-ghost { @apply text-slate-600 hover:text-slate-900 rounded-lg px-3 py-1.5 text-sm; }
</style>