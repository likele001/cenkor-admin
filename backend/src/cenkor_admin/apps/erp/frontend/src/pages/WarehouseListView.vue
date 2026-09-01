<template>
  <PageShell title="仓库" subtitle="仓库管理 · 库存余额 · 出入库流水">
    <template #actions>
      <el-button type="primary" :icon="Plus" @click="openCreate">新增仓库</el-button>
    </template>

    <el-tabs v-model="activeTab">
      <!-- 仓库列表 -->
      <el-tab-pane label="仓库" name="wh">
        <DataTable
          :data="whRows" :columns="whColumns" :total="whTotal" :page="whPage"
          :page-size="whPageSize" :loading="whLoading"
          @update:page="loadWh" @update:pageSize="onWhSize"
        >
          <template #operation>
            <el-table-column label="操作" width="100" align="center" fixed="right">
              <template #default="{ row }">
                <el-button link type="primary" @click="openEdit(row)">编辑</el-button>
              </template>
            </el-table-column>
          </template>
        </DataTable>
      </el-tab-pane>

      <!-- 库存余额 -->
      <el-tab-pane label="库存余额" name="stock">
        <div class="filter-row">
          <el-input v-model="stockKeyword" placeholder="商品编码/名称" clearable style="width: 220px" @keyup.enter="loadStock(1)" @clear="loadStock(1)">
            <template #append><el-button @click="loadStock(1)">查询</el-button></template>
          </el-input>
        </div>
        <DataTable
          :data="stockRows" :columns="stockColumns" :total="stockTotal" :page="stockPage"
          :page-size="stockPageSize" :loading="stockLoading"
          @update:page="loadStock" @update:pageSize="onStockSize"
        />
      </el-tab-pane>

      <!-- 出入库流水 -->
      <el-tab-pane label="出入库流水" name="movement">
        <div class="filter-row">
          <el-select v-model="moType" placeholder="类型" clearable style="width: 140px" @change="loadMovement(1)">
            <el-option label="入库" value="in" />
            <el-option label="出库" value="out" />
            <el-option label="调整" value="adjust" />
          </el-select>
        </div>
        <DataTable
          :data="moRows" :columns="moColumns" :total="moTotal" :page="moPage"
          :page-size="moPageSize" :loading="moLoading"
          @update:page="loadMovement" @update:pageSize="onMoSize"
        />
      </el-tab-pane>
    </el-tabs>

    <FormDrawer v-model="drawerVisible" :title="drawerTitle" width="520px" :saving="saving" @save="save">
      <el-form ref="formRef" :model="form" :rules="rules" label-width="90px">
        <el-form-item label="仓库编号" prop="code"><el-input v-model="form.code" /></el-form-item>
        <el-form-item label="仓库名称" prop="name"><el-input v-model="form.name" /></el-form-item>
        <el-form-item label="所在位置"><el-input v-model="form.location" /></el-form-item>
        <el-form-item label="负责人"><el-input v-model="form.manager" /></el-form-item>
        <el-form-item label="联系电话"><el-input v-model="form.phone" /></el-form-item>
        <el-form-item label="备注"><el-input v-model="form.remarks" type="textarea" :rows="2" /></el-form-item>
      </el-form>
    </FormDrawer>
  </PageShell>
</template>

<script setup>
import { ref, reactive, computed, onMounted } from 'vue'
import {
  ElMessage, ElButton, ElInput, ElSelect, ElOption, ElForm, ElFormItem, ElTabs, ElTabPane
} from 'element-plus'
import { Plus } from '@element-plus/icons-vue'
import PageShell from '../components/PageShell.vue'
import DataTable from '../components/DataTable.vue'
import FormDrawer from '../components/FormDrawer.vue'
import { api, fmtMoney, fmtDate, statusLabel, statusTagType } from '../api'

const activeTab = ref('wh')

// ---- 仓库 ----
const whRows = ref([])
const whTotal = ref(0)
const whPage = ref(1)
const whPageSize = ref(20)
const whLoading = ref(false)

const whColumns = [
  { prop: 'code', label: '编号', width: 120 },
  { prop: 'name', label: '仓库名称', minWidth: 160 },
  { prop: 'location', label: '位置', minWidth: 160 },
  { prop: 'manager', label: '负责人', width: 110 },
  { prop: 'phone', label: '电话', width: 140 },
  { prop: 'status', label: '状态', width: 90, tag: { text: (r) => statusLabel(r.status), type: (r) => statusTagType(r.status) } }
]

async function loadWh(p = 1) {
  whPage.value = p
  whLoading.value = true
  try {
    const data = await api.get('/warehouses', { page: whPage.value, page_size: whPageSize.value })
    whRows.value = data.items
    whTotal.value = data.total
  } catch (e) { ElMessage.error(e.message) } finally { whLoading.value = false }
}
function onWhSize(s) { whPageSize.value = s; loadWh(1) }

// ---- 库存余额 ----
const stockRows = ref([])
const stockTotal = ref(0)
const stockPage = ref(1)
const stockPageSize = ref(20)
const stockLoading = ref(false)
const stockKeyword = ref('')

const stockColumns = [
  { prop: 'warehouse_name', label: '仓库', width: 140 },
  { prop: 'product_code', label: '商品编码', width: 120 },
  { prop: 'product_name', label: '商品名称', minWidth: 180 },
  { prop: 'unit', label: '单位', width: 70 },
  { prop: 'quantity', label: '库存', width: 100, align: 'right', formatter: (r) => fmtMoney(r.quantity, 2) },
  { prop: 'available_qty', label: '可用', width: 100, align: 'right', formatter: (r) => fmtMoney(r.available_qty, 2) },
  { prop: 'last_movement_at', label: '最近变动', width: 140, formatter: (r) => fmtDate(r.last_movement_at) }
]

async function loadStock(p = 1) {
  stockPage.value = p
  stockLoading.value = true
  try {
    const data = await api.get('/stock/balance', {
      page: stockPage.value, page_size: stockPageSize.value, keyword: stockKeyword.value || undefined
    })
    stockRows.value = data.items
    stockTotal.value = data.total
  } catch (e) { ElMessage.error(e.message) } finally { stockLoading.value = false }
}
function onStockSize(s) { stockPageSize.value = s; loadStock(1) }

// ---- 出入库流水 ----
const moRows = ref([])
const moTotal = ref(0)
const moPage = ref(1)
const moPageSize = ref(20)
const moLoading = ref(false)
const moType = ref('')
const moTypeLabel = { in: '入库', out: '出库', adjust: '调整' }

const moColumns = [
  { prop: 'warehouse_id', label: '仓库ID', width: 90 },
  { prop: 'product_code', label: '商品编码', width: 120 },
  { prop: 'product_name', label: '商品名称', minWidth: 180 },
  { prop: 'movement_type', label: '类型', width: 90, tag: { text: (r) => moTypeLabel[r.movement_type] || r.movement_type, type: (r) => (r.movement_type === 'out' ? 'danger' : 'success') } },
  { prop: 'quantity', label: '数量', width: 100, align: 'right', formatter: (r) => (r.quantity > 0 ? '+' : '') + r.quantity },
  { prop: 'balance_after', label: '结存', width: 100, align: 'right', formatter: (r) => fmtMoney(r.balance_after) },
  { prop: 'ref_type', label: '来源', width: 110 },
  { prop: 'created_at', label: '时间', width: 140, formatter: (r) => fmtDate(r.created_at) }
]

async function loadMovement(p = 1) {
  moPage.value = p
  moLoading.value = true
  try {
    const data = await api.get('/stock/movements', {
      page: moPage.value, page_size: moPageSize.value, movement_type: moType.value || undefined
    })
    moRows.value = data.items
    moTotal.value = data.total
  } catch (e) { ElMessage.error(e.message) } finally { moLoading.value = false }
}
function onMoSize(s) { moPageSize.value = s; loadMovement(1) }

// ---- 仓库编辑 ----
const drawerVisible = ref(false)
const drawerTitle = computed(() => (editingId.value ? '编辑仓库' : '新增仓库'))
const editingId = ref(null)
const saving = ref(false)
const formRef = ref()
const form = reactive({})
const rules = {
  code: [{ required: true, message: '请输入仓库编号', trigger: 'blur' }],
  name: [{ required: true, message: '请输入仓库名称', trigger: 'blur' }]
}

function emptyForm() { return { code: '', name: '', location: '', manager: '', phone: '', remarks: '' } }
function openCreate() { editingId.value = null; Object.assign(form, emptyForm()); drawerVisible.value = true }
function openEdit(row) {
  editingId.value = row.id
  Object.assign(form, {
    code: row.code, name: row.name, location: row.location || '', manager: row.manager || '',
    phone: row.phone || '', remarks: row.remarks || ''
  })
  drawerVisible.value = true
}

async function save() {
  await formRef.value.validate()
  saving.value = true
  try {
    if (editingId.value) await api.put(`/warehouses/${editingId.value}`, { ...form })
    else await api.post('/warehouses', { ...form })
    ElMessage.success('保存成功')
    drawerVisible.value = false
    loadWh(whPage.value)
  } catch (e) { ElMessage.error(e.message) } finally { saving.value = false }
}

onMounted(() => loadWh(1))
</script>

<style scoped>
.filter-row { margin-bottom: 12px; display: flex; gap: 8px; }
</style>