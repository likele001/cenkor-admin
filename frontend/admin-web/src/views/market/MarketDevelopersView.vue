<script setup lang="ts">
/**
 * 应用市场 · 开发者与分账余额。
 * GET  /api/v1/store/market/developers         列表（含钱包三池）
 * POST /api/v1/store/market/developers/{id}/adjust  手工调整余额（补偿 / 扣罚）
 */
import { ref, computed, onMounted, watch } from 'vue'
import { api } from '@/lib/api'
import { centsToYuan, errText, fmtDate } from '@/lib/market'

const loading = ref(true)
const error = ref('')
const items = ref<any[]>([])
const total = ref(0)
const page = ref(1)
const pageSize = 50
const keyword = ref('')

async function load() {
  loading.value = true
  error.value = ''
  try {
    const params: any = { page: page.value, page_size: pageSize }
    if (keyword.value.trim()) params.q = keyword.value.trim()
    const { data } = await api.get('/api/v1/store/market/developers', { params })
    items.value = data?.items ?? []
    total.value = data?.total ?? 0
  } catch (e: any) {
    error.value = errText(e)
  } finally {
    loading.value = false
  }
}

onMounted(load)
watch(page, load)

let timer: any = null
watch(keyword, () => {
  clearTimeout(timer)
  timer = setTimeout(() => { page.value = 1; load() }, 300)
})

const totalPages = computed(() => Math.max(1, Math.ceil(total.value / pageSize)))

// ---------------- 余额调整 ----------------
const showAdjust = ref(false)
const saving = ref(false)
const formError = ref('')
const current = ref<any>(null)
const form = ref({
  direction: 'add' as 'add' | 'sub',
  amount_yuan: '',
  pool: 'available',
  remark: '',
})

const POOL_HINT: Record<string, string> = {
  available: '可提现余额',
  pending: '待结算余额',
  frozen: '提现冻结余额',
}

function openAdjust(dev: any) {
  current.value = dev
  formError.value = ''
  form.value = { direction: 'add', amount_yuan: '', pool: 'available', remark: '' }
  showAdjust.value = true
}

async function submitAdjust() {
  if (!current.value) return
  const f = form.value
  const amount = Math.abs(Math.round(parseFloat(f.amount_yuan || '0') * 100))
  if (!amount) { formError.value = '请输入调整金额'; return }
  if (!f.remark.trim()) { formError.value = '必须填写调整备注'; return }

  saving.value = true
  formError.value = ''
  try {
    await api.post(`/api/v1/store/market/developers/${current.value.id}/adjust`, {
      amount_cents: f.direction === 'add' ? amount : -amount,
      pool: f.pool,
      remark: f.remark.trim(),
    })
    showAdjust.value = false
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
          <h2 class="font-semibold">开发者与分账余额</h2>
          <p class="text-xs text-ink-500 mt-1">共 {{ total }} 位开发者 · 余额由账本流水累计，可在此做人工补偿或扣罚</p>
        </div>
        <input v-model="keyword" class="input !w-56" placeholder="搜索开发者名称" />
      </div>

      <div v-if="loading" class="p-6 text-ink-500 text-sm">加载中…</div>
      <div v-else-if="error" class="p-8 text-center">
        <p class="text-red-600 mb-4 text-sm">{{ error }}</p>
        <button class="btn-primary" @click="load">重新加载</button>
      </div>
      <div v-else-if="items.length === 0" class="p-10 text-center text-ink-500 text-sm">暂无开发者</div>

      <table v-else class="w-full text-sm">
        <thead class="text-left text-ink-500 border-b border-ink-200">
          <tr>
            <th class="px-3 py-2 font-normal">开发者</th>
            <th class="px-3 py-2 font-normal">状态</th>
            <th class="px-3 py-2 font-normal text-right">应用数</th>
            <th class="px-3 py-2 font-normal text-right">可提现</th>
            <th class="px-3 py-2 font-normal text-right">待结算</th>
            <th class="px-3 py-2 font-normal text-right">提现中</th>
            <th class="px-3 py-2 font-normal text-right">累计收入</th>
            <th class="px-3 py-2 font-normal text-right">操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="d in items" :key="d.id" class="border-b border-ink-100 last:border-0">
            <td class="px-3 py-3">
              <div class="font-medium">{{ d.display_name }}</div>
              <div class="text-xs text-ink-400">
                #{{ d.id }}<span v-if="d.email"> · {{ d.email }}</span>
              </div>
            </td>
            <td class="px-3 py-3">
              <span
                class="text-xs px-1.5 py-0.5 rounded"
                :class="d.status === 'active' ? 'bg-emerald-50 text-emerald-600' : 'bg-ink-100 text-ink-500'"
              >{{ d.status === 'active' ? '正常' : '已停用' }}</span>
              <div class="text-xs text-ink-400 mt-1">{{ fmtDate(d.created_at) }}</div>
            </td>
            <td class="px-3 py-3 text-right">{{ d.app_count }}</td>
            <td class="px-3 py-3 text-right font-medium">¥{{ d.wallet?.available ?? '0.00' }}</td>
            <td class="px-3 py-3 text-right text-ink-500">¥{{ d.wallet?.pending ?? '0.00' }}</td>
            <td class="px-3 py-3 text-right text-ink-500">¥{{ d.wallet?.frozen ?? '0.00' }}</td>
            <td class="px-3 py-3 text-right">¥{{ d.wallet?.total_income ?? '0.00' }}</td>
            <td class="px-3 py-3 text-right">
              <button class="text-xs text-blue-600 hover:text-blue-800" @click="openAdjust(d)">调整余额</button>
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

    <!-- 调整弹层 -->
    <div v-if="showAdjust" class="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4" @click.self="showAdjust = false">
      <div class="bg-white rounded-2xl w-full max-w-md shadow-xl">
        <div class="px-5 py-4 border-b border-ink-200 flex items-center justify-between">
          <div>
            <h3 class="font-semibold">调整余额</h3>
            <p class="text-xs text-ink-500 mt-0.5">{{ current?.display_name }} · #{{ current?.id }}</p>
          </div>
          <button class="text-ink-400 hover:text-ink-900" @click="showAdjust = false">✕</button>
        </div>

        <div class="px-5 py-4 space-y-3">
          <div class="rounded-xl bg-ink-50 border border-ink-200 p-3 text-xs text-ink-600 space-y-1">
            <div>可提现 ¥{{ current?.wallet?.available ?? '0.00' }}</div>
            <div>待结算 ¥{{ current?.wallet?.pending ?? '0.00' }} · 提现中 ¥{{ current?.wallet?.frozen ?? '0.00' }}</div>
          </div>

          <div>
            <label class="block text-xs text-ink-500 mb-1">方向</label>
            <div class="flex gap-4 text-sm">
              <label class="inline-flex items-center gap-2 cursor-pointer">
                <input v-model="form.direction" type="radio" value="add" /><span>增加（补偿发放）</span>
              </label>
              <label class="inline-flex items-center gap-2 cursor-pointer">
                <input v-model="form.direction" type="radio" value="sub" /><span>扣减（扣罚）</span>
              </label>
            </div>
          </div>

          <div>
            <label class="block text-xs text-ink-500 mb-1">金额（元）</label>
            <input v-model="form.amount_yuan" type="number" min="0" step="0.01" class="input" placeholder="0.00" />
          </div>

          <div>
            <label class="block text-xs text-ink-500 mb-1">资金池</label>
            <select v-model="form.pool" class="input">
              <option value="available">可提现</option>
              <option value="pending">待结算</option>
              <option value="frozen">提现冻结</option>
            </select>
            <p class="text-xs text-ink-400 mt-1">{{ POOL_HINT[form.pool] }}，调整会计入资金流水</p>
          </div>

          <div>
            <label class="block text-xs text-ink-500 mb-1">备注（必填）</label>
            <textarea v-model="form.remark" rows="2" class="input" placeholder="如：618 活动补偿 / 违规扣罚"></textarea>
          </div>

          <p v-if="formError" class="text-sm text-red-600">{{ formError }}</p>
        </div>

        <div class="px-5 py-4 border-t border-ink-200 flex justify-end gap-2">
          <button class="btn-ghost" @click="showAdjust = false">取消</button>
          <button class="btn-primary" :disabled="saving" @click="submitAdjust">{{ saving ? '提交中…' : '确认调整' }}</button>
        </div>
      </div>
    </div>
  </div>
</template>
