<template>
  <div class="erp-datatable">
    <el-table
      :data="data"
      v-loading="loading"
      border
      stripe
      size="default"
      :row-key="rowKey"
      :height="height"
      @selection-change="(rows) => $emit('selection-change', rows)"
      @row-dblclick="(row) => $emit('row-dblclick', row)"
    >
      <el-table-column v-if="selectable" type="selection" width="46" align="center" />
      <el-table-column
        v-for="col in columns"
        :key="col.prop || col.slot"
        :prop="col.prop"
        :label="col.label"
        :width="col.width"
        :min-width="col.minWidth"
        :fixed="col.fixed"
        :align="col.align || 'left'"
        :sortable="col.sortable || false"
        show-overflow-tooltip
      >
        <template #default="{ row }">
          <!-- 自定义 slot 单元格 -->
          <slot v-if="col.slot" :name="col.slot" :row="row" />
          <!-- tag 状态显示 -->
          <el-tag v-else-if="col.tag" :type="col.tag.type(row, row[col.prop]) || 'info'" size="small">
            {{ col.tag.text(row, row[col.prop]) ?? row[col.prop] }}
          </el-tag>
          <!-- formatter -->
          <template v-else-if="col.formatter">{{ col.formatter(row, row[col.prop]) }}</template>
          <template v-else>{{ row[col.prop] ?? '—' }}</template>
        </template>
      </el-table-column>
      <slot name="operation" />
    </el-table>

    <div v-if="showPagination" class="erp-datatable__footer">
      <el-pagination
        background
        layout="total, sizes, prev, pager, next, jumper"
        :total="total"
        :current-page="page"
        :page-size="pageSize"
        :page-sizes="[10, 20, 50, 100]"
        @current-change="(p) => $emit('update:page', p)"
        @size-change="(s) => $emit('update:pageSize', s)"
      />
    </div>
  </div>
</template>

<script setup>
import { ElTable, ElTableColumn, ElPagination, ElTag } from 'element-plus'

defineProps({
  data: { type: Array, default: () => [] },
  columns: { type: Array, default: () => [] },
  total: { type: Number, default: 0 },
  page: { type: Number, default: 1 },
  pageSize: { type: Number, default: 20 },
  loading: { type: Boolean, default: false },
  showPagination: { type: Boolean, default: true },
  selectable: { type: Boolean, default: false },
  rowKey: { type: [String, Function], default: 'id' },
  height: { type: [Number, String], default: '' }
})

defineEmits(['update:page', 'update:pageSize', 'selection-change', 'row-dblclick'])
</script>

<style scoped>
.erp-datatable__footer {
  display: flex;
  justify-content: flex-end;
  margin-top: 14px;
}
</style>