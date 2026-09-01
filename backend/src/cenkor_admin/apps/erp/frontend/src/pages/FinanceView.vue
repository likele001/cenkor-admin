<template>
  <PageShell title="财务" subtitle="应收应付 · 发票 · 收付款">
    <!-- 总览卡片 -->
    <div v-loading="overviewLoading" class="stat-grid">
      <div class="stat-card receivable">
        <div class="stat-label">应收余额</div>
        <div class="stat-value">{{ fmtMoney(overview.receivable_balance) }}</div>
        <div class="stat-extra">{{ overview.receivable_count }} 笔未结</div>
      </div>
      <div class="stat-card payable">
        <div class="stat-label">应付余额</div>
        <div class="stat-value">{{ fmtMoney(overview.payable_balance) }}</div>
        <div class="stat-extra">{{ overview.payable_count }} 笔未结</div>
      </div>
      <div class="stat-card income">
        <div class="stat-label">累计收款</div>
        <div class="stat-value">{{ fmtMoney(overview.received_total) }}</div>
      </div>
      <div class="stat-card expense">
        <div class="stat-label">累计付款</div>
        <div class="stat-value">{{ fmtMoney(overview.paid_total) }}</div>
      </div>
    </div>

    <el-tabs v-model="activeTab" class="fin-tabs">
      <!-- 销售发票 -->
      <el-tab-pane label="销售发票" name="inv">
        <div class="tab-actions">
          <el-button type="primary" size="small" :icon="Plus" @click="openInv(null)">新增销售发票</el-button>
        </div>
        <DataTable
          :data="invRows" :columns="invColumns" :total="invTotal" :page="invPage"
          :page-size="invPageSize" :loading="invLoading"
          @update:page="loadInv" @update:pageSize="(s)=>{invPageSize=s;loadInv(1)}"
        >
          <template #operation>
            <el-table-column label="操作" width="110" align="center" fixed="right">
              <template #default="{ row }">
                <el-button v-if="row.status !== 'paid'" link type="success" @click="openReceive(row)">收款</el-button>
              </template>
            </el-table-column>
          </template>
        </DataTable>
      </el-tab-pane>

      <!-- 采购发票 -->
      <el-tab-pane label="采购发票" name="pinv">
        <div class="tab-actions">
          <el-button type="primary" size="small" :icon="Plus" @click="openPInv(null)">新增采购发票</el-button>
        </div>
        <DataTable
          :data="pInvRows" :columns="pInvColumns" :total="pInvTotal" :page="pInvPage"
          :page-size="pInvPageSize" :loading="pInvLoading"
          @update:page="loadPInv" @update:pageSize="(s)=>{pInvPageSize=s;loadPInv(1)}"
        >
          <template #operation>
            <el-table-column label="操作" width="110" align="center" fixed="right">
              <template #default="{ row }">
                <el-button v-if="row.status !== 'paid'" link type="warning" @click="openPay(row)">付款</el-button>
              </template>
            </el-table-column>
          </template>
        </DataTable>
      </el-tab-pane>

      <!-- 收付款记录 -->
      <el-tab-pane label="收付款记录" name="payments">
        <DataTable
          :data="payRows" :columns="payColumns" :total="payTotal" :page="payPage"
          :page-size="payPageSize" :loading="payLoading"
          @update:page="loadPayments" @update:pageSize="(s)=>{payPageSize=s;loadPayments(1)}"
        />
      </el-tab-pane>

      <!-- 应收账款 -->
      <el-tab-pane label="应收账款" name="ar">
        <DataTable
          :data="arRows" :columns="arColumns" :total="arTotal" :page="arPage"
          :page-size="arPageSize" :loading="arLoading"
          @update:page="loadAr" @update:pageSize="(s)=>{arPageSize=s;loadAr(1)}"
        />
      </el-tab-pane>

      <!-- 应付账款 -->
      <el-tab-pane label="应付账款" name="ap">
        <DataTable
          :data="apRows" :columns="apColumns" :total="apTotal" :page="apPage"
          :page-size="apPageSize" :loading="apLoading"
          @update:page="loadAp" @update:pageSize="(s)=>{apPageSize=s;loadAp(1)}"
        />
      </el-tab-pane>
    </el-tabs>

    <!-- 新增销售发票 -->
    <FormDrawer v-model="invDrawer" title="新增销售发票" width="520px" :saving="saving" @save="createInv">
      <el-form :model="invForm" label-width="100px">
        <el-form-item label="客户" required><el-select v-model="invForm.customer_id" filterable placeholder="选择客户" style="width:100%"><el-option v-for="c in customers" :key="c.id" :label="c.name" :value="c.id" /></el-select></el-form-item>
        <el-form-item label="关联订单"><el-select v-model="invForm.sales_order_id" filterable clearable style="width:100%"><el-option v-for="o in salesOrders" :key="o.id" :label="`${o.code}（${fmtMoney(o.total_amount)}）`" :value="o.id" /></el-select></el-form-item>
        <el-row :gutter="16">
          <el-col :span="12"><el-form-item label="开票日期"><el-date-picker v-model="invForm.invoice_date" type="date" value-format="YYYY-MM-DD" style="width:100%" /></el-form-item></el-col>
          <el-col :span="12"><el-form-item label="到期日"><el-date-picker v-model="invForm.due_date" type="date" value-format="YYYY-MM-DD" style="width:100%" /></el-form-item></el-col>
        </el-row>
        <el-row :gutter="16">
          <el-col :span="12"><el-form-item label="金额(不含税)"><el-input-number v-model="invForm.amount" :min="0" :precision="2" style="width:100%" /></el-form-item></el-col>
          <el-col :span="12"><el-form-item label="税额"><el-input-number v-model="invForm.tax_total" :min="0" :precision="2" style="width:100%" /></el-form-item></el-col>
        </el-row>
        <el-form-item label="价税合计"><el-input-number v-model="invForm.total_amount" :min="0" :precision="2" style="width:100%" /></el-form-item>
        <el-form-item label="备注"><el-input v-model="invForm.notes" type="textarea" :rows="2" /></el-form-item>
      </el-form>
    </FormDrawer>

    <!-- 新增采购发票 -->
    <FormDrawer v-model="pInvDrawer" title="新增采购发票" width="520px" :saving="saving" @save="createPInv">
      <el-form :model="pInvForm" label-width="100px">
        <el-form-item label="供应商" required><el-select v-model="pInvForm.supplier_id" filterable placeholder="选择供应商" style="width:100%"><el-option v-for="s in suppliers" :key="s.id" :label="s.name" :value="s.id" /></el-select></el-form-item>
        <el-form-item label="关联采购单"><el-select v-model="pInvForm.purchase_order_id" filterable clearable style="width:100%"><el-option v-for="o in poOrders" :key="o.id" :label="`${o.code}（${fmtMoney(o.total_amount)}）`" :value="o.id" /></el-select></el-form-item>
        <el-row :gutter="16">
          <el-col :span="12"><el-form-item label="开票日期"><el-date-picker v-model="pInvForm.invoice_date" type="date" value-format="YYYY-MM-DD" style="width:100%" /></el-form-item></el-col>
          <el-col :span="12"><el-form-item label="到期日"><el-date-picker v-model="pInvForm.due_date" type="date" value-format="YYYY-MM-DD" style="width:100%" /></el-form-item></el-col>
        </el-row>
        <el-row :gutter="16">
          <el-col :span="12"><el-form-item label="金额(不含税)"><el-input-number v-model="pInvForm.amount" :min="0" :precision="2" style="width:100%" /></el-form-item></el-col>
          <el-col :span="12"><el-form-item label="税额"><el-input-number v-model="pInvForm.tax_total" :min="0" :precision="2" style="width:100%" /></el-form-item></el-col>
        </el-row>
        <el-form-item label="价税合计"><el-input-number v-model="pInvForm.total_amount" :min="0" :precision="2" style="width:100%" /></el-form-item>
      </el-form>
    </FormDrawer>

    <!-- 收款 -->
    <FormDrawer v-model="receiveDrawer" title="发票收款" width="440px" :saving="saving" @save="doReceive">
      <el-form :model="payForm" label-width="90px">
        <el-form-item label="收款金额"><el-input-number v-model="payForm.amount" :min="0.01" :precision="2" style="width:100%" /></el-form-item>
        <el-form-item label="方式">
          <el-select v-model="payForm.method" style="width:100%">
            <el-option label="银行转账" value="bank" />
            <el-option label="现金" value="cash" />
            <el-option label="微信" value="wechat" />
            <el-option label="支付宝" value="alipay" />
          </el-select>
        </el-form-item>
        <el-form-item label="收款日期"><el-date-picker v-model="payForm.paid_at" type="date" value-format="YYYY-MM-DD" style="width:100%" /></el-form-item>
        <el-form-item label="备注"><el-input v-model="payForm.remark" /></el-form-item>
      </el-form>
    </FormDrawer>
  </PageShell>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue'
import {
  ElMessage, ElButton, ElForm, ElFormItem, ElInput, ElInputNumber, ElSelect, ElOption,
  ElRow, ElCol, ElDatePicker, ElTabs, ElTabPane
} from 'element-plus'
import { Plus } from '@element-plus/icons-vue'
import PageShell from '../components/PageShell.vue'
import DataTable from '../components/DataTable.vue'
import FormDrawer from '../components/FormDrawer.vue'
import { api, fmtMoney, fmtDate, statusLabel, statusTagType } from '../api'

const activeTab = ref('inv')
const overview = reactive({ receivable_balance: 0, payable_balance: 0, received_total: 0, paid_total: 0, receivable_count: 0, payable_count: 0 })
const overviewLoading = ref(false)
const saving = ref(false)
const customers = ref([])
const suppliers = ref([])
const salesOrders = ref([])
const poOrders = ref([])

async function loadOverview() {
  overviewLoading.value = true
  try { Object.assign(overview, await api.get('/finance/overview')) } catch (e) { ElMessage.error(e.message) } finally { overviewLoading.value = false }
}

// ---- 销售发票 ----
const invRows = ref([])
const invTotal = ref(0)
const invPage = ref(1)
const invPageSize = ref(20)
const invLoading = ref(false)
const invColumns = [
  { prop: 'code', label: '发票号', width: 120 },
  { prop: 'customer_id', label: '客户', minWidth: 160, formatter: (r) => custName(r.customer_id) },
  { prop: 'invoice_date', label: '开票日期', width: 110, formatter: (r) => fmtDate(r.invoice_date) },
  { prop: 'total_amount', label: '价税合计', width: 120, align: 'right', formatter: (r) => fmtMoney(r.total_amount) },
  { prop: 'paid_amount', label: '已收', width: 110, align: 'right', formatter: (r) => fmtMoney(r.paid_amount) },
  { prop: 'status', label: '状态', width: 90, tag: { text: (r) => statusLabel(r.status), type: (r) => statusTagType(r.status) } }
]
async function loadInv(p = 1) {
  invPage.value = p
  invLoading.value = true
  try {
    const data = await api.get('/finance/invoices', { page: invPage.value, page_size: invPageSize.value })
    invRows.value = data.items
    invTotal.value = data.total
  } catch (e) { ElMessage.error(e.message) } finally { invLoading.value = false }
}

// ---- 采购发票 ----
const pInvRows = ref([])
const pInvTotal = ref(0)
const pInvPage = ref(1)
const pInvPageSize = ref(20)
const pInvLoading = ref(false)
const pInvColumns = [
  { prop: 'code', label: '发票号', width: 130 },
  { prop: 'supplier_id', label: '供应商', minWidth: 160, formatter: (r) => supName(r.supplier_id) },
  { prop: 'invoice_date', label: '开票日期', width: 110, formatter: (r) => fmtDate(r.invoice_date) },
  { prop: 'total_amount', label: '价税合计', width: 120, align: 'right', formatter: (r) => fmtMoney(r.total_amount) },
  { prop: 'paid_amount', label: '已付', width: 110, align: 'right', formatter: (r) => fmtMoney(r.paid_amount) },
  { prop: 'status', label: '状态', width: 90, tag: { text: (r) => statusLabel(r.status), type: (r) => statusTagType(r.status) } }
]
async function loadPInv(p = 1) {
  pInvPage.value = p
  pInvLoading.value = true
  try {
    const data = await api.get('/finance/purchase-invoices', { page: pInvPage.value, page_size: pInvPageSize.value })
    pInvRows.value = data.items
    pInvTotal.value = data.total
  } catch (e) { ElMessage.error(e.message) } finally { pInvLoading.value = false }
}

// ---- 收付款 ----
const payRows = ref([])
const payTotal = ref(0)
const payPage = ref(1)
const payPageSize = ref(20)
const payLoading = ref(false)
const payColumns = [
  { prop: 'code', label: '流水号', width: 130 },
  { prop: 'direction', label: '方向', width: 90, tag: { text: (r) => (r.direction === 'in' ? '收款' : '付款'), type: (r) => (r.direction === 'in' ? 'success' : 'danger') } },
  { prop: 'method', label: '方式', width: 100 },
  { prop: 'amount', label: '金额', width: 130, align: 'right', formatter: (r) => fmtMoney(r.amount) },
  { prop: 'paid_at', label: '日期', width: 110, formatter: (r) => fmtDate(r.paid_at) },
  { prop: 'ref_type', label: '关联', width: 100 },
  { prop: 'remark', label: '备注', minWidth: 140 }
]
async function loadPayments(p = 1) {
  payPage.value = p
  payLoading.value = true
  try {
    const data = await api.get('/finance/payments', { page: payPage.value, page_size: payPageSize.value })
    payRows.value = data.items
    payTotal.value = data.total
  } catch (e) { ElMessage.error(e.message) } finally { payLoading.value = false }
}

// ---- 应收 ----
const arRows = ref([])
const arTotal = ref(0)
const arPage = ref(1)
const arPageSize = ref(20)
const arLoading = ref(false)
const arColumns = [
  { prop: 'customer_id', label: '客户', minWidth: 160, formatter: (r) => custName(r.customer_id) },
  { prop: 'amount', label: '应收', width: 120, align: 'right', formatter: (r) => fmtMoney(r.amount) },
  { prop: 'paid_amount', label: '已收', width: 110, align: 'right', formatter: (r) => fmtMoney(r.paid_amount) },
  { prop: 'balance', label: '余额', width: 120, align: 'right', formatter: (r) => fmtMoney(r.balance) },
  { prop: 'due_date', label: '到期日', width: 110, formatter: (r) => fmtDate(r.due_date) },
  { prop: 'status', label: '状态', width: 90, tag: { text: (r) => statusLabel(r.status), type: (r) => statusTagType(r.status) } }
]
async function loadAr(p = 1) {
  arPage.value = p
  arLoading.value = true
  try {
    const data = await api.get('/finance/receivables', { page: arPage.value, page_size: arPageSize.value })
    arRows.value = data.items
    arTotal.value = data.total
  } catch (e) { ElMessage.error(e.message) } finally { arLoading.value = false }
}

// ---- 应付 ----
const apRows = ref([])
const apTotal = ref(0)
const apPage = ref(1)
const apPageSize = ref(20)
const apLoading = ref(false)
const apColumns = [
  { prop: 'supplier_id', label: '供应商', minWidth: 160, formatter: (r) => supName(r.supplier_id) },
  { prop: 'amount', label: '应付', width: 120, align: 'right', formatter: (r) => fmtMoney(r.amount) },
  { prop: 'paid_amount', label: '已付', width: 110, align: 'right', formatter: (r) => fmtMoney(r.paid_amount) },
  { prop: 'balance', label: '余额', width: 120, align: 'right', formatter: (r) => fmtMoney(r.balance) },
  { prop: 'due_date', label: '到期日', width: 110, formatter: (r) => fmtDate(r.due_date) },
  { prop: 'status', label: '状态', width: 90, tag: { text: (r) => statusLabel(r.status), type: (r) => statusTagType(r.status) } }
]
async function loadAp(p = 1) {
  apPage.value = p
  apLoading.value = true
  try {
    const data = await api.get('/finance/payables', { page: apPage.value, page_size: apPageSize.value })
    apRows.value = data.items
    apTotal.value = data.total
  } catch (e) { ElMessage.error(e.message) } finally { apLoading.value = false }
}

function custName(id) { return customers.value.find((c) => c.id === id)?.name || `#${id}` }
function supName(id) { return suppliers.value.find((s) => s.id === id)?.name || `#${id}` }

async function loadRefs() {
  try { customers.value = (await api.get('/customers', { page: 1, page_size: 200 })).items } catch (e) {}
  try { suppliers.value = (await api.get('/suppliers', { page: 1, page_size: 200 })).items } catch (e) {}
  try { salesOrders.value = (await api.get('/sales-orders', { page: 1, page_size: 200 })).items } catch (e) {}
  try { poOrders.value = (await api.get('/purchase-orders', { page: 1, page_size: 200 })).items } catch (e) {}
}

// ---- 新增销售发票 ----
const invDrawer = ref(false)
const invForm = reactive({})
function openInv() {
  Object.assign(invForm, {
    customer_id: null, sales_order_id: null, invoice_date: new Date().toISOString().slice(0, 10),
    due_date: '', amount: 0, tax_total: 0, total_amount: 0, notes: ''
  })
  invDrawer.value = true
}
async function createInv() {
  if (!invForm.customer_id) { ElMessage.warning('请选择客户'); return }
  saving.value = true
  try {
    await api.post('/finance/invoices', {
      customer_id: invForm.customer_id, sales_order_id: invForm.sales_order_id || null,
      invoice_date: invForm.invoice_date || null, due_date: invForm.due_date || null,
      amount: Number(invForm.amount) || 0, tax_total: Number(invForm.tax_total) || 0,
      total_amount: Number(invForm.total_amount) || 0, notes: invForm.notes || null
    })
    ElMessage.success('发票已创建')
    invDrawer.value = false
    loadInv(1); loadOverview()
  } catch (e) { ElMessage.error(e.message) } finally { saving.value = false }
}

// ---- 新增采购发票 ----
const pInvDrawer = ref(false)
const pInvForm = reactive({})
function openPInv() {
  Object.assign(pInvForm, {
    supplier_id: null, purchase_order_id: null, invoice_date: new Date().toISOString().slice(0, 10),
    due_date: '', amount: 0, tax_total: 0, total_amount: 0
  })
  pInvDrawer.value = true
}
async function createPInv() {
  if (!pInvForm.supplier_id) { ElMessage.warning('请选择供应商'); return }
  saving.value = true
  try {
    await api.post('/finance/purchase-invoices', {
      supplier_id: pInvForm.supplier_id, purchase_order_id: pInvForm.purchase_order_id || null,
      invoice_date: pInvForm.invoice_date || null, due_date: pInvForm.due_date || null,
      amount: Number(pInvForm.amount) || 0, tax_total: Number(pInvForm.tax_total) || 0,
      total_amount: Number(pInvForm.total_amount) || 0
    })
    ElMessage.success('采购发票已创建')
    pInvDrawer.value = false
    loadPInv(1); loadOverview()
  } catch (e) { ElMessage.error(e.message) } finally { saving.value = false }
}

// ---- 收款/付款 ----
const receiveDrawer = ref(false)
const isReceive = ref(true)
const targetInvoiceId = ref(null)
const payForm = reactive({})
function openReceive(row) { isReceive.value = true; targetInvoiceId.value = row.id; openPayForm() }
function openPay(row) { isReceive.value = false; targetInvoiceId.value = row.id; openPayForm() }
function openPayForm() {
  Object.assign(payForm, { amount: 0, method: 'bank', paid_at: new Date().toISOString().slice(0, 10), remark: '' })
  receiveDrawer.value = true
}
async function doReceive() {
  const amount = Number(payForm.amount) || 0
  if (amount <= 0) { ElMessage.warning('请输入金额'); return }
  saving.value = true
  const path = isReceive.value
    ? `/finance/invoices/${targetInvoiceId.value}/receive`
    : `/finance/purchase-invoices/${targetInvoiceId.value}/pay`
  try {
    await api.post(path, { amount, method: payForm.method, paid_at: payForm.paid_at || null, remark: payForm.remark || null })
    ElMessage.success(isReceive.value ? '收款成功' : '付款成功')
    receiveDrawer.value = false
    loadInv(invPage.value); loadPInv(pInvPage.value); loadAr(1); loadAp(1); loadPayments(1); loadOverview()
  } catch (e) { ElMessage.error(e.message) } finally { saving.value = false }
}

onMounted(async () => {
  await loadRefs()
  await Promise.all([loadOverview(), loadInv(1), loadPInv(1), loadPayments(1), loadAr(1), loadAp(1)])
})
</script>

<style scoped>
.stat-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 14px;
  margin-bottom: 18px;
}
.stat-card {
  border-radius: 10px;
  padding: 16px 18px;
  color: #fff;
}
.stat-card.receivable { background: linear-gradient(135deg, #f59e0b, #f97316); }
.stat-card.payable { background: linear-gradient(135deg, #ef4444, #dc2626); }
.stat-card.income { background: linear-gradient(135deg, #10b981, #059669); }
.stat-card.expense { background: linear-gradient(135deg, #6366f1, #4f46e5); }
.stat-label { font-size: 13px; opacity: 0.9; }
.stat-value { font-size: 24px; font-weight: 700; margin: 6px 0; }
.stat-extra { font-size: 12px; opacity: 0.85; }
.tab-actions { display: flex; justify-content: flex-end; margin-bottom: 10px; }
.fin-tabs { margin-top: 4px; }
@media (max-width: 900px) { .stat-grid { grid-template-columns: repeat(2, 1fr); } }
</style>