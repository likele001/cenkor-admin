<template>
  <PageShell title="客户管理" subtitle="客户主数据 · 联系人 · 多地址">
    <template #actions>
      <el-button type="primary" :icon="Plus" @click="openCreate">新增客户</el-button>
    </template>

    <SearchBar :fields="searchFields" @search="onSearch" />

    <div class="filter-row">
      <el-select v-model="filters.status" placeholder="客户状态" clearable style="width: 140px" @change="load(1)">
        <el-option label="启用" value="active" />
        <el-option label="停用" value="inactive" />
      </el-select>
    </div>

    <DataTable
      :data="rows"
      :columns="columns"
      :total="total"
      :page="page"
      :page-size="pageSize"
      :loading="loading"
      @update:page="load"
      @update:pageSize="onSizeChange"
    >
      <template #operation>
        <el-table-column label="操作" width="150" align="center" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" @click="goDetail(row)">详情</el-button>
            <el-button link type="primary" @click="openEdit(row)">编辑</el-button>
            <el-button link type="danger" @click="remove(row)">删除</el-button>
          </template>
        </el-table-column>
      </template>
    </DataTable>

    <!-- 新增/编辑抽屉 -->
    <FormDrawer
      v-model="drawerVisible"
      :title="drawerTitle"
      width="600px"
      :saving="saving"
      @save="save"
    >
      <el-form ref="formRef" :model="form" :rules="rules" label-width="100px">
        <el-row :gutter="16">
          <el-col :span="12">
            <el-form-item label="客户编号" prop="code"><el-input v-model="form.code" placeholder="留空自动生成" /></el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="客户名称" prop="name"><el-input v-model="form.name" /></el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="简称"><el-input v-model="form.short_name" /></el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="客户类型">
              <el-select v-model="form.customer_type" style="width: 100%">
                <el-option label="企业" value="company" />
                <el-option label="个人" value="person" />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="税号"><el-input v-model="form.tax_id" /></el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="结算币种">
              <el-select v-model="form.currency" style="width: 100%">
                <el-option label="CNY" value="CNY" />
                <el-option label="USD" value="USD" />
                <el-option label="EUR" value="EUR" />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="信用额度"><el-input-number v-model="form.credit_limit" :min="0" :precision="2" style="width: 100%" /></el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="所属行业"><el-input v-model="form.industry" /></el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="结算方式"><el-input v-model="form.payment_terms" placeholder="如：月结30天" /></el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="规模">
              <el-select v-model="form.scale" clearable style="width: 100%">
                <el-option label="微型" value="micro" />
                <el-option label="小型" value="small" />
                <el-option label="中型" value="medium" />
                <el-option label="大型" value="large" />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :span="24">
            <el-form-item label="备注"><el-input v-model="form.notes" type="textarea" :rows="2" /></el-form-item>
          </el-col>
        </el-row>
      </el-form>
    </FormDrawer>
  </PageShell>
</template>

<script setup>
import { ref, reactive, computed, onMounted } from 'vue'
import { ElMessage, ElMessageBox, ElButton, ElSelect, ElOption, ElInput, ElInputNumber, ElRow, ElCol, ElForm, ElFormItem } from 'element-plus'
import { Plus } from '@element-plus/icons-vue'
import PageShell from '../components/PageShell.vue'
import SearchBar from '../components/SearchBar.vue'
import DataTable from '../components/DataTable.vue'
import FormDrawer from '../components/FormDrawer.vue'
import { api, fmtDate, statusLabel, statusTagType } from '../api'
import { go } from '../nav'

const rows = ref([])
const total = ref(0)
const page = ref(1)
const pageSize = ref(20)
const loading = ref(false)
const filters = reactive({ keyword: '', status: '' })
const drawerVisible = ref(false)
const saving = ref(false)
const editingId = ref(null)
const formRef = ref()

const searchFields = [
  { prop: 'keyword', label: '关键词', type: 'input', placeholder: '名称/编号/简称' }
]

const columns = [
  { prop: 'code', label: '编号', width: 130 },
  { prop: 'name', label: '客户名称', minWidth: 180 },
  { prop: 'short_name', label: '简称', minWidth: 120 },
  { prop: 'customer_type', label: '类型', width: 90, formatter: (r) => (r.customer_type === 'company' ? '企业' : '个人') },
  { prop: 'status', label: '状态', width: 90, tag: { text: (r) => statusLabel(r.status), type: (r) => statusTagType(r.status) } },
  { prop: 'created_at', label: '创建时间', width: 130, formatter: (r) => fmtDate(r.created_at) }
]

const drawerTitle = computed(() => (editingId.value ? '编辑客户' : '新增客户'))

const form = reactive({
  code: '', name: '', short_name: '', customer_type: 'company', tax_id: '',
  currency: 'CNY', credit_limit: 0, industry: '', payment_terms: '', scale: '', notes: ''
})

const rules = {
  name: [{ required: true, message: '请输入客户名称', trigger: 'blur' }]
}

async function load(p = 1) {
  page.value = p
  loading.value = true
  try {
    const data = await api.get('/customers', {
      page: page.value, page_size: pageSize.value,
      keyword: filters.keyword || undefined, status: filters.status || undefined
    })
    rows.value = data.items
    total.value = data.total
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    loading.value = false
  }
}

function onSearch(q) {
  filters.keyword = q.keyword || ''
  load(1)
}

function onSizeChange(s) {
  pageSize.value = s
  load(1)
}

function openCreate() {
  editingId.value = null
  Object.assign(form, { code: '', name: '', short_name: '', customer_type: 'company', tax_id: '', currency: 'CNY', credit_limit: 0, industry: '', payment_terms: '', scale: '', notes: '' })
  drawerVisible.value = true
}

function openEdit(row) {
  editingId.value = row.id
  Object.assign(form, {
    code: row.code, name: row.name, short_name: row.short_name || '', customer_type: row.customer_type || 'company',
    tax_id: row.tax_id || '', currency: row.currency || 'CNY', credit_limit: Number(row.credit_limit) || 0,
    industry: row.industry || '', payment_terms: row.payment_terms || '', scale: row.scale || '', notes: row.notes || ''
  })
  drawerVisible.value = true
}

function goDetail(row) {
  go(`/erp/customers/${row.id}`)
}

async function save() {
  await formRef.value.validate()
  saving.value = true
  try {
    const payload = { ...form, credit_limit: Number(form.credit_limit) || 0 }
    if (editingId.value) {
      await api.put(`/customers/${editingId.value}`, payload)
    } else {
      await api.post('/customers', payload)
    }
    ElMessage.success('保存成功')
    drawerVisible.value = false
    load(page.value)
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    saving.value = false
  }
}

async function remove(row) {
  try {
    await ElMessageBox.confirm(`确认删除客户「${row.name}」吗？`, '提示', { type: 'warning' })
  } catch (e) { return }
  try {
    await api.del(`/customers/${row.id}`)
    ElMessage.success('已删除')
    load(rows.value.length === 1 && page.value > 1 ? page.value - 1 : page.value)
  } catch (e) {
    ElMessage.error(e.message)
  }
}

onMounted(() => load(1))
</script>

<style scoped>
.filter-row {
  margin-bottom: 12px;
  display: flex;
  gap: 8px;
}
</style>