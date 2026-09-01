<template>
  <PageShell :title="title">
    <template #actions>
      <el-button :icon="ArrowLeft" @click="back()">返回</el-button>
    </template>

    <!-- 创建模式 -->
    <el-form v-if="isNew" ref="formRef" :model="form" :rules="rules" label-width="110px" style="max-width: 1000px">
      <el-row :gutter="16">
        <el-col :span="8"><el-form-item label="供应商" prop="supplier_id"><el-select v-model="form.supplier_id" filterable placeholder="选择供应商" style="width:100%"><el-option v-for="s in suppliers" :key="s.id" :label="s.name" :value="s.id" /></el-select></el-form-item></el-col>
        <el-col :span="8"><el-form-item label="下单日期"><el-date-picker v-model="form.order_date" type="date" value-format="YYYY-MM-DD" style="width:100%" /></el-form-item></el-col>
        <el-col :span="8"><el-form-item label="期望到货"><el-date-picker v-model="form.expected_date" type="date" value-format="YYYY-MM-DD" style="width:100%" /></el-form-item></el-col>
        <el-col :span="8"><el-form-item label="币种"><el-select v-model="form.currency" style="width:100%"><el-option label="CNY" value="CNY" /><el-option label="USD" value="USD" /></el-select></el-form-item></el-col>
        <el-col :span="8"><el-form-item label="折扣"><el-input-number v-model="form.discount" :min="0" :precision="2" style="width:100%" /></el-form-item></el-col>
      </el-row>
      <el-form-item label="备注"><el-input v-model="form.notes" type="textarea" :rows="2" style="max-width: 720px" /></el-form-item>
      <el-form-item label="商品明细">
        <div class="items-wrap">
          <div class="items-actions">
            <el-button type="primary" size="small" :icon="Plus" @click="itemsRef.addLine()">添加商品</el-button>
          </div>
          <OrderItemsEditor ref="itemsRef" v-model="form.items" :products="products" price-key="purchase_price" @computed="onComputed" />
        </div>
      </el-form-item>
      <el-divider />
      <el-descriptions :column="3" border size="small" style="margin-bottom: 16px">
        <el-descriptions-item label="小计">{{ fmtMoney(summary.subtotal) }}</el-descriptions-item>
        <el-descriptions-item label="税额">{{ fmtMoney(summary.taxTotal) }}</el-descriptions-item>
        <el-descriptions-item label="合计"><b>{{ fmtMoney(summary.subtotal + summary.taxTotal - Number(form.discount) || 0) }}</b></el-descriptions-item>
      </el-descriptions>
      <el-button type="primary" :loading="saving" @click="createOrder">保存采购订单</el-button>
    </el-form>

    <!-- 查看模式 -->
    <template v-else>
      <el-descriptions v-loading="loading" :column="3" border style="margin-bottom: 16px">
        <el-descriptions-item label="订单编号">{{ order.code }}</el-descriptions-item>
        <el-descriptions-item label="供应商">{{ supName(order.supplier_id) }}</el-descriptions-item>
        <el-descriptions-item label="状态"><el-tag :type="statusTagType(order.status)" size="small">{{ statusLabel(order.status) }}</el-tag></el-descriptions-item>
        <el-descriptions-item label="下单日期">{{ fmtDate(order.order_date) }}</el-descriptions-item>
        <el-descriptions-item label="期望到货">{{ fmtDate(order.expected_date) }}</el-descriptions-item>
        <el-descriptions-item label="付款状态">{{ order.payment_status }}</el-descriptions-item>
        <el-descriptions-item label="小计">{{ fmtMoney(order.subtotal) }}</el-descriptions-item>
        <el-descriptions-item label="税额">{{ fmtMoney(order.tax_total) }}</el-descriptions-item>
        <el-descriptions-item label="合计"><b>{{ fmtMoney(order.total_amount) }}</b></el-descriptions-item>
        <el-descriptions-item label="已付/未付" :span="3">{{ fmtMoney(order.paid_amount) }} / {{ fmtMoney(order.total_amount - order.paid_amount) }}</el-descriptions-item>
      </el-descriptions>

      <div class="detail-actions">
        <el-button v-if="order.status === 'draft'" type="warning" @click="confirmOrder">确认订单</el-button>
        <el-button v-if="['confirmed', 'received'].includes(order.status)" type="success" @click="openReceive">收货入库</el-button>
      </div>

      <OrderItemsEditor v-model="order.items" :products="products" price-key="purchase_price" read-only received-key="received_qty" received-label="已收" />
    </template>

    <!-- 收货抽屉 -->
    <FormDrawer v-model="receiveVisible" title="收货入库" width="480px" :saving="saving" @save="receiveOrder">
      <el-form :model="receiveForm" label-width="90px">
        <el-form-item label="仓库" prop="warehouse_id">
          <el-select v-model="receiveForm.warehouse_id" placeholder="选择仓库" style="width:100%">
            <el-option v-for="w in warehouses" :key="w.id" :label="w.name" :value="w.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="收货日期"><el-date-picker v-model="receiveForm.receipt_date" type="date" value-format="YYYY-MM-DD" style="width:100%" /></el-form-item>
        <el-form-item label="承运商"><el-input v-model="receiveForm.carrier" /></el-form-item>
        <el-form-item label="物流单号"><el-input v-model="receiveForm.tracking_no" /></el-form-item>
      </el-form>
    </FormDrawer>
  </PageShell>
</template>

<script setup>
import { ref, reactive, computed, onMounted } from 'vue'
import {
  ElMessage, ElButton, ElForm, ElFormItem, ElInput, ElInputNumber, ElSelect, ElOption,
  ElRow, ElCol, ElDatePicker, ElDivider, ElDescriptions, ElDescriptionsItem, ElTag
} from 'element-plus'
import { Plus, ArrowLeft } from '@element-plus/icons-vue'
import PageShell from '../components/PageShell.vue'
import FormDrawer from '../components/FormDrawer.vue'
import OrderItemsEditor from '../components/OrderItemsEditor.vue'
import { api, fmtMoney, fmtDate, statusLabel, statusTagType } from '../api'
import { back, go, currentId, isNew as isNewRoute } from '../nav'

const orderId = currentId()
const isNew = isNewRoute() || orderId == null

const suppliers = ref([])
const products = ref([])
const warehouses = ref([])
const order = ref({})
const loading = ref(false)
const saving = ref(false)
const formRef = ref()
const itemsRef = ref()

const form = reactive({
  supplier_id: null, order_date: '', expected_date: '', currency: 'CNY', discount: 0, notes: '', items: []
})
const summary = reactive({ subtotal: 0, taxTotal: 0 })
const rules = { supplier_id: [{ required: true, message: '请选择供应商', trigger: 'change' }] }

const title = computed(() => (isNew ? '新建采购订单' : `采购订单 ${order.value.code || ''}`))
const receiveVisible = ref(false)
const receiveForm = reactive({ warehouse_id: null, receipt_date: new Date().toISOString().slice(0, 10), carrier: '', tracking_no: '' })

function supName(id) { return suppliers.value.find((s) => s.id === id)?.name || `#${id}` }

async function loadRefs() {
  try { suppliers.value = (await api.get('/suppliers', { page: 1, page_size: 200 })).items } catch (e) {}
  try { products.value = (await api.get('/products', { page: 1, page_size: 200 })).items } catch (e) {}
  try { warehouses.value = (await api.get('/warehouses', { page: 1, page_size: 200 })).items } catch (e) {}
}

async function loadOrder() {
  if (isNew) return
  loading.value = true
  try { order.value = await api.get(`/purchase-orders/${orderId}`) } catch (e) { ElMessage.error(e.message) } finally { loading.value = false }
}

function onComputed(s) { summary.subtotal = s.subtotal; summary.taxTotal = s.taxTotal }

async function createOrder() {
  await formRef.value.validate()
  if (!form.items.length) { ElMessage.warning('请添加商品明细'); return }
  saving.value = true
  try {
    await api.post('/purchase-orders', {
      supplier_id: form.supplier_id, order_date: form.order_date || null,
      expected_date: form.expected_date || null, currency: form.currency,
      discount: Number(form.discount) || 0, notes: form.notes || null, items: form.items
    })
    ElMessage.success('采购订单已创建')
    go('/erp/purchase-orders')
  } catch (e) { ElMessage.error(e.message) } finally { saving.value = false }
}

async function confirmOrder() {
  try {
    await api.post(`/purchase-orders/${order.value.id}/confirm`)
    ElMessage.success('订单已确认')
    await loadOrder()
  } catch (e) { ElMessage.error(e.message) }
}

function openReceive() {
  if (!warehouses.value.length) { ElMessage.warning('请先在「仓库」模块创建仓库'); return }
  receiveForm.warehouse_id = warehouses.value[0].id
  receiveVisible.value = true
}

async function receiveOrder() {
  if (!receiveForm.warehouse_id) { ElMessage.warning('请选择仓库'); return }
  saving.value = true
  try {
    await api.post(`/purchase-orders/${order.value.id}/receive`, {
      warehouse_id: receiveForm.warehouse_id, receipt_date: receiveForm.receipt_date || null,
      carrier: receiveForm.carrier || null, tracking_no: receiveForm.tracking_no || null
    })
    ElMessage.success('收货完成，库存已更新')
    receiveVisible.value = false
    await loadOrder()
  } catch (e) { ElMessage.error(e.message) } finally { saving.value = false }
}

onMounted(async () => {
  await loadRefs()
  await loadOrder()
})
</script>

<style scoped>
.items-wrap { width: 100%; }
.items-actions { display: flex; justify-content: flex-end; margin-bottom: 8px; }
.detail-actions { display: flex; gap: 8px; margin-bottom: 12px; }
</style>