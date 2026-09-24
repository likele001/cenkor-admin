<script setup lang="ts">
/**
 * 门户「确认绑定实例」页（/connect）
 *
 * 客户实例后台点「连接 Cenkor 账号」后会拿到一个一次性绑定码（如 5H4X-RZ6W），
 * 用户在本页输入、或直接点实例给出的带 code 的链接，确认后实例即可换取长期实例令牌。
 * 本页只负责「确认」这一件事，不接触任何实例凭证。
 */
import { ref, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { api } from '@/lib/api'
import { useAuthStore } from '@/stores/auth'

const route = useRoute()
const auth = useAuthStore()

const code = ref('')
const preview = ref<any>(null)
const loading = ref(false)
const error = ref('')
const needsLogin = ref(false)
const done = ref<'' | 'approved' | 'denied'>('')

async function lookup() {
  const c = code.value.trim().toUpperCase()
  if (!c) return
  loading.value = true
  error.value = ''
  needsLogin.value = false
  preview.value = null
  try {
    const { data } = await api.get('/api/v1/store/public/cloud/device/preview', {
      params: { user_code: c },
    })
    preview.value = data
  } catch (e: any) {
    if (e?.response?.status === 401) needsLogin.value = true
    else error.value = e?.response?.data?.detail || '绑定码不存在或已失效'
  } finally {
    loading.value = false
  }
}

async function act(action: 'approve' | 'deny') {
  loading.value = true
  error.value = ''
  try {
    await api.post('/api/v1/store/public/cloud/device/approve', {
      user_code: code.value.trim().toUpperCase(),
      action,
    })
    done.value = action === 'approve' ? 'approved' : 'denied'
  } catch (e: any) {
    if (e?.response?.status === 401) needsLogin.value = true
    else error.value = e?.response?.data?.detail || '操作失败'
  } finally {
    loading.value = false
  }
}

onMounted(() => {
  const q = String(route.query.code || '').trim()
  if (q) {
    code.value = q
    lookup()
  }
})
</script>

<template>
  <div class="min-h-screen bg-[#f8f9fb] font-['Plus_Jakarta_Sans',system-ui,sans-serif]">
    <div class="container-wide py-10">
      <div class="mx-auto max-w-xl">
        <h1 class="text-2xl font-semibold tracking-tight text-[#111827] mb-2">连接 Cenkor 实例</h1>
        <p class="text-sm text-[#6b6e76] mb-6 leading-relaxed">
          在你的 cenkor-admin 后台点击「连接 Cenkor 账号」后会得到一个绑定码，
          在下面输入即可把这台实例绑定到当前账号，之后就能在后台浏览官方应用市场并安装已购应用。
        </p>

        <!-- 结果态 -->
        <div v-if="done === 'approved'" class="bg-white rounded-xl border border-[#e5e7eb] p-6">
          <h2 class="font-semibold text-[#111827] mb-1">✅ 绑定成功</h2>
          <p class="text-sm text-[#6b6e76] leading-relaxed">
            实例「{{ preview?.instance_name || '未命名实例' }}」已绑定到当前账号，
            回到后台即可浏览官方应用市场并下载安装已购应用。
          </p>
        </div>

        <div v-else-if="done === 'denied'" class="bg-white rounded-xl border border-[#e5e7eb] p-6">
          <h2 class="font-semibold text-[#111827] mb-1">已拒绝本次绑定</h2>
          <p class="text-sm text-[#6b6e76]">该实例不会获得任何访问权限。</p>
        </div>

        <template v-else>
          <div class="bg-white rounded-xl border border-[#e5e7eb] p-6">
            <label class="block text-sm font-medium text-[#374151] mb-2">绑定码</label>
            <div class="flex gap-2">
              <input
                v-model="code"
                class="flex-1 px-3 py-2 rounded-lg border border-[#e5e7eb] bg-[#f8f9fb] text-sm font-mono tracking-wider uppercase text-[#111827] focus:outline-none focus:border-[#4f46e5]"
                placeholder="XXXX-XXXX"
                @keyup.enter="lookup"
              />
              <button
                class="px-4 py-2 rounded-lg bg-[#4f46e5] text-white text-sm font-medium hover:bg-[#4338ca] transition-colors disabled:opacity-50"
                :disabled="loading || !code.trim()"
                @click="lookup"
              >{{ loading ? '查询中…' : '查询' }}</button>
            </div>

            <p v-if="needsLogin" class="mt-3 text-sm text-[#b45309]">
              需要先登录门户账号才能确认绑定。
              <router-link to="/login" class="underline">去登录</router-link>
            </p>
            <p v-else-if="error" class="mt-3 text-sm text-red-600">{{ error }}</p>
          </div>

          <div v-if="preview" class="mt-4 bg-white rounded-xl border border-[#e5e7eb] p-6">
            <h2 class="font-semibold text-[#111827] mb-4">确认绑定以下实例？</h2>
            <dl class="text-sm space-y-2 mb-5">
              <div class="flex gap-3">
                <dt class="text-[#9ca3af] w-20 shrink-0">实例名称</dt>
                <dd class="font-medium text-[#111827]">{{ preview.instance_name || '未命名实例' }}</dd>
              </div>
              <div class="flex gap-3">
                <dt class="text-[#9ca3af] w-20 shrink-0">实例地址</dt>
                <dd class="text-[#374151] break-all">{{ preview.instance_url || '—' }}</dd>
              </div>
              <div class="flex gap-3">
                <dt class="text-[#9ca3af] w-20 shrink-0">状态</dt>
                <dd>
                  <span v-if="preview.usable" class="text-[#047857]">可绑定</span>
                  <span v-else class="text-red-600">{{ preview.status }}</span>
                </dd>
              </div>
              <div v-if="auth.user" class="flex gap-3">
                <dt class="text-[#9ca3af] w-20 shrink-0">当前账号</dt>
                <dd class="text-[#374151]">{{ auth.user.email || auth.user.username }}</dd>
              </div>
            </dl>

            <div class="flex gap-2">
              <button
                class="px-4 py-2 rounded-lg bg-[#4f46e5] text-white text-sm font-medium hover:bg-[#4338ca] transition-colors disabled:opacity-50"
                :disabled="loading || !preview.usable"
                @click="act('approve')"
              >确认绑定</button>
              <button
                class="px-4 py-2 rounded-lg border border-[#e5e7eb] text-sm text-[#6b6e76] hover:bg-[#f3f4f6] transition-colors disabled:opacity-50"
                :disabled="loading || !preview.usable"
                @click="act('deny')"
              >拒绝</button>
            </div>
            <p v-if="!preview.usable" class="mt-3 text-xs text-[#9ca3af]">
              该绑定码当前不可用，请回到实例后台重新发起绑定。
            </p>
          </div>
        </template>
      </div>
    </div>
  </div>
</template>
