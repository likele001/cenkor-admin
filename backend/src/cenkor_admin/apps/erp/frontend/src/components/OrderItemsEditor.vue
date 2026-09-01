<template>
  <el-table :data="items" border size="small" empty-text="请添加商品行">
    <el-table-column label="商品" min-width="240">
      <template #default="{ row, $index }">
        <el-select
          v-if="!readOnly"
          v-model="row.product_id"
          filterable
          :disabled="!products.length"
          placeholder="搜索选择商品"
          style="width: 100%"
          @change="(id) => onPick(row, id)"
        >
          <el-option v-for="p in products" :key="p.id" :label="`${p.code} ${p.name}`" :value="p.id" />
        </el-select>
        <template v-else>{{ row.product_code }} {{ row.product_name }}</template>
      </template>
    </el-table-column>
    <el-table-column label="数量" width="120" align="center">
      <template #default="{ row }">
        <el-input-number v-if="!readOnly" v-model="row.quantity" :min="0.01" :precision="2" size="small" controls-position="right" style="width: 100%" @change="touch" />
        <span v-else>{{ row.quantity }}</span>
      </template>
    </el-table-column>
    <el-table-column label="单位" width="90" align="center">
      <template #default="{ row }">
        <el-input v-if="!readOnly" v-model="row.unit" size="small" />
        <span v-else>{{ row.unit }}</span>
      </template>
    </el-table-column>
    <el-table-column label="单价" width="130" align="right">
      <template #default="{ row }">
        <el-input-number v-if="!readOnly" v-model="row.unit_price" :min="0" :precision="2" size="small" controls-position="right" style="width: 100%" @change="touch" />
        <span v-else>{{ fmtMoney(row.unit_price) }}</span>
      </template>
    </el-table-column>
    <el-table-column label="税率%" width="110" align="center">
      <template #default="{ row }">
        <el-input-number v-if="!readOnly" v-model="row.tax_rate" :min="0" :max="100" :precision="2" size="small" controls-position="right" style="width: 100%" @change="touch" />
        <span v-else>{{ row.tax_rate || 0 }}</span>
      </template>
    </el-table-column>
    <el-table-column label="金额" width="130" align="right">
      <template #default="{ row }">{{ fmtMoney(lineAmount(row)) }}</template>
    </el-table-column>
    <el-table-column v-if="receivedKey" :label="receivedLabel" width="110" align="center">
      <template #default="{ row }">{{ row[receivedKey] ?? 0 }}</template>
    </el-table-column>
    <el-table-column v-if="!readOnly" label="" width="56" align="center">
      <template #default="{ $index }">
        <el-button link type="danger" :icon="Delete" @click="removeLine($index)" />
      </template>
    </el-table-column>
  </el-table>
</template>

<script setup>
import { ElTable, ElTableColumn, ElSelect, ElOption, ElInput, ElInputNumber, ElButton } from 'element-plus'
import { Delete } from '@element-plus/icons-vue'
import { fmtMoney } from '../api'

const props = defineProps({
  modelValue: { type: Array, default: () => [] },
  products: { type: Array, default: () => [] },
  priceKey: { type: String, default: 'sale_price' },
  readOnly: { type: Boolean, default: false },
  receivedKey: { type: String, default: '' },
  receivedLabel: { type: String, default: '已收' }
})
const emit = defineEmits(['update:modelValue', 'computed'])
const items = props.modelValue

function onPick(row, id) {
  const p = props.products.find((x) => x.id === id)
  if (!p) return
  row.product_code = p.code
  row.product_name = p.name
  row.unit = p.unit || row.unit
  row.unit_price = Number(p[props.priceKey]) || 0
  touch()
}

function lineAmount(row) {
  return Number(row.quantity || 0) * Number(row.unit_price || 0)
}

function touch() {
  emit('update:modelValue', items)
  emit('computed', compute())
}

function compute() {
  let subtotal = 0
  let tax = 0
  for (const it of items) {
    const amt = Number(it.quantity || 0) * Number(it.unit_price || 0)
    subtotal += amt
    tax += amt * Number(it.tax_rate || 0) / 100
  }
  return { subtotal: round2(subtotal), taxTotal: round2(tax) }
}

function round2(n) { return Math.round(n * 100) / 100 }

function addLine() {
  items.push({ product_id: null, product_code: '', product_name: '', quantity: 1, unit: '', unit_price: 0, tax_rate: 0 })
  touch()
}

function removeLine(i) {
  items.splice(i, 1)
  touch()
}

defineExpose({ addLine, compute })
</script>