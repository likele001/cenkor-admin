<script setup lang="ts">
/**
 * 定价字段（原价 / 售价 / 限时促销）—— 提交应用页与「应用与定价」弹层共用。
 *
 * 抽成组件是为了让两处的字段、校验文案与折扣预览口径**只有一处**，
 * 不会出现「提交页能填促销、定价页不能」这类漂移。
 */
import { computed } from 'vue'
import {
  MODEL_LABEL, PROMO_STATE_LABEL, PROMO_STATE_CLASS,
  previewDiscount, centsToYuan,
  type PriceForm,
} from '@/lib/market'

const form = defineModel<PriceForm>({ required: true })
withDefaults(defineProps<{
  /** 是否渲染「商品简介 / 上架销售 / 购买需审核」（弹层里已有这些字段，就不重复渲染） */
  advanced?: boolean
}>(), { advanced: true })

const paid = computed(() => form.value.model !== 'free')
const isSeat = computed(() => form.value.model === 'seat')
const preview = computed(() => previewDiscount(form.value))

/** 折扣预览文案，如「原价 ¥199.00 → 实付 ¥99.00 · 4.9折」 */
const previewText = computed(() => {
  const p = preview.value
  if (!paid.value) return '免费应用不涉及价格'
  const unitLabel = isSeat.value ? '/席' : ''
  const eff = `实付 ¥${centsToYuan(p.unit)}${unitLabel}`
  if (p.unitList > 0 && p.label) {
    return `原价 ¥${centsToYuan(p.unitList)}${unitLabel} → ${eff} · ${p.label}`
  }
  return eff
})
</script>

<template>
  <div class="space-y-4">
    <div>
      <label class="block text-xs text-ink-500 mb-1">计费模式</label>
      <select v-model="form.model" class="input">
        <option v-for="(label, key) in MODEL_LABEL" :key="key" :value="key">{{ label }}</option>
      </select>
      <p v-if="form.model === 'free'" class="text-xs text-ink-400 mt-1">
        免费应用不展示价格与促销，也不会产生订单与收入。
      </p>
      <p v-else-if="form.model === 'one_time'" class="text-xs text-ink-400 mt-1">
        买断后授权永久有效，不设试用期。
      </p>
      <p v-else-if="isSeat" class="text-xs text-ink-400 mt-1">
        按席位数计费，授权按周期有效。
      </p>
    </div>

    <template v-if="paid">
      <div class="grid grid-cols-2 gap-3">
        <div>
          <label class="block text-xs text-ink-500 mb-1">原价（划线价，选填）</label>
          <input v-model="form.list_price" type="number" min="0" step="0.01" class="input" placeholder="199.00" />
          <p class="text-xs text-ink-400 mt-1">仅用于划线与折扣展示，不参与结算</p>
        </div>
        <div>
          <label class="block text-xs text-ink-500 mb-1">{{ isSeat ? '售价（元/席）' : '售价（元）' }}</label>
          <input v-model="form.price" type="number" min="0" step="0.01" class="input" placeholder="99.00" />
          <p class="text-xs text-ink-400 mt-1">{{ isSeat ? '每席位单价，按席位数量相乘' : '常规成交价' }}</p>
        </div>
      </div>

      <div v-if="isSeat" class="grid grid-cols-2 gap-3">
        <div>
          <label class="block text-xs text-ink-500 mb-1">授权周期（天）</label>
          <input v-model.number="form.period_days" type="number" min="1" class="input" />
          <p class="text-xs text-ink-400 mt-1">席位制按周期授权，到期需续期</p>
        </div>
        <div>
          <label class="block text-xs text-ink-500 mb-1">最小席位</label>
          <input v-model.number="form.min_seats" type="number" min="1" class="input" />
        </div>
        <div>
          <label class="block text-xs text-ink-500 mb-1">最大席位（0 = 不限）</label>
          <input v-model.number="form.max_seats" type="number" min="0" class="input" />
        </div>
      </div>

      <!-- 限时促销 -->
      <div class="rounded-xl border border-ink-200 p-3 space-y-3">
        <div class="flex items-center justify-between">
          <div class="text-xs font-medium text-ink-700">限时促销（选填）</div>
          <span
            v-if="form.promo_price"
            class="text-[10px] px-1.5 py-0.5 rounded"
            :class="PROMO_STATE_CLASS[preview.state]"
          >{{ PROMO_STATE_LABEL[preview.state] }}</span>
        </div>

        <div class="grid grid-cols-2 gap-3">
          <div>
            <label class="block text-xs text-ink-500 mb-1">{{ isSeat ? '促销价（元/席）' : '促销价（元）' }}</label>
            <input v-model="form.promo_price" type="number" min="0" step="0.01" class="input" placeholder="不促销留空" />
          </div>
          <div>
            <label class="block text-xs text-ink-500 mb-1">活动名（选填）</label>
            <input v-model="form.promo_label" class="input" maxlength="60" placeholder="如：首发 5 折" />
          </div>
        </div>

        <div class="grid grid-cols-2 gap-3">
          <div>
            <label class="block text-xs text-ink-500 mb-1">开始时间</label>
            <input v-model="form.promo_start" type="datetime-local" class="input" :disabled="!form.promo_price" />
          </div>
          <div>
            <label class="block text-xs text-ink-500 mb-1">结束时间</label>
            <input v-model="form.promo_end" type="datetime-local" class="input" :disabled="!form.promo_price" />
          </div>
        </div>
        <p class="text-xs text-ink-400">
          促销价填了才生效；时间留空表示该侧不限制。到期后自动回落售价，无需手动改回。
        </p>
      </div>

      <div class="rounded-xl bg-ink-50 border border-ink-200 p-3 text-xs text-ink-600">
        <span class="text-ink-500">当前成交价：</span><strong>{{ previewText }}</strong>
      </div>

      <template v-if="advanced">
        <div>
          <label class="block text-xs text-ink-500 mb-1">商品简介（可选）</label>
          <textarea v-model="form.intro" rows="2" class="input" placeholder="一句话说明这个应用解决什么问题"></textarea>
        </div>
        <div class="flex flex-wrap gap-5 text-sm">
          <label class="inline-flex items-center gap-2 cursor-pointer">
            <input v-model="form.enabled" type="checkbox" />
            <span>上架销售</span>
          </label>
          <label class="inline-flex items-center gap-2 cursor-pointer">
            <input v-model="form.require_approval" type="checkbox" />
            <span>购买需人工审核</span>
          </label>
        </div>
      </template>
    </template>
  </div>
</template>
