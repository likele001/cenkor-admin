<script setup lang="ts">
import { useI18n } from 'vue-i18n'
const { t } = useI18n()
/**
 * 应用市场 · 提现审核与打款。
 * GET  /api/v1/store/market/withdrawals               提现单列表
 * POST /api/v1/store/market/withdrawals/{id}/review   approve 通过 / reject 驳回（金额退回可提现）
 * POST /api/v1/store/market/withdrawals/{id}/pay      标记已打款（记打款凭证）
 */
import { ref, computed, onMounted, watch } from 'vue'
import { api } from '@/lib/api'
import { WD_LABEL, WD_CLASS, ACCOUNT_LABEL, fmtTime, errText } from '@/lib/market'

const loading = ref(true)
const error = ref('')
const items = ref<any[]>([])
const total = ref(0)
const page = ref(1)
const pageSize = 20
const statusFilter = ref('pending')

async function load() {
  loading.value = true
  error.value = ''
  try {
    const params: any = { page: page.value, page_size: pageSize }
    if (statusFilter.value) params.status = statusFilter.value
    const { data } = await api.get('/api/v1/store/market/withdrawals', { params })
    items.value = data?.items ?? []
    total.value = data?.total ?? 0
  } catch (e: any) {
    error.value = errText(e)
  } finally {
    loading.value = false
  }
}

onMounted(load)
watch(statusFilter, () => { page.value = 1; load() })
watch(page, load)

const totalPages = computed(() => Math.max(1, Math.ceil(total.value / pageSize)))

// ---------------- 审核 / 打款 ----------------
const acting = ref<number | null>(null)
const showReject = ref(false)
const showPay = ref(false)
const current = ref<any>(null)
const formError = ref('')
const rejectRemark = ref('')
const payVoucher = ref('')
const payRemark = ref('')

function openReject(w: any) {
  current.value = w
  rejectRemark.value = ''
  formError.value = ''
  showReject.value = true
}

function openPay(w: any) {
  current.value = w
  payVoucher.value = ''
  payRemark.value = ''
  formError.value = ''
  showPay.value = true
}

async function approve(w: any) {
  if (!confirm(`通过 ${w.developer_name} 的提现 ¥${w.amount}？通过后进入待打款状态。`)) return
  acting.value = w.id
  try {
    await api.post(`/api/v1/store/market/withdrawals/${w.id}/review`, { action: 'approve' })
    await load()
  } catch (e: any) {
    alert(errText(e))
  } finally {
    acting.value = null
  }
}

async function submitReject() {
  if (!current.value) return
  formError.value = ''
  acting.value = current.value.id
  try {
    await api.post(`/api/v1/store/market/withdrawals/${current.value.id}/review`, {
      action: 'reject',
      remark: rejectRemark.value || null,
    })
    showReject.value = false
    await load()
  } catch (e: any) {
    formError.value = errText(e)
  } finally {
    acting.value = null
  }
}

async function submitPay() {
  if (!current.value) return
  formError.value = ''
  acting.value = current.value.id
  try {
    await api.post(`/api/v1/store/market/withdrawals/${current.value.id}/pay`, {
      voucher: payVoucher.value || null,
      remark: payRemark.value || null,
    })
    showPay.value = false
    await load()
  } catch (e: any) {
    formError.value = errText(e)
  } finally {
    acting.value = null
  }
}
</script>

<template>
  <div class="space-y-4">
    <div class="card">
      <div class="flex flex-wrap items-center justify-between gap-3 pb-4 border-b border-ink-200">
        <div>
          <h2 class="font-semibold">{{ t("marketWithdrawals.提现审核_1b04zc") }}</h2>
          <p class="text-xs text-ink-500 mt-1">
            审核通过后线下打款，再回填凭证；驳回则金额退回开发者可提现余额。共 {{ total }} 单
          </p>
        </div>
        <select v-model="statusFilter" class="input !w-36">
          <option value="">{{ t("entryList.全部状态_avez63") }}</option>
          <option value="pending">{{ t("marketWithdrawals.待审核_eftvg") }}</option>
          <option value="approved">{{ t("marketWithdrawals.待打款_egzgw") }}</option>
          <option value="paid">{{ t("marketWithdrawals.已打款_e8on1") }}</option>
          <option value="rejected">{{ t("marketWithdrawals.已驳回_ei4al") }}</option>
        </select>
      </div>

      <div v-if="loading" class="p-6 text-ink-500 text-sm">{{ t("apiKeys.加载中_b0k5km") }}</div>
      <div v-else-if="error" class="p-8 text-center">
        <p class="text-red-600 mb-4 text-sm">{{ error }}</p>
        <button class="btn-primary" @click="load">{{ t("marketDevelopers.重新加载_itbyqo") }}</button>
      </div>
      <div v-else-if="items.length === 0" class="p-10 text-center text-ink-500 text-sm">{{ t("marketWithdrawals.没有符合_a3clsg") }}</div>

      <table v-else class="w-full text-sm">
        <thead class="text-left text-ink-500 border-b border-ink-200">
          <tr>
            <th class="px-3 py-2 font-normal">{{ t("marketWithdrawals.单号_emv6") }}</th>
            <th class="px-3 py-2 font-normal">{{ t("marketWithdrawals.开发者_ebw44") }}</th>
            <th class="px-3 py-2 font-normal text-right">{{ t("marketWithdrawals.申请金额_fddbm8") }}</th>
            <th class="px-3 py-2 font-normal text-right">{{ t("marketWithdrawals.手续费_f0nsn") }}</th>
            <th class="px-3 py-2 font-normal text-right">{{ t("marketWithdrawals.应到账_e9gne") }}</th>
            <th class="px-3 py-2 font-normal">{{ t("marketWithdrawals.收款账户_d7y7bt") }}</th>
            <th class="px-3 py-2 font-normal">{{ t("marketWithdrawals.status") }}</th>
            <th class="px-3 py-2 font-normal">{{ t("marketWithdrawals.time") }}</th>
            <th class="px-3 py-2 font-normal text-right">{{ t("marketWithdrawals.actions") }}</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="w in items" :key="w.id" class="border-b border-ink-100 last:border-0">
            <td class="px-3 py-3"><code class="text-xs">#{{ w.id }}</code></td>
            <td class="px-3 py-3">
              <div>{{ w.developer_name }}</div>
              <div class="text-xs text-ink-400">#{{ w.developer_id }}</div>
            </td>
            <td class="px-3 py-3 text-right font-medium">¥{{ w.amount }}</td>
            <td class="px-3 py-3 text-right text-ink-500">¥{{ w.fee }}</td>
            <td class="px-3 py-3 text-right">¥{{ w.actual }}</td>
            <td class="px-3 py-3 text-xs">
              <div>{{ ACCOUNT_LABEL[w.account_type] || w.account_type }}</div>
              <div class="text-ink-500">{{ w.account_no || '—' }}</div>
              <div class="text-ink-400">{{ w.account_name || '' }} {{ w.bank_name || '' }}</div>
            </td>
            <td class="px-3 py-3">
              <span class="text-xs px-1.5 py-0.5 rounded" :class="WD_CLASS[w.status]">
                {{ WD_LABEL[w.status] || w.status }}
              </span>
              <div v-if="w.review_remark" class="text-xs text-ink-400 mt-1">{{ w.review_remark }}</div>
              <div v-if="w.pay_voucher" class="text-xs text-ink-400 mt-1">凭证 {{ w.pay_voucher }}</div>
            </td>
            <td class="px-3 py-3 text-xs text-ink-500 whitespace-nowrap">
              申请 {{ fmtTime(w.created_at) }}
              <div v-if="w.paid_at">打款 {{ fmtTime(w.paid_at) }}</div>
              <div v-if="w.remark" class="text-ink-400">备注 {{ w.remark }}</div>
            </td>
            <td class="px-3 py-3">
              <div class="flex justify-end gap-2">
                <template v-if="w.status === 'pending'">
                  <button
                    class="text-xs text-emerald-600 hover:text-emerald-800 disabled:opacity-50"
                    :disabled="acting === w.id" @click="approve(w)"
                  >{{ t("marketWithdrawals.通过_past") }}</button>
                  <button
                    class="text-xs text-red-600 hover:text-red-800 disabled:opacity-50"
                    :disabled="acting === w.id" @click="openReject(w)"
                  >{{ t("marketWithdrawals.驳回_qqx7") }}</button>
                </template>
                <button
                  v-else-if="w.status === 'approved'"
                  class="text-xs text-blue-600 hover:text-blue-800 disabled:opacity-50"
                  :disabled="acting === w.id" @click="openPay(w)"
                >{{ t("marketWithdrawals.标记已打_1xlqzk") }}</button>
                <span v-else class="text-xs text-ink-400">—</span>
              </div>
            </td>
          </tr>
        </tbody>
      </table>

      <div v-if="totalPages > 1" class="flex items-center justify-between pt-4 text-sm">
        <span class="text-ink-500">共 {{ total }} 条</span>
        <div class="flex items-center gap-2">
          <button class="btn-outline !py-1 !px-3" :disabled="page <= 1" @click="page--">{{ t("marketWithdrawals.上一页_btlof") }}</button>
          <span class="text-ink-500">{{ page }} / {{ totalPages }}</span>
          <button class="btn-outline !py-1 !px-3" :disabled="page >= totalPages" @click="page++">{{ t("marketWithdrawals.下一页_btmf4") }}</button>
        </div>
      </div>
    </div>

    <!-- 驳回 -->
    <div v-if="showReject" class="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4" @click.self="showReject = false">
      <div class="bg-white rounded-2xl w-full max-w-md shadow-xl">
        <div class="px-5 py-4 border-b border-ink-200 flex items-center justify-between">
          <h3 class="font-semibold">{{ t("marketWithdrawals.驳回提现_juia5n") }}</h3>
          <button class="text-ink-400 hover:text-ink-900" @click="showReject = false">✕</button>
        </div>
        <div class="px-5 py-4 space-y-3">
          <div class="rounded-xl bg-ink-50 border border-ink-200 p-3 text-xs text-ink-600">
            {{ current?.developer_name }} 申请 ¥{{ current?.amount }}，驳回后金额退回其可提现余额。
          </div>
          <div>
            <label class="block text-xs text-ink-500 mb-1">{{ t("marketWithdrawals.驳回理由_jul1py") }}</label>
            <textarea v-model="rejectRemark" rows="3" class="input" :placeholder="t('marketWithdrawals.如_dw41l3')"></textarea>
          </div>
          <p v-if="formError" class="text-sm text-red-600">{{ formError }}</p>
        </div>
        <div class="px-5 py-4 border-t border-ink-200 flex justify-end gap-2">
          <button class="btn-ghost" @click="showReject = false">{{ t("marketWithdrawals.cancel") }}</button>
          <button class="btn-primary !bg-red-600 hover:!bg-red-700" :disabled="!!acting" @click="submitReject">
            {{ acting ? '提交中…' : '确认驳回' }}
          </button>
        </div>
      </div>
    </div>

    <!-- 打款 -->
    <div v-if="showPay" class="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4" @click.self="showPay = false">
      <div class="bg-white rounded-2xl w-full max-w-md shadow-xl">
        <div class="px-5 py-4 border-b border-ink-200 flex items-center justify-between">
          <h3 class="font-semibold">{{ t("marketWithdrawals.标记已打_1xlqzk") }}</h3>
          <button class="text-ink-400 hover:text-ink-900" @click="showPay = false">✕</button>
        </div>
        <div class="px-5 py-4 space-y-3">
          <div class="rounded-xl bg-ink-50 border border-ink-200 p-3 text-xs text-ink-600 space-y-1">
            <div>开发者：{{ current?.developer_name }}</div>
            <div>{{ t("marketWithdrawals.应到账_ca6qj4") }}<strong>¥{{ current?.actual }}</strong>（申请 ¥{{ current?.amount }}，手续费 ¥{{ current?.fee }}）</div>
            <div>
              收款：{{ ACCOUNT_LABEL[current?.account_type] }} {{ current?.account_no }}
              {{ current?.account_name }}
            </div>
          </div>
          <div>
            <label class="block text-xs text-ink-500 mb-1">{{ t("marketWithdrawals.打款凭证_1u74zh") }}</label>
            <input v-model="payVoucher" class="input" :placeholder="t('marketWithdrawals.如_8olvp1')" />
          </div>
          <div>
            <label class="block text-xs text-ink-500 mb-1">{{ t("quality.备注_qeo808") }}</label>
            <input v-model="payRemark" class="input" />
          </div>
          <p v-if="formError" class="text-sm text-red-600">{{ formError }}</p>
        </div>
        <div class="px-5 py-4 border-t border-ink-200 flex justify-end gap-2">
          <button class="btn-ghost" @click="showPay = false">{{ t("marketWithdrawals.cancel") }}</button>
          <button class="btn-primary" :disabled="!!acting" @click="submitPay">{{ acting ? '提交中…' : '确认已打款' }}</button>
        </div>
      </div>
    </div>
  </div>
</template>
