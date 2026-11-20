<script setup lang="ts">
import { RouterView } from 'vue-router'
import ConfirmModal from '@/components/ConfirmModal.vue'
import LicenseRequiredBanner from '@/components/LicenseRequiredBanner.vue'
</script>

<template>
  <RouterView />
  <!-- 全局 402 提示：付费应用未授权/失效时给出去应用市场的入口 -->
  <LicenseRequiredBanner />
  <!-- 全局 ConfirmModal 单例：撑起静态 confirm({...}) 弹窗 -->
  <ConfirmModal :open="false" title="" message="" />
</template>
