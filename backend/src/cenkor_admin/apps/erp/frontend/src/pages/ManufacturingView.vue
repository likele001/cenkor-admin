<template>
  <PageShell title="制造" subtitle="BOM · 生产工单 · 领料报工 · 质检 · 可用量">
    <template #actions>
      <el-button type="primary" :icon="Plus" @click="openBom">新增BOM</el-button>
    </template>

    <el-tabs v-model="activeTab">
      <!-- BOM -->
      <el-tab-pane label="BOM" name="bom">
        <div class="filter-row">
          <el-select v-model="bomProdId" placeholder="商品" filterable clearable style="width: 200px" @change="loadBoms(1)">
            <el-option v-for="p in products" :key="p.id" :label="`${p.code} ${p.name}`" :value="p.id" />
          </el-select>
        </div>
        <DataTable
          :data="bomRows" :columns="bomColumns" :total="bomTotal" :page="bomPage"
          :page-size="bomPageSize" :loading="bomLoading"
          @update:page="loadBoms" @update:pageSize="onBomSize"
        >
          <template #operation>
            <el-table-column label="操作" width="90" align="center" fixed="right">
              <template #default="{ row }">
                <el-button link type="primary" @click="viewBom(row)">查看</el-button>
              </template>
            </el-table-column>
          </template>
        </DataTable>
      </el-tab-pane>

      <!-- 生产工单 -->
      <el-tab-pane label="生产工单" name="wo">
        <div class="filter-row">
          <el-button type="primary" plain :icon="Plus" @click="openWO">新增工单</el-button>
          <el-select v-model="woStatus" placeholder="状态" clearable style="width: 130px" @change="loadWOs(1)">
            <el-option label="草稿" value="draft" />
            <el-option label="已下达" value="released" />
            <el-option label="生产中" value="in_progress" />
            <el-option label="已完成" value="completed" />
            <el-option label="已取消" value="cancelled" />
          </el-select>
        </div>
        <DataTable
          :data="woRows" :columns="woColumns" :total="woTotal" :page="woPage"
          :page-size="woPageSize" :loading="woLoading"
          @update:page="loadWOs" @update:pageSize="onWoSize"
        >
          <template #operation>
            <el-table-column label="操作" min-width="180" align="center" fixed="right">
              <template #default="{ row }">
                <el-button v-if="['draft','cancelled'].includes(row.status)" link type="primary" @click="releaseWO(row)">下达</el-button>
                <el-button v-if="['released','in_progress'].includes(row.status)" link type="warning" @click="issueWO(row)">领料</el-button>
                <el-button v-if="['released','in_progress'].includes(row.status)" link type="success" @click="completeWO(row)">完工</el-button>
                <el-button v-if="['released','in_progress'].includes(row.status)" link type="danger" @click="reportOp(row)">报工</el-button>
              </template>
            </el-table-column>
          </template>
        </DataTable>
      </el-tab-pane>

      <!-- 报工 -->
      <el-tab-pane label="工序报工" name="op">
        <div class="filter-row">
          <el-select v-model="opWoId" placeholder="工单" filterable clearable style="width: 200px" @change="loadOps(1)">
            <el-option v-for="w in woRows" :key="w.id" :label="`${w.code} ${w.product_name}`" :value="w.id" />
          </el-select>
        </div>
        <DataTable
          :data="opRows" :columns="opColumns" :total="opTotal" :page="opPage"
          :page-size="opPageSize" :loading="opLoading"
          @update:page="loadOps" @update:pageSize="onOpSize"
        />
      </el-tab-pane>

      <!-- 质检 -->
      <el-tab-pane label="质检" name="qc">
        <div class="filter-row">
          <el-button type="primary" plain :icon="Plus" @click="openQC">新增质检</el-button>
          <el-select v-model="qcType" placeholder="类型" clearable style="width: 120px" @change="loadQCs(1)">
            <el-option label="来料IQC" value="IQC" />
            <el-option label="制程IPQC" value="IPQC" />
            <el-option label="成品FQC" value="FQC" />
          </el-select>
          <el-select v-model="qcResult" placeholder="结果" clearable style="width: 120px" @change="loadQCs(1)">
            <el-option label="合格" value="pass" />
            <el-option label="不合格" value="fail" />
          </el-select>
        </div>
        <DataTable
          :data="qcRows" :columns="qcColumns" :total="qcTotal" :page="qcPage"
          :page-size="qcPageSize" :loading="qcLoading"
          @update:page="loadQCs" @update:pageSize="onQcSize"
        />
      </el-tab-pane>

      <!-- 可用量 -->
      <el-tab-pane label="MRP可用量" name="mrp">
        <div class="filter-row">
          <el-select v-model="mrpProdId" placeholder="商品" filterable clearable style="width: 200px" @change="loadMrp">
            <el-option v-for="p in products" :key="p.id" :label="`${p.code} ${p.name}`" :value="p.id" />
          </el-select>
          <el-button type="primary" plain @click="loadMrp">查询</el-button>
        </div>
        <DataTable :data="mrpRows" :columns="mrpColumns" :total="mrpRows.length" :page="1" :page-size="mrpRows.length" :loading="mrpLoading" :show-pagination="false" />
      </el-tab-pane>
    </el-tabs>

    <!-- BOM 新增 -->
    <el-drawer v-model="bomDrawer" title="新增BOM" size="760px" destroy-on-close>
      <div class="form-wrap">
        <el-form label-width="100px" :model="bomForm">
          <el-row :gutter="12">
            <el-col :span="12">
              <el-form-item label="成品" required>
                <el-select v-model="bomForm.product_id" filterable placeholder="选择成品" style="width: 100%">
                  <el-option v-for="p in products" :key="p.id" :label="`${p.code} ${p.name}`" :value="p.id" />
                </el-select>
              </el-form-item>
            </el-col>
            <el-col :span="6">
              <el-form-item label="版本" label-width="60px">
                <el-input v-model="bomForm.version" placeholder="V1" />
              </el-form-item>
            </el-col>
            <el-col :span="6">
              <el-form-item label="产量" label-width="60px">
                <el-input-number v-model="bomForm.output_qty" :min="0.01" :precision="2" style="width: 100%" />
              </el-form-item>
            </el-col>
          </el-row>
          <el-form-item label="名称"><el-input v-model="bomForm.name" placeholder="默认取成品名" /></el-form-item>
          <el-form-item label="备注"><el-input v-model="bomForm.remark" type="textarea" :rows="2" /></el-form-item>
          <el-form-item label="明细">
            <el-button type="primary" plain size="small" :icon="Plus" @click="addBomItem">添加物料</el-button>
          </el-form-item>
        </el-form>
        <el-table :data="bomForm.items" border size="small" empty-text="请添加物料（组件）">
          <el-table-column label="组件物料" min-width="220">
            <template #default="{ row }">
              <el-select v-model="row.component_id" filterable placeholder="选择组件" style="width: 100%" @change="(id) => fillBomItem(row, id)">
                <el-option v-for="p in products" :key="p.id" :label="`${p.code} ${p.name}`" :value="p.id" />
              </el-select>
            </template>
          </el-table-column>
          <el-table-column label="用量" width="120" align="center">
            <template #default="{ row }">
              <el-input-number v-model="row.quantity" :min="0" :precision="4" controls-position="right" style="width: 100%" />
            </template>
          </el-table-column>
          <el-table-column label="损耗率%" width="120" align="center">
            <template #default="{ row }">
              <el-input-number v-model="row.loss_rate" :min="0" :precision="2" controls-position="right" style="width: 100%" />
            </template>
          </el-table-column>
          <el-table-column label="" width="56" align="center">
            <template #default="{ $index }">
              <el-button link type="danger" :icon="Delete" @click="bomForm.items.splice($index, 1)" />
            </template>
          </el-table-column>
        </el-table>
      </div>
      <template #footer>
        <div class="drawer-footer">
          <el-button @click="bomDrawer = false">取消</el-button>
          <el-button type="primary" :loading="bomSaving" @click="saveBom">保存BOM</el-button>
        </div>
      </template>
    </el-drawer>

    <!-- BOM 查看 -->
    <el-drawer v-model="bomViewDrawer" title="BOM明细" size="720px" destroy-on-close>
      <div class="bom-view-head">
        <span class="head-code">{{ bomView.product_code }}</span>
        <b>{{ bomView.product_name }}</b>
        <el-tag size="small">版本 {{ bomView.version }}</el-tag>
        <el-tag size="small" :type="bomView.is_active ? 'success' : 'info'">{{ bomView.is_active ? '启用' : '停用' }}</el-tag>
      </div>
      <el-table :data="bomViewItems" border size="small">
        <el-table-column prop="component_code" label="组件编码" width="120" />
        <el-table-column prop="component_name" label="组件名称" min-width="180" />
        <el-table-column prop="spec" label="规格" width="120" :formatter="(r) => r.spec || '—'" />
        <el-table-column prop="quantity" label="用量" width="100" align="right" />
        <el-table-column prop="loss_rate" label="损耗率%" width="100" align="right" :formatter="(r) => r.loss_rate || 0" />
        <el-table-column prop="unit" label="单位" width="90" :formatter="(r) => r.unit || '—'" />
      </el-table>
    </el-drawer>

    <!-- 工单新增 -->
    <FormDrawer v-model="woDrawer" title="新增生产工单" width="500px" :saving="woSaving" @save="saveWO">
      <el-form ref="woFormRef" :model="woForm" :rules="woRules" label-width="90px">
        <el-form-item label="产品" prop="product_id">
          <el-select v-model="woForm.product_id" filterable placeholder="选择产品" style="width: 100%">
            <el-option v-for="p in products" :key="p.id" :label="`${p.code} ${p.name}`" :value="p.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="生产数量" prop="quantity">
          <el-input-number v-model="woForm.quantity" :min="0.01" :precision="2" style="width: 100%" />
        </el-form-item>
        <el-form-item label="BOM版本">
          <el-input v-model="woForm.bom_version" placeholder="留空用启用版BOM" />
        </el-form-item>
        <el-form-item label="仓库">
          <el-select v-model="woForm.warehouse_id" filterable clearable placeholder="选择仓库" style="width: 100%">
            <el-option v-for="w in warehouses" :key="w.id" :label="`${w.code} ${w.name}`" :value="w.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="计划开始">
          <el-date-picker v-model="woForm.start_date" type="date" value-format="YYYY-MM-DD" style="width: 100%" />
        </el-form-item>
        <el-form-item label="计划完成">
          <el-date-picker v-model="woForm.due_date" type="date" value-format="YYYY-MM-DD" style="width: 100%" />
        </el-form-item>
        <el-form-item label="备注">
          <el-input v-model="woForm.remark" type="textarea" :rows="2" />
        </el-form-item>
      </el-form>
    </FormDrawer>

    <!-- 报工 -->
    <el-dialog v-model="opDialog" title="工序报工" width="460px">
      <el-form :model="opForm" label-width="90px">
        <el-form-item label="工序">
          <el-input v-model="opForm.process_name" placeholder="如 车削/装配/检验" />
        </el-form-item>
        <el-form-item label="报工数量">
          <el-input-number v-model="opForm.quantity" :min="0" :precision="2" style="width: 100%" />
        </el-form-item>
        <el-form-item label="合格数量">
          <el-input-number v-model="opForm.qualified_qty" :min="0" :precision="2" style="width: 100%" />
        </el-form-item>
        <el-form-item label="报废数量">
          <el-input-number v-model="opForm.reject_qty" :min="0" :precision="2" style="width: 100%" />
        </el-form-item>
        <el-form-item label="工时">
          <el-input-number v-model="opForm.work_hours" :min="0" :precision="2" style="width: 100%" />
        </el-form-item>
        <el-form-item label="操作员">
          <el-input v-model="opForm.operator" />
        </el-form-item>
        <el-form-item label="报工日期">
          <el-date-picker v-model="opForm.report_date" type="date" value-format="YYYY-MM-DD" style="width: 100%" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="opDialog = false">取消</el-button>
        <el-button type="primary" :loading="opSaving" @click="saveOp">提交报工</el-button>
      </template>
    </el-dialog>

    <!-- 质检新增 -->
    <FormDrawer v-model="qcDrawer" title="新增质检" width="500px" :saving="qcSaving" @save="saveQC">
      <el-form ref="qcFormRef" :model="qcForm" :rules="qcRules" label-width="90px">
        <el-form-item label="类型">
          <el-select v-model="qcForm.check_type" style="width: 100%">
            <el-option label="来料IQC" value="IQC" />
            <el-option label="制程IPQC" value="IPQC" />
            <el-option label="成品FQC" value="FQC" />
          </el-select>
        </el-form-item>
        <el-form-item label="商品" prop="product_id">
          <el-select v-model="qcForm.product_id" filterable placeholder="选择商品" style="width: 100%">
            <el-option v-for="p in products" :key="p.id" :label="`${p.code} ${p.name}`" :value="p.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="检验数量">
          <el-input-number v-model="qcForm.check_qty" :min="0" :precision="2" style="width: 100%" />
        </el-form-item>
        <el-form-item label="合格数量">
          <el-input-number v-model="qcForm.qualified_qty" :min="0" :precision="2" style="width: 100%" />
        </el-form-item>
        <el-form-item label="不合格数量">
          <el-input-number v-model="qcForm.reject_qty" :min="0" :precision="2" style="width: 100%" />
        </el-form-item>
        <el-form-item label="检验员">
          <el-input v-model="qcForm.inspector" />
        </el-form-item>
        <el-form-item label="检验日期">
          <el-date-picker v-model="qcForm.check_date" type="date" value-format="YYYY-MM-DD" style="width: 100%" />
        </el-form-item>
        <el-form-item label="备注">
          <el-input v-model="qcForm.remark" type="textarea" :rows="2" />
        </el-form-item>
      </el-form>
    </FormDrawer>
  </PageShell>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue'
import {
  ElMessage, ElMessageBox, ElButton, ElInput, ElSelect, ElOption, ElInputNumber,
  ElForm, ElFormItem, ElTabs, ElTabPane, ElDrawer, ElDialog, ElDatePicker,
  ElTable, ElTableColumn, ElTag, ElRow, ElCol
} from 'element-plus'
import { Plus, Delete } from '@element-plus/icons-vue'
import PageShell from '../components/PageShell.vue'
import DataTable from '../components/DataTable.vue'
import FormDrawer from '../components/FormDrawer.vue'
import { api, fmtMoney, fmtDate } from '../api'

const activeTab = ref('bom')

const products = ref([])
const warehouses = ref([])
async function loadProducts() {
  try { const d = await api.get('/products', { page: 1, page_size: 500 }); products.value = d.items || [] } catch (e) {}
}
async function loadWarehouses() {
  try { const d = await api.get('/warehouses', { page: 1, page_size: 200 }); warehouses.value = d.items || [] } catch (e) {}
}

// ---------- BOM ----------
const bomRows = ref([])
const bomTotal = ref(0)
const bomPage = ref(1)
const bomPageSize = ref(20)
const bomLoading = ref(false)
const bomProdId = ref('')
const bomColumns = [
  { prop: 'product_code', label: '成品编码', width: 120 },
  { prop: 'product_name', label: '成品名称', minWidth: 180 },
  { prop: 'version', label: '版本', width: 90 },
  { prop: 'output_qty', label: '产出数量', width: 100, align: 'right', formatter: (r) => fmtMoney(r.output_qty, 2) },
  { prop: 'status', label: '状态', width: 90, formatter: (r) => ({ draft: '草稿', active: '启用' }[r.status] || r.status) },
  { prop: 'is_active', label: '是否启用', width: 90, formatter: (r) => (r.is_active ? '启用' : '停用') }
]
async function loadBoms(p = 1) {
  bomPage.value = p
  bomLoading.value = true
  try {
    const data = await api.get('/mfg/boms', { page: bomPage.value, page_size: bomPageSize.value, product_id: bomProdId.value || undefined })
    bomRows.value = data.items
    bomTotal.value = data.total
  } catch (e) { ElMessage.error(e.message) } finally { bomLoading.value = false }
}
function onBomSize(s) { bomPageSize.value = s; loadBoms(1) }

const bomDrawer = ref(false)
const bomSaving = ref(false)
const bomForm = reactive({ items: [] })
function addBomItem() {
  bomForm.items.push({ component_id: null, component_code: '', component_name: '', quantity: 1, loss_rate: 0, is_substitute: 0, sort: bomForm.items.length })
}
function fillBomItem(row, id) {
  const p = products.value.find((x) => x.id === id)
  if (p) { row.component_code = p.code; row.component_name = p.name; row.unit = p.unit }
}
function openBom() {
  Object.assign(bomForm, { product_id: null, name: '', version: 'V1', is_active: 1, output_qty: 1, unit: '', remark: '', items: [] })
  addBomItem()
  bomDrawer.value = true
}
async function saveBom() {
  if (!bomForm.product_id) return ElMessage.warning('请选择成品')
  const rest = bomForm.items.filter((it) => it.component_id)
  if (!rest.length) return ElMessage.warning('请至少添加一个组件物料')
  bomSaving.value = true
  try {
    await api.post('/mfg/boms', {
      product_id: bomForm.product_id, name: bomForm.name || undefined, version: bomForm.version || 'V1',
      is_active: bomForm.is_active, output_qty: bomForm.output_qty, unit: bomForm.unit || undefined,
      remark: bomForm.remark || undefined,
      items: rest.map((it) => ({
        component_id: it.component_id, quantity: it.quantity, loss_rate: it.loss_rate || 0,
        is_substitute: 0, sort: it.sort || 0, unit: it.unit || undefined
      }))
    })
    ElMessage.success('BOM已保存')
    bomDrawer.value = false
    loadBoms(1)
  } catch (e) { ElMessage.error(e.message) } finally { bomSaving.value = false }
}

const bomViewDrawer = ref(false)
const bomView = ref({})
const bomViewItems = ref([])
async function viewBom(row) {
  try {
    const d = await api.get(`/mfg/boms/${row.id}`)
    bomView.value = d
    bomViewItems.value = d.items || []
    bomViewDrawer.value = true
  } catch (e) { ElMessage.error(e.message) }
}

// ---------- 生产工单 ----------
const woRows = ref([])
const woTotal = ref(0)
const woPage = ref(1)
const woPageSize = ref(20)
const woLoading = ref(false)
const woStatus = ref('')
const woColumns = [
  { prop: 'code', label: '工单号', width: 130 },
  { prop: 'product_code', label: '产品编码', width: 120 },
  { prop: 'product_name', label: '产品名称', minWidth: 160 },
  { prop: 'quantity', label: '计划数量', width: 100, align: 'right', formatter: (r) => fmtMoney(r.quantity, 2) },
  { prop: 'produced_qty', label: '已完工', width: 100, align: 'right', formatter: (r) => fmtMoney(r.produced_qty, 2) },
  { prop: 'unit', label: '单位', width: 70, formatter: (r) => r.unit || '—' },
  { prop: 'status', label: '状态', width: 100, formatter: (r) => woStatusMap[r.status] || r.status },
  { prop: 'due_date', label: '计划完成', width: 110, formatter: (r) => fmtDate(r.due_date) }
]
const woStatusMap = { draft: '草稿', released: '已下达', in_progress: '生产中', completed: '已完成', cancelled: '已取消' }
async function loadWOs(p = 1) {
  woPage.value = p
  woLoading.value = true
  try {
    const data = await api.get('/mfg/work-orders', { page: woPage.value, page_size: woPageSize.value, status: woStatus.value || undefined })
    woRows.value = data.items
    woTotal.value = data.total
  } catch (e) { ElMessage.error(e.message) } finally { woLoading.value = false }
}
function onWoSize(s) { woPageSize.value = s; loadWOs(1) }

const woDrawer = ref(false)
const woSaving = ref(false)
const woFormRef = ref()
const woForm = reactive({})
const woRules = {
  product_id: [{ required: true, message: '请选择产品', trigger: 'change' }],
  quantity: [{ required: true, message: '请输入数量', trigger: 'blur' }]
}
function openWO() {
  Object.assign(woForm, { product_id: null, quantity: 1, bom_version: '', sales_order_id: null, warehouse_id: null, start_date: null, due_date: null, remark: '' })
  woDrawer.value = true
}
async function saveWO() {
  await woFormRef.value.validate()
  woSaving.value = true
  try {
    await api.post('/mfg/work-orders', {
      product_id: woForm.product_id, quantity: woForm.quantity,
      bom_version: woForm.bom_version || undefined,
      warehouse_id: woForm.warehouse_id || undefined,
      start_date: woForm.start_date || undefined, due_date: woForm.due_date || undefined,
      remark: woForm.remark || undefined
    })
    ElMessage.success('工单已创建')
    woDrawer.value = false
    loadWOs(1)
  } catch (e) { ElMessage.error(e.message) } finally { woSaving.value = false }
}

async function releaseWO(row) {
  try { await api.post(`/mfg/work-orders/${row.id}/release`); ElMessage.success('已下达'); loadWOs(woPage.value) } catch (e) { ElMessage.error(e.message) }
}
async function issueWO(row) {
  try {
    await ElMessageBox.confirm(`对工单 ${row.code} 执行领料（从仓库扣减物料）？`, '领料', { type: 'warning' })
    await api.post(`/mfg/work-orders/${row.id}/issue`)
    ElMessage.success('领料完成，工单进入生产')
    loadWOs(woPage.value)
  } catch (e) { if (e !== 'cancel' && e?.message) ElMessage.error(e.message) }
}
async function completeWO(row) {
  try {
    await ElMessageBox.confirm(`对工单 ${row.code} 完工入库？`, '完工', { type: 'success' })
    await api.post(`/mfg/work-orders/${row.id}/complete`)
    ElMessage.success('已完工入库')
    loadWOs(woPage.value)
  } catch (e) { if (e !== 'cancel' && e?.message) ElMessage.error(e.message) }
}

// ---------- 报工 ----------
const opRows = ref([])
const opTotal = ref(0)
const opPage = ref(1)
const opPageSize = ref(50)
const opLoading = ref(false)
const opWoId = ref('')
const opColumns = [
  { prop: 'work_order_id', label: '工单ID', width: 90 },
  { prop: 'process_name', label: '工序', width: 120, formatter: (r) => r.process_name || '—' },
  { prop: 'quantity', label: '报工数量', width: 100, align: 'right', formatter: (r) => fmtMoney(r.quantity, 2) },
  { prop: 'qualified_qty', label: '合格', width: 90, align: 'right', formatter: (r) => fmtMoney(r.qualified_qty, 2) },
  { prop: 'reject_qty', label: '报废', width: 90, align: 'right', formatter: (r) => fmtMoney(r.reject_qty, 2) },
  { prop: 'work_hours', label: '工时', width: 80, align: 'right', formatter: (r) => fmtMoney(r.work_hours, 2) },
  { prop: 'operator', label: '操作员', width: 100 },
  { prop: 'report_date', label: '日期', width: 110, formatter: (r) => fmtDate(r.report_date) }
]
async function loadOps(p = 1) {
  opPage.value = p
  opLoading.value = true
  try {
    const data = await api.get('/mfg/op-reports', { page: opPage.value, page_size: opPageSize.value, work_order_id: opWoId.value || undefined })
    opRows.value = data.items
    opTotal.value = data.total
  } catch (e) { ElMessage.error(e.message) } finally { opLoading.value = false }
}
function onOpSize(s) { opPageSize.value = s; loadOps(1) }

const opDialog = ref(false)
const opSaving = ref(false)
const opForm = reactive({})
function reportOp(row) {
  Object.assign(opForm, {
    work_order_id: row.id, process_name: '', quantity: row.quantity - row.produced_qty, qualified_qty: 0, reject_qty: 0, work_hours: 0, operator: '', report_date: new Date().toISOString().slice(0, 10), remark: ''
  })
  opDialog.value = true
}
async function saveOp() {
  opSaving.value = true
  try {
    await api.post('/mfg/op-reports', { ...opForm, report_date: opForm.report_date || undefined, remark: opForm.remark || undefined })
    ElMessage.success('报工成功')
    opDialog.value = false
    loadOps(opPage.value)
  } catch (e) { ElMessage.error(e.message) } finally { opSaving.value = false }
}

// ---------- 质检 ----------
const qcRows = ref([])
const qcTotal = ref(0)
const qcPage = ref(1)
const qcPageSize = ref(50)
const qcLoading = ref(false)
const qcType = ref('')
const qcResult = ref('')
const qcColumns = [
  { prop: 'code', label: '质检单', width: 110 },
  { prop: 'check_type', label: '类型', width: 110, formatter: (r) => ({ IQC: '来料IQC', IPQC: '制程IPQC', FQC: '成品FQC' }[r.check_type] || r.check_type) },
  { prop: 'product_code', label: '商品编码', width: 110 },
  { prop: 'product_name', label: '商品名称', minWidth: 150 },
  { prop: 'check_qty', label: '检验数量', width: 90, align: 'right', formatter: (r) => fmtMoney(r.check_qty, 2) },
  { prop: 'qualified_qty', label: '合格', width: 80, align: 'right', formatter: (r) => fmtMoney(r.qualified_qty, 2) },
  { prop: 'reject_qty', label: '不合格', width: 90, align: 'right', formatter: (r) => fmtMoney(r.reject_qty, 2) },
  { prop: 'result', label: '结果', width: 90, formatter: (r) => (r.result === 'pass' ? '合格' : r.result === 'fail' ? '不合格' : r.result) },
  { prop: 'inspector', label: '检验员', width: 100 },
  { prop: 'check_date', label: '日期', width: 110, formatter: (r) => fmtDate(r.check_date) }
]
async function loadQCs(p = 1) {
  qcPage.value = p
  qcLoading.value = true
  try {
    const data = await api.get('/mfg/quality-checks', {
      page: qcPage.value, page_size: qcPageSize.value,
      check_type: qcType.value || undefined, result: qcResult.value || undefined
    })
    qcRows.value = data.items
    qcTotal.value = data.total
  } catch (e) { ElMessage.error(e.message) } finally { qcLoading.value = false }
}
function onQcSize(s) { qcPageSize.value = s; loadQCs(1) }

const qcDrawer = ref(false)
const qcSaving = ref(false)
const qcFormRef = ref()
const qcForm = reactive({})
const qcRules = {
  product_id: [{ required: true, message: '请选择商品', trigger: 'change' }]
}
function openQC() {
  Object.assign(qcForm, { check_type: 'IQC', product_id: null, ref_type: null, ref_id: null, check_qty: 0, qualified_qty: 0, reject_qty: 0, result: 'pending', inspector: '质检员', check_date: null, remark: '' })
  qcDrawer.value = true
}
async function saveQC() {
  await qcFormRef.value.validate()
  qcSaving.value = true
  try {
    await api.post('/mfg/quality-checks', {
      check_type: qcForm.check_type, product_id: qcForm.product_id,
      check_qty: qcForm.check_qty, qualified_qty: qcForm.qualified_qty, reject_qty: qcForm.reject_qty,
      inspector: qcForm.inspector || '质检员', check_date: qcForm.check_date || undefined,
      remark: qcForm.remark || undefined
    })
    ElMessage.success('质检已记录')
    qcDrawer.value = false
    loadQCs(1)
  } catch (e) { ElMessage.error(e.message) } finally { qcSaving.value = false }
}

// ---------- MRP 可用量 ----------
const mrpRows = ref([])
const mrpLoading = ref(false)
const mrpProdId = ref('')
const mrpColumns = [
  { prop: 'code', label: '商品编码', width: 130 },
  { prop: 'name', label: '商品名称', minWidth: 180 },
  { prop: 'on_hand', label: '现有库存', width: 110, align: 'right', formatter: (r) => fmtMoney(r.on_hand, 2) },
  { prop: 'in_transit', label: '在购', width: 100, align: 'right', formatter: (r) => fmtMoney(r.in_transit, 2) },
  { prop: 'in_production', label: '在产', width: 100, align: 'right', formatter: (r) => fmtMoney(r.in_production, 2) },
  { prop: 'allocated', label: '已分配', width: 100, align: 'right', formatter: (r) => fmtMoney(r.allocated, 2) },
  { prop: 'available', label: '可用量', width: 110, align: 'right', formatter: (r) => fmtMoney(r.available, 2) }
]
async function loadMrp() {
  mrpLoading.value = true
  try {
    const d = await api.get('/mrp/availabilities', { product_id: mrpProdId.value || undefined })
    mrpRows.value = d.items || []
  } catch (e) { ElMessage.error(e.message) } finally { mrpLoading.value = false }
}

onMounted(() => { loadProducts(); loadWarehouses(); loadBoms(1); loadWOs(1); loadOps(1); loadQCs(1); loadMrp() })
</script>

<style scoped>
.filter-row { margin-bottom: 12px; display: flex; gap: 8px; flex-wrap: wrap; }
.form-wrap { display: flex; flex-direction: column; gap: 12px; }
.drawer-footer { display: flex; justify-content: flex-end; gap: 8px; }
.bom-view-head { display: flex; align-items: center; gap: 10px; margin-bottom: 12px; }
.bom-view-head .head-code { color: #2563eb; font-weight: 600; }
</style>