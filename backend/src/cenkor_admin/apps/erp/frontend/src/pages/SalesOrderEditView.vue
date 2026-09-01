<template>
  <PageShell :title="title">
    <template #actions>
      <el-button :icon="ArrowLeft" @click="router.back()">返回</el-button>
    </template>

    <!-- 创建模式 -->
    <el-form v-if="isNew" ref="formRef" :model="form" :rules="rules" label-width="110px" style="max-width: 1000px">
      <el-row :gutter="16">
        <el-col :span="8"><el-form-item label="客户" prop="customer_id"><el-select v-model="form.customer_id" filterable placeholder="选择客户" style="width:100%"><el-option v-for="c in customers" :key="c.id" :label="c.name" :value="c.id" /></el-select></el-form-item></el-col>
        <el-col :span="8"><el-form-item label="下单日期"><el-date-picker v-model="form.order_date" type="date" value-format="YYYY-MM-DD" style="width:100%" /></el-form-item></el-col>
        <el-col :span="8"><el-form-item label="交货日期"><el-date-picker v-model="form.delivery_date" type="date" value-format="YYYY-MM-DD" style="width:100%" /></el-form-item></el-col>
        <el-col :span="8"><el-form-item label="币种"><el-select v-model="form.currency" style="width:100%"><el-option label="CNY" value="CNY" /><el-option label="USD" value="USD" /></el-select></el-form-item></el-col>
        <el-col :span="8"><el-form-item label="折扣"><el-input-number v-model="form.discount" :min="0" :precision="2" style="width:100%" /></el-form-item></el-col>
      </el-row>
      <el-form-item label="备注"><el-input v-model="form.notes" type="textarea" :rows="2" style="max-width: 720px" /></el-form-item>
      <el-form-item label="商品明细">
        <div class="items-wrap">
          <div class="items-actions">
            <el-button type="primary" size="small" :icon="Plus" @click="itemsRef.addLine()">添加商品</el-button>
          </div>
          <OrderItemsEditor ref="itemsRef" v-model="form.items" :products="products" price-key="sale_price" @computed="onComputed" />
        </div>
      </el-form-item>
      <el-divider />
      <el-descriptions :column="3" border size="small" style="margin-bottom: 16px">
        <el-descriptions-item label="小计">{{ fmtMoney(summary.subtotal) }}</el-descriptions-item>
        <el-descriptions-item label="税额">{{ fmtMoney(summary.taxTotal) }}</el-descriptions-item>
        <el-descriptions-item label="合计">
          <b>{{ fmtMoney(summary.subtotal + summary.taxTotal - Number(form.discount) || 0) }}</b>
        </el-descriptions-item>
      </el-descriptions>
      <el-button type="primary" :loading="saving" @click="createOrder">保存订单</el-button>
    </el-form>

    <!-- 查看模式 -->
    <template v-else>
      <el-descriptions v-loading="loading" :column="3" border style="margin-bottom: 16px">
        <el-descriptions-item label="订单编号">{{ order.code }}</el-descriptions-item>
        <el-descriptions-item label="客户">{{ custName(order.customer_id) }}</el-descriptions-item>
        <el-descriptions-item label="状态"><el-tag :type="statusTagType(order.status)" size="small">{{ statusLabel(order.status) }}</el-tag></el-descriptions-item>
        <el-descriptions-item label="下单日期">{{ fmtDate(order.order_date) }}</el-descriptions-item>
        <el-descriptions-item label="交货日期">{{ fmtDate(order.delivery_date) }}</el-descriptions-item>
        <el-descriptions-item label="收款状态">{{ order.payment_status }}</el-descriptions-item>
        <el-descriptions-item label="小计">{{ fmtMoney(order.subtotal) }}</el-descriptions-item>
        <el-descriptions-item label="税额">{{ fmtMoney(order.tax_total) }}</el-descriptions-item>
        <el-descriptions-item label="合计"><b>{{ fmtMoney(order.total_amount) }}</b></el-descriptions-item>
        <el-descriptions-item label="已收/未收" :span="3">{{ fmtMoney(order.paid_amount) }} / {{ fmtMoney(order.total_amount - order.paid_amount) }}</el-descriptions-item>
      </el-descriptions>

      <div class="detail-actions">
        <el-button v-if="order.status === 'draft'" type="warning" @click="confirmOrder">确认订单</el-button>
        <el-button v-if="['confirmed', 'fulfilled'].includes(order.status)" type="success" @click="shipVisible = true">生成出货单</el-button>
        <el-button v-if="order.shipments && order.shipments.length" link type="primary" @click="router.push('/erp/warehouses')">查看仓库存货</el-button>
      </div>

      <OrderItemsEditor v-model="order.items" :products="products" price-key="sale_price" read-only />
    </template>

    <!-- 出货抽屉 -->
    <FormDrawer v-model="shipVisible" title="生成出货单" width="480px" :saving="saving" @save="shipOrder">
      <el-form :model="shipForm" label-width="90px">
        <el-form-item label="出货日期"><el-date-picker v-model="shipForm.ship_date" type="date" value-format="YYYY-MM-DD" style="width:100%" /></el-form-item>
        <el-form-item label="收货人"><el-input v-model="shipForm.receiver" /></el-form-item>
        <el-form-item label="联系电话"><el-input v-model="shipForm.phone" /></el-form-item>
        <el-form-item label="收货地址"><el-input v-model="shipForm.address" type="textarea" :rows="2" /></el-form-item>
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
import { back, currentId, isNew, go } from '../nav'

const orderId = currentId()
const isNewRoute = isNew() || orderId == null

const customers = ref([])
const products = ref([])
const order = ref({})
const loading = ref(false)
const saving = ref(false)
const formRef = ref()
const itemsRef = ref()

const form = reactive({
  customer_id: null, order_date: '', delivery_date: '', currency: 'CNY', discount: 0, notes: '', items: []
})
const summary = reactive({ subtotal: 0, taxTotal: 0 })
const rules = { customer_id: [{ required: true, message: '请选择客户', trigger: 'change' }] }

const title = computed(() => (isNew ? '新建销售订单' : `销售订单 ${order.value.code || ''}`))
const shipVisible = ref(false)
const shipForm = reactive({ ship_date: new Date().toISOString().slice(0, 10), receiver: '', phone: '', address: '' })

function custName(id) { return customers.value.find((c) => c.id === id)?.name || `#${id}` }

async function loadRefs() {
  try { customers.value = (await api.get('/customers', { page: 1, page_size: 200 })).items } catch (e) {}
  try { products.value = (await api.get('/products', { page: 1, page_size: 200 })).items } catch (e) {}
}

async function loadOrder() {
  if (isNew) return
  loading.value = true
  try { order.value = await api.get(`/sales-orders/${orderId}`) } catch (e) { ElMessage.error(e.message) } finally { loading.value = false }
}

function onComputed(s) { summary.subtotal = s.subtotal; summary.taxTotal = s.taxTotal }

async function createOrder() {
  await formRef.value.validate()
  if (!form.items.length) { ElMessage.warning('请添加商品明细'); return }
  saving.value = true
  try {
    await api.post('/sales-orders', {
      customer_id: form.customer_id, order_date: form.order_date || null,
      delivery_date: form.delivery_date || null, currency: form.currency,
      discount: Number(form.discount) || 0, notes: form.notes || null, items: form.items
    })
    ElMessage.success('订单已创建')
    router.push('/erp/sales-orders')
  } catch (e) { ElMessage.error(e.message) } finally { saving.value = false }
}

async function confirmOrder() {
  try {
    await api.post(`/sales-orders/${order.value.id}/confirm`)
    ElMessage.success('订单已确认')
    await loadOrder()
  } catch (e) { ElMessage.error(e.message) }
}

async function shipOrder() {
  saving.value = true
  try {
    await api.post(`/sales-orders/${order.value.id}/ship`, { ...shipForm })
    ElMessage.success('出货单已生成')
    shipVisible.value = false
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