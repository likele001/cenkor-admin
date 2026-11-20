<script setup lang="ts">
/**
 * 门户「授权管理」页（/my/licenses）
 *
 * 与「我的应用」（/my/apps）的分工：
 * - 我的应用 = 我买过什么（含待付款订单、下载入口）
 * - 授权管理 = 我的授权现在绑在哪台机器上（按授权码聚合，可自助解绑）
 *
 * 数据来自 GET /store/account/licenses；解绑走
 * POST /store/account/licenses/{license_key}/bindings/{binding_id}/unbind。
 * 解绑后该实例心跳会被授权中心拒绝，必须重新填授权码才能恢复。
 */
import { ref, computed, onMounted } from 'vue'
import { RouterLink } from 'vue-router'
import SiteHeader from '@/components/SiteHeader.vue'
import { api } from '@/lib/api'

interface Binding {
  binding_id: number
  instance_fp: string
  fp_short: string
  instance_name: string | null
  instance_url: string | null
  domain: string | null
  version: string | null
  activated_at: string | null
  last_seen_at: string | null
  revoked: boolean
  revoked_at: string | null
}

interface License {
  license_key: string
  app_key: string
  app_name: string
  product: string
  model: string
  seats: number
  status: string
  issued_at: string | null
  activated_at: string | null
  expires_at: string | null
  permanent: boolean
  max_instances: number
  active_instances: number
  bindings: Binding[]
}

const loading = ref(true)
const error = ref('')
const licenses = ref<License[]>([])
const copied = ref('')
const unbinding = ref<number | null>(null)
const downloading = ref('')

const MODEL_LABEL: Record<string, string> = {
  free: '免费',
  one_time: '永久买断',
  seat: '按席位',
}

const STATUS_LABEL: Record<string, string> = {
  issued: '已签发',
  active: '已激活',
  revoked: '已吊销',
  expired: '已过期',
  suspended: '已暂停',
}

const totalBinding = computed(() =>
  licenses.value.reduce((n, l) => n + l.bindings.filter((b) => !b.revoked).length, 0),
)

/** 30 天内到期（买断不算） */
const expiringSoon = computed(() => {
  const now = Date.now()
  const in30 = now + 30 * 24 * 3600 * 1000
  return licenses.value.filter((l) => {
    if (l.permanent || !l.expires_at) return false
    const t = new Date(l.expires_at).getTime()
    return !Number.isNaN(t) && t > now && t <= in30
  }).length
})

function modelText(l: License): string {
  const base = MODEL_LABEL[l.model] || l.model
  return l.model === 'seat' ? `${base} · ${l.seats} 席` : base
}

function statusText(s: string): string {
  return STATUS_LABEL[s] || s
}

function validityText(l: License): string {
  if (l.permanent || !l.expires_at) return '永久有效'
  const d = new Date(l.expires_at)
  if (Number.isNaN(d.getTime())) return '—'
  return `至 ${d.toLocaleDateString('zh-CN')}`
}

function dateText(v: string | null): string {
  if (!v) return '—'
  const d = new Date(v)
  return Number.isNaN(d.getTime())
    ? '—'
    : d.toLocaleString('zh-CN', { dateStyle: 'short', timeStyle: 'short' })
}

async function load() {
  loading.value = true
  error.value = ''
  try {
    const { data } = await api.get('/api/v1/store/account/licenses')
    licenses.value = data.items || []
  } catch (e: any) {
    error.value = e?.response?.data?.detail || '加载失败，请稍后重试'
  } finally {
    loading.value = false
  }
}

async function copy(text: string) {
  try {
    await navigator.clipboard.writeText(text)
    copied.value = text
    window.setTimeout(() => {
      if (copied.value === text) copied.value = ''
    }, 1500)
  } catch {
    /* 剪贴板不可用（非 HTTPS / 权限拒绝）时静默忽略 */
  }
}

async function unbind(lic: License, b: Binding) {
  const label = b.instance_name || b.domain || b.fp_short
  if (
    !confirm(
      `确认解绑「${label}」？\n解绑后该实例会在下次心跳时失效，需要在实例后台重新填写授权码才能恢复。`,
    )
  )
    return
  unbinding.value = b.binding_id
  try {
    await api.post(
      `/api/v1/store/account/licenses/${lic.license_key}/bindings/${b.binding_id}/unbind`,
    )
    await load()
  } catch (e: any) {
    alert(e?.response?.data?.detail || '解绑失败')
  } finally {
    unbinding.value = null
  }
}

/** 下载官方分发的安装包（授权码即凭证，不要求已绑定实例） */
async function downloadPackage(l: License) {
  downloading.value = l.app_key
  try {
    const res = await api.get(`/api/v1/store/cloud/packages/${l.app_key}`, {
      params: { license_key: l.license_key },
      responseType: 'blob',
      timeout: 300_000,
    })
    const version = String(res.headers['x-app-version'] || '')
    const filename = version ? `${l.app_key}-${version}.zip` : `${l.app_key}.zip`
    const url = URL.createObjectURL(res.data as Blob)
    const a = document.createElement('a')
    a.href = url
    a.download = filename
    document.body.appendChild(a)
    a.click()
    a.remove()
    URL.revokeObjectURL(url)
  } catch (e: any) {
    let msg = '下载失败，请稍后重试'
    const d = e?.response?.data
    if (d instanceof Blob) {
      try {
        const parsed = JSON.parse(await d.text())
        if (parsed?.detail) msg = parsed.detail
      } catch {
        /* 非 JSON 错误体，保留默认文案 */
      }
    } else if (d?.detail) {
      msg = d.detail
    } else if (e?.message) {
      msg = e.message
    }
    alert(msg)
  } finally {
    downloading.value = ''
  }
}

onMounted(load)
</script>

<template>
  <div class="min-h-screen bg-[#f8f9fb] font-['Plus_Jakarta_Sans',system-ui,sans-serif]">
    <SiteHeader />

    <section class="bg-white border-b border-[#eef0f4]">
      <div class="container-wide py-12">
        <div class="max-w-3xl">
          <h1 class="text-3xl md:text-4xl font-semibold tracking-tight text-[#111827]">授权管理</h1>
          <p class="mt-3 text-[#6b6e76] leading-relaxed">
            管理你购买的软件授权：查看授权码、当前绑定的实例，换机时可直接解绑旧设备。
            解绑后旧实例会在下次心跳时失效，在新实例后台重新填写授权码即可恢复。
          </p>
          <div class="mt-4 flex flex-wrap items-center gap-3 text-xs">
            <RouterLink to="/my/apps" class="text-[#4f46e5] hover:underline">我的应用 →</RouterLink>
            <RouterLink to="/apps" class="text-[#4f46e5] hover:underline">应用中心 →</RouterLink>
          </div>
        </div>

        <div class="mt-8 grid grid-cols-3 gap-3 max-w-2xl">
          <div class="rounded-xl border border-[#eef0f4] bg-[#fbfcfd] px-4 py-3">
            <div class="text-xl font-semibold text-[#111827]">{{ licenses.length }}</div>
            <div class="mt-0.5 text-[11px] text-[#8b8e96]">授权总数</div>
          </div>
          <div class="rounded-xl border border-[#eef0f4] bg-[#fbfcfd] px-4 py-3">
            <div class="text-xl font-semibold text-[#111827]">{{ totalBinding }}</div>
            <div class="mt-0.5 text-[11px] text-[#8b8e96]">已绑实例</div>
          </div>
          <div class="rounded-xl border border-[#eef0f4] bg-[#fbfcfd] px-4 py-3">
            <div class="text-xl font-semibold" :class="expiringSoon ? 'text-[#b45309]' : 'text-[#111827]'">
              {{ expiringSoon }}
            </div>
            <div class="mt-0.5 text-[11px] text-[#8b8e96]">30 天内到期</div>
          </div>
        </div>
      </div>
    </section>

    <section class="container-wide py-8">
      <p v-if="error" class="mb-4 text-sm text-red-600">{{ error }}</p>

      <div
        v-if="!loading && expiringSoon"
        class="mb-4 rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800"
      >
        有 <span class="font-semibold">{{ expiringSoon }}</span> 个授权将在 30 天内到期，
        到期后对应应用的接口会返回 402，请提前续费。
      </div>

      <div class="flex items-center justify-between mb-4">
        <h2 class="text-lg font-semibold text-[#111827]">我的授权</h2>
        <button
          class="text-xs text-[#6b6e76] hover:text-[#111827] transition-colors disabled:opacity-50"
          :disabled="loading"
          @click="load"
        >{{ loading ? '刷新中…' : '刷新' }}</button>
      </div>

      <div v-if="loading" class="text-sm text-[#8b8e96] py-10 text-center">加载中…</div>

      <div v-else-if="!licenses.length" class="bg-white rounded-xl border border-[#e5e7eb] p-10 text-center">
        <p class="text-sm text-[#6b6e76] mb-4">还没有可管理的授权。</p>
        <RouterLink
          to="/apps"
          class="inline-block px-4 py-2 rounded-lg bg-[#4f46e5] text-white text-sm font-medium hover:bg-[#4338ca] transition-colors"
        >去应用中心看看</RouterLink>
      </div>

      <div v-else class="space-y-4">
        <div
          v-for="l in licenses"
          :key="l.license_key"
          class="bg-white rounded-xl border border-[#e5e7eb] p-5"
        >
          <div class="flex flex-wrap items-start justify-between gap-3">
            <div class="min-w-0">
              <RouterLink
                :to="`/apps/${l.app_key}`"
                class="font-semibold text-[#111827] hover:text-[#4f46e5] transition-colors"
              >{{ l.app_name || l.app_key }}</RouterLink>
              <div class="mt-1.5 flex flex-wrap items-center gap-2">
                <span class="px-2 py-0.5 rounded-md bg-[#eef2ff] text-[11px] text-[#4338ca]">{{ modelText(l) }}</span>
                <span class="px-2 py-0.5 rounded-md bg-[#f3f4f6] text-[11px] text-[#4b5563]">{{ statusText(l.status) }}</span>
                <span class="text-[11px] text-[#8b8e96]">{{ validityText(l) }}</span>
              </div>
            </div>
            <div class="text-right shrink-0">
              <div class="text-sm font-medium text-[#111827]">
                {{ l.active_instances }}/{{ l.max_instances || 1 }}
                <span class="text-[11px] font-normal text-[#8b8e96]">台实例</span>
              </div>
              <div class="mt-0.5 text-[11px] text-[#9ca3af]">签发 {{ dateText(l.issued_at) }}</div>
            </div>
          </div>

          <div class="mt-4 pt-4 border-t border-[#f1f3f7] flex flex-wrap items-center gap-x-6 gap-y-2 text-xs">
            <div class="flex items-center gap-2">
              <span class="text-[#9ca3af]">授权码</span>
              <code class="font-mono text-[#374151] tracking-wide">{{ l.license_key }}</code>
              <button class="text-[#4f46e5] hover:underline" @click="copy(l.license_key)">
                {{ copied === l.license_key ? '已复制' : '复制' }}
              </button>
            </div>
            <button
              class="text-[#4f46e5] hover:underline disabled:opacity-50"
              :disabled="downloading === l.app_key"
              @click="downloadPackage(l)"
            >{{ downloading === l.app_key ? '下载中…' : '下载安装包' }}</button>
          </div>

          <!-- 绑定明细 -->
          <div class="mt-4">
            <div class="text-xs text-[#9ca3af] mb-2">实例绑定</div>
            <div v-if="!l.bindings.length" class="text-xs text-[#8b8e96] bg-[#fbfcfd] border border-dashed border-[#e5e7eb] rounded-lg px-3 py-3">
              尚未激活。在实例后台「应用管理 → 官方应用市场」填入上面的授权码即可绑定。
            </div>
            <div v-else class="divide-y divide-[#f1f3f7]">
              <div
                v-for="b in l.bindings"
                :key="b.binding_id"
                class="py-2.5 flex flex-wrap items-center justify-between gap-3"
                :class="b.revoked ? 'opacity-60' : ''"
              >
                <div class="min-w-0">
                  <div class="flex items-center gap-2">
                    <span class="text-sm text-[#111827]">{{ b.instance_name || b.domain || b.fp_short }}</span>
                    <span
                      class="px-2 py-0.5 rounded-md text-[11px]"
                      :class="b.revoked ? 'bg-[#f3f4f6] text-[#6b6e76]' : 'bg-[#ecfdf5] text-[#047857]'"
                    >{{ b.revoked ? '已解绑' : '已连接' }}</span>
                  </div>
                  <div class="mt-0.5 text-[11px] text-[#9ca3af] break-all">
                    {{ b.domain || b.instance_url || '未上报域名' }} · 指纹 {{ b.fp_short }}<template v-if="b.version"> · v{{ b.version }}</template>
                  </div>
                  <div class="mt-0.5 text-[11px] text-[#9ca3af]">
                    激活 {{ dateText(b.activated_at) }} · 最后心跳 {{ dateText(b.last_seen_at) }}
                  </div>
                </div>
                <button
                  v-if="!b.revoked"
                  class="shrink-0 px-3 py-1.5 rounded-lg border border-[#e5e7eb] text-xs text-[#b91c1c] hover:bg-[#fef2f2] hover:border-[#fecaca] transition-colors disabled:opacity-50"
                  :disabled="unbinding === b.binding_id"
                  @click="unbind(l, b)"
                >{{ unbinding === b.binding_id ? '处理中…' : '解绑' }}</button>
              </div>
            </div>
          </div>
        </div>
      </div>
    </section>
  </div>
</template>
