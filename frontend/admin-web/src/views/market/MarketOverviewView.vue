<script setup lang="ts">
/**
 * 应用市场 · 平台总览 + 结算参数。
 * GET  /api/v1/store/market/overview
 * GET  /api/v1/store/market/settings
 * PUT  /api/v1/store/market/settings
 *
 * 收入口径互不重叠：
 *  - 自营收入 = 平台自己应用的订单全额
 *  - 抽成收入 = 第三方应用订单中平台抽走的部分
 *  - 开发者应结 = 第三方订单中归开发者的净收入（按资金池细分）
 */
import { ref, computed, onMounted } from 'vue'
import { api } from '@/lib/api'
import { centsToYuan, toCents, errText } from '@/lib/market'

const loading = ref(true)
const error = ref('')
const ov = ref<any>(null)

// 结算参数表单
const saving = ref(false)
const msg = ref('')
const cfgError = ref('')
const form = ref({
  platform_fee_percent: '20.00',
  settle_delay_days: 7,
  min_withdraw_yuan: '100.00',
  withdraw_fee_percent: '0.00',
})

async function load() {
  loading.value = true
  error.value = ''
  try {
    const { data } = await api.get('/api/v1/store/market/overview')
    ov.value = data
    const s = data?.settings ?? {}
    form.value = {
      platform_fee_percent: ((Number(s.platform_fee_bp) || 0) / 100).toFixed(2),
      settle_delay_days: Number(s.settle_delay_days ?? 7),
      min_withdraw_yuan: centsToYuan(s.min_withdraw_cents ?? 10000),
      withdraw_fee_percent: ((Number(s.withdraw_fee_bp) || 0) / 100).toFixed(2),
    }
  } catch (e: any) {
    error.value = errText(e)
  } finally {
    loading.value = false
  }
}

onMounted(load)

async function saveSettings() {
  saving.value = true
  msg.value = ''
  cfgError.value = ''
  try {
    const feeBp = Math.round(parseFloat(form.value.platform_fee_percent || '0') * 100)
    const wdFeeBp = Math.round(parseFloat(form.value.withdraw_fee_percent || '0') * 100)
    await api.put('/api/v1/store/market/settings', {
      platform_fee_bp: feeBp,
      settle_delay_days: Number(form.value.settle_delay_days) || 0,
      min_withdraw_cents: toCents(form.value.min_withdraw_yuan),
      withdraw_fee_bp: wdFeeBp,
    })
    msg.value = '已保存并即时生效（仅影响新订单）'
    await load()
  } catch (e: any) {
    cfgError.value = errText(e)
  } finally {
    saving.value = false
  }
}

const devTotalCents = computed(() => {
  const d = ov.value
  if (!d) return 0
  return (d.developer_pending_cents || 0) + (d.developer_available_cents || 0) + (d.developer_frozen_cents || 0)
})
</script>

<template>
  <div class="space-y-4">
    <div v-if="loading" class="card text-sm text-ink-500">加载中…</div>
    <div v-else-if="error" class="card text-center py-8">
      <p class="text-red-600 mb-4 text-sm">{{ error }}</p>
      <button class="btn-primary" @click="load">重新加载</button>
    </div>

    <template v-else-if="ov">
      <!-- 平台收入 -->
      <div class="grid grid-cols-1 md:grid-cols-3 gap-3">
        <div class="card">
          <div class="text-xs text-ink-500 mb-1">平台自营收入</div>
          <div class="text-2xl font-semibold">¥{{ ov.platform_self_revenue }}</div>
          <div class="text-xs text-ink-400 mt-1">平台自有应用的订单全额</div>
        </div>
        <div class="card">
          <div class="text-xs text-ink-500 mb-1">平台抽成收入</div>
          <div class="text-2xl font-semibold">¥{{ ov.platform_commission }}</div>
          <div class="text-xs text-ink-400 mt-1">第三方应用订单的抽成部分</div>
        </div>
        <div class="card !bg-ink-900 !border-ink-900">
          <div class="text-xs text-ink-300 mb-1">平台合计收入</div>
          <div class="text-2xl font-semibold text-white">¥{{ ov.platform_total }}</div>
          <div class="text-xs text-ink-400 mt-1">自营 + 抽成，已直接入账</div>
        </div>
      </div>

      <!-- 开发者应结 -->
      <div class="card">
        <div class="flex items-center justify-between mb-3">
          <h3 class="font-semibold">开发者应结（三池）</h3>
          <span class="text-sm text-ink-500">合计 ¥{{ centsToYuan(devTotalCents) }}</span>
        </div>
        <div class="grid grid-cols-2 md:grid-cols-5 gap-4 text-sm">
          <div>
            <div class="text-xs text-ink-500 mb-1">待结算</div>
            <div class="text-lg font-medium">¥{{ ov.developer_pending }}</div>
          </div>
          <div>
            <div class="text-xs text-ink-500 mb-1">可提现</div>
            <div class="text-lg font-medium">¥{{ ov.developer_available }}</div>
          </div>
          <div>
            <div class="text-xs text-ink-500 mb-1">提现冻结</div>
            <div class="text-lg font-medium">¥{{ ov.developer_frozen }}</div>
          </div>
          <div>
            <div class="text-xs text-ink-500 mb-1">累计已打款</div>
            <div class="text-lg font-medium">¥{{ ov.developer_withdrawn_cents != null ? centsToYuan(ov.developer_withdrawn_cents) : '0.00' }}</div>
          </div>
          <div>
            <div class="text-xs text-ink-500 mb-1">累计退款冲正</div>
            <div class="text-lg font-medium text-red-600">¥{{ centsToYuan(ov.developer_refunded_cents) }}</div>
          </div>
        </div>
      </div>

      <!-- 交易概览 -->
      <div class="grid grid-cols-2 md:grid-cols-5 gap-3">
        <div class="card !p-4">
          <div class="text-xs text-ink-500 mb-1">成交订单</div>
          <div class="text-lg font-semibold">{{ ov.paid_order_count }}</div>
          <div class="text-xs text-ink-400 mt-0.5">¥{{ ov.paid_amount }}</div>
        </div>
        <div class="card !p-4">
          <div class="text-xs text-ink-500 mb-1">已退款订单</div>
          <div class="text-lg font-semibold">{{ ov.refunded_order_count }}</div>
        </div>
        <div class="card !p-4">
          <div class="text-xs text-ink-500 mb-1">待审提现</div>
          <div class="text-lg font-semibold" :class="ov.withdrawal_pending_count > 0 ? 'text-amber-600' : ''">
            {{ ov.withdrawal_pending_count }}
          </div>
          <div class="text-xs text-ink-400 mt-0.5">¥{{ ov.withdrawal_pending }}</div>
        </div>
        <div class="card !p-4">
          <div class="text-xs text-ink-500 mb-1">活跃开发者</div>
          <div class="text-lg font-semibold">{{ ov.developer_count }}</div>
        </div>
        <div class="card !p-4 flex flex-col justify-center">
          <button v-if="ov.withdrawal_pending_count > 0" class="btn-primary !text-xs" @click="$router.push('/market/withdrawals')">
            去处理提现 →
          </button>
          <span v-else class="text-xs text-ink-400">暂无待处理提现</span>
        </div>
      </div>

      <!-- 结算参数 -->
      <div class="card">
        <h3 class="font-semibold">结算参数</h3>
        <p class="text-xs text-ink-500 mt-1 mb-4">
          全局默认值，可被单个应用覆盖（见「商品与扣点」）。修改只影响之后产生的新订单，历史订单的分账在下单时已快照。
        </p>
        <div class="grid grid-cols-1 md:grid-cols-2 gap-4 max-w-2xl">
          <div>
            <label class="block text-xs text-ink-500 mb-1">平台默认扣点（%）</label>
            <input v-model="form.platform_fee_percent" type="number" min="0" max="100" step="0.01" class="input" />
            <p class="text-xs text-ink-400 mt-1">第三方应用默认抽成比例，平台自营恒为 0</p>
          </div>
          <div>
            <label class="block text-xs text-ink-500 mb-1">结算周期 T+N（天）</label>
            <input v-model.number="form.settle_delay_days" type="number" min="0" max="365" class="input" />
            <p class="text-xs text-ink-400 mt-1">成交后经过 N 天转入可提现余额</p>
          </div>
          <div>
            <label class="block text-xs text-ink-500 mb-1">单笔提现门槛（元）</label>
            <input v-model="form.min_withdraw_yuan" type="number" min="0" step="0.01" class="input" />
          </div>
          <div>
            <label class="block text-xs text-ink-500 mb-1">提现手续费（%）</label>
            <input v-model="form.withdraw_fee_percent" type="number" min="0" max="100" step="0.01" class="input" />
            <p class="text-xs text-ink-400 mt-1">0 表示平台承担手续费</p>
          </div>
        </div>
        <div class="flex items-center gap-3 mt-5">
          <button class="btn-primary" :disabled="saving" @click="saveSettings">
            {{ saving ? '保存中…' : '保存参数' }}
          </button>
          <span v-if="msg" class="text-sm text-emerald-600">{{ msg }}</span>
          <span v-if="cfgError" class="text-sm text-red-600">{{ cfgError }}</span>
        </div>
      </div>
    </template>
  </div>
</template>
