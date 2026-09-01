<template>
  <el-config-provider :locale="zhCn">
    <div class="erp-page">
      <div v-if="title || $slots.actions" class="erp-page__header">
        <div class="erp-page__title">
          <h2>{{ title }}</h2>
          <span v-if="subtitle" class="erp-page__subtitle">{{ subtitle }}</span>
        </div>
        <div class="erp-page__actions">
          <slot name="actions" />
        </div>
      </div>
      <div class="erp-page__body">
        <slot />
      </div>
    </div>
  </el-config-provider>
</template>

<script setup>
import { ElConfigProvider } from 'element-plus'
import zhCn from 'element-plus/es/locale/lang/zh-cn'

defineProps({
  title: { type: String, default: '' },
  subtitle: { type: String, default: '' }
})
</script>

<style scoped>
.erp-page {
  background: #fff;
  border-radius: 8px;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.06);
  padding: 18px 20px 20px;
}
.erp-page__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 16px;
  flex-wrap: wrap;
  gap: 8px;
}
.erp-page__title h2 {
  margin: 0;
  font-size: 18px;
  color: #1f2937;
  font-weight: 600;
}
.erp-page__subtitle {
  margin-left: 8px;
  font-size: 13px;
  color: #9ca3af;
}
.erp-page__actions {
  display: flex;
  gap: 8px;
  align-items: center;
}
.erp-page__body {
  min-height: 200px;
}
</style>