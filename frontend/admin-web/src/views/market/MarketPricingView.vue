<script setup lang="ts">
import { useI18n } from 'vue-i18n'
const { t } = useI18n()
/**
 * 应用市场 · 商品与扣点（平台侧全量视图）。
 * GET /api/v1/store/market/pricing        全量商品 + 归属 + 生效扣点 + 销量
 * PUT /api/v1/store/market/pricing/{key}  改定价 / 改归属 / 覆盖单应用扣点
 * GET /api/v1/store/market/developers     归属下拉用
 *
 * 定价字段（原价 / 售价 / 限时促销）复用与开发者端同一个 PriceFields 组件：
 * 提交接口是「整体覆盖」语义，若这里只发部分字段，会把开发者设好的原价与促销清空。
 */
import { ref, computed, onMounted, watch } from 'vue'
import { api } from '@/lib/api'
import PriceFields from '@/components/PriceFields.vue'
import {
  MODEL_LABEL, MODEL_CLASS, PROMO_STATE_LABEL, PROMO_STATE_CLASS,
  centsToYuan, bpToPercent, errText,
  emptyPriceForm, priceFormFrom, priceFormToPayload, validatePriceForm,
  type PriceForm,
} from '@/lib/market'

const loading = ref(true)
const error = ref('')
const items = ref<any[]>([])
const total = ref(0)
const defaultFeeBp = ref(2000)
const page = ref(1)
const pageSize = 50
const keyword = ref('')
const devOptions = ref<any[]>([])

async function load() {
  loading.value = true
  error.value = ''
  try {
    const params: any = { page: page.value, page_size: pageSize }
    if (keyword.value.trim()) params.q = keyword.value.trim()
    const { data } = await api.get('/api/v1/store/market/pricing', { params })
    items.value = data?.items ?? []
    total.value = data?.total ?? 0
    defaultFeeBp.value = Number(data?.default_fee_bp ?? 2000)
  } catch (e: any) {
    error.value = errText(e)
  } finally {
    loading.value = false
  }
}

async function loadDevelopers() {
  try {
    const { data } = await api.get('/api/v1/store/market/developers', { params: { page: 1, page_size: 200 } })
    devOptions.value = data?.items ?? []
  } catch { /* 下拉只是便利项 */ }
}

onMounted(() => { load(); loadDevelopers() })
watch(page, load)

let timer: any = null
watch(keyword, () => {
  clearTimeout(timer)
  timer = setTimeout(() => { page.value = 1; load() }, 300)
})

const totalPages = computed(() => Math.max(1, Math.ceil(total.value / pageSize)))

// ---------------- 编辑弹层 ----------------
const showEdit = ref(false)
const saving = ref(false)
const formError = ref('')
const current = ref<any>(null)
/** 价格部分：与开发者端共用同一套字段与校验 */
const price = ref<PriceForm>(emptyPriceForm())
/** 市场专有部分：归属与扣点 */
const meta = ref({
  owner: 'platform' as 'platform' | 'developer',
  developer_id: 0,
  fee_mode: 'default' as 'default' | 'override',
  fee_percent: '20.00',
})

function openEdit(row: any) {
  current.value = row
  formError.value = ''
  price.value = priceFormFrom(row)
  const isSelf = !row.developer_id || row.developer_id === 1
  meta.value = {
    owner: isSelf ? 'platform' : 'developer',
    developer_id: isSelf ? 0 : Number(row.developer_id),
    fee_mode: row.platform_fee_bp == null ? 'default' : 'override',
    fee_percent: row.platform_fee_bp == null
      ? bpToPercent(defaultFeeBp.value)
      : bpToPercent(row.platform_fee_bp),
  }
  showEdit.value = true
}

async function save() {
  if (!current.value) return
  const bad = validatePriceForm(price.value)
  if (bad) {
    formError.value = bad
    return
  }
  if (meta.value.owner === 'developer' && !meta.value.developer_id) {
    formError.value = t("marketPricing.请选择归_3y4m29")
    return
  }

  saving.value = true
  formError.value = ''
  try {
    await api.put(`/api/v1/store/market/pricing/${current.value.app_key}`, {
      ...priceFormToPayload(price.value),
      // 归属：0 = 收归平台自营
      developer_id: meta.value.owner === 'platform' ? 0 : Number(meta.value.developer_id),
      // 扣点：null = 清除覆盖，回落全局默认
      platform_fee_bp: meta.value.fee_mode === 'default'
        ? null
        : Math.round(parseFloat(meta.value.fee_percent || '0') * 100),
    })
    showEdit.value = false
    await load()
  } catch (e: any) {
    formError.value = errText(e)
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <div class="space-y-4">
    <div class="card">
      <div class="flex flex-wrap items-center justify-between gap-3 pb-4 border-b border-ink-200">
        <div>
          <h2 class="font-semibold">{{ t("marketPricing.商品与扣_1obbh9") }}</h2>
          <p class="text-xs text-ink-500 mt-1">
            {{ $t('marketPricing.共_g35') }} {{ total }} {{ $t('marketPricing.个商品_1ybz4j') }} {{ bpToPercent(defaultFeeBp) }}%
          </p>
        </div>
        <input v-model="keyword" class="input !w-56" :placeholder="t('marketPricing.搜索_mamtnr')" />
      </div>

      <div v-if="loading" class="p-6 text-ink-500 text-sm">{{ t("apiKeys.加载中_b0k5km") }}</div>
      <div v-else-if="error" class="p-8 text-center">
        <p class="text-red-600 mb-4 text-sm">{{ error }}</p>
        <button class="btn-primary" @click="load">{{ t("marketDevelopers.重新加载_itbyqo") }}</button>
      </div>
      <div v-else-if="items.length === 0" class="p-10 text-center text-ink-500 text-sm">
        {{ t("marketPricing.还没有配_wvhsox") }}
      </div>

      <table v-else class="w-full text-sm">
        <thead class="text-left text-ink-500 border-b border-ink-200">
          <tr>
            <th class="px-3 py-2 font-normal">{{ t("marketPricing.应用_gqac") }}</th>
            <th class="px-3 py-2 font-normal">{{ t("marketPricing.归属_gpxo") }}</th>
            <th class="px-3 py-2 font-normal">{{ t("marketPricing.模式_ikni") }}</th>
            <th class="px-3 py-2 font-normal text-right">{{ t("marketPricing.售价_ex6x") }}</th>
            <th class="px-3 py-2 font-normal text-right">{{ t("marketPricing.生效扣点_f74adb") }}</th>
            <th class="px-3 py-2 font-normal text-right">{{ t("marketPricing.销量_q573") }}</th>
            <th class="px-3 py-2 font-normal text-right">{{ t("marketPricing.成交额_eramh") }}</th>
            <th class="px-3 py-2 font-normal text-right">{{ t("marketPricing.actions") }}</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="r in items" :key="r.app_key" class="border-b border-ink-100 last:border-0">
            <td class="px-3 py-3">
              <div class="font-medium">{{ r.app_name }}</div>
              <code class="text-xs text-ink-400">{{ r.app_key }}</code>
            </td>
            <td class="px-3 py-3">
              <span class="text-xs px-1.5 py-0.5 rounded bg-ink-100 text-ink-600">{{ r.owner }}</span>
            </td>
            <td class="px-3 py-3">
              <span class="text-xs px-1.5 py-0.5 rounded" :class="MODEL_CLASS[r.model]">
                {{ MODEL_LABEL[r.model] || r.model }}
              </span>
              <div v-if="r.model !== 'free'" class="text-xs text-ink-400 mt-1">
                {{ r.enabled ? $t('marketPricing.在售_faiu') : $t('marketPricing.已下架_e57r1') }}
              </div>
            </td>
            <td class="px-3 py-3 text-right">
              <div v-if="r.model === 'free'">{{ t("marketPricing.免费_elqk") }}</div>
              <template v-else>
                <div class="flex items-center justify-end gap-1.5 flex-wrap">
                  <span>¥{{ r.unit_price }}<span v-if="r.model === 'seat'" class="text-xs text-ink-400">{{ t("marketPricing.text_hf73") }}</span></span>
                  <span
                    v-if="r.is_discounted"
                    class="text-xs text-ink-400 line-through"
                    :title="t('marketPricing.原价_1rm6if')"
                  >¥{{ r.model === 'seat' ? r.seat_list_price : r.list_price }}</span>
                  <span
                    v-if="r.discount_label"
                    class="text-[10px] px-1.5 py-0.5 rounded bg-red-50 text-red-600 font-medium"
                  >{{ r.discount_label }}</span>
                </div>
                <div v-if="r.promo_price_cents" class="mt-0.5">
                  <span
                    class="text-[10px] px-1.5 py-0.5 rounded"
                    :class="PROMO_STATE_CLASS[r.promo_state]"
                    :title="r.promo_label || '限时促销'"
                  >{{ PROMO_STATE_LABEL[r.promo_state] }}<template v-if="r.promo_label"> · {{ r.promo_label }}</template></span>
                </div>
              </template>
            </td>
            <td class="px-3 py-3 text-right">
              {{ r.effective_fee_percent }}%
              <div v-if="r.fee_overridden" class="text-xs text-amber-600">{{ t("marketPricing.已覆盖_efeyq") }}</div>
              <div v-else class="text-xs text-ink-400">{{ t("marketPricing.默认_rs98") }}</div>
            </td>
            <td class="px-3 py-3 text-right">{{ r.order_count }}</td>
            <td class="px-3 py-3 text-right">¥{{ centsToYuan(r.paid_cents) }}</td>
            <td class="px-3 py-3 text-right">
              <button class="text-xs text-blue-600 hover:text-blue-800" @click="openEdit(r)">{{ t("marketPricing.edit") }}</button>
            </td>
          </tr>
        </tbody>
      </table>

      <div v-if="totalPages > 1" class="flex items-center justify-between pt-4 text-sm">
        <span class="text-ink-500">{{ $t('marketPricing.共_g35') }} {{ total }} {{ $t('marketPricing.条_kf5') }}</span>
        <div class="flex items-center gap-2">
          <button class="btn-outline !py-1 !px-3" :disabled="page <= 1" @click="page--">{{ t("marketPricing.上一页_btlof") }}</button>
          <span class="text-ink-500">{{ page }} / {{ totalPages }}</span>
          <button class="btn-outline !py-1 !px-3" :disabled="page >= totalPages" @click="page++">{{ t("marketPricing.下一页_btmf4") }}</button>
        </div>
      </div>
    </div>

    <!-- 编辑弹层 -->
    <div v-if="showEdit" class="fixed inset-0 z-50 flex items-start justify-center bg-black/40 p-4 overflow-y-auto" @click.self="showEdit = false">
      <div class="bg-white rounded-2xl w-full max-w-2xl my-8 shadow-xl">
        <div class="px-5 py-4 border-b border-ink-200 flex items-center justify-between">
          <div>
            <h3 class="font-semibold">{{ t("marketPricing.编辑商品_gmhqye") }}</h3>
            <p class="text-xs text-ink-500 mt-0.5">{{ current?.app_name }} · <code>{{ current?.app_key }}</code></p>
          </div>
          <button class="text-ink-400 hover:text-ink-900" @click="showEdit = false">✕</button>
        </div>

        <div class="px-5 py-4 space-y-4 max-h-[65vh] overflow-y-auto">
          <!-- 归属 -->
          <div class="rounded-xl border border-ink-200 p-3 space-y-3">
            <div class="text-xs font-medium text-ink-600">{{ t("marketPricing.商品归属_nbia2r") }}</div>
            <div class="flex gap-4 text-sm">
              <label class="inline-flex items-center gap-2 cursor-pointer">
                <input v-model="meta.owner" type="radio" value="platform" />
                <span>{{ t("marketPricing.平台自营_nyaefi") }}</span>
              </label>
              <label class="inline-flex items-center gap-2 cursor-pointer">
                <input v-model="meta.owner" type="radio" value="developer" />
                <span>{{ t("marketPricing.归属开发_tldpc8") }}</span>
              </label>
            </div>
            <select v-if="meta.owner === 'developer'" v-model.number="meta.developer_id" class="input">
              <option :value="0">{{ t("marketPricing.请选择开_w4um89") }}</option>
              <option v-for="d in devOptions" :key="d.id" :value="d.id">
                {{ d.display_name }}（#{{ d.id }}{{ d.email ? ' · ' + d.email : '' }}）
              </option>
            </select>
            <p class="text-xs text-ink-400">{{ t("marketPricing.改归属只_1qhivr") }}</p>
          </div>

          <!-- 扣点 -->
          <div class="rounded-xl border border-ink-200 p-3 space-y-3">
            <div class="text-xs font-medium text-ink-600">{{ t("marketPricing.单应用扣_1i4dsw") }}</div>
            <div class="flex gap-4 text-sm">
              <label class="inline-flex items-center gap-2 cursor-pointer">
                <input v-model="meta.fee_mode" type="radio" value="default" />
                <span>{{ $t('marketPricing.用全局默_14pw8u') }}{{ bpToPercent(defaultFeeBp) }}%）</span>
              </label>
              <label class="inline-flex items-center gap-2 cursor-pointer">
                <input v-model="meta.fee_mode" type="radio" value="override" />
                <span>{{ t("marketPricing.单独设置_azw3c7") }}</span>
              </label>
            </div>
            <div v-if="meta.fee_mode === 'override'" class="flex items-center gap-2">
              <input v-model="meta.fee_percent" type="number" min="0" max="100" step="0.01" class="input !w-32" />
              <span class="text-sm text-ink-500">%</span>
            </div>
            <p v-if="meta.owner === 'platform'" class="text-xs text-amber-600">
              {{ t("marketPricing.平台自营_17p7b2") }}
            </p>
          </div>

          <!-- 定价：与开发者端同一套字段 -->
          <PriceFields v-model="price" />

          <p v-if="formError" class="text-sm text-red-600">{{ formError }}</p>
        </div>

        <div class="px-5 py-4 border-t border-ink-200 flex justify-end gap-2">
          <button class="btn-ghost" @click="showEdit = false">{{ t("marketPricing.cancel") }}</button>
          <button class="btn-primary" :disabled="saving" @click="save">{{ saving ? $t('marketPricing.保存中_agdrec') : $t('marketPricing.保存_e32z') }}</button>
        </div>
      </div>
    </div>
  </div>
</template>
