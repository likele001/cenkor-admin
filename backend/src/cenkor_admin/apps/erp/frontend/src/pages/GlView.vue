<template>
  <PageShell title="总账" subtitle="会计科目 · 记账凭证 · 账簿分录 · 会计期间 · 三大报表">
    <template #actions>
      <el-button type="primary" :icon="Plus" @click="seedAccounts">初始化科目</el-button>
    </template>

    <el-tabs v-model="activeTab">
      <!-- 会计科目 -->
      <el-tab-pane label="会计科目" name="account">
        <div class="filter-row">
          <el-select v-model="acctCategory" placeholder="科目类别" clearable style="width: 150px" @change="loadAccounts(1)">
            <el-option label="资产" value="asset" />
            <el-option label="负债" value="liability" />
            <el-option label="权益" value="equity" />
            <el-option label="收入" value="revenue" />
            <el-option label="费用" value="expense" />
          </el-select>
          <el-button type="primary" plain :icon="Plus" @click="openAccount(null)">新增科目</el-button>
        </div>
        <DataTable
          :data="acctRows" :columns="acctColumns" :total="acctTotal" :page="acctPage"
          :page-size="acctPageSize" :loading="acctLoading"
          @update:page="loadAccounts" @update:pageSize="onAcctSize"
        />
      </el-tab-pane>

      <!-- 记账凭证 -->
      <el-tab-pane label="记账凭证" name="voucher">
        <div class="filter-row">
          <el-button type="primary" plain :icon="Plus" @click="openVoucher">新增凭证</el-button>
          <el-select v-model="vStatus" placeholder="状态" clearable style="width: 130px" @change="loadVouchers(1)">
            <el-option label="已过账" value="posted" />
          </el-select>
        </div>
        <DataTable
          :data="vRows" :columns="vColumns" :total="vTotal" :page="vPage"
          :page-size="vPageSize" :loading="vLoading"
          @update:page="loadVouchers" @update:pageSize="onVSize"
        >
          <template #operation>
            <el-table-column label="操作" width="90" align="center" fixed="right">
              <template #default="{ row }">
                <el-button link type="primary" @click="viewVoucher(row)">查看</el-button>
              </template>
            </el-table-column>
          </template>
        </DataTable>
      </el-tab-pane>

      <!-- 账簿分录 -->
      <el-tab-pane label="账簿分录" name="entry">
        <div class="filter-row">
          <el-input v-model="entryAcct" placeholder="科目ID" clearable style="width: 120px" @keyup.enter="loadEntries(1)" @clear="loadEntries(1)" />
          <el-input v-model="entryPeriod" placeholder="期间 YYYY-MM" clearable style="width: 160px" @keyup.enter="loadEntries(1)" @clear="loadEntries(1)" />
          <el-button type="primary" plain @click="loadEntries(1)">查询分录</el-button>
          <el-button type="primary" plain @click="loadLedger()">科目余额汇总</el-button>
        </div>
        <DataTable
          :data="entryRows" :columns="entryColumns" :total="entryTotal" :page="entryPage"
          :page-size="entryPageSize" :loading="entryLoading"
          @update:page="loadEntries" @update:pageSize="onEntrySize"
        />
        <el-collapse style="margin-top: 12px">
          <el-collapse-item v-if="ledgerRows.length" title="科目余额汇总（含期初）">
            <el-table :data="ledgerRows" border size="small">
              <el-table-column prop="account_code" label="科目编码" width="120" />
              <el-table-column prop="account_name" label="科目名称" min-width="160" />
              <el-table-column prop="debit" label="借方发生" width="120" align="right" :formatter="moneyFmt" />
              <el-table-column prop="credit" label="贷方发生" width="120" align="right" :formatter="moneyFmt" />
              <el-table-column prop="initial_balance" label="期初" width="120" align="right" :formatter="moneyFmt" />
              <el-table-column prop="balance" label="余额" width="120" align="right" :formatter="moneyFmt" />
            </el-table>
          </el-collapse-item>
        </el-collapse>
      </el-tab-pane>

      <!-- 会计期间 -->
      <el-tab-pane label="会计期间" name="period">
        <div class="filter-row">
          <el-button type="primary" plain :icon="Plus" @click="openPeriod">新增期间</el-button>
        </div>
        <DataTable
          :data="pRows" :columns="pColumns" :total="pTotal" :page="pPage"
          :page-size="pPageSize" :loading="pLoading"
          @update:page="loadPeriods" @update:pageSize="onPSize"
        >
          <template #operation>
            <el-table-column label="操作" width="100" align="center" fixed="right">
              <template #default="{ row }">
                <el-button
                  v-if="row.status !== 'closed'" link type="warning"
                  @click="closePeriod(row)"
                >期末结转</el-button>
              </template>
            </el-table-column>
          </template>
        </DataTable>
      </el-tab-pane>

      <!-- 三大报表 -->
      <el-tab-pane label="三大报表" name="report">
        <div class="filter-row">
          <el-input v-model="reportPeriod" placeholder="期间 YYYY-MM" clearable style="width: 160px" />
          <el-button type="primary" plain @click="loadReports">生成报表</el-button>
        </div>
        <template v-if="reportsLoaded">
          <el-row :gutter="12">
            <el-col :span="8">
              <el-card shadow="never" header="资产负债表">
                <div class="rep-total">资产合计 <b>{{ fmtMoney(balance.asset_total) }}</b></div>
                <div class="rep-total">负债合计 <b>{{ fmtMoney(balance.liability_total) }}</b></div>
                <div class="rep-total">权益合计 <b>{{ fmtMoney(balance.equity_total) }}</b></div>
                <el-tag :type="balance.balanced ? 'success' : 'danger'" size="small">
                  {{ balance.balanced ? '平衡' : '不平衡' }}
                </el-tag>
              </el-card>
            </el-col>
            <el-col :span="8">
              <el-card shadow="never" header="利润表">
                <div class="rep-total">营业收入 <b>{{ fmtMoney(income.revenue_total) }}</b></div>
                <div class="rep-total">营业费用 <b>{{ fmtMoney(income.expense_total) }}</b></div>
                <div class="rep-total net">净利润 <b>{{ fmtMoney(income.net_profit) }}</b></div>
              </el-card>
            </el-col>
            <el-col :span="8">
              <el-card shadow="never" header="现金流量表">
                <div class="rep-total">现金流入 <b>{{ fmtMoney(cash.cash_inflow) }}</b></div>
                <div class="rep-total">现金流出 <b>{{ fmtMoney(cash.cash_outflow) }}</b></div>
                <div class="rep-total net">净现金流 <b>{{ fmtMoney(cash.net_cash) }}</b></div>
              </el-card>
            </el-col>
          </el-row>
        </template>
      </el-tab-pane>
    </el-tabs>

    <!-- 科目表单 -->
    <FormDrawer v-model="acctDrawer" :title="acctForm.id ? '编辑科目' : '新增科目'" width="480px" :saving="acctSaving" @save="saveAccount">
      <el-form ref="acctFormRef" :model="acctForm" :rules="acctRules" label-width="90px">
        <el-form-item label="科目编码" prop="code"><el-input v-model="acctForm.code" /></el-form-item>
        <el-form-item label="科目名称" prop="name"><el-input v-model="acctForm.name" /></el-form-item>
        <el-form-item label="类别">
          <el-select v-model="acctForm.category" style="width: 100%">
            <el-option label="资产" value="asset" />
            <el-option label="负债" value="liability" />
            <el-option label="权益" value="equity" />
            <el-option label="收入" value="revenue" />
            <el-option label="费用" value="expense" />
          </el-select>
        </el-form-item>
        <el-form-item label="余额方向">
          <el-radio-group v-model="acctForm.direction">
            <el-radio value="debit">借方</el-radio>
            <el-radio value="credit">贷方</el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item label="期初余额">
          <el-input-number v-model="acctForm.initial_balance" :precision="2" :step="100" style="width: 100%" />
        </el-form-item>
        <el-form-item label="排序">
          <el-input-number v-model="acctForm.seq" :min="0" style="width: 100%" />
        </el-form-item>
      </el-form>
    </FormDrawer>

    <!-- 凭证新增/查看 -->
    <el-drawer v-model="vDrawer" :title="vDrawerTitle" size="640px" destroy-on-close>
      <div class="voucher-form">
        <el-form label-width="90px" :model="vForm">
          <el-form-item label="凭证日期" required>
            <el-date-picker v-model="vForm.voucher_date" type="date" value-format="YYYY-MM-DD" style="width: 100%" :disabled="vReadonly" />
          </el-form-item>
          <el-form-item label="摘要">
            <el-input v-model="vForm.remark" type="textarea" :rows="2" :disabled="vReadonly" />
          </el-form-item>
          <el-form-item label="分录">
            <el-button v-if="!vReadonly" type="primary" plain size="small" :icon="Plus" @click="addEntryLine">新增分录</el-button>
          </el-form-item>
        </el-form>
        <el-table :data="vForm.entries" border size="small" empty-text="请添加分录">
          <el-table-column label="科目" min-width="220">
            <template #default="{ row }">
              <el-select
                v-if="!vReadonly" v-model="row.account_id" filterable placeholder="选择科目"
                style="width: 100%" @change="(id) => fillEntryAccount(row, id)"
              >
                <el-option v-for="a in acctRows" :key="a.id" :label="`${a.code} ${a.name}`" :value="a.id" />
              </el-select>
              <span v-else>{{ row.account_code }} {{ row.account_name }}</span>
            </template>
          </el-table-column>
          <el-table-column label="摘要" min-width="140">
            <template #default="{ row }">
              <el-input v-if="!vReadonly" v-model="row.summary" />
              <span v-else>{{ row.summary }}</span>
            </template>
          </el-table-column>
          <el-table-column label="借方" width="140" align="right">
            <template #default="{ row }">
              <el-input-number v-if="!vReadonly" v-model="row.debit" :min="0" :precision="2" controls-position="right" style="width: 100%" @change="calcVoucher" />
              <span v-else>{{ fmtMoney(row.debit) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="贷方" width="140" align="right">
            <template #default="{ row }">
              <el-input-number v-if="!vReadonly" v-model="row.credit" :min="0" :precision="2" controls-position="right" style="width: 100%" @change="calcVoucher" />
              <span v-else>{{ fmtMoney(row.credit) }}</span>
            </template>
          </el-table-column>
          <el-table-column v-if="!vReadonly" label="" width="56" align="center">
            <template #default="{ $index }">
              <el-button link type="danger" :icon="Delete" @click="vForm.entries.splice($index, 1)" />
            </template>
          </el-table-column>
        </el-table>
        <div class="voucher-sum">
          <span>借方合计：{{ fmtMoney(vTotalDebit) }}</span>
          <span>贷方合计：{{ fmtMoney(vTotalCredit) }}</span>
          <el-tag :type="vBalanced ? 'success' : 'danger'" size="small">{{ vBalanced ? '平衡' : '不平衡' }}</el-tag>
        </div>
      </div>
      <template #footer>
        <div class="drawer-footer">
          <el-button @click="vDrawer = false">关闭</el-button>
          <el-button v-if="!vReadonly" type="primary" :loading="vSaving" @click="saveVoucher">保存并过账</el-button>
        </div>
      </template>
    </el-drawer>

    <!-- 期间新增 -->
    <FormDrawer v-model="pDrawer" title="新增会计期间" width="420px" :saving="pSaving" @save="savePeriod">
      <el-form ref="pFormRef" :model="pForm" :rules="pRules" label-width="90px">
        <el-form-item label="期间" prop="period">
          <el-input v-model="pForm.period" placeholder="YYYY-MM" />
        </el-form-item>
      </el-form>
    </FormDrawer>
  </PageShell>
</template>

<script setup>
import { ref, reactive, computed, onMounted } from 'vue'
import {
  ElMessage, ElMessageBox, ElButton, ElInput, ElSelect, ElOption, ElInputNumber,
  ElForm, ElFormItem, ElTabs, ElTabPane, ElDrawer, ElDatePicker, ElCollapse,
  ElCollapseItem, ElCard, ElRow, ElCol, ElTag, ElRadio, ElRadioGroup, ElTable, ElTableColumn
} from 'element-plus'
import { Plus, Delete } from '@element-plus/icons-vue'
import PageShell from '../components/PageShell.vue'
import DataTable from '../components/DataTable.vue'
import FormDrawer from '../components/FormDrawer.vue'
import { api, fmtMoney, fmtDate, statusLabel, statusTagType } from '../api'

const activeTab = ref('account')

// ---------- 会计科目 ----------
const acctRows = ref([])
const acctTotal = ref(0)
const acctPage = ref(1)
const acctPageSize = ref(200)
const acctLoading = ref(false)
const acctCategory = ref('')
const acctCategoryLabel = { asset: '资产', liability: '负债', equity: '权益', revenue: '收入', expense: '费用' }
const acctColumns = [
  { prop: 'code', label: '科目编码', width: 120 },
  { prop: 'name', label: '科目名称', minWidth: 180 },
  { prop: 'category', label: '类别', width: 90, formatter: (r) => acctCategoryLabel[r.category] || r.category },
  { prop: 'direction', label: '方向', width: 80, formatter: (r) => (r.direction === 'debit' ? '借方' : '贷方') },
  { prop: 'initial_balance', label: '期初', width: 120, align: 'right', formatter: (r) => fmtMoney(r.initial_balance) },
  { prop: 'status', label: '状态', width: 90, tag: { text: (r) => statusLabel(r.status), type: (r) => statusTagType(r.status) } }
]

async function loadAccounts(p = 1) {
  acctPage.value = p
  acctLoading.value = true
  try {
    const data = await api.get('/gl/accounts', {
      page: acctPage.value, page_size: acctPageSize.value, category: acctCategory.value || undefined
    })
    acctRows.value = data.items
    acctTotal.value = data.total
  } catch (e) { ElMessage.error(e.message) } finally { acctLoading.value = false }
}
function onAcctSize(s) { acctPageSize.value = s; loadAccounts(1) }

async function seedAccounts() {
  try {
    await ElMessageBox.confirm('将初始化标准会计科目表（已有科目则不重复），继续？', '初始化科目', { type: 'info' })
    const r = await api.post('/gl/accounts/seed')
    ElMessage.success(`初始化 ${r.seeded} 个科目`)
    loadAccounts(1)
  } catch (e) { if (e !== 'cancel' && e?.message) ElMessage.error(e.message) }
}

// ---------- 科目表单 ----------
const acctDrawer = ref(false)
const acctSaving = ref(false)
const acctFormRef = ref()
const acctForm = reactive({})
const acctRules = {
  code: [{ required: true, message: '请输入编码', trigger: 'blur' }],
  name: [{ required: true, message: '请输入名称', trigger: 'blur' }]
}
function openAccount(row) {
  Object.assign(acctForm, { id: null, code: '', name: '', category: 'asset', direction: 'debit', initial_balance: 0, seq: acctRows.value.length + 1 })
  acctDrawer.value = true
}
async function saveAccount() {
  await acctFormRef.value.validate()
  acctSaving.value = true
  try {
    await api.post('/gl/accounts', { ...acctForm })
    ElMessage.success('保存成功')
    acctDrawer.value = false
    loadAccounts(acctPage.value)
  } catch (e) { ElMessage.error(e.message) } finally { acctSaving.value = false }
}

// ---------- 记账凭证 ----------
const vRows = ref([])
const vTotal = ref(0)
const vPage = ref(1)
const vPageSize = ref(20)
const vLoading = ref(false)
const vStatus = ref('')
const vColumns = [
  { prop: 'code', label: '凭证号', width: 120 },
  { prop: 'period', label: '期间', width: 90 },
  { prop: 'voucher_date', label: '日期', width: 110, formatter: (r) => fmtDate(r.voucher_date) },
  { prop: 'word', label: '字', width: 70 },
  { prop: 'source_type', label: '来源', width: 110, formatter: (r) => sourceLabel(r.source_type) },
  { prop: 'total_debit', label: '借方合计', width: 130, align: 'right', formatter: (r) => fmtMoney(r.total_debit) },
  { prop: 'total_credit', label: '贷方合计', width: 130, align: 'right', formatter: (r) => fmtMoney(r.total_credit) },
  { prop: 'status', label: '状态', width: 90, tag: { text: (r) => statusLabel(r.status), type: (r) => statusTagType(r.status) } }
]
function sourceLabel(s) {
  return { manual: '手工', period_close: '期末结转', sales: '销售', purchase: '采购' }[s] || s || '—'
}

async function loadVouchers(p = 1) {
  vPage.value = p
  vLoading.value = true
  try {
    const data = await api.get('/gl/vouchers', { page: vPage.value, page_size: vPageSize.value, status: vStatus.value || undefined })
    vRows.value = data.items
    vTotal.value = data.total
  } catch (e) { ElMessage.error(e.message) } finally { vLoading.value = false }
}
function onVSize(s) { vPageSize.value = s; loadVouchers(1) }

// ---------- 凭证表单 ----------
const vDrawer = ref(false)
const vDrawerTitle = ref('新增凭证')
const vSaving = ref(false)
const vReadonly = ref(false)
const vForm = reactive({ entries: [] })
const vTotalDebit = ref(0)
const vTotalCredit = ref(0)
const vBalanced = computed(() => Math.abs(vTotalDebit.value - vTotalCredit.value) < 0.001)

function calcVoucher() {
  vTotalDebit.value = Math.round(vForm.entries.reduce((s, e) => s + Number(e.debit || 0), 0) * 100) / 100
  vTotalCredit.value = Math.round(vForm.entries.reduce((s, e) => s + Number(e.credit || 0), 0) * 100) / 100
}
function fillEntryAccount(row, id) {
  const a = acctRows.value.find((x) => x.id === id)
  if (a) { row.account_code = a.code; row.account_name = a.name }
  if (!row.direction && a?.direction === 'debit') row.debit = 0
}
function openVoucher() {
  vReadonly.value = false
  vDrawerTitle.value = '新增凭证'
  Object.assign(vForm, { voucher_date: new Date().toISOString().slice(0, 10), word: '记', source_type: 'manual', remark: '', entries: [] })
  vTotalDebit.value = 0
  vTotalCredit.value = 0
  vDrawer.value = true
  // 载入科目备选
  if (!acctRows.value.length) loadAccounts(1)
}
function addEntryLine() {
  vForm.entries.push({ account_id: null, account_code: '', account_name: '', summary: '', debit: 0, credit: 0 })
  calcVoucher()
}
function showAddEntry() {
  if (vReadonly.value) return
  addEntryLine()
}
async function saveVoucher() {
  if (!vForm.entries.length) return ElMessage.warning('请至少添加一条分录')
  if (vForm.entries.some((e) => !e.account_id)) return ElMessage.warning('请选择科目')
  if (!vBalanced.value) return ElMessage.warning('借贷不平衡，无法过账')
  vSaving.value = true
  try {
    const payload = {
      voucher_date: vForm.voucher_date,
      word: vForm.word || '记',
      source_type: vForm.source_type || 'manual',
      remark: vForm.remark || undefined,
      entries: vForm.entries.map((e) => ({ account_id: e.account_id, summary: e.summary || undefined, debit: e.debit, credit: e.credit }))
    }
    await api.post('/gl/vouchers', payload)
    ElMessage.success('凭证已过账')
    vDrawer.value = false
    loadVouchers(vPage.value)
  } catch (e) { ElMessage.error(e.message) } finally { vSaving.value = false }
}
async function viewVoucher(row) {
  vReadonly.value = true
  vDrawerTitle.value = `凭证 ${row.code}`
  try {
    const d = await api.get(`/gl/vouchers/${row.id}`)
    Object.assign(vForm, {
      voucher_date: fmtDate(d.voucher_date), word: d.word, source_type: d.source_type,
      remark: d.remark || '', entries: (d.entries || []).map((e) => ({
        account_id: e.account_id, account_code: e.account_code, account_name: e.account_name,
        summary: e.summary, debit: e.debit, credit: e.credit
      }))
    })
    vTotalDebit.value = d.total_debit
    vTotalCredit.value = d.total_credit
    vDrawer.value = true
  } catch (e) { ElMessage.error(e.message) }
}

// ---------- 账簿分录 ----------
const entryRows = ref([])
const entryTotal = ref(0)
const entryPage = ref(1)
const entryPageSize = ref(50)
const entryLoading = ref(false)
const entryAcct = ref('')
const entryPeriod = ref('')
const ledgerRows = ref([])
const entryColumns = [
  { prop: 'id', label: 'ID', width: 80 },
  { prop: 'account_code', label: '科目编码', width: 110 },
  { prop: 'account_name', label: '科目名称', minWidth: 160 },
  { prop: 'summary', label: '摘要', minWidth: 160 },
  { prop: 'debit', label: '借方', width: 120, align: 'right', formatter: (r) => fmtMoney(r.debit) },
  { prop: 'credit', label: '贷方', width: 120, align: 'right', formatter: (r) => fmtMoney(r.credit) }
]
function moneyFmt(row, col) { return fmtMoney(row[col.property]) }
async function loadEntries(p = 1) {
  entryPage.value = p
  entryLoading.value = true
  try {
    const data = await api.get('/gl/entries', {
      page: entryPage.value, page_size: entryPageSize.value,
      account_id: entryAcct.value || undefined, period: entryPeriod.value || undefined
    })
    entryRows.value = data.items
    entryTotal.value = data.total
  } catch (e) { ElMessage.error(e.message) } finally { entryLoading.value = false }
}
function onEntrySize(s) { entryPageSize.value = s; loadEntries(1) }
async function loadLedger() {
  try {
    const data = await api.get('/gl/ledger', {
      account_id: entryAcct.value || undefined, period: entryPeriod.value || undefined
    })
    ledgerRows.value = data.items || []
    ElMessage.success(`共 ${data.count || 0} 个科目`)
  } catch (e) { ElMessage.error(e.message) }
}

// ---------- 会计期间 ----------
const pRows = ref([])
const pTotal = ref(0)
const pPage = ref(1)
const pPageSize = ref(60)
const pLoading = ref(false)
const pColumns = [
  { prop: 'period', label: '期间', width: 110 },
  { prop: 'start_date', label: '开始', width: 120, formatter: (r) => fmtDate(r.start_date) },
  { prop: 'end_date', label: '结束', width: 120, formatter: (r) => fmtDate(r.end_date) },
  { prop: 'status', label: '状态', width: 90, tag: { text: (r) => (r.status === 'closed' ? '已关闭' : '开启'), type: (r) => (r.status === 'closed' ? 'info' : 'success') } }
]
async function loadPeriods(p = 1) {
  pPage.value = p
  pLoading.value = true
  try {
    const data = await api.get('/gl/periods', { page: pPage.value, page_size: pPageSize.value })
    pRows.value = data.items
    pTotal.value = data.total
  } catch (e) { ElMessage.error(e.message) } finally { pLoading.value = false }
}
function onPSize(s) { pPageSize.value = s; loadPeriods(1) }

const pDrawer = ref(false)
const pSaving = ref(false)
const pFormRef = ref()
const pForm = reactive({ period: '' })
const pRules = { period: [{ required: true, message: '请输入期间 YYYY-MM', trigger: 'blur' }] }
function openPeriod() { Object.assign(pForm, { period: '' }); pDrawer.value = true }
async function savePeriod() {
  await pFormRef.value.validate()
  pSaving.value = true
  try {
    await api.post('/gl/periods', { period: pForm.period })
    ElMessage.success('已创建期间')
    pDrawer.value = false
    loadPeriods(1)
  } catch (e) { ElMessage.error(e.message) } finally { pSaving.value = false }
}
async function closePeriod(row) {
  try {
    await ElMessageBox.confirm(`对 ${row.period} 执行期末结转并关闭期间？`, '期末结转', { type: 'warning' })
    await api.post(`/gl/periods/${row.period}/close`)
    ElMessage.success('结转完成')
    loadPeriods(1)
  } catch (e) { if (e !== 'cancel' && e?.message) ElMessage.error(e.message) }
}

// ---------- 三大报表 ----------
const reportPeriod = ref(new Date().toISOString().slice(0, 7))
const reportsLoaded = ref(false)
const balance = ref({})
const income = ref({})
const cash = ref({})
async function loadReports() {
  if (!reportPeriod.value) return ElMessage.warning('请输入期间')
  try {
    const [b, i, c] = await Promise.all([
      api.get('/gl/balance-sheet', { period: reportPeriod.value }),
      api.get('/gl/income-statement', { period: reportPeriod.value }),
      api.get('/gl/cash-flow', { period: reportPeriod.value })
    ])
    balance.value = b
    income.value = i
    cash.value = c
    reportsLoaded.value = true
  } catch (e) { ElMessage.error(e.message) }
}

onMounted(() => { loadAccounts(1); loadVouchers(1) })
</script>

<style scoped>
.filter-row { margin-bottom: 12px; display: flex; gap: 8px; flex-wrap: wrap; }
.voucher-form { display: flex; flex-direction: column; gap: 12px; }
.voucher-sum { display: flex; gap: 16px; align-items: center; justify-content: flex-end; margin-top: 10px; }
.rep-total { margin: 8px 0; font-size: 14px; color: #374151; }
.rep-total b { float: right; }
.rep-total.net b { color: #2563eb; }
.drawer-footer { display: flex; justify-content: flex-end; gap: 8px; }
</style>