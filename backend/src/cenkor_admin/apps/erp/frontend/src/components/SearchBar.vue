<template>
  <div class="erp-searchbar">
    <el-form :inline="true" :model="form" @submit.prevent>
      <el-form-item v-for="f in fields" :key="f.prop" :label="f.label">
        <el-input
          v-if="f.type === 'input'"
          v-model="form[f.prop]"
          :placeholder="f.placeholder || `请输入${f.label}`"
          clearable
          style="width: 200px"
          @keyup.enter="onSearch"
        />
        <el-select
          v-else-if="f.type === 'select'"
          v-model="form[f.prop]"
          :placeholder="f.placeholder || `请选择${f.label}`"
          clearable
          style="width: 160px"
        >
          <el-option v-for="o in f.options" :key="o.value" :label="o.label" :value="o.value" />
        </el-select>
        <el-date-picker
          v-else-if="f.type === 'daterange' || f.type === 'date'"
          v-model="form[f.prop]"
          :type="f.type === 'daterange' ? 'daterange' : 'date'"
          value-format="YYYY-MM-DD"
          range-separator="至"
          start-placeholder="开始日期"
          end-placeholder="结束日期"
          style="width: 240px"
        />
      </el-form-item>
      <el-form-item>
        <el-button type="primary" :icon="Search" @click="onSearch">查询</el-button>
        <el-button :icon="Refresh" @click="onReset">重置</el-button>
      </el-form-item>
    </el-form>
  </div>
</template>

<script setup>
import { reactive } from 'vue'
import { ElForm, ElFormItem, ElInput, ElSelect, ElOption, ElDatePicker, ElButton } from 'element-plus'
import { Search, Refresh } from '@element-plus/icons-vue'

const props = defineProps({
  fields: { type: Array, default: () => [] }
})
const emit = defineEmits(['search'])

// fields: [{prop, label, type:'input'|'select'|'date'|'daterange', options, placeholder}]
const form = reactive({})
props.fields.forEach((f) => {
  form[f.prop] = f.default !== undefined ? f.default : ''
})

function onSearch() {
  const q = {}
  for (const f of props.fields) {
    if (f.type === 'daterange' && Array.isArray(form[f.prop]) && form[f.prop].length) {
      q[`${f.prop}_from`] = form[f.prop][0]
      q[`${f.prop}_to`] = form[f.prop][1]
    } else if (form[f.prop] !== '' && form[f.prop] != null) {
      q[f.prop] = form[f.prop]
    }
  }
  emit('search', q)
}

function onReset() {
  for (const f of props.fields) form[f.prop] = f.default !== undefined ? f.default : ''
  emit('search', {})
}
</script>