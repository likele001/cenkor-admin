<template>
  <PageShell title="供应商" subtitle="供应商主数据">
    <template #actions>
      <el-button type="primary" :icon="Plus" @click="openCreate">新增供应商</el-button>
    </template>

    <SearchBar :fields="searchFields" @search="onSearch" />

    <DataTable
      :data="rows" :columns="columns" :total="total" :page="page"
      :page-size="pageSize" :loading="loading"
      @update:page="load" @update:pageSize="onSizeChange"
    >
      <template #operation>
        <el-table-column label="操作" width="150" align="center" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" @click="openEdit(row)">编辑</el-button>
            <el-button link type="danger" @click="remove(row)">删除</el-button>
          </template>
        </el-table-column>
      </template>
    </DataTable>

    <FormDrawer v-model="drawerVisible" :title="drawerTitle" width="600px" :saving="saving" @save="save">
      <el-form ref="formRef" :model="form" :rules="rules" label-width="110px">
        <el-row :gutter="16">
          <el-col :span="12"><el-form-item label="供应商编号"><el-input v-model="form.code" placeholder="留空自动生成" /></el-form-item></el-col>
          <el-col :span="12"><el-form-item label="供应商名称" prop="name"><el-input v-model="form.name" /></el-form-item></el-col>
          <el-col :span="12"><el-form-item label="简称"><el-input v-model="form.short_name" /></el-form-item></el-col>
          <el-col :span="12"><el-form-item label="联系人"><el-input v-model="form.contact_person" /></el-form-item></el-col>
          <el-col :span="12"><el-form-item label="联系电话"><el-input v-model="form.phone" /></el-form-item></el-col>
          <el-col :span="12"><el-form-item label="邮箱"><el-input v-model="form.email" /></el-form-item></el-col>
          <el-col :span="12"><el-form-item label="税号"><el-input v-model="form.tax_id" /></el-form-item></el-col>
          <el-col :span="12"><el-form-item label="分类"><el-input v-model="form.category" placeholder="如：原材料/包材/服务" /></el-form-item></el-col>
          <el-col :span="12"><el-form-item label="结算方式"><el-input v-model="form.payment_terms" placeholder="如：月结30天" /></el-form-item></el-col>
          <el-col :span="12"><el-form-item label="币种"><el-select v-model="form.currency" style="width:100%"><el-option label="CNY" value="CNY" /><el-option label="USD" value="USD" /></el-select></el-form-item></el-col>
          <el-col :span="12"><el-form-item label="信用额度"><el-input-number v-model="form.credit_limit" :min="0" :precision="2" style="width:100%" /></el-form-item></el-col>
          <el-col :span="24"><el-form-item label="备注"><el-input v-model="form.notes" type="textarea" :rows="2" /></el-form-item></el-col>
        </el-row>
      </el-form>
    </FormDrawer>
  </PageShell>
</template>

<script setup>
import { ref, reactive, computed, onMounted } from 'vue'
import {
  ElMessage, ElMessageBox, ElButton, ElInput, ElInputNumber, ElSelect, ElOption,
  ElRow, ElCol, ElForm, ElFormItem
} from 'element-plus'
import { Plus } from '@element-plus/icons-vue'
import PageShell from '../components/PageShell.vue'
import SearchBar from '../components/SearchBar.vue'
import DataTable from '../components/DataTable.vue'
import FormDrawer from '../components/FormDrawer.vue'
import { api, fmtDate, statusLabel, statusTagType } from '../api'

const rows = ref([])
const total = ref(0)
const page = ref(1)
const pageSize = ref(20)
const loading = ref(false)
const filters = reactive({ keyword: '' })
const drawerVisible = ref(false)
const saving = ref(false)
const editingId = ref(null)
const formRef = ref()

const searchFields = [
  { prop: 'keyword', label: '关键词', type: 'input', placeholder: '名称/编号/联系人' }
]

const columns = [
  { prop: 'code', label: '编号', width: 130 },
  { prop: 'name', label: '供应商名称', minWidth: 180 },
  { prop: 'contact_person', label: '联系人', width: 110 },
  { prop: 'phone', label: '联系电话', width: 140 },
  { prop: 'category', label: '分类', width: 110 },
  { prop: 'status', label: '状态', width: 90, tag: { text: (r) => statusLabel(r.status), type: (r) => statusTagType(r.status) } },
  { prop: 'created_at', label: '创建时间', width: 130, formatter: (r) => fmtDate(r.created_at) }
]

const drawerTitle = computed(() => (editingId.value ? '编辑供应商' : '新增供应商'))
const form = reactive({})
const rules = { name: [{ required: true, message: '请输入供应商名称', trigger: 'blur' }] }

function emptyForm() {
  return { code: '', name: '', short_name: '', contact_person: '', phone: '', email: '', tax_id: '', category: '', payment_terms: '', currency: 'CNY', credit_limit: 0, notes: '' }
}

async function load(p = 1) {
  page.value = p
  loading.value = true
  try {
    const data = await api.get('/suppliers', {
      page: page.value, page_size: pageSize.value, keyword: filters.keyword || undefined
    })
    rows.value = data.items
    total.value = data.total
  } catch (e) { ElMessage.error(e.message) } finally { loading.value = false }
}

function onSearch(q) { filters.keyword = q.keyword || ''; load(1) }
function onSizeChange(s) { pageSize.value = s; load(1) }

function openCreate() {
  editingId.value = null
  Object.assign(form, emptyForm())
  drawerVisible.value = true
}

function openEdit(row) {
  editingId.value = row.id
  Object.assign(form, {
    code: row.code, name: row.name, short_name: row.short_name || '', contact_person: row.contact_person || '',
    phone: row.phone || '', email: row.email || '', tax_id: row.tax_id || '', category: row.category || '',
    payment_terms: row.payment_terms || '', currency: row.currency || 'CNY', credit_limit: Number(row.credit_limit) || 0,
    notes: row.notes || ''
  })
  drawerVisible.value = true
}

async function save() {
  await formRef.value.validate()
  saving.value = true
  try {
    const payload = { ...form, credit_limit: Number(form.credit_limit) || 0 }
    if (editingId.value) await api.put(`/suppliers/${editingId.value}`, payload)
    else await api.post('/suppliers', payload)
    ElMessage.success('保存成功')
    drawerVisible.value = false
    load(page.value)
  } catch (e) { ElMessage.error(e.message) } finally { saving.value = false }
}

async function remove(row) {
  try { await ElMessageBox.confirm(`确认删除供应商「${row.name}」吗？`, '提示', { type: 'warning' }) } catch (e) { return }
  try {
    await api.del(`/suppliers/${row.id}`)
    ElMessage.success('已删除')
    load(rows.value.length === 1 && page.value > 1 ? page.value - 1 : page.value)
  } catch (e) { ElMessage.error(e.message) }
}

onMounted(() => load(1))
</script>