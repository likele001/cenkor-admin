<script setup lang="ts">
/**
 * 应用市场 · 订单管理（商店订单 + 支付订单）。
 *
 * 后端接口：
 *  GET    /api/v1/store/orders           商店订单（应用中心，app_orders）
 *  GET    /api/v1/payment/orders         支付订单（支付中心，pay_orders）
 *  POST   {前缀}/{单号}/cancel|pay|refund|archive|unarchive     商店订单动作
 *  POST   /api/v1/payment/orders/{单号}/close|sync|archive|unarchive  支付订单动作
 *  DELETE {前缀}/{单号}                  删除（分层，见下）
 *  POST   {前缀}/orders/cleanup          批量清理，默认 dry_run
 *
 * 删除语义与后端保持同一口径：
 *  · 待支付 / 已取消 / 已过期（且没签发过授权）→ 允许物理删除
 *  · 已支付 / 已退款 → 只能「作废隐藏」，账目、分账、授权必须留痕
 * 「作废」只写标记不改状态，所以市场总览的统计不会因为清理而变形。
 */
import { ref, computed, onMounted, watch } from 'vue'
import { api } from '@/lib/api'
import { ORDER_LABEL, ORDER_CLASS, fmtTime, errText, localToIso, yuan } from '@/lib/market'

type Tab = 'store' | 'pay'
const tab = ref<Tab>('store')

const STORE_STATUS = ['pending', 'paid', 'cancelled', 'refunded', 'expired']
const PAY_STATUS = ['pending', 'paid', 'closed', 'failed', 'refunded', 'partial_refunded']
const PAY_LABEL: Record<string, string> = {
  pending: '待支付', paid: '已支付', closed: '已关闭',
  failed: '失败', refunded: '已退款', partial_refunded: '部分退款',
}
const PAY_CLASS: Record<string, string> = {
  pending: 'bg-amber-50 text-amber-600', paid: 'bg-emerald-50 text-emerald-600',
  closed: 'bg-ink-100 text-ink-500', failed: 'bg-red-50 text-red-600',
  refunded: 'bg-red-50 text-red-600', partial_refunded: 'bg-orange-50 text-orange-600',
}

const prefix = computed(() => (tab.value === 'store' ? '/api/v1/store/orders' : '/api/v1/payment/orders'))
const keyField = computed(() => (tab.value === 'store' ? 'order_no' : 'out_trade_no'))

// ---------------- 列表 ----------------
const loading = ref(true)
const error = ref('')
const items = ref<any[]>([])
const total = ref(0)
const page = ref(1)
const pageSize = 20

const keyword = ref('')
const status = ref('')
const appKey = ref('')
const sceneKey = ref('')
const showArchived = ref(false)
const dateFrom = ref('')
const dateTo = ref('')

const scenes = ref<{ scene_key: string; name: string }[]>([])

async function loadScenes() {
  try {
    const { data } = await api.get('/api/v1/payment/scenes')
    scenes.value = (data?.items ?? []).map((s: any) => ({
      scene_key: s.scene_key ?? s.key ?? s,
      name: s.name ?? s.scene_key ?? s.key ?? s,
    }))
  } catch {
    scenes.value = []   // 支付中心没装就不显示这个筛选器
  }
}

async function load() {
  loading.value = true
  error.value = ''
  try {
    const params: Record<string, any> = {
      page: page.value, page_size: pageSize,
      keyword: keyword.value.trim() || undefined,
      status: status.value || undefined,
      date_from: localToIso(dateFrom.value) || undefined,
      date_to: localToIso(dateTo.value) || undefined,
    }
    if (showArchived.value) params.include_archived = true
    if (tab.value === 'store') params.app_key = appKey.value.trim() || undefined
    else params.scene_key = sceneKey.value || undefined

    const { data } = await api.get(prefix.value, { params })
    items.value = data?.items ?? []
    total.value = data?.total ?? 0
  } catch (e: any) {
    error.value = errText(e)
  } finally {
    loading.value = false
  }
}

const totalPages = computed(() => Math.max(1, Math.ceil(total.value / pageSize)))

function resetAndLoad() { page.value = 1; load() }

onMounted(() => { load(); loadScenes() })
watch(tab, () => {
  status.value = ''; keyword.value = ''; page.value = 1; showArchived.value = false; load()
})
watch(page, load)
watch([status, sceneKey], resetAndLoad)

// ---------------- 弹层通用 ----------------
const busy = ref('')
const toast = ref('')
function flash(msg: string) {
  toast.value = msg
  setTimeout(() => { if (toast.value === msg) toast.value = '' }, 2600)
}

async function act(url: string, method: 'post' | 'delete' = 'post', body: any = {}) {
  busy.value = url
  try {
    if (method === 'delete') await api.delete(url, { data: body })
    else await api.post(url, body)
    flash('已完成')
    await load()
    return true
  } catch (e: any) {
    flash(errText(e))
    return false
  } finally {
    busy.value = ''
  }
}

function keyOf(row: any) { return row[keyField.value] }

// ---------------- 作废弹层 ----------------
const showArchive = ref(false)
const archiveTarget = ref<any>(null)
const archiveReason = ref('')
const archiveError = ref('')

function openArchive(row: any) {
  archiveTarget.value = row
  archiveReason.value = ''
  archiveError.value = ''
  showArchive.value = true
}

async function submitArchive() {
  if (!archiveReason.value.trim()) { archiveError.value = '请填写作废原因（会记进订单，事后好查）'; return }
  const ok = await act(`${prefix.value}/${keyOf(archiveTarget.value)}/archive`, 'post', { reason: archiveReason.value.trim() })
  if (ok) showArchive.value = false
}

// ---------------- 删除（分层） ----------------
const showDelete = ref(false)
const deleteTarget = ref<any>(null)
const deleteForce = ref(false)
const deleteError = ref('')

function openDelete(row: any) {
  deleteTarget.value = row
  deleteForce.value = false
  deleteError.value = ''
  showDelete.value = true
}

async function submitDelete() {
  const ok = await act(`${prefix.value}/${keyOf(deleteTarget.value)}`, 'delete', { force: deleteForce.value })
  if (ok) showDelete.value = false
}

// ---------------- 退款弹层（商店订单：整单退；支付订单：可指定金额） ----------------
const showRefund = ref(false)
const refundTarget = ref<any>(null)
const refundYuan = ref('')
const refundReason = ref('')
const refundError = ref('')

function openRefund(row: any) {
  refundTarget.value = row
  refundYuan.value = (Number(row.amount_cents || 0) / 100).toFixed(2)
  refundReason.value = ''
  refundError.value = ''
  showRefund.value = true
}

async function submitRefund() {
  const cents = Math.round((parseFloat(refundYuan.value) || 0) * 100)
  if (cents <= 0) { refundError.value = '退款金额必须大于 0'; return }
  if (!refundReason.value.trim()) { refundError.value = '请填写退款原因'; return }
  const body = tab.value === 'store'
    ? { reason: refundReason.value.trim() }
    : { amount_cents: cents, reason: refundReason.value.trim() }
  const ok = await act(`${prefix.value}/${keyOf(refundTarget.value)}/refund`, 'post', body)
  if (ok) showRefund.value = false
}

// ---------------- 详情 ----------------
const showDetail = ref(false)
const detail = ref<any>(null)
const detailRow = ref<any>(null)

async function openDetail(row: any) {
  detailRow.value = row
  detail.value = null
  showDetail.value = true
  try {
    const { data } = await api.get(`${prefix.value}/${keyOf(row)}`)
    detail.value = data
  } catch (e: any) {
    detail.value = { error: errText(e) }
  }
}

// ---------------- 批量清理 ----------------
const showCleanup = ref(false)
const cleanMode = ref<'archive' | 'delete'>('archive')
const cleanMinutes = ref(1440)
const cleanStatuses = ref<string[]>([])
const cleanPreview = ref<any>(null)
const cleanError = ref('')
const cleanBusy = ref(false)

const cleanupOptions = computed(() => (tab.value === 'store' ? STORE_STATUS : PAY_STATUS))

function openCleanup() {
  cleanMode.value = 'archive'
  cleanMinutes.value = 1440
  cleanStatuses.value = tab.value === 'store' ? ['pending', 'cancelled', 'expired'] : ['pending', 'closed', 'failed']
  cleanPreview.value = null
  cleanError.value = ''
  showCleanup.value = true
}

async function runCleanup(exec: boolean) {
  cleanBusy.value = true
  cleanError.value = ''
  try {
    const { data } = await api.post(`${prefix.value}/cleanup`, {
      dry_run: !exec,
      mode: cleanMode.value,
      older_than_minutes: Number(cleanMinutes.value) || 0,
      statuses: cleanStatuses.value,
    })
    cleanPreview.value = data
    if (exec) { flash(`已${cleanMode.value === 'delete' ? '删除' : '作废'} ${data.processed} 条`); await load() }
  } catch (e: any) {
    cleanError.value = errText(e)
    cleanPreview.value = null
  } finally {
    cleanBusy.value = false
  }
}
</script>

<template>
  <div class="space-y-4">
    <div class="card">
      <div class="flex flex-wrap items-center justify-between gap-3 pb-4 border-b border-ink-200">
        <div>
          <h2 class="font-semibold">订单管理</h2>
          <p class="text-xs text-ink-500 mt-1">
            共 {{ total }} 条 · 未付款的单可直接删除，已付款的只能作废隐藏（账目留痕）
          </p>
        </div>
        <div class="flex gap-2">
          <button
            class="btn-outline !py-1.5"
            :class="{ '!bg-ink-900 !text-white !border-ink-900': tab === 'store' }"
            @click="tab = 'store'"
          >商店订单</button>
          <button
            class="btn-outline !py-1.5"
            :class="{ '!bg-ink-900 !text-white !border-ink-900': tab === 'pay' }"
            @click="tab = 'pay'"
          >支付订单</button>
          <button class="btn-ghost !py-1.5" @click="openCleanup">批量清理</button>
        </div>
      </div>

      <div class="flex flex-wrap gap-2 py-4 border-b border-ink-100">
        <input v-model="keyword" class="input !w-56" placeholder="单号 / 应用 / 买家 / 标题" @keyup.enter="resetAndLoad" />
        <select v-model="status" class="input !w-32">
          <option value="">全部状态</option>
          <option v-for="s in (tab === 'store' ? STORE_STATUS : PAY_STATUS)" :key="s" :value="s">
            {{ (tab === 'store' ? ORDER_LABEL : PAY_LABEL)[s] }}
          </option>
        </select>
        <input v-if="tab === 'store'" v-model="appKey" class="input !w-40" placeholder="应用 key" @keyup.enter="resetAndLoad" />
        <select v-else-if="scenes.length" v-model="sceneKey" class="input !w-40">
          <option value="">全部业务场景</option>
          <option v-for="s in scenes" :key="s.scene_key" :value="s.scene_key">{{ s.name }}</option>
        </select>
        <input v-model="dateFrom" type="datetime-local" class="input !w-52" />
        <input v-model="dateTo" type="datetime-local" class="input !w-52" />
        <label class="inline-flex items-center gap-2 text-sm text-ink-600 px-1">
          <input v-model="showArchived" type="checkbox" /><span>含已作废</span>
        </label>
        <button class="btn-primary !py-1.5" @click="resetAndLoad">查询</button>
      </div>

      <div v-if="loading" class="p-6 text-sm text-ink-500">加载中…</div>
      <div v-else-if="error" class="p-8 text-center">
        <p class="text-red-600 text-sm mb-4">{{ error }}</p>
        <button class="btn-primary" @click="load">重新加载</button>
      </div>
      <div v-else-if="!items.length" class="p-10 text-center text-sm text-ink-500">没有符合条件的订单</div>

      <table v-else class="w-full text-sm">
        <thead class="text-left text-ink-500 border-b border-ink-200">
          <tr>
            <th class="px-3 py-2 font-normal">单号</th>
            <th class="px-3 py-2 font-normal">标的</th>
            <th class="px-3 py-2 font-normal">买家 / 场景</th>
            <th class="px-3 py-2 font-normal text-right">金额</th>
            <th class="px-3 py-2 font-normal">状态</th>
            <th class="px-3 py-2 font-normal">时间</th>
            <th class="px-3 py-2 font-normal text-right">操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="row in items" :key="keyOf(row)" class="border-b border-ink-100 last:border-0">
            <td class="px-3 py-3">
              <div class="font-medium">{{ keyOf(row) }}</div>
              <div v-if="tab === 'store' && row.channel" class="text-xs text-ink-400">{{ row.channel }}</div>
              <div v-else-if="row.provider" class="text-xs text-ink-400">{{ row.provider }} · {{ row.sub_type }}</div>
            </td>
            <td class="px-3 py-3">
              <div>{{ tab === 'store' ? (row.app_name || row.app_key) : row.subject }}</div>
              <div v-if="tab === 'store'" class="text-xs text-ink-400">{{ row.app_key }} · {{ row.seats }} 席</div>
              <div v-else-if="row.biz_id" class="text-xs text-ink-400">业务单 {{ row.biz_id }}</div>
            </td>
            <td class="px-3 py-3">
              <div>{{ row.buyer_name || row.buyer_email || '—' }}</div>
              <div class="text-xs text-ink-400">{{ tab === 'store' ? row.buyer_type : row.scene_key }}</div>
            </td>
            <td class="px-3 py-3 text-right font-medium">{{ yuan(row.amount_cents) }}</td>
            <td class="px-3 py-3">
              <span
                class="text-xs px-1.5 py-0.5 rounded"
                :class="(tab === 'store' ? ORDER_CLASS : PAY_CLASS)[row.status] || 'bg-ink-100 text-ink-500'"
              >{{ (tab === 'store' ? ORDER_LABEL : PAY_LABEL)[row.status] || row.status }}</span>
              <div v-if="row.archived_at" class="text-xs text-ink-400 mt-1">已作废</div>
            </td>
            <td class="px-3 py-3">
              <div class="text-xs">{{ fmtTime(row.created_at) }}</div>
              <div v-if="row.paid_at" class="text-xs text-emerald-600 mt-1">付款 {{ fmtTime(row.paid_at) }}</div>
            </td>
            <td class="px-3 py-3 text-right whitespace-nowrap">
              <button class="text-xs text-blue-600 hover:text-blue-800 mr-2" @click="openDetail(row)">详情</button>

              <template v-if="!row.archived_at">
                <button
                  v-if="tab === 'store' && row.status === 'pending'"
                  class="text-xs text-ink-600 hover:text-ink-900 mr-2"
                  :disabled="!!busy"
                  @click="act(`${prefix}/${keyOf(row)}/cancel`)"
                >取消</button>
                <button
                  v-if="tab === 'store' && row.status === 'pending'"
                  class="text-xs text-ink-600 hover:text-ink-900 mr-2"
                  :disabled="!!busy"
                  @click="act(`${prefix}/${keyOf(row)}/pay`, 'post', { channel: 'manual' })"
                >确认收款</button>
                <button
                  v-if="tab === 'pay' && row.status === 'pending'"
                  class="text-xs text-ink-600 hover:text-ink-900 mr-2"
                  :disabled="!!busy"
                  @click="act(`${prefix}/${keyOf(row)}/sync`)"
                >查单</button>
                <button
                  v-if="tab === 'pay' && row.status === 'pending'"
                  class="text-xs text-ink-600 hover:text-ink-900 mr-2"
                  :disabled="!!busy"
                  @click="act(`${prefix}/${keyOf(row)}/close`)"
                >关闭</button>
                <button
                  v-if="row.status === 'paid' || row.status === 'partial_refunded'"
                  class="text-xs text-orange-600 hover:text-orange-800 mr-2"
                  @click="openRefund(row)"
                >退款</button>
                <button
                  class="text-xs text-ink-500 hover:text-ink-800 mr-2"
                  :disabled="!!busy"
                  @click="openArchive(row)"
                >作废</button>
                <button
                  v-if="row.deletable"
                  class="text-xs text-red-600 hover:text-red-800"
                  @click="openDelete(row)"
                >删除</button>
              </template>
              <button
                v-else
                class="text-xs text-ink-500 hover:text-ink-800"
                :disabled="!!busy"
                @click="act(`${prefix}/${keyOf(row)}/unarchive`)"
              >取消作废</button>
            </td>
          </tr>
        </tbody>
      </table>

      <div v-if="totalPages > 1" class="flex items-center justify-between pt-4 text-sm">
        <span class="text-ink-500">共 {{ total }} 条</span>
        <div class="flex items-center gap-2">
          <button class="btn-outline !py-1 !px-3" :disabled="page <= 1" @click="page--">上一页</button>
          <span class="text-ink-500">{{ page }} / {{ totalPages }}</span>
          <button class="btn-outline !py-1 !px-3" :disabled="page >= totalPages" @click="page++">下一页</button>
        </div>
      </div>
    </div>

    <p v-if="toast" class="text-sm text-ink-700 bg-ink-50 border border-ink-200 rounded-lg px-3 py-2">{{ toast }}</p>

    <!-- 详情 -->
    <div v-if="showDetail" class="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4" @click.self="showDetail = false">
      <div class="bg-white rounded-2xl w-full max-w-2xl shadow-xl max-h-[85vh] overflow-auto">
        <div class="px-5 py-4 border-b border-ink-200 flex items-center justify-between">
          <div>
            <h3 class="font-semibold">订单详情</h3>
            <p class="text-xs text-ink-500 mt-0.5">{{ detailRow ? keyOf(detailRow) : '' }}</p>
          </div>
          <button class="text-ink-400 hover:text-ink-900" @click="showDetail = false">✕</button>
        </div>
        <div class="px-5 py-4 text-sm space-y-3">
          <div v-if="!detail" class="text-ink-500">加载中…</div>
          <div v-else-if="detail.error" class="text-red-600">{{ detail.error }}</div>
          <template v-else>
            <div class="rounded-xl bg-ink-50 border border-ink-200 p-3 text-xs text-ink-600 grid grid-cols-2 gap-y-1">
              <div>状态：{{ detail.status || detailRow?.status }}</div>
              <div>金额：{{ yuan(detail.amount_cents ?? detailRow?.amount_cents) }}</div>
              <div>创建：{{ fmtTime(detail.created_at || detailRow?.created_at) }}</div>
              <div>付款：{{ fmtTime(detail.paid_at || detailRow?.paid_at) }}</div>
              <div v-if="detail.biz_id">业务单：{{ detail.biz_id }}</div>
              <div v-if="detail.trade_no">网关单号：{{ detail.trade_no }}</div>
              <div v-if="detail.expire_at">失效时间：{{ fmtTime(detail.expire_at) }}</div>
              <div v-if="detail.return_url" class="col-span-2">回跳：{{ detail.return_url }}</div>
              <div v-if="detail.refunds?.length" class="col-span-2">
                退款：{{ detail.refunds.length }} 笔，合计 {{ yuan(detail.refunds.reduce((s: number, r: any) => s + (r.amount_cents || 0), 0)) }}
              </div>
              <div v-if="detail.notify_count !== undefined">回调次数：{{ detail.notify_count }}</div>
            </div>

            <div v-if="detail.order">
              <p class="text-xs text-ink-500 mb-1">商店订单字段</p>
              <pre class="text-xs bg-ink-50 rounded-lg p-3 overflow-auto">{{ JSON.stringify(detail.order, null, 2) }}</pre>
            </div>
            <div v-if="detail.license">
              <p class="text-xs text-ink-500 mb-1">已签发授权</p>
              <pre class="text-xs bg-ink-50 rounded-lg p-3 overflow-auto">{{ JSON.stringify({ ...detail.license, token: undefined }, null, 2) }}</pre>
            </div>
            <div v-if="detail.pay_orders?.length">
              <p class="text-xs text-ink-500 mb-1">关联支付单（{{ detail.pay_orders.length }} 笔）</p>
              <div class="space-y-1">
                <div
                  v-for="p in detail.pay_orders"
                  :key="p.out_trade_no"
                  class="flex items-center justify-between text-xs border border-ink-100 rounded-lg px-3 py-2"
                >
                  <span class="font-mono">{{ p.out_trade_no }}</span>
                  <span class="text-ink-500">{{ PAY_LABEL[p.status] || p.status }} · {{ yuan(p.amount_cents) }}</span>
                  <span v-if="p.archived_at" class="text-ink-400">已作废</span>
                </div>
              </div>
            </div>
            <div v-if="detail.notify_logs?.length">
              <p class="text-xs text-ink-500 mb-1">最近回调（{{ detail.notify_logs.length }} 条）</p>
              <div class="space-y-1">
                <div v-for="lg in detail.notify_logs" :key="lg.id" class="text-xs border border-ink-100 rounded-lg px-3 py-2 flex gap-3">
                  <span class="text-ink-400">{{ fmtTime(lg.created_at) }}</span>
                  <span>{{ lg.direction }}</span>
                  <span :class="lg.verified ? 'text-emerald-600' : 'text-red-600'">{{ lg.verified ? '验签通过' : '验签失败' }}</span>
                  <span v-if="lg.error" class="text-red-600 truncate">{{ lg.error }}</span>
                </div>
              </div>
            </div>
          </template>
        </div>
        <div class="px-5 py-4 border-t border-ink-200 flex justify-end">
          <button class="btn-ghost" @click="showDetail = false">关闭</button>
        </div>
      </div>
    </div>

    <!-- 作废 -->
    <div v-if="showArchive" class="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4" @click.self="showArchive = false">
      <div class="bg-white rounded-2xl w-full max-w-md shadow-xl">
        <div class="px-5 py-4 border-b border-ink-200">
          <h3 class="font-semibold">作废订单</h3>
          <p class="text-xs text-ink-500 mt-0.5">{{ archiveTarget ? keyOf(archiveTarget) : '' }} · 只从列表隐藏，状态与账目不动</p>
        </div>
        <div class="px-5 py-4 space-y-3">
          <textarea v-model="archiveReason" rows="2" class="input" placeholder="作废原因（必填），如：重复下单 / 买家放弃"></textarea>
          <p v-if="archiveError" class="text-sm text-red-600">{{ archiveError }}</p>
        </div>
        <div class="px-5 py-4 border-t border-ink-200 flex justify-end gap-2">
          <button class="btn-ghost" @click="showArchive = false">取消</button>
          <button class="btn-primary" :disabled="!!busy" @click="submitArchive">确认作废</button>
        </div>
      </div>
    </div>

    <!-- 删除 -->
    <div v-if="showDelete" class="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4" @click.self="showDelete = false">
      <div class="bg-white rounded-2xl w-full max-w-md shadow-xl">
        <div class="px-5 py-4 border-b border-ink-200">
          <h3 class="font-semibold text-red-700">删除订单（不可恢复）</h3>
          <p class="text-xs text-ink-500 mt-0.5">{{ deleteTarget ? keyOf(deleteTarget) : '' }}</p>
        </div>
        <div class="px-5 py-4 space-y-3 text-sm">
          <p class="text-ink-600">仅未收到钱的订单可删；已支付 / 已退款的订单后端会直接拒绝。</p>
          <label class="inline-flex items-start gap-2 text-xs text-ink-600">
            <input v-model="deleteForce" type="checkbox" class="mt-0.5" />
            <span>强行删除（连带其名下未关闭的支付单；买家可能正在扫码，风险自负）</span>
          </label>
          <p v-if="deleteError" class="text-sm text-red-600">{{ deleteError }}</p>
        </div>
        <div class="px-5 py-4 border-t border-ink-200 flex justify-end gap-2">
          <button class="btn-ghost" @click="showDelete = false">取消</button>
          <button class="btn-primary !bg-red-600 hover:!bg-red-700" :disabled="!!busy" @click="submitDelete">确认删除</button>
        </div>
      </div>
    </div>

    <!-- 退款 -->
    <div v-if="showRefund" class="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4" @click.self="showRefund = false">
      <div class="bg-white rounded-2xl w-full max-w-md shadow-xl">
        <div class="px-5 py-4 border-b border-ink-200">
          <h3 class="font-semibold">退款</h3>
          <p class="text-xs text-ink-500 mt-0.5">{{ refundTarget ? keyOf(refundTarget) : '' }}</p>
        </div>
        <div class="px-5 py-4 space-y-3">
          <div v-if="tab === 'pay'">
            <label class="block text-xs text-ink-500 mb-1">退款金额（元）</label>
            <input v-model="refundYuan" type="number" min="0" step="0.01" class="input" />
          </div>
          <div>
            <label class="block text-xs text-ink-500 mb-1">退款原因（必填）</label>
            <textarea v-model="refundReason" rows="2" class="input" placeholder="如：买家申请 / 功能不符合预期"></textarea>
          </div>
          <p v-if="refundError" class="text-sm text-red-600">{{ refundError }}</p>
          <p class="text-xs text-ink-400">商店订单退款为整单退，会同时吊销授权并冲正分账。</p>
        </div>
        <div class="px-5 py-4 border-t border-ink-200 flex justify-end gap-2">
          <button class="btn-ghost" @click="showRefund = false">取消</button>
          <button class="btn-primary" :disabled="!!busy" @click="submitRefund">提交退款</button>
        </div>
      </div>
    </div>

    <!-- 批量清理 -->
    <div v-if="showCleanup" class="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4" @click.self="showCleanup = false">
      <div class="bg-white rounded-2xl w-full max-w-lg shadow-xl max-h-[85vh] overflow-auto">
        <div class="px-5 py-4 border-b border-ink-200">
          <h3 class="font-semibold">批量清理 · {{ tab === 'store' ? '商店订单' : '支付订单' }}</h3>
          <p class="text-xs text-ink-500 mt-0.5">只会碰未付款的残单；已签发授权、仍有有效支付单的一律跳过</p>
        </div>
        <div class="px-5 py-4 space-y-3">
          <div>
            <label class="block text-xs text-ink-500 mb-1">处理方式</label>
            <div class="flex gap-4 text-sm">
              <label class="inline-flex items-center gap-2 cursor-pointer">
                <input v-model="cleanMode" type="radio" value="archive" /><span>作废隐藏（推荐）</span>
              </label>
              <label class="inline-flex items-center gap-2 cursor-pointer">
                <input v-model="cleanMode" type="radio" value="delete" /><span>物理删除</span>
              </label>
            </div>
          </div>

          <div>
            <label class="block text-xs text-ink-500 mb-1">清理哪些状态</label>
            <div class="flex flex-wrap gap-x-4 gap-y-1 text-sm">
              <label v-for="s in cleanupOptions" :key="s" class="inline-flex items-center gap-1.5">
                <input v-model="cleanStatuses" type="checkbox" :value="s" />
                <span>{{ (tab === 'store' ? ORDER_LABEL : PAY_LABEL)[s] }}</span>
              </label>
            </div>
          </div>

          <div>
            <label class="block text-xs text-ink-500 mb-1">只处理早于多少分钟的订单</label>
            <input v-model="cleanMinutes" type="number" min="0" step="60" class="input" />
            <p class="text-xs text-ink-400 mt-1">1440 = 一天前；单次最多处理 500 条</p>
          </div>

          <p v-if="cleanError" class="text-sm text-red-600">{{ cleanError }}</p>

          <div v-if="cleanPreview" class="rounded-xl bg-ink-50 border border-ink-200 p-3 text-xs text-ink-600 space-y-1">
            <div>
              {{ cleanPreview.dry_run ? '预计影响' : '已处理' }} {{ cleanPreview.dry_run ? cleanPreview.will_process : cleanPreview.processed }} 条
              · 命中 {{ cleanPreview.matched }} · 跳过 {{ cleanPreview.skipped }}
            </div>
            <div>分界线：{{ fmtTime(cleanPreview.cutoff) }}</div>
            <div v-if="cleanPreview.sample?.length" class="mt-2 space-y-0.5">
              <div v-for="s in cleanPreview.sample" :key="s.order_no || s.out_trade_no" class="font-mono">
                {{ s.order_no || s.out_trade_no }} · {{ s.status }} · {{ yuan(s.amount_cents) }}
              </div>
            </div>
          </div>
        </div>
        <div class="px-5 py-4 border-t border-ink-200 flex justify-end gap-2">
          <button class="btn-ghost" @click="showCleanup = false">关闭</button>
          <button class="btn-outline" :disabled="cleanBusy" @click="runCleanup(false)">先预览</button>
          <button class="btn-primary" :disabled="cleanBusy || !cleanPreview" @click="runCleanup(true)">
            {{ cleanBusy ? '处理中…' : '确认执行' }}
          </button>
        </div>
      </div>
    </div>
  </div>
</template>
