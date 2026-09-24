<script setup lang="ts">
/**
 * 门户「我的应用」页（/my/apps）
 *
 * 承接两件事，都是「官网购买 → 后台安装」闭环里买家侧的可见性：
 * 1. 我买过什么（授权码 / 模式 / 有效期 / 已绑实例数）—— 数据来自 GET /store/account/purchases
 * 2. 我绑定了哪些实例（可随时吊销）—— 数据来自 GET /store/account/instances
 *
 * 注意：此处只展示本账号的数据，接口按门户登录态过滤，不做任何客户端侧筛选。
 */
import { ref, computed, onMounted } from 'vue'
import { RouterLink } from 'vue-router'
import SiteHeader from '@/components/SiteHeader.vue'
import { api } from '@/lib/api'
import { yuanText } from '@/lib/pricing'

interface Purchase {
  license_key: string
  app_key: string
  app_name: string
  model: string
  seats: number
  status: string
  order_id: number | null
  issued_at: string | null
  activated_at: string | null
  expires_at: string | null
  permanent: boolean
  bound_instances: number
  max_instances: number
  bound_domain: string | null
  price?: any
}

interface Instance {
  instance_uid: string
  name: string | null
  instance_url: string | null
  created_at: string | null
  last_seen_at: string | null
  revoked: boolean
}

/** 待付款订单（用户关掉收银台后回来续付的入口） */
interface PendingOrder {
  order_no: string
  app_key: string
  app_name: string
  amount: string
  currency: string
  model: string
  seats: number
  created_at: string | null
  expires_at: string | null
}

const loading = ref(true)
const error = ref('')
const purchases = ref<Purchase[]>([])
const instances = ref<Instance[]>([])
const orders = ref<PendingOrder[]>([])
const copied = ref('')
const revoking = ref('')
const paying = ref('')
const downloading = ref('')

const activeInstances = computed(() => instances.value.filter((i) => !i.revoked))

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
}

function modelText(p: Purchase): string {
  const base = MODEL_LABEL[p.model] || p.model
  return p.model === 'seat' ? `${base} · ${p.seats} 席` : base
}

function statusText(s: string): string {
  return STATUS_LABEL[s] || s
}

/** 授权有效期：买断为永久；否则显示到期日。 */
function validityText(p: Purchase): string {
  if (p.permanent || !p.expires_at) return '永久有效'
  const d = new Date(p.expires_at)
  if (Number.isNaN(d.getTime())) return '—'
  return `至 ${d.toLocaleDateString('zh-CN')}`
}

function priceText(p: Purchase): string {
  const pr = p.price
  if (!pr) return '—'
  const unit = pr.unit_price ?? pr.price
  if (Number(unit ?? 0) <= 0) return '免费'
  return `¥${yuanText(unit)}`
}

function dateText(v: string | null): string {
  if (!v) return '—'
  const d = new Date(v)
  return Number.isNaN(d.getTime()) ? '—' : d.toLocaleString('zh-CN', { dateStyle: 'short', timeStyle: 'short' })
}

async function load() {
  loading.value = true
  error.value = ''
  try {
    const [pur, inst] = await Promise.all([
      api.get('/api/v1/store/account/purchases'),
      api.get('/api/v1/store/account/instances'),
    ])
    purchases.value = pur.data.items || []
    instances.value = inst.data.items || []
  } catch (e: any) {
    error.value = e?.response?.data?.detail || '加载失败，请稍后重试'
  } finally {
    loading.value = false
  }

  // 待付款订单单独拉取：接口异常不应拖垮主内容
  try {
    const { data } = await api.get('/api/v1/store/orders', {
      params: { status: 'pending', page_size: 20 },
    })
    orders.value = data?.items || []
  } catch {
    orders.value = []
  }
}

/** 继续支付：向收银台下单并跳转。 */
async function payAgain(o: PendingOrder) {
  paying.value = o.order_no
  try {
    const { data } = await api.post(`/api/v1/store/orders/${o.order_no}/checkout`, {})
    const url = data?.pay?.cashier_url
    if (!url) {
      alert('未取到收银台地址，请稍后重试')
      return
    }
    window.location.href = url
  } catch (e: any) {
    alert(e?.response?.data?.detail || '发起支付失败')
  } finally {
    paying.value = ''
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

/**
 * 下载官方分发的安装包（离线部署 / 手动安装）。
 *
 * 凭证就是授权码本身 —— 该接口在授权中心侧只校验授权码有效性，不要求先绑定实例，
 * 所以用户买完就能拿到包，不必先有一台实例。
 */
async function downloadPackage(p: Purchase) {
  downloading.value = p.app_key
  try {
    const res = await api.get(`/api/v1/store/cloud/packages/${p.app_key}`, {
      params: { license_key: p.license_key },
      responseType: 'blob',
      timeout: 300_000,
    })
    const version = String(res.headers['x-app-version'] || '')
    const filename = version ? `${p.app_key}-${version}.zip` : `${p.app_key}.zip`
    const url = URL.createObjectURL(res.data as Blob)
    const a = document.createElement('a')
    a.href = url
    a.download = filename
    document.body.appendChild(a)
    a.click()
    a.remove()
    URL.revokeObjectURL(url)
  } catch (e: any) {
    // responseType=blob 时错误体同样是 Blob，得先转文本才拿得到 detail
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

async function revoke(inst: Instance) {
  const label = inst.name || inst.instance_uid
  if (!confirm(`确认吊销实例「${label}」？\n吊销后该实例将无法再下载已购应用，需重新绑定。`)) return
  revoking.value = inst.instance_uid
  try {
    await api.post(`/api/v1/store/account/instances/${inst.instance_uid}/revoke`)
    await load()
  } catch (e: any) {
    alert(e?.response?.data?.detail || '吊销失败')
  } finally {
    revoking.value = ''
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
          <h1 class="text-3xl md:text-4xl font-semibold tracking-tight text-[#111827]">我的应用</h1>
          <p class="mt-3 text-[#6b6e76] leading-relaxed">
            这里汇总你在官方门户购买的应用授权，以及已绑定到本账号的客户实例。
            购买后，在实例后台「应用管理 → 官方应用市场」即可一键下载安装。
          </p>
        </div>

        <div class="mt-8 grid grid-cols-2 md:grid-cols-3 gap-3 max-w-2xl">
          <div class="rounded-xl border border-[#eef0f4] bg-[#fbfcfd] px-4 py-3">
            <div class="text-xl font-semibold text-[#111827]">{{ purchases.length }}</div>
            <div class="mt-0.5 text-[11px] text-[#8b8e96]">已购应用</div>
          </div>
          <div class="rounded-xl border border-[#eef0f4] bg-[#fbfcfd] px-4 py-3">
            <div class="text-xl font-semibold text-[#111827]">{{ activeInstances.length }}</div>
            <div class="mt-0.5 text-[11px] text-[#8b8e96]">已绑定实例</div>
          </div>
          <div class="rounded-xl border border-[#eef0f4] bg-[#fbfcfd] px-4 py-3 col-span-2 md:col-span-1">
            <RouterLink to="/connect" class="text-sm font-medium text-[#4f46e5] hover:underline">
              连接新实例 →
            </RouterLink>
            <div class="mt-0.5 text-[11px] text-[#8b8e96]">在实例后台发起绑定</div>
          </div>
        </div>
      </div>
    </section>

    <section class="container-wide py-8">
      <p v-if="error" class="mb-4 text-sm text-red-600">{{ error }}</p>

      <!-- 待付款订单：关掉收银台后从这里继续支付 -->
      <div v-if="orders.length" class="mb-10">
        <h2 class="text-lg font-semibold text-[#111827] mb-4">待付款订单</h2>
        <div class="space-y-3">
          <div
            v-for="o in orders"
            :key="o.order_no"
            class="bg-white rounded-xl border border-[#fde68a] p-5 flex flex-wrap items-start justify-between gap-3"
          >
            <div class="min-w-0">
              <div class="font-semibold text-[#111827]">{{ o.app_name || o.app_key }}</div>
              <div class="mt-1 text-xs text-[#8b8e96]">订单号 {{ o.order_no }} · 下单 {{ dateText(o.created_at) }}</div>
              <div v-if="o.expires_at" class="mt-0.5 text-xs text-[#b45309]">支付截止 {{ dateText(o.expires_at) }}</div>
            </div>
            <div class="flex items-center gap-4 shrink-0">
              <span class="font-semibold text-[#111827]">¥{{ yuanText(o.amount) }}</span>
              <button
                class="px-3 py-1.5 rounded-lg bg-[#4f46e5] text-white text-xs font-medium hover:bg-[#4338ca] transition-colors disabled:opacity-50"
                :disabled="paying === o.order_no"
                @click="payAgain(o)"
              >{{ paying === o.order_no ? '处理中…' : '继续支付' }}</button>
            </div>
          </div>
        </div>
      </div>

      <!-- 我的授权 -->
      <div class="flex items-center justify-between mb-4">
        <h2 class="text-lg font-semibold text-[#111827]">应用授权</h2>
        <button
          class="text-xs text-[#6b6e76] hover:text-[#111827] transition-colors disabled:opacity-50"
          :disabled="loading"
          @click="load"
        >{{ loading ? '刷新中…' : '刷新' }}</button>
      </div>

      <div v-if="loading" class="text-sm text-[#8b8e96] py-10 text-center">加载中…</div>

      <div v-else-if="!purchases.length" class="bg-white rounded-xl border border-[#e5e7eb] p-10 text-center">
        <p class="text-sm text-[#6b6e76] mb-4">你还没有购买任何应用。</p>
        <RouterLink
          to="/apps"
          class="inline-block px-4 py-2 rounded-lg bg-[#4f46e5] text-white text-sm font-medium hover:bg-[#4338ca] transition-colors"
        >去应用中心看看</RouterLink>
      </div>

      <div v-else class="space-y-3">
        <div
          v-for="p in purchases"
          :key="p.license_key"
          class="bg-white rounded-xl border border-[#e5e7eb] p-5"
        >
          <div class="flex flex-wrap items-start justify-between gap-3">
            <div class="min-w-0">
              <RouterLink
                :to="`/apps/${p.app_key}`"
                class="font-semibold text-[#111827] hover:text-[#4f46e5] transition-colors"
              >{{ p.app_name || p.app_key }}</RouterLink>
              <div class="mt-1.5 flex flex-wrap items-center gap-2">
                <span class="px-2 py-0.5 rounded-md bg-[#eef2ff] text-[11px] text-[#4338ca]">{{ modelText(p) }}</span>
                <span class="px-2 py-0.5 rounded-md bg-[#f3f4f6] text-[11px] text-[#4b5563]">{{ statusText(p.status) }}</span>
                <span class="text-[11px] text-[#8b8e96]">{{ validityText(p) }}</span>
              </div>
            </div>
            <div class="text-right shrink-0">
              <div class="font-semibold text-[#111827]">{{ priceText(p) }}</div>
              <div class="mt-0.5 text-[11px] text-[#8b8e96]">
                实例 {{ p.bound_instances }}/{{ p.max_instances || 1 }}
              </div>
            </div>
          </div>

          <div class="mt-4 pt-4 border-t border-[#f1f3f7] flex flex-wrap items-center gap-x-6 gap-y-2 text-xs">
            <div class="flex items-center gap-2">
              <span class="text-[#9ca3af]">授权码</span>
              <code class="font-mono text-[#374151] tracking-wide">{{ p.license_key }}</code>
              <button
                class="text-[#4f46e5] hover:underline"
                @click="copy(p.license_key)"
              >{{ copied === p.license_key ? '已复制' : '复制' }}</button>
            </div>
            <div class="flex items-center gap-2">
              <span class="text-[#9ca3af]">签发</span>
              <span class="text-[#6b6e76]">{{ dateText(p.issued_at) }}</span>
            </div>
            <div v-if="p.bound_domain" class="flex items-center gap-2">
              <span class="text-[#9ca3af]">绑定域名</span>
              <span class="text-[#6b6e76] break-all">{{ p.bound_domain }}</span>
            </div>
          </div>

          <div class="mt-3 flex flex-wrap items-center gap-3">
            <button
              class="px-3 py-1.5 rounded-lg bg-[#4f46e5] text-white text-xs font-medium hover:bg-[#4338ca] transition-colors disabled:opacity-50"
              :disabled="downloading === p.app_key"
              @click="downloadPackage(p)"
            >{{ downloading === p.app_key ? '下载中…' : '下载安装包' }}</button>
            <span class="text-[11px] text-[#9ca3af]">
              下载后可在实例后台「应用管理 → 上传安装包」安装，或解压到 backend/src/apps/ 下同名目录
            </span>
          </div>
        </div>
      </div>

      <!-- 我的实例 -->
      <div class="flex items-center justify-between mt-10 mb-4">
        <h2 class="text-lg font-semibold text-[#111827]">已绑定实例</h2>
        <RouterLink to="/connect" class="text-xs text-[#4f46e5] hover:underline">连接新实例</RouterLink>
      </div>

      <div v-if="loading" class="text-sm text-[#8b8e96] py-10 text-center">加载中…</div>

      <div v-else-if="!instances.length" class="bg-white rounded-xl border border-[#e5e7eb] p-10 text-center">
        <p class="text-sm text-[#6b6e76] leading-relaxed">
          还没有绑定任何实例。在 cenkor-admin 后台「应用管理 → 官方应用市场」点击
          「连接 Cenkor 账号」获取绑定码，然后在
          <RouterLink to="/connect" class="text-[#4f46e5] hover:underline">连接页</RouterLink>
          确认即可。
        </p>
      </div>

      <div v-else class="space-y-3">
        <div
          v-for="i in instances"
          :key="i.instance_uid"
          class="bg-white rounded-xl border border-[#e5e7eb] p-5 flex flex-wrap items-start justify-between gap-3"
          :class="i.revoked ? 'opacity-60' : ''"
        >
          <div class="min-w-0">
            <div class="flex items-center gap-2">
              <span class="font-semibold text-[#111827]">{{ i.name || '未命名实例' }}</span>
              <span
                class="px-2 py-0.5 rounded-md text-[11px]"
                :class="i.revoked ? 'bg-[#f3f4f6] text-[#6b6e76]' : 'bg-[#ecfdf5] text-[#047857]'"
              >{{ i.revoked ? '已吊销' : '已连接' }}</span>
            </div>
            <div class="mt-1.5 text-xs text-[#8b8e96] break-all">{{ i.instance_url || i.instance_uid }}</div>
            <div class="mt-1 text-xs text-[#9ca3af]">
              绑定于 {{ dateText(i.created_at) }} · 最后活跃 {{ dateText(i.last_seen_at) }}
            </div>
          </div>
          <button
            v-if="!i.revoked"
            class="shrink-0 px-3 py-1.5 rounded-lg border border-[#e5e7eb] text-xs text-[#b91c1c] hover:bg-[#fef2f2] hover:border-[#fecaca] transition-colors disabled:opacity-50"
            :disabled="revoking === i.instance_uid"
            @click="revoke(i)"
          >{{ revoking === i.instance_uid ? '处理中…' : '吊销' }}</button>
        </div>
      </div>
    </section>
  </div>
</template>
