<script setup lang="ts">
/**
 * 应用市场 · 商品与扣点（平台侧全量视图）。
 * GET /api/v1/store/market/pricing        全量商品 + 归属 + 生效扣点 + 销量
 * PUT /api/v1/store/market/pricing/{key}  改定价 / 改归属 / 覆盖单应用扣点
 * GET /api/v1/store/market/developers     归属下拉用
 */
import { ref, computed, onMounted, watch } from 'vue'
import { api } from '@/lib/api'
import { MODEL_LABEL, MODEL_CLASS, centsToYuan, toCents, bpToPercent, errText } from '@/lib/market'

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
const form = ref({
  model: 'free',
  price_yuan: '0.00',
  seat_price_yuan: '0.00',
  period_days: 365,
  trial_days: 0,
  min_seats: 1,
  max_seats: 0,
  require_approval: false,
  enabled: true,
  intro: '',
  owner: 'platform' as 'platform' | 'developer',
  developer_id: 0,
  fee_mode: 'default' as 'default' | 'override',
  fee_percent: '20.00',
})

function openEdit(row: any) {
  current.value = row
  formError.value = ''
  const isSelf = !row.developer_id || row.developer_id === 1
  form.value = {
    model: row.model || 'free',
    price_yuan: centsToYuan(row.price_cents),
    seat_price_yuan: centsToYuan(row.seat_price_cents),
    period_days: row.period_days ?? 365,
    trial_days: row.trial_days ?? 0,
    min_seats: row.min_seats ?? 1,
    max_seats: row.max_seats ?? 0,
    require_approval: !!row.require_approval,
    enabled: row.enabled !== false,
    intro: row.intro || '',
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
  const f = form.value
  if (f.model !== 'free' && f.model !== 'seat' && toCents(f.price_yuan) <= 0) {
    formError.value = '售价必须大于 0'; return
  }
  if (f.model === 'seat' && toCents(f.seat_price_yuan) <= 0) {
    formError.value = '席位单价必须大于 0'; return
  }
  if (f.owner === 'developer' && !f.developer_id) {
    formError.value = '请选择归属开发者'; return
  }

  saving.value = true
  formError.value = ''
  try {
    await api.put(`/api/v1/store/market/pricing/${current.value.app_key}`, {
      model: f.model,
      price_cents: toCents(f.price_yuan),
      seat_price_cents: toCents(f.seat_price_yuan),
      period_days: Number(f.period_days) || 365,
      trial_days: Number(f.trial_days) || 0,
      min_seats: Number(f.min_seats) || 1,
      max_seats: Number(f.max_seats) || 0,
      require_approval: !!f.require_approval,
      enabled: !!f.enabled,
      intro: f.intro || null,
      // 归属：0 = 收归平台自营
      developer_id: f.owner === 'platform' ? 0 : Number(f.developer_id),
      // 扣点：null = 清除覆盖，回落全局默认
      platform_fee_bp: f.fee_mode === 'default'
        ? null
        : Math.round(parseFloat(f.fee_percent || '0') * 100),
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
          <h2 class="font-semibold">商品与扣点</h2>
          <p class="text-xs text-ink-500 mt-1">
            共 {{ total }} 个商品 · 全局默认扣点 {{ bpToPercent(defaultFeeBp) }}%
          </p>
        </div>
        <input v-model="keyword" class="input !w-56" placeholder="搜索 app_key" />
      </div>

      <div v-if="loading" class="p-6 text-ink-500 text-sm">加载中…</div>
      <div v-else-if="error" class="p-8 text-center">
        <p class="text-red-600 mb-4 text-sm">{{ error }}</p>
        <button class="btn-primary" @click="load">重新加载</button>
      </div>
      <div v-else-if="items.length === 0" class="p-10 text-center text-ink-500 text-sm">
        还没有配置定价的商品
      </div>

      <table v-else class="w-full text-sm">
        <thead class="text-left text-ink-500 border-b border-ink-200">
          <tr>
            <th class="px-3 py-2 font-normal">应用</th>
            <th class="px-3 py-2 font-normal">归属</th>
            <th class="px-3 py-2 font-normal">模式</th>
            <th class="px-3 py-2 font-normal text-right">售价</th>
            <th class="px-3 py-2 font-normal text-right">生效扣点</th>
            <th class="px-3 py-2 font-normal text-right">销量</th>
            <th class="px-3 py-2 font-normal text-right">成交额</th>
            <th class="px-3 py-2 font-normal text-right">操作</th>
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
                {{ r.enabled ? '在售' : '已下架' }}
              </div>
            </td>
            <td class="px-3 py-3 text-right">
              <div v-if="r.model === 'free'">免费</div>
              <div v-else-if="r.model === 'seat'">¥{{ r.seat_price }}<span class="text-xs text-ink-400">/席位</span></div>
              <div v-else>¥{{ r.price }}</div>
            </td>
            <td class="px-3 py-3 text-right">
              {{ r.effective_fee_percent }}%
              <div v-if="r.fee_overridden" class="text-xs text-amber-600">已覆盖</div>
              <div v-else class="text-xs text-ink-400">默认</div>
            </td>
            <td class="px-3 py-3 text-right">{{ r.order_count }}</td>
            <td class="px-3 py-3 text-right">¥{{ centsToYuan(r.paid_cents) }}</td>
            <td class="px-3 py-3 text-right">
              <button class="text-xs text-blue-600 hover:text-blue-800" @click="openEdit(r)">编辑</button>
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

    <!-- 编辑弹层 -->
    <div v-if="showEdit" class="fixed inset-0 z-50 flex items-start justify-center bg-black/40 p-4 overflow-y-auto" @click.self="showEdit = false">
      <div class="bg-white rounded-2xl w-full max-w-xl my-8 shadow-xl">
        <div class="px-5 py-4 border-b border-ink-200 flex items-center justify-between">
          <div>
            <h3 class="font-semibold">编辑商品</h3>
            <p class="text-xs text-ink-500 mt-0.5">{{ current?.app_name }} · <code>{{ current?.app_key }}</code></p>
          </div>
          <button class="text-ink-400 hover:text-ink-900" @click="showEdit = false">✕</button>
        </div>

        <div class="px-5 py-4 space-y-4 max-h-[65vh] overflow-y-auto">
          <!-- 归属 -->
          <div class="rounded-xl border border-ink-200 p-3 space-y-3">
            <div class="text-xs font-medium text-ink-600">商品归属（决定收入归谁）</div>
            <div class="flex gap-4 text-sm">
              <label class="inline-flex items-center gap-2 cursor-pointer">
                <input v-model="form.owner" type="radio" value="platform" />
                <span>平台自营（收入全额归平台）</span>
              </label>
              <label class="inline-flex items-center gap-2 cursor-pointer">
                <input v-model="form.owner" type="radio" value="developer" />
                <span>归属开发者</span>
              </label>
            </div>
            <select v-if="form.owner === 'developer'" v-model.number="form.developer_id" class="input">
              <option :value="0">请选择开发者…</option>
              <option v-for="d in devOptions" :key="d.id" :value="d.id">
                {{ d.display_name }}（#{{ d.id }}{{ d.email ? ' · ' + d.email : '' }}）
              </option>
            </select>
            <p class="text-xs text-ink-400">改归属只影响之后的新订单，历史订单分账已快照。</p>
          </div>

          <!-- 扣点 -->
          <div class="rounded-xl border border-ink-200 p-3 space-y-3">
            <div class="text-xs font-medium text-ink-600">单应用扣点</div>
            <div class="flex gap-4 text-sm">
              <label class="inline-flex items-center gap-2 cursor-pointer">
                <input v-model="form.fee_mode" type="radio" value="default" />
                <span>用全局默认（{{ bpToPercent(defaultFeeBp) }}%）</span>
              </label>
              <label class="inline-flex items-center gap-2 cursor-pointer">
                <input v-model="form.fee_mode" type="radio" value="override" />
                <span>单独设置</span>
              </label>
            </div>
            <div v-if="form.fee_mode === 'override'" class="flex items-center gap-2">
              <input v-model="form.fee_percent" type="number" min="0" max="100" step="0.01" class="input !w-32" />
              <span class="text-sm text-ink-500">%</span>
            </div>
            <p v-if="form.owner === 'platform'" class="text-xs text-amber-600">
              平台自营商品不抽成，扣点恒为 0。
            </p>
          </div>

          <!-- 定价 -->
          <div>
            <label class="block text-xs text-ink-500 mb-1">计费模式</label>
            <select v-model="form.model" class="input">
              <option value="free">免费</option>
              <option value="one_time">一次性买断</option>
              <option value="subscription">按期订阅</option>
              <option value="seat">按席位</option>
            </select>
          </div>

          <template v-if="form.model !== 'free'">
            <div class="grid grid-cols-2 gap-3">
              <div>
                <label class="block text-xs text-ink-500 mb-1">{{ form.model === 'seat' ? '席位单价（元）' : '售价（元）' }}</label>
                <input v-if="form.model !== 'seat'" v-model="form.price_yuan" type="number" min="0" step="0.01" class="input" />
                <input v-else v-model="form.seat_price_yuan" type="number" min="0" step="0.01" class="input" />
              </div>
              <div>
                <label class="block text-xs text-ink-500 mb-1">试用天数</label>
                <input v-model.number="form.trial_days" type="number" min="0" class="input" />
              </div>
            </div>
            <div v-if="form.model === 'subscription'">
              <label class="block text-xs text-ink-500 mb-1">授权周期（天）</label>
              <input v-model.number="form.period_days" type="number" min="1" class="input" />
            </div>
            <div v-if="form.model === 'seat'" class="grid grid-cols-2 gap-3">
              <div>
                <label class="block text-xs text-ink-500 mb-1">最小席位</label>
                <input v-model.number="form.min_seats" type="number" min="1" class="input" />
              </div>
              <div>
                <label class="block text-xs text-ink-500 mb-1">最大席位（0 = 不限）</label>
                <input v-model.number="form.max_seats" type="number" min="0" class="input" />
              </div>
            </div>
          </template>

          <div>
            <label class="block text-xs text-ink-500 mb-1">商品简介</label>
            <textarea v-model="form.intro" rows="2" class="input"></textarea>
          </div>

          <div class="flex flex-wrap gap-5 text-sm">
            <label class="inline-flex items-center gap-2 cursor-pointer">
              <input v-model="form.enabled" type="checkbox" /><span>上架销售</span>
            </label>
            <label class="inline-flex items-center gap-2 cursor-pointer">
              <input v-model="form.require_approval" type="checkbox" /><span>购买需人工审核</span>
            </label>
          </div>

          <p v-if="formError" class="text-sm text-red-600">{{ formError }}</p>
        </div>

        <div class="px-5 py-4 border-t border-ink-200 flex justify-end gap-2">
          <button class="btn-ghost" @click="showEdit = false">取消</button>
          <button class="btn-primary" :disabled="saving" @click="save">{{ saving ? '保存中…' : '保存' }}</button>
        </div>
      </div>
    </div>
  </div>
</template>
