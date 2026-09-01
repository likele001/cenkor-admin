<template>
  <el-drawer
    :model-value="modelValue"
    :title="title"
    :size="width"
    :destroy-on-close="destroyOnClose"
    :modal="modal"
    :with-header="true"
    @update:model-value="(v) => $emit('update:modelValue', v)"
    @close="onClose"
  >
    <div class="erp-drawer__body" v-loading="loading">
      <slot />
    </div>
    <template #footer>
      <slot name="footer">
        <div class="erp-drawer__footer">
          <el-button @click="$emit('update:modelValue', false)">取消</el-button>
          <el-button type="primary" :loading="saving" @click="$emit('save')">
            {{ saveText }}
          </el-button>
        </div>
      </slot>
    </template>
  </el-drawer>
</template>

<script setup>
import { ElDrawer, ElButton } from 'element-plus'

defineProps({
  modelValue: { type: Boolean, default: false },
  title: { type: String, default: '' },
  width: { type: String, default: '560px' },
  loading: { type: Boolean, default: false },
  saving: { type: Boolean, default: false },
  saveText: { type: String, default: '保存' },
  destroyOnClose: { type: Boolean, default: true },
  modal: { type: Boolean, default: true }
})

const emit = defineEmits(['update:modelValue', 'save', 'closed'])

function onClose() {
  emit('closed')
}
</script>

<style scoped>
.erp-drawer__body {
  min-height: 100px;
}
.erp-drawer__footer {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
}
</style>