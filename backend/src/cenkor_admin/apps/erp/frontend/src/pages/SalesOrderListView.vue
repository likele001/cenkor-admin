<template>
  <PageShell title="销售订单" subtitle="报价单 → 订单 → 出货">
    <template #actions>
      <el-button type="primary" :icon="Plus" @click="goCreate">新建订单</el-button>
    </template>

    <SearchBar :fields="searchFields" @search="onSearch" />
    <div class="filter-row">
      <el-select v-model="filters.status" placeholder="订单状态" clearable style="width: 160px" @change="load(1)">
        <el-option v-for="(l, v) in orderStatus" :key="v" :label="l" :value="v" />
      </el-select>
      <el-select v-model="filters.customer_id" placeholder="客户" clearable filterable style="width: 200px" @change="load(1)">
        <el-option v-for="c in customers" :key="c.id" :label="c.name" :value="c.id" />
      </el-select>
    </div>

    <DataTable
      :data="rows" :columns="columns" :total="total" :page="page"
      :page-size="pageSize" :loading="loading"
      @update:page="load" @update:pageSize="onSizeChange"
    >
      <template #operation>
        <el-table-column label="操作" width="170" align="center" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" @click="goDetail(row)">详情</el-button>
            <el-button v-if="row.status === 'draft'" link type="warning" @click="confirm(row)">确认</el-button>
          </template>
        </el-table-column>
      </template>
    </DataTable>
  </PageShell>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue'
import { ElMessage, ElButton, ElSelect, ElOption } from 'element-plus'
import { Plus } from '@element-plus/icons-vue'
import PageShell from '../components/PageShell.vue'
import SearchBar from '../components/SearchBar.vue'
import DataTable from '../components/DataTable.vue'
import { api, fmtMoney, fmtDate, statusLabel, statusTagType } from '../api'
import { go } from '../nav'

const rows = ref([])
const customers = ref([])
const total = ref(0)
const page = ref(1)
const pageSize = ref(20)
const loading = ref(false)
const filters = reactive({ keyword: '', status: '', customer_id: '' })

const orderStatus = { draft: '草稿', confirmed: '已确认', shipped: '已出货', fulfilled: '已完成', cancelled: '已取消' }
const pdStatus = { unpaid: '未收款', partial: '部分收款', paid: '已收清' }

const searchFields = [
  { prop: 'keyword', label: '单号', type: 'input', placeholder: '订单编号' }
]

const columns = [
  { prop: 'code', label: '订单编号', width: 130 },
  { prop: 'customer_id', label: '客户', minWidth: 200, formatter: (r) => custName(r.customer_id) },
  { prop: 'status', label: '状态', width: 100, tag: { text: (r) => statusLabel(r.status), type: (r) => statusTagType(r.status) } },
  { prop: 'order_date', label: '下单日期', width: 120, formatter: (r) => fmtDate(r.order_date) },
  { prop: 'total_amount', label: '金额', width: 120, align: 'right', formatter: (r) => fmtMoney(r.total_amount) },
  { prop: 'payment_status', label: '收款', width: 100, tag: { text: (r) => pdStatus[r.payment_status] || r.payment_status, type: (r) => (r.payment_status === 'paid' ? 'success' : 'warning') } }
]

function custName(id) { return customers.value.find((c) => c.id === id)?.name || `#${id}` }

async function loadCustomers() {
  try { customers.value = (await api.get('/customers', { page: 1, page_size: 200 })).items } catch (e) {}
}

async function load(p = 1) {
  page.value = p
  loading.value = true
  try {
    const data = await api.get('/sales-orders', {
      page: page.value, page_size: pageSize.value,
      keyword: filters.keyword || undefined, status: filters.status || undefined,
      customer_id: filters.customer_id || undefined
    })
    rows.value = data.items
    total.value = data.total
  } catch (e) { ElMessage.error(e.message) } finally { loading.value = false }
}

function onSearch(q) { filters.keyword = q.keyword || ''; load(1) }
function onSizeChange(s) { pageSize.value = s; load(1) }
function goCreate() { go('/erp/sales-orders/new') }
function goDetail(row) { go(`/erp/sales-orders/${row.id}`) }

async function confirm(row) {
  try {
    await api.post(`/sales-orders/${row.id}/confirm`)
    ElMessage.success('已确认')
    load(page.value)
  } catch (e) { ElMessage.error(e.message) }
}

onMounted(async () => {
  await loadCustomers()
  load(1)
})
</script>

<style scoped>
.filter-row { margin-bottom: 12px; display: flex; gap: 8px; }
</style>