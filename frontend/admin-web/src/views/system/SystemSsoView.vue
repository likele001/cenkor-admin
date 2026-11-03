<script setup lang="ts">
/**
 * 系统 → 登录方式
 *
 * 一个页面管三件事：
 * 1. 回调域名：填一次，五个渠道的回调地址自动拼出来
 * 2. 各渠道凭证与开关：微信/抖音/飞书/Google/GitHub 各填各的
 * 3. 每端开放哪些渠道：前台默认全开，后台只允许组织内渠道
 *
 * 凭证保存后不再回显明文，只显示末四位提示 —— 后台页面可能被截图、
 * 被录屏、被非超管看到，明文回显等于把 secret 摊在屏幕上。
 */
import { computed, onMounted, ref } from 'vue'
import { api } from '@/lib/api'

interface ExtraField {
  key: string
  label: string
  type?: 'text' | 'select' | 'checkbox'
  default?: any
  options?: { value: string; label: string }[]
  hint?: string
}

interface ProviderItem {
  key: string
  name: string
  icon: string
  note: string
  supports_pkce: boolean
  admin_allowed: boolean
  enabled: boolean
  configured: boolean
  client_id: string
  client_secret_hint: string
  realms: string[]
  extra: Record<string, any>
  extra_fields: ExtraField[]
  callback_url: string
}

const loading = ref(true)
const saving = ref('')
const baseUrl = ref('')
const portalFrontend = ref('')
const adminFrontend = ref('')
const providers = ref<ProviderItem[]>([])
// 每个渠道的编辑态：secret 单独存，空串表示"不改"
const secrets = ref<Record<string, string>>({})

const anyEnabled = computed(() => providers.value.some((p) => p.enabled && p.configured))

async function load() {
  loading.value = true
  try {
    const { data } = await api.get('/api/v1/sso/providers')
    baseUrl.value = data.base_url || ''
    portalFrontend.value = data.portal_frontend || ''
    adminFrontend.value = data.admin_frontend || ''
    providers.value = data.providers || []
    // 用 extra 的默认值兜底，避免未配置时下拉框是空的
    for (const p of providers.value) {
      for (const f of p.extra_fields) {
        if (p.extra[f.key] === undefined && f.default !== undefined) {
          p.extra[f.key] = f.default
        }
      }
      secrets.value[p.key] = ''
    }
  } catch (e: any) {
    alert(e?.response?.data?.detail || '加载失败')
  } finally {
    loading.value = false
  }
}

async function saveSettings() {
  saving.value = 'settings'
  try {
    await api.put('/api/v1/sso/settings', {
      base_url: baseUrl.value,
      portal_frontend: portalFrontend.value,
      admin_frontend: adminFrontend.value,
    })
    await load()
    alert('已保存')
  } catch (e: any) {
    alert(e?.response?.data?.detail || '保存失败')
  } finally {
    saving.value = ''
  }
}

async function saveProvider(p: ProviderItem) {
  saving.value = p.key
  try {
    const payload: Record<string, any> = {
      enabled: p.enabled,
      client_id: p.client_id,
      realms: p.realms,
      extra: p.extra,
    }
    // 只有真正输入了新密钥才提交，否则后端会当作"清空"
    if (secrets.value[p.key]) payload.client_secret = secrets.value[p.key]
    await api.put(`/api/v1/sso/providers/${p.key}`, payload)
    secrets.value[p.key] = ''
    await load()
  } catch (e: any) {
    alert(e?.response?.data?.detail || '保存失败')
  } finally {
    saving.value = ''
  }
}

function toggleRealm(p: ProviderItem, realm: string) {
  const idx = p.realms.indexOf(realm)
  if (idx >= 0) p.realms.splice(idx, 1)
  else p.realms.push(realm)
}

async function copy(text: string) {
  try {
    await navigator.clipboard.writeText(text)
  } catch {
    // 非 HTTPS 环境下 clipboard API 不可用，退回选中提示
    window.prompt('复制下面这段：', text)
  }
}

onMounted(load)
</script>

<template>
  <div>
    <div class="flex items-center justify-between mb-6">
      <div class="flex items-center gap-2">
        <h1 class="text-2xl font-semibold tracking-tight">🔐 登录方式</h1>
        <span class="text-sm text-ink-400">第三方登录 · 可插拔渠道</span>
      </div>
      <button class="btn-ghost text-sm" :disabled="loading" @click="load">刷新</button>
    </div>

    <!-- 回调域名：五个渠道共用一套拼装规则 -->
    <div class="card p-5 mb-5">
      <div class="flex items-start justify-between mb-4">
        <div>
          <h2 class="font-medium">回调域名</h2>
          <p class="text-sm text-ink-400 mt-1">
            填一次即可，各渠道的回调地址按
            <code class="text-xs bg-ink-50 px-1 rounded">{{ baseUrl }}/api/v1/public/sso/{渠道}/callback</code>
            自动生成。微信和抖音强制 HTTPS 且需备案。
          </p>
        </div>
      </div>
      <div class="grid grid-cols-1 md:grid-cols-3 gap-3">
        <label class="block">
          <span class="text-xs text-ink-400">后端域名（回调基址）</span>
          <input v-model="baseUrl" class="input mt-1" placeholder="https://www.example.com" />
        </label>
        <label class="block">
          <span class="text-xs text-ink-400">前台站点地址</span>
          <input v-model="portalFrontend" class="input mt-1" placeholder="https://www.example.com" />
        </label>
        <label class="block">
          <span class="text-xs text-ink-400">后台站点地址</span>
          <input v-model="adminFrontend" class="input mt-1" placeholder="https://admin.example.com" />
        </label>
      </div>
      <div class="mt-3">
        <button class="btn-primary text-sm" :disabled="saving === 'settings'" @click="saveSettings">
          {{ saving === 'settings' ? '保存中…' : '保存域名' }}
        </button>
      </div>
    </div>

    <!-- 状态提示 -->
    <div
      v-if="!loading && !anyEnabled"
      class="card p-4 mb-5 border-l-4 border-amber-400 bg-amber-50"
    >
      <p class="text-sm text-amber-800">
        还没有任何渠道配置完整。前台登录页此时不会显示第三方按钮，
        账号密码登录不受影响。
      </p>
    </div>

    <!-- 渠道卡片 -->
    <div class="space-y-3">
      <div v-for="p in providers" :key="p.key" class="card p-5">
        <div class="flex items-start justify-between gap-4">
          <div class="flex items-start gap-3 min-w-0">
            <span class="text-2xl leading-none mt-0.5">{{ p.icon }}</span>
            <div class="min-w-0">
              <div class="flex items-center gap-2 flex-wrap">
                <h3 class="font-medium">{{ p.name }}</h3>
                <span
                  v-if="p.configured"
                  class="text-[11px] px-1.5 py-0.5 rounded bg-green-50 text-green-700"
                >已配置</span>
                <span
                  v-else
                  class="text-[11px] px-1.5 py-0.5 rounded bg-ink-50 text-ink-400"
                >未配置</span>
                <span
                  v-if="p.supports_pkce"
                  class="text-[11px] px-1.5 py-0.5 rounded bg-blue-50 text-blue-700"
                >PKCE</span>
              </div>
              <p class="text-sm text-ink-400 mt-1">{{ p.note }}</p>
            </div>
          </div>
          <label class="flex items-center gap-2 shrink-0 cursor-pointer">
            <input v-model="p.enabled" type="checkbox" class="w-4 h-4" />
            <span class="text-sm">启用</span>
          </label>
        </div>

        <div class="grid grid-cols-1 md:grid-cols-2 gap-3 mt-4">
          <label class="block">
            <span class="text-xs text-ink-400">{{ p.key === 'douyin' ? 'Client Key' : 'AppID / Client ID' }}</span>
            <input v-model="p.client_id" class="input mt-1 font-mono text-xs" placeholder="填入开放平台的应用 ID" />
          </label>
          <label class="block">
            <span class="text-xs text-ink-400">
              AppSecret
              <span v-if="p.client_secret_hint" class="text-ink-300">（当前 {{ p.client_secret_hint }}）</span>
            </span>
            <input
              v-model="secrets[p.key]"
              type="password"
              class="input mt-1 font-mono text-xs"
              :placeholder="p.configured ? '留空表示不修改' : '填入应用密钥'"
            />
          </label>
        </div>

        <!-- 渠道特有项：由后端声明，前端只按类型渲染 -->
        <div v-if="p.extra_fields.length" class="grid grid-cols-1 md:grid-cols-2 gap-3 mt-3">
          <label v-for="f in p.extra_fields" :key="f.key" class="block">
            <span class="text-xs text-ink-400">{{ f.label }}</span>
            <select
              v-if="f.type === 'select'"
              v-model="p.extra[f.key]"
              class="input mt-1"
            >
              <option v-for="o in f.options" :key="o.value" :value="o.value">{{ o.label }}</option>
            </select>
            <label v-else-if="f.type === 'checkbox'" class="flex items-center gap-2 mt-2">
              <input v-model="p.extra[f.key]" type="checkbox" class="w-4 h-4" />
              <span class="text-sm text-ink-500">启用</span>
            </label>
            <input v-else v-model="p.extra[f.key]" class="input mt-1" />
            <span v-if="f.hint" class="text-[11px] text-ink-300 block mt-1">{{ f.hint }}</span>
          </label>
        </div>

        <!-- 开放端 -->
        <div class="mt-4 flex items-center gap-4 flex-wrap">
          <span class="text-xs text-ink-400">开放端</span>
          <label class="flex items-center gap-1.5 text-sm">
            <input
              type="checkbox"
              class="w-4 h-4"
              :checked="p.realms.includes('portal')"
              @change="toggleRealm(p, 'portal')"
            />
            前台（客户）
          </label>
          <label
            class="flex items-center gap-1.5 text-sm"
            :class="p.admin_allowed ? '' : 'opacity-40 cursor-not-allowed'"
          >
            <input
              type="checkbox"
              class="w-4 h-4"
              :disabled="!p.admin_allowed"
              :checked="p.realms.includes('admin')"
              @change="toggleRealm(p, 'admin')"
            />
            后台（管理账号）
            <span v-if="!p.admin_allowed" class="text-[11px] text-ink-300">该渠道仅限前台</span>
          </label>
        </div>

        <!-- 回调地址 -->
        <div class="mt-3 flex items-center gap-2 flex-wrap">
          <span class="text-xs text-ink-400 shrink-0">回调地址</span>
          <code class="text-xs font-mono bg-ink-50 px-2 py-1 rounded truncate flex-1 min-w-0">{{ p.callback_url }}</code>
          <button class="btn-ghost text-xs shrink-0" @click="copy(p.callback_url)">复制</button>
        </div>

        <div class="mt-4 flex justify-end">
          <button
            class="btn-primary text-sm"
            :disabled="saving === p.key"
            @click="saveProvider(p)"
          >
            {{ saving === p.key ? '保存中…' : `保存 ${p.name}` }}
          </button>
        </div>
      </div>
    </div>

    <!-- 配置指引 -->
    <div class="card p-5 mt-5">
      <h2 class="font-medium mb-3">在各平台要填什么</h2>
      <table class="w-full text-sm">
        <thead>
          <tr class="text-left text-ink-400 border-b">
            <th class="p-2">渠道</th>
            <th class="p-2">去哪个后台建应用</th>
            <th class="p-2">回调地址填哪里</th>
          </tr>
        </thead>
        <tbody class="text-ink-600">
          <tr class="border-b last:border-0">
            <td class="p-2">微信</td>
            <td class="p-2">微信开放平台 → 网站应用（需企业认证 300元/年）</td>
            <td class="p-2">授权回调域填域名，不带路径</td>
          </tr>
          <tr class="border-b last:border-0">
            <td class="p-2">抖音</td>
            <td class="p-2">抖音开放平台 → 网站应用（需企业主体 + 网站备案）</td>
            <td class="p-2">填完整回调地址</td>
          </tr>
          <tr class="border-b last:border-0">
            <td class="p-2">飞书</td>
            <td class="p-2">飞书开放平台 → 企业自建应用</td>
            <td class="p-2">重定向 URL 填完整地址</td>
          </tr>
          <tr class="border-b last:border-0">
            <td class="p-2">Google</td>
            <td class="p-2">Google Cloud Console → OAuth 客户端 ID</td>
            <td class="p-2">已获授权的重定向 URI 填完整地址</td>
          </tr>
          <tr>
            <td class="p-2">GitHub</td>
            <td class="p-2">GitHub → Settings → Developer settings → OAuth Apps</td>
            <td class="p-2">Authorization callback URL 填完整地址</td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>
