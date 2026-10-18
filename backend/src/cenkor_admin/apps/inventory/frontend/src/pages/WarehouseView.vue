<template>
  <PageShell title="仓库" subtitle="仓库基础资料">
    <template #actions>
      <el-button type="primary" :icon="Plus" @click="openCreate">新建</el-button>
    </template>

    <SearchBar :fields="searchFields" @search="onSearch" />

    <DataTable :data="rows" :columns="columns" :total="total" :page="page" :page-size="pageSize"
               :loading="loading" @update:page="load" @update:pageSize="onSizeChange">
      <template #operation>
        <el-table-column label="操作" width="140" align="center" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" @click="openEdit(row)">编辑</el-button>
            <el-button link type="danger" @click="onDelete(row)">删除</el-button>
          </template>
        </el-table-column>
      </template>
    </DataTable>

    <FormDrawer v-model="drawerVisible" :title="drawerTitle" :saving="saving" @save="onSave">
      <el-form ref="formRef" :model="form" :rules="rules" label-width="110px">
        <el-form-item label="仓库编码" prop="code">
          <el-input v-model="form.code" />
        </el-form-item>
        <el-form-item label="仓库名称" prop="name">
          <el-input v-model="form.name" />
        </el-form-item>
        <el-form-item label="仓库类型" prop="type">
          <el-select v-model="form.type" placeholder="请选择" clearable style="width: 200px">
            <el-option label="成品仓" value="成品仓" />
            <el-option label="原料仓" value="原料仓" />
            <el-option label="半成品仓" value="半成品仓" />
          </el-select>
        </el-form-item>
        <el-form-item label="是否启用" prop="enable">
          <el-switch v-model="form.enable" />
        </el-form-item>
        <el-form-item label="备注" prop="remark">
          <el-input v-model="form.remark" type="textarea" :rows="3" />
        </el-form-item>
      </el-form>
    </FormDrawer>
  </PageShell>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Plus } from '@element-plus/icons-vue'
import PageShell from '../components/PageShell.vue'
import SearchBar from '../components/SearchBar.vue'
import DataTable from '../components/DataTable.vue'
import FormDrawer from '../components/FormDrawer.vue'
import { api, fmtMoney, fmtDate } from '../api'

const RES = '/warehouse'
const rows = ref([])
const total = ref(0)
const page = ref(1)
const pageSize = ref(20)
const loading = ref(false)
const saving = ref(false)
const drawerVisible = ref(false)
const drawerTitle = ref("新建")
const formRef = ref(null)
const editingId = ref(null)

const filters = reactive({})

const searchFields = [
  { prop: 'code', label: '仓库编码', type: 'input', placeholder: '请输入仓库编码' },
  { prop: 'name', label: '仓库名称', type: 'input', placeholder: '请输入仓库名称' },
  { prop: 'type', label: '仓库类型', type: 'select', options: [{ value: '成品仓', label: '成品仓' }, { value: '原料仓', label: '原料仓' }, { value: '半成品仓', label: '半成品仓' }] },
]

const columns = [
  { prop: "code", label: "仓库编码", width: 120 },
  { prop: "name", label: "仓库名称", width: 120 },
  { prop: "type", label: "仓库类型", width: 110, formatter: (r) => ({'成品仓': '成品仓', '原料仓': '原料仓', '半成品仓': '半成品仓'}[r.type] || r.type || "—") },
  { prop: "enable", label: "是否启用", width: 90, formatter: (r) => (r.enable ? "是" : "否") },
  { prop: "remark", label: "备注", minWidth: 160, formatter: (r) => { const v = r.remark; return v && v.length > 30 ? v.slice(0, 30) + "…" : (v || "—") } },
]

function emptyForm() {
  return { code: null, name: null, type: null, enable: true, remark: null }
}
const form = reactive(emptyForm())

const rules = {
  code: [{ required: true, message: '仓库编码必填', trigger: 'blur' }],
  name: [{ required: true, message: '仓库名称必填', trigger: 'blur' }],
}

async function load(p = 1) {
  page.value = p
  loading.value = true
  try {
    const params = { page: page.value, page_size: pageSize.value }
    for (const [k, v] of Object.entries(filters)) {
      if (v !== '' && v !== null && v !== undefined) params[k] = v
    }
    const data = await api.get(RES, params)
    rows.value = data.items || []
    total.value = data.total || 0
  } catch (e) { ElMessage.error(e.message) } finally { loading.value = false }
}

function onSearch(q) {
  Object.keys(filters).forEach((k) => delete filters[k])
  Object.assign(filters, q || {})
  load(1)
}
function onSizeChange(s) { pageSize.value = s; load(1) }

function openCreate() {
  editingId.value = null
  Object.assign(form, emptyForm())
  drawerTitle.value = "新建"
  drawerVisible.value = true
}
function openEdit(row) {
  editingId.value = row.id
  Object.assign(form, emptyForm())
  Object.assign(form, row)
  drawerTitle.value = "编辑"
  drawerVisible.value = true
}

async function onSave() {
  if (formRef.value) {
    const ok = await formRef.value.validate().catch(() => false)
    if (!ok) return
  }
  saving.value = true
  try {
    if (editingId.value) {
      await api.patch(RES + "/" + editingId.value, form)
      ElMessage.success('已更新')
    } else {
      await api.post(RES, form)
      ElMessage.success('已创建')
    }
    drawerVisible.value = false
    load(editingId.value ? page.value : 1)
  } catch (e) { ElMessage.error(e.message) } finally { saving.value = false }
}

function onDelete(row) {
  ElMessageBox.confirm('确认删除该记录？', '提示', { type: 'warning' })
    .then(async () => {
      try {
        await api.del(RES + "/" + row.id)
        ElMessage.success('已删除')
        load(page.value)
      } catch (e) { ElMessage.error(e.message) }
    })
    .catch(() => {})
}

onMounted(() => load(1))
</script>

<style scoped></style>
