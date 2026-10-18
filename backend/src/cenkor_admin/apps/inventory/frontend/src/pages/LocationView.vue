<template>
  <PageShell title="库位" subtitle="仓库下的库位">
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
        <el-form-item label="库位编码" prop="code">
          <el-input v-model="form.code" />
        </el-form-item>
        <el-form-item label="库位名称" prop="name">
          <el-input v-model="form.name" />
        </el-form-item>
        <!-- TODO(business): fk 远程下拉为 P1，先用数字输入 -->
        <el-form-item label="所属仓库" prop="warehouse_id">
          <el-input-number v-model="form.warehouse_id" :min="0" style="width: 200px" />
        </el-form-item>
        <el-form-item label="容量" prop="capacity">
          <el-input-number v-model="form.capacity" :precision="2" :step="0.01" style="width: 200px" />
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

const RES = '/location'
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
  { prop: 'code', label: '库位编码', type: 'input', placeholder: '请输入库位编码' },
]

const columns = [
  { prop: "code", label: "库位编码", width: 120 },
  { prop: "name", label: "库位名称", width: 120 },
  { prop: "warehouse_id", label: "所属仓库", width: 120 },
  { prop: "capacity", label: "容量", width: 120, formatter: (r) => fmtMoney(r.capacity) },
]

function emptyForm() {
  return { code: null, name: null, warehouse_id: null, capacity: null }
}
const form = reactive(emptyForm())

const rules = {
  code: [{ required: true, message: '库位编码必填', trigger: 'blur' }],
  name: [{ required: true, message: '库位名称必填', trigger: 'blur' }],
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
