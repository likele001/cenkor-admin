<script setup lang="ts">
import { useI18n } from 'vue-i18n'
const { t } = useI18n()
</script>

<template>
  <div class="card text-center py-16">
    <h1 class="text-4xl font-semibold text-ink-900">403</h1>
    <p class="mt-2 text-ink-500">{{ t('forbidden.您没有权_1x56r3') }}</p>
    <router-link to="/" class="btn-primary inline-block mt-6">{{ t('notFound.返回首页_iijhd5') }}</router-link>
  </div>
</template>