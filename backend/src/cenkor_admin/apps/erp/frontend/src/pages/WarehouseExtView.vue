<template>
  <PageShell title="仓储深度" subtitle="库位 · 批次 · 序列号 · 盘点 · 安全库存预警">
    <template #actions>
      <el-button type="primary" :icon="Plus" @click="openLocation">新增库位</el-button>
    </template>

    <el-tabs v-model="activeTab">
      <!-- 库位 -->
      <el-tab-pane label="库位" name="location">
        <div class="filter-row">
          <el-select v-model="locWarehouseId" placeholder="仓库" clearable style="width: 180px" @change="loadLocations(1)">
            <el-option v-for="w in warehouses" :key="w.id" :label="`${w.code} ${w.name}`" :value="w.id" />
          </el-select>
        </div>
        <DataTable
          :data="locRows" :columns="locColumns" :total="locTotal" :page="locPage"
          :page-size="locPageSize" :loading="locLoading"
          @update:page="loadLocations" @update:pageSize="onLocSize"
        />
      </el-tab-pane>

      <!-- 批次 -->
      <el-tab-pane label="批次" name="batch">
        <div class="filter-row">
          <el-select v-model="batchProdId" placeholder="商品" filterable clearable style="width: 200px" @change="loadBatches(1)">
            <el-option v-for="p in products" :key="p.id" :label="`${p.code} ${p.name}`" :value="p.id" />
          </el-select>
          <el-select v-model="batchStatus" placeholder="状态" clearable style="width: 120px" @change="loadBatches(1)">
            <el-option label="启用" value="active" />
            <el-option label="停用" value="inactive" />
          </el-select>
          <el-button type="primary" plain :icon="Plus" @click="openBatch">新增批次</el-button>
        </div>
        <DataTable
          :data="batchRows" :columns="batchColumns" :total="batchTotal" :page="batchPage"
          :page-size="batchPageSize" :loading="batchLoading"
          @update:page="loadBatches" @update:pageSize="onBatchSize"
        />
      </el-tab-pane>

      <!-- 序列号 -->
      <el-tab-pane label="序列号" name="serial">
        <div class="filter-row">
          <el-select v-model="serialProdId" placeholder="商品" filterable clearable style="width: 200px" @change="loadSerials(1)">
            <el-option v-for="p in products" :key="p.id" :label="`${p.code} ${p.name}`" :value="p.id" />
          </el-select>
          <el-select v-model="serialStatus" placeholder="状态" clearable style="width: 120px" @change="loadSerials(1)">
            <el-option label="在库" value="in_stock" />
            <el-option label="已出库" value="sold" />
          </el-select>
          <el-button type="primary" plain :icon="Plus" @click="openSerial">新增序列号</el-button>
        </div>
        <DataTable
          :data="serialRows" :columns="serialColumns" :total="serialTotal" :page="serialPage"
          :page-size="serialPageSize" :loading="serialLoading"
          @update:page="loadSerials" @update:pageSize="onSerialSize"
        />
      </el-tab-pane>

      <!-- 盘点 -->
      <el-tab-pane label="盘点" name="stocktake">
        <div class="filter-row">
          <el-select v-model="stStatus" placeholder="状态" clearable style="width: 130px" @change="loadStocktakes(1)">
            <el-option label="草稿" value="draft" />
            <el-option label="待盘点" value="pending" />
            <el-option label="已完成" value="done" />
          </el-select>
          <el-button type="primary" plain :icon="Plus" @click="openStocktake">新增盘点</el-button>
        </div>
        <DataTable
          :data="stRows" :columns="stColumns" :total="stTotal" :page="stPage"
          :page-size="stPageSize" :loading="stLoading"
          @update:page="loadStocktakes" @update:pageSize="onStSize"
        >
          <template #operation>
            <el-table-column label="操作" width="110" align="center" fixed="right">
              <template #default="{ row }">
                <el-button
                  v-if="row.status !== 'done'" link type="warning"
                  @click="confirmStocktake(row)"
                >确认盘点</el-button>
              </template>
            </el-table-column>
          </template>
        </DataTable>
      </el-tab-pane>

      <!-- 安全库存预警 -->
      <el-tab-pane label="安全库存预警" name="alert">
        <DataTable :data="alertRows" :columns="alertColumns" :total="alertRows.length" :page="1" :page-size="alertRows.length" :loading="alertLoading" :show-pagination="false" />
      </el-tab-pane>
    </el-tabs>

    <!-- 库位新增 -->
    <FormDrawer v-model="locDrawer" title="新增库位" width="480px" :saving="locSaving" @save="saveLocation">
      <el-form ref="locFormRef" :model="locForm" :rules="locRules" label-width="90px">
        <el-form-item label="仓库" prop="warehouse_id">
          <el-select v-model="locForm.warehouse_id" filterable placeholder="选择仓库" style="width: 100%">
            <el-option v-for="w in warehouses" :key="w.id" :label="`${w.code} ${w.name}`" :value="w.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="库位编码" prop="code"><el-input v-model="locForm.code" /></el-form-item>
        <el-form-item label="库位名称"><el-input v-model="locForm.name" /></el-form-item>
        <el-form-item label="库区"><el-input v-model="locForm.area" /></el-form-item>
        <el-form-item label="备注"><el-input v-model="locForm.remarks" type="textarea" :rows="2" /></el-form-item>
      </el-form>
    </FormDrawer>

    <!-- 批次新增 -->
    <FormDrawer v-model="batchDrawer" title="新增批次" width="500px" :saving="batchSaving" @save="saveBatch">
      <el-form ref="batchFormRef" :model="batchForm" :rules="batchRules" label-width="90px">
        <el-form-item label="批次号" prop="batch_no"><el-input v-model="batchForm.batch_no" /></el-form-item>
        <el-form-item label="商品" prop="product_id">
          <el-select v-model="batchForm.product_id" filterable placeholder="选择商品" style="width: 100%">
            <el-option v-for="p in products" :key="p.id" :label="`${p.code} ${p.name}`" :value="p.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="数量"><el-input-number v-model="batchForm.quantity" :min="0" :precision="2" style="width: 100%" /></el-form-item>
        <el-form-item label="生产日期"><el-date-picker v-model="batchForm.production_date" type="date" value-format="YYYY-MM-DD" style="width: 100%" /></el-form-item>
        <el-form-item label="有效期至"><el-date-picker v-model="batchForm.expiry_date" type="date" value-format="YYYY-MM-DD" style="width: 100%" /></el-form-item>
      </el-form>
    </FormDrawer>

    <!-- 序列号新增 -->
    <FormDrawer v-model="serialDrawer" title="新增序列号" width="500px" :saving="serialSaving" @save="saveSerial">
      <el-form ref="serialFormRef" :model="serialForm" :rules="serialRules" label-width="90px">
        <el-form-item label="序列号" prop="serial_no"><el-input v-model="serialForm.serial_no" /></el-form-item>
        <el-form-item label="商品" prop="product_id">
          <el-select v-model="serialForm.product_id" filterable placeholder="选择商品" style="width: 100%">
            <el-option v-for="p in products" :key="p.id" :label="`${p.code} ${p.name}`" :value="p.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="批次">
          <el-select v-model="serialForm.batch_id" filterable clearable placeholder="选择批次" style="width: 100%">
            <el-option v-for="b in batchRows" :key="b.id" :label="b.batch_no" :value="b.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="仓库">
          <el-select v-model="serialForm.warehouse_id" filterable clearable placeholder="选择仓库" style="width: 100%">
            <el-option v-for="w in warehouses" :key="w.id" :label="`${w.code} ${w.name}`" :value="w.id" />
          </el-select>
        </el-form-item>
      </el-form>
    </FormDrawer>

    <!-- 盘点新增 -->
    <el-drawer v-model="stDrawer" title="新增盘点" size="680px" destroy-on-close>
      <div class="st-form">
        <el-form label-width="90px" :model="stForm">
          <el-form-item label="仓库" required>
            <el-select v-model="stForm.warehouse_id" filterable placeholder="选择仓库" style="width: 60%">
              <el-option v-for="w in warehouses" :key="w.id" :label="`${w.code} ${w.name}`" :value="w.id" />
            </el-select>
          </el-form-item>
          <el-form-item label="盘点日期">
            <el-date-picker v-model="stForm.take_date" type="date" value-format="YYYY-MM-DD" style="width: 60%" />
          </el-form-item>
          <el-form-item label="备注">
            <el-input v-model="stForm.remark" type="textarea" :rows="2" />
          </el-form-item>
          <el-form-item label="明细">
            <el-button type="primary" plain size="small" :icon="Plus" @click="addStItem">添加盘点项</el-button>
          </el-form-item>
        </el-form>
        <el-table :data="stForm.items" border size="small" empty-text="请添加盘点商品">
          <el-table-column label="商品" min-width="240">
            <template #default="{ row }">
              <el-select v-model="row.product_id" filterable placeholder="选择商品" style="width: 100%" @change="(id) => fillStItem(row, id)">
                <el-option v-for="p in products" :key="p.id" :label="`${p.code} ${p.name}`" :value="p.id" />
              </el-select>
            </template>
          </el-table-column>
          <el-table-column label="实盘数量" width="140" align="right">
            <template #default="{ row }">
              <el-input-number v-model="row.actual_qty" :min="0" :precision="2" controls-position="right" style="width: 100%" />
            </template>
          </el-table-column>
          <el-table-column label="" width="56" align="center">
            <template #default="{ $index }">
              <el-button link type="danger" :icon="Delete" @click="stForm.items.splice($index, 1)" />
            </template>
          </el-table-column>
        </el-table>
      </div>
      <template #footer>
        <div class="drawer-footer">
          <el-button @click="stDrawer = false">取消</el-button>
          <el-button type="primary" :loading="stSaving" @click="saveStocktake">保存盘点单</el-button>
        </div>
      </template>
    </el-drawer>
  </PageShell>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue'
import {
  ElMessage, ElMessageBox, ElButton, ElInput, ElSelect, ElOption, ElInputNumber,
  ElForm, ElFormItem, ElTabs, ElTabPane, ElDrawer, ElDatePicker, ElTable, ElTableColumn
} from 'element-plus'
import { Plus, Delete } from '@element-plus/icons-vue'
import PageShell from '../components/PageShell.vue'
import DataTable from '../components/DataTable.vue'
import FormDrawer from '../components/FormDrawer.vue'
import { api, fmtMoney, fmtDate } from '../api'

const activeTab = ref('location')

// 公共下拉数据
const warehouses = ref([])
const products = ref([])
async function loadWarehouses() {
  try { const d = await api.get('/warehouses', { page: 1, page_size: 200 }); warehouses.value = d.items || [] } catch (e) {}
}
async function loadProducts() {
  try { const d = await api.get('/products', { page: 1, page_size: 500 }); products.value = d.items || [] } catch (e) {}
}

// ---------- 库位 ----------
const locRows = ref([])
const locTotal = ref(0)
const locPage = ref(1)
const locPageSize = ref(100)
const locLoading = ref(false)
const locWarehouseId = ref('')
const locColumns = [
  { prop: 'code', label: '库位编码', width: 130 },
  { prop: 'name', label: '库位名称', minWidth: 150 },
  { prop: 'warehouse_id', label: '仓库ID', width: 90 },
  { prop: 'area', label: '库区', width: 120, formatter: (r) => r.area || '—' },
  { prop: 'status', label: '状态', width: 90, formatter: (r) => (r.status === 'active' ? '启用' : '停用') }
]
async function loadLocations(p = 1) {
  locPage.value = p
  locLoading.value = true
  try {
    const data = await api.get('/warehouse/locations', {
      page: locPage.value, page_size: locPageSize.value, warehouse_id: locWarehouseId.value || undefined
    })
    locRows.value = data.items
    locTotal.value = data.total
  } catch (e) { ElMessage.error(e.message) } finally { locLoading.value = false }
}
function onLocSize(s) { locPageSize.value = s; loadLocations(1) }

const locDrawer = ref(false)
const locSaving = ref(false)
const locFormRef = ref()
const locForm = reactive({})
const locRules = {
  warehouse_id: [{ required: true, message: '请选择仓库', trigger: 'change' }],
  code: [{ required: true, message: '请输入库位编码', trigger: 'blur' }]
}
function openLocation() {
  Object.assign(locForm, { warehouse_id: null, code: '', name: '', area: '', status: 'active', remarks: '' })
  locDrawer.value = true
}
async function saveLocation() {
  await locFormRef.value.validate()
  locSaving.value = true
  try {
    await api.post('/warehouse/locations', { ...locForm })
    ElMessage.success('保存成功')
    locDrawer.value = false
    loadLocations(1)
  } catch (e) { ElMessage.error(e.message) } finally { locSaving.value = false }
}

// ---------- 批次 ----------
const batchRows = ref([])
const batchTotal = ref(0)
const batchPage = ref(1)
const batchPageSize = ref(100)
const batchLoading = ref(false)
const batchProdId = ref('')
const batchStatus = ref('')
const batchColumns = [
  { prop: 'batch_no', label: '批次号', width: 150 },
  { prop: 'product_code', label: '商品编码', width: 120 },
  { prop: 'product_name', label: '商品名称', minWidth: 160 },
  { prop: 'quantity', label: '数量', width: 100, align: 'right', formatter: (r) => fmtMoney(r.quantity, 2) },
  { prop: 'production_date', label: '生产日期', width: 110, formatter: (r) => fmtDate(r.production_date) },
  { prop: 'expiry_date', label: '有效期至', width: 110, formatter: (r) => fmtDate(r.expiry_date) },
  { prop: 'status', label: '状态', width: 90, formatter: (r) => (r.status === 'active' ? '启用' : '停用') }
]
async function loadBatches(p = 1) {
  batchPage.value = p
  batchLoading.value = true
  try {
    const data = await api.get('/warehouse/batches', {
      page: batchPage.value, page_size: batchPageSize.value,
      product_id: batchProdId.value || undefined, status: batchStatus.value || undefined
    })
    batchRows.value = data.items
    batchTotal.value = data.total
  } catch (e) { ElMessage.error(e.message) } finally { batchLoading.value = false }
}
function onBatchSize(s) { batchPageSize.value = s; loadBatches(1) }

const batchDrawer = ref(false)
const batchSaving = ref(false)
const batchFormRef = ref()
const batchForm = reactive({})
const batchRules = {
  batch_no: [{ required: true, message: '请输入批次号', trigger: 'blur' }],
  product_id: [{ required: true, message: '请选择商品', trigger: 'change' }]
}
function openBatch() {
  Object.assign(batchForm, { batch_no: '', product_id: null, quantity: 0, production_date: null, expiry_date: null, supplier_id: null, status: 'active' })
  batchDrawer.value = true
}
async function saveBatch() {
  await batchFormRef.value.validate()
  batchSaving.value = true
  try {
    await api.post('/warehouse/batches', { ...batchForm, production_date: batchForm.production_date || undefined, expiry_date: batchForm.expiry_date || undefined })
    ElMessage.success('保存成功')
    batchDrawer.value = false
    loadBatches(1)
  } catch (e) { ElMessage.error(e.message) } finally { batchSaving.value = false }
}

// ---------- 序列号 ----------
const serialRows = ref([])
const serialTotal = ref(0)
const serialPage = ref(1)
const serialPageSize = ref(100)
const serialLoading = ref(false)
const serialProdId = ref('')
const serialStatus = ref('')
const serialColumns = [
  { prop: 'serial_no', label: '序列号', width: 170 },
  { prop: 'product_code', label: '商品编码', width: 120 },
  { prop: 'product_name', label: '商品名称', minWidth: 160 },
  { prop: 'batch_id', label: '批次ID', width: 90, formatter: (r) => r.batch_id || '—' },
  { prop: 'status', label: '状态', width: 90, formatter: (r) => (r.status === 'in_stock' ? '在库' : r.status) }
]
async function loadSerials(p = 1) {
  serialPage.value = p
  serialLoading.value = true
  try {
    const data = await api.get('/warehouse/serials', {
      page: serialPage.value, page_size: serialPageSize.value,
      product_id: serialProdId.value || undefined, status: serialStatus.value || undefined
    })
    serialRows.value = data.items
    serialTotal.value = data.total
  } catch (e) { ElMessage.error(e.message) } finally { serialLoading.value = false }
}
function onSerialSize(s) { serialPageSize.value = s; loadSerials(1) }

const serialDrawer = ref(false)
const serialSaving = ref(false)
const serialFormRef = ref()
const serialForm = reactive({})
const serialRules = {
  serial_no: [{ required: true, message: '请输入序列号', trigger: 'blur' }],
  product_id: [{ required: true, message: '请选择商品', trigger: 'change' }]
}
function openSerial() {
  Object.assign(serialForm, { serial_no: '', product_id: null, batch_id: null, warehouse_id: null, location_id: null, status: 'in_stock' })
  serialDrawer.value = true
}
async function saveSerial() {
  await serialFormRef.value.validate()
  serialSaving.value = true
  try {
    await api.post('/warehouse/serials', { ...serialForm, batch_id: serialForm.batch_id || undefined, warehouse_id: serialForm.warehouse_id || undefined })
    ElMessage.success('保存成功')
    serialDrawer.value = false
    loadSerials(1)
  } catch (e) { ElMessage.error(e.message) } finally { serialSaving.value = false }
}

// ---------- 盘点 ----------
const stRows = ref([])
const stTotal = ref(0)
const stPage = ref(1)
const stPageSize = ref(20)
const stLoading = ref(false)
const stStatus = ref('')
const stColumns = [
  { prop: 'code', label: '盘点单号', width: 130 },
  { prop: 'warehouse_id', label: '仓库ID', width: 90 },
  { prop: 'take_date', label: '盘点日期', width: 110, formatter: (r) => fmtDate(r.take_date) },
  { prop: 'status', label: '状态', width: 90, formatter: (r) => ({ draft: '草稿', pending: '待盘点', done: '已完成' }[r.status] || r.status) },
  { prop: 'remark', label: '备注', minWidth: 160, formatter: (r) => r.remark || '—' }
]
const stStatusMap = { draft: '草稿', pending: '待盘点', done: '已完成' }
async function loadStocktakes(p = 1) {
  stPage.value = p
  stLoading.value = true
  try {
    const data = await api.get('/warehouse/stocktakes', { page: stPage.value, page_size: stPageSize.value, status: stStatus.value || undefined })
    stRows.value = data.items
    stTotal.value = data.total
  } catch (e) { ElMessage.error(e.message) } finally { stLoading.value = false }
}
function onStSize(s) { stPageSize.value = s; loadStocktakes(1) }

const stDrawer = ref(false)
const stSaving = ref(false)
const stForm = reactive({ items: [] })
function addStItem() {
  stForm.items.push({ product_id: null, actual_qty: 0, remark: '' })
}
function fillStItem(row, id) {
  const p = products.value.find((x) => x.id === id)
  if (p) { row.product_code = p.code; row.product_name = p.name }
}
function openStocktake() {
  Object.assign(stForm, { warehouse_id: null, location_id: null, take_date: new Date().toISOString().slice(0, 10), remark: '', items: [] })
  addStItem()
  stDrawer.value = true
}
async function saveStocktake() {
  if (!stForm.warehouse_id) return ElMessage.warning('请选择仓库')
  const rest = stForm.items.filter((it) => it.product_id)
  if (!rest.length) return ElMessage.warning('请至少添加一个盘点商品')
  stSaving.value = true
  try {
    await api.post('/warehouse/stocktakes', {
      warehouse_id: stForm.warehouse_id, location_id: stForm.location_id || undefined,
      take_date: stForm.take_date || undefined, remark: stForm.remark || undefined,
      items: rest.map((it) => ({ product_id: it.product_id, actual_qty: it.actual_qty, remark: it.remark || undefined }))
    })
    ElMessage.success('盘点单已创建')
    stDrawer.value = false
    loadStocktakes(1)
  } catch (e) { ElMessage.error(e.message) } finally { stSaving.value = false }
}

async function confirmStocktake(row) {
  try {
    await ElMessageBox.confirm(`确认盘点单 ${row.code} 并按差异调整库存？`, '确认盘点', { type: 'warning' })
    await api.post(`/warehouse/stocktakes/${row.id}/confirm`)
    ElMessage.success('盘盈盘亏已调整')
    loadStocktakes(stPage.value)
  } catch (e) { if (e !== 'cancel' && e?.message) ElMessage.error(e.message) }
}

// ---------- 安全库存预警 ----------
const alertRows = ref([])
const alertLoading = ref(false)
const alertColumns = [
  { prop: 'code', label: '商品编码', width: 130 },
  { prop: 'name', label: '商品名称', minWidth: 180 },
  { prop: 'quantity', label: '现有量', width: 100, align: 'right', formatter: (r) => fmtMoney(r.quantity, 2) },
  { prop: 'min_stock', label: '安全库存', width: 110, align: 'right', formatter: (r) => fmtMoney(r.min_stock, 2) },
  { prop: 'shortage', label: '缺口', width: 100, align: 'right', formatter: (r) => fmtMoney(r.shortage, 2) }
]
async function loadAlerts() {
  alertLoading.value = true
  try {
    const d = await api.get('/warehouse/alerts')
    alertRows.value = d.items || []
  } catch (e) { ElMessage.error(e.message) } finally { alertLoading.value = false }
}

function moneyFmt(row, col) { return fmtMoney(row[col.property]) }

onMounted(() => { loadWarehouses(); loadProducts(); loadLocations(1); loadBatches(1); loadSerials(1); loadStocktakes(1); loadAlerts() })
</script>

<style scoped>
.filter-row { margin-bottom: 12px; display: flex; gap: 8px; flex-wrap: wrap; }
.st-form { display: flex; flex-direction: column; gap: 12px; }
.drawer-footer { display: flex; justify-content: flex-end; gap: 8px; }
</style>