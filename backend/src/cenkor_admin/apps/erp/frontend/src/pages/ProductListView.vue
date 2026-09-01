<template>
  <PageShell title="商品" subtitle="商品主数据 · 分类">
    <template #actions>
      <el-button type="primary" :icon="Plus" @click="openCreate">新增商品</el-button>
    </template>

    <SearchBar :fields="searchFields" @search="onSearch" />
    <div class="filter-row">
      <el-select v-model="filters.category_id" placeholder="分类" clearable style="width: 160px" @change="load(1)">
        <el-option v-for="c in categories" :key="c.id" :label="c.name" :value="c.id" />
      </el-select>
    </div>

    <DataTable
      :data="rows" :columns="columns" :total="total" :page="page"
      :page-size="pageSize" :loading="loading"
      @update:page="load" @update:pageSize="onSizeChange"
    >
      <template #operation>
        <el-table-column label="操作" width="150" align="center" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" @click="openEdit(row.id)">编辑</el-button>
            <el-button link type="danger" @click="remove(row)">删除</el-button>
          </template>
        </el-table-column>
      </template>
    </DataTable>

    <FormDrawer v-model="drawerVisible" :title="drawerTitle" width="620px" :saving="saving" @save="save">
      <el-form ref="formRef" :model="form" :rules="rules" label-width="110px">
        <el-row :gutter="16">
          <el-col :span="12"><el-form-item label="商品编号"><el-input v-model="form.code" placeholder="留空自动生成" /></el-form-item></el-col>
          <el-col :span="12"><el-form-item label="商品名称" prop="name"><el-input v-model="form.name" /></el-form-item></el-col>
          <el-col :span="12"><el-form-item label="规格型号"><el-input v-model="form.model" /></el-form-item></el-col>
          <el-col :span="12"><el-form-item label="分类">
            <el-select v-model="form.category_id" clearable style="width: 100%">
              <el-option v-for="c in categories" :key="c.id" :label="c.name" :value="c.id" />
            </el-select>
          </el-form-item></el-col>
          <el-col :span="12"><el-form-item label="单位"><el-input v-model="form.unit" placeholder="如：件/kg/米" /></el-form-item></el-col>
          <el-col :span="12"><el-form-item label="条码"><el-input v-model="form.barcode" /></el-form-item></el-col>
          <el-col :span="12"><el-form-item label="售价"><el-input-number v-model="form.sale_price" :min="0" :precision="2" style="width:100%" /></el-form-item></el-col>
          <el-col :span="12"><el-form-item label="采购价"><el-input-number v-model="form.purchase_price" :min="0" :precision="2" style="width:100%" /></el-form-item></el-col>
          <el-col :span="12"><el-form-item label="成本价"><el-input-number v-model="form.cost_price" :min="0" :precision="2" style="width:100%" /></el-form-item></el-col>
          <el-col :span="12"><el-form-item label="最低库存"><el-input-number v-model="form.min_stock" :min="0" style="width:100%" /></el-form-item></el-col>
          <el-col :span="12"><el-form-item label="税率(%)"><el-input-number v-model="form.tax_rate" :min="0" :max="100" :precision="2" style="width:100%" /></el-form-item></el-col>
          <el-col :span="24"><el-form-item label="备注"><el-input v-model="form.remarks" type="textarea" :rows="2" /></el-form-item></el-col>
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
import { api, fmtMoney, statusLabel, statusTagType } from '../api'

const rows = ref([])
const categories = ref([])
const total = ref(0)
const page = ref(1)
const pageSize = ref(20)
const loading = ref(false)
const filters = reactive({ keyword: '', category_id: '' })
const drawerVisible = ref(false)
const saving = ref(false)
const editingId = ref(null)
const formRef = ref()

const searchFields = [
  { prop: 'keyword', label: '关键词', type: 'input', placeholder: '名称/编号/型号' }
]

const columns = [
  { prop: 'code', label: '编号', width: 120 },
  { prop: 'name', label: '商品名称', minWidth: 180 },
  { prop: 'model', label: '型号', width: 120 },
  { prop: 'unit', label: '单位', width: 80 },
  { prop: 'sale_price', label: '售价', width: 110, formatter: (r) => fmtMoney(r.sale_price) },
  { prop: 'status', label: '状态', width: 90, tag: { text: (r) => statusLabel(r.status), type: (r) => statusTagType(r.status) } }
]

const drawerTitle = computed(() => (editingId.value ? '编辑商品' : '新增商品'))
const form = reactive({})
const rules = { name: [{ required: true, message: '请输入商品名称', trigger: 'blur' }] }

function emptyForm() {
  return { code: '', name: '', model: '', category_id: null, unit: '件', barcode: '', sale_price: 0, purchase_price: 0, cost_price: 0, min_stock: 0, tax_rate: 0, remarks: '' }
}

async function loadCategories() {
  try { categories.value = await api.get('/product-categories') } catch (e) {}
}

async function load(p = 1) {
  page.value = p
  loading.value = true
  try {
    const data = await api.get('/products', {
      page: page.value, page_size: pageSize.value,
      keyword: filters.keyword || undefined,
      category_id: filters.category_id || undefined
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

async function openEdit(id) {
  try {
    const data = await api.get(`/products/${id}`)
    editingId.value = id
    Object.assign(form, {
      code: data.code, name: data.name, model: data.model || '', category_id: data.category_id || null,
      unit: data.unit || '件', barcode: data.barcode || '', sale_price: Number(data.sale_price) || 0,
      purchase_price: Number(data.purchase_price) || 0, cost_price: Number(data.cost_price) || 0,
      min_stock: Number(data.min_stock) || 0, tax_rate: Number(data.tax_rate) || 0, remarks: data.remarks || ''
    })
    drawerVisible.value = true
  } catch (e) { ElMessage.error(e.message) }
}

async function save() {
  await formRef.value.validate()
  saving.value = true
  try {
    const payload = {
      ...form, category_id: form.category_id || null,
      sale_price: Number(form.sale_price) || 0, purchase_price: Number(form.purchase_price) || 0,
      cost_price: Number(form.cost_price) || 0, min_stock: Number(form.min_stock) || 0,
      tax_rate: Number(form.tax_rate) || 0
    }
    if (editingId.value) await api.put(`/products/${editingId.value}`, payload)
    else await api.post('/products', payload)
    ElMessage.success('保存成功')
    drawerVisible.value = false
    load(page.value)
  } catch (e) { ElMessage.error(e.message) } finally { saving.value = false }
}

async function remove(row) {
  try { await ElMessageBox.confirm(`确认删除商品「${row.name}」吗？`, '提示', { type: 'warning' }) } catch (e) { return }
  try {
    await api.del(`/products/${row.id}`)
    ElMessage.success('已删除')
    load(rows.value.length === 1 && page.value > 1 ? page.value - 1 : page.value)
  } catch (e) { ElMessage.error(e.message) }
}

onMounted(async () => {
  await loadCategories()
  load(1)
})
</script>

<style scoped>
.filter-row { margin-bottom: 12px; display: flex; gap: 8px; }
</style>