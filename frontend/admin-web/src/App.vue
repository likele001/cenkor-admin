<script setup lang="ts">
import { RouterView } from 'vue-router'
import ConfirmModal from '@/components/ConfirmModal.vue'
</script>

<template>
  <RouterView />
  <!-- 全局 ConfirmModal 单例：撑起静态 confirm({...}) 弹窗 -->
  <ConfirmModal :open="false" title="" message="" />
</template>
