<script setup lang="ts">
import { useAuthStore } from '@/stores/auth'

const props = defineProps<{ code: string }>()
const auth = useAuthStore()
</script>

<template>
  <slot v-if="auth.hasPermission(code)" />
</template>
