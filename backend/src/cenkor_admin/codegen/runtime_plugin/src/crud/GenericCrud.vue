<template>
  <PageShell :title="entity.title" :subtitle="entity.subtitle || ''">
    <template #actions>
      <el-button type="primary" :icon="Plus" @click="openCreate">新建</el-button>
    </template>

    <SearchBar v-if="searchFields.length" :fields="searchFields" @search="onSearch" />

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
            <el-button link type="primary" @click="openEdit(row)">编辑</el-button>
            <el-button link type="danger" @click="onDelete(row)">删除</el-button>
          </template>
        </el-table-column>
      </template>
    </DataTable>

    <FormDrawer v-model="drawerVisible" :title="drawerTitle" :saving="saving" @save="onSave">
      <el-form ref="formRef" :model="form" :rules="rules" label-width="120px">
        <el-form-item v-for="f in entity.fields" :key="f.name" :label="f.label" :prop="f.name">
          <el-input v-if="f.type === 'string'" v-model="form[f.name]" />
          <el-input v-else-if="f.type === 'text'" v-model="form[f.name]" type="textarea" :rows="3" />
          <el-input
            v-else-if="f.type === 'json'"
            v-model="form[f.name + '_text']"
            type="textarea"
            :rows="3"
            placeholder='JSON，如 {"k": "v"}'
          />
          <el-input-number
            v-else-if="f.type === 'int' || f.type === 'fk'"
            v-model="form[f.name]"
            :min="0"
            style="width: 200px"
          />
          <el-input-number
            v-else-if="f.type === 'decimal'"
            v-model="form[f.name]"
            :precision="f.scale || 2"
            :step="0.01"
            style="width: 200px"
          />
          <el-switch v-else-if="f.type === 'bool'" v-model="form[f.name]" />
          <el-select
            v-else-if="f.type === 'enum'"
            v-model="form[f.name]"
            placeholder="请选择"
            clearable
            style="width: 200px"
          >
            <el-option v-for="c in f.choices || []" :key="c" :label="c" :value="c" />
          </el-select>
          <el-date-picker
            v-else-if="f.type === 'date'"
            v-model="form[f.name]"
            type="date"
            value-format="YYYY-MM-DD"
            style="width: 200px"
          />
          <el-date-picker
            v-else-if="f.type === 'datetime'"
            v-model="form[f.name]"
            type="datetime"
            value-format="YYYY-MM-DD HH:mm:ss"
            style="width: 220px"
          />
          <el-input v-else v-model="form[f.name]" />
        </el-form-item>
      </el-form>
    </FormDrawer>
  </PageShell>
</template>

<script setup>
import { ref, reactive, computed, onMounted } from 'vue'
import { ElMessage, ElMessageBox, ElForm, ElFormItem, ElInput, ElInputNumber, ElSwitch, ElSelect, ElOption, ElDatePicker, ElButton, ElTableColumn } from 'element-plus'
import { Plus } from '@element-plus/icons-vue'
import PageShell from './PageShell.vue'
import SearchBar from './SearchBar.vue'
import DataTable from './DataTable.vue'
import FormDrawer from './FormDrawer.vue'
import { makeApi, fmtMoney, fmtDate } from './api'

const props = defineProps({
  appKey: { type: String, required: true },
  entity: { type: Object, required: true }
})

const entity = props.entity
const api = makeApi(props.appKey)
const RES = '/' + entity.key
const SELECT_TYPES = ['enum', 'date', 'datetime', 'int', 'decimal', 'fk']

const rows = ref([])
const total = ref(0)
const page = ref(1)
const pageSize = ref(20)
const loading = ref(false)
const saving = ref(false)
const drawerVisible = ref(false)
const drawerTitle = ref('新建')
const formRef = ref(null)
const editingId = ref(null)
const filters = reactive({})

const searchFields = computed(() =>
  entity.fields
    .filter((f) => f.search)
    .map((f) => {
      if (f.type === 'enum') {
        return { prop: f.name, label: f.label, type: 'select', options: (f.choices || []).map((c) => ({ value: c, label: c })) }
      }
      if (f.type === 'bool') {
        return { prop: f.name, label: f.label, type: 'select', options: [{ value: true, label: '是' }, { value: false, label: '否' }] }
      }
      return { prop: f.name, label: f.label, type: 'input', placeholder: `请输入${f.label}` }
    })
)

const columns = computed(() =>
  entity.fields
    .filter((f) => f.list)
    .map((f) => {
      const base = { prop: f.name, label: f.label }
      if (f.type === 'bool') return { ...base, width: 90, formatter: (r) => (r[f.name] ? '是' : '否') }
      if (f.type === 'enum') return { ...base, width: 110, formatter: (r) => r[f.name] || '—' }
      if (f.type === 'decimal') return { ...base, width: 120, formatter: (r) => fmtMoney(r[f.name]) }
      if (f.type === 'date' || f.type === 'datetime') return { ...base, width: 130, formatter: (r) => fmtDate(r[f.name]) }
      if (f.type === 'text') {
        return {
          ...base,
          minWidth: 160,
          formatter: (r) => {
            const v = r[f.name]
            return v && v.length > 30 ? v.slice(0, 30) + '…' : (v || '—')
          }
        }
      }
      return { ...base, width: 140 }
    })
)

const rules = computed(() => {
  const out = {}
  for (const f of entity.fields) {
    if (!f.required || f.type === 'bool') continue
    out[f.name] = [{ required: true, message: f.label + '必填', trigger: SELECT_TYPES.includes(f.type) ? 'change' : 'blur' }]
  }
  return out
})

function emptyForm() {
  const o = {}
  for (const f of entity.fields) {
    if (f.type === 'json') {
      o[f.name] = null
      o[f.name + '_text'] = ''
    } else if (f.default !== undefined && f.default !== null) {
      o[f.name] = f.default
    } else {
      o[f.name] = f.type === 'bool' ? false : null
    }
  }
  return o
}

const form = reactive(emptyForm())

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
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    loading.value = false
  }
}

function onSearch(q) {
  Object.keys(filters).forEach((k) => delete filters[k])
  Object.assign(filters, q || {})
  load(1)
}

function onSizeChange(s) {
  pageSize.value = s
  load(1)
}

function openCreate() {
  editingId.value = null
  Object.assign(form, emptyForm())
  drawerTitle.value = '新建'
  drawerVisible.value = true
}

function openEdit(row) {
  editingId.value = row.id
  Object.assign(form, emptyForm())
  Object.assign(form, row)
  for (const f of entity.fields) {
    if (f.type !== 'json') continue
    const v = row[f.name]
    form[f.name + '_text'] = v === null || v === undefined ? '' : JSON.stringify(v)
  }
  drawerTitle.value = '编辑'
  drawerVisible.value = true
}

async function onSave() {
  if (formRef.value) {
    const ok = await formRef.value.validate().catch(() => false)
    if (!ok) return
  }
  // json 字段：把文本缓冲区解析回对象
  const payload = { ...form }
  for (const f of entity.fields) {
    if (f.type !== 'json') continue
    const raw = form[f.name + '_text']
    delete payload[f.name + '_text']
    if (raw === '' || raw === null || raw === undefined) {
      payload[f.name] = null
    } else {
      try {
        payload[f.name] = JSON.parse(raw)
      } catch (e) {
        ElMessage.error(`${f.label} 不是合法 JSON`)
        return
      }
    }
  }
  saving.value = true
  try {
    if (editingId.value) {
      await api.patch(RES + '/' + editingId.value, payload)
      ElMessage.success('已更新')
    } else {
      await api.post(RES, payload)
      ElMessage.success('已创建')
    }
    drawerVisible.value = false
    load(editingId.value ? page.value : 1)
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    saving.value = false
  }
}

function onDelete(row) {
  ElMessageBox.confirm('确认删除该记录？', '提示', { type: 'warning' })
    .then(async () => {
      try {
        await api.del(RES + '/' + row.id)
        ElMessage.success('已删除')
        load(page.value)
      } catch (e) {
        ElMessage.error(e.message)
      }
    })
    .catch(() => {})
}

onMounted(() => load(1))
</script>

<style scoped></style>
