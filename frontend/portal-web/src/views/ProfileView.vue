<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { api } from '@/lib/api'

const router = useRouter()
const auth = useAuthStore()
const profile = ref({ nickname: '', email: '' })
const pwd = ref({ old_password: '', new_password: '' })
const msg = ref('')
const err = ref('')

onMounted(async () => {
  try {
    const { data } = await api.get('/api/v1/auth/me')
    profile.value = { nickname: data.nickname, email: data.email }
    auth.setSession(auth.token, data)
  } catch { /* ignore */ }
})

async function saveProfile() {
  err.value = ''
  msg.value = ''
  try {
    const { data } = await api.patch('/api/v1/auth/profile', profile.value)
    auth.setSession(auth.token, data)
    msg.value = '资料已保存'
  } catch (e: any) {
    err.value = e?.response?.data?.detail || '保存失败'
  }
}

async function changePassword() {
  err.value = ''
  msg.value = ''
  try {
    await api.post('/api/v1/auth/change-password', pwd.value)
    msg.value = '密码已修改，请重新登录'
    auth.logout()
    router.push('/login')
  } catch (e: any) {
    err.value = e?.response?.data?.detail || '修改失败'
  }
}

function logout() {
  auth.logout()
  router.push('/login')
}
</script>

<template>
  <div class="min-h-screen bg-slate-50">
    <header class="bg-white border-b">
      <div class="max-w-3xl mx-auto px-6 h-14 flex items-center justify-between">
        <span class="font-semibold">Cenkor 用户中心</span>
        <button class="text-sm text-slate-500" @click="logout">登出</button>
      </div>
    </header>
    <main class="max-w-3xl mx-auto px-6 py-10 space-y-6">
      <section class="bg-white rounded-2xl border p-6 space-y-4">
        <h2 class="font-semibold text-lg">个人资料</h2>
        <input v-model="profile.nickname" class="input" placeholder="昵称" />
        <input v-model="profile.email" type="email" class="input" placeholder="邮箱" />
        <button class="btn" @click="saveProfile">保存资料</button>
      </section>
      <section class="bg-white rounded-2xl border p-6 space-y-4">
        <h2 class="font-semibold text-lg">修改密码</h2>
        <input v-model="pwd.old_password" type="password" class="input" placeholder="原密码" />
        <input v-model="pwd.new_password" type="password" class="input" placeholder="新密码" />
        <button class="btn" @click="changePassword">修改密码</button>
      </section>
      <p v-if="msg" class="text-emerald-600 text-sm">{{ msg }}</p>
      <p v-if="err" class="text-red-600 text-sm">{{ err }}</p>
    </main>
  </div>
</template>

<style scoped>
.input { @apply w-full border rounded-lg px-3 py-2; }
.btn { @apply bg-slate-900 text-white rounded-lg px-4 py-2 text-sm font-medium; }
</style>
