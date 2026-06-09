<script setup lang="ts">
withDefaults(defineProps<{
  title?: string
  description?: string
  actionLabel?: string
  icon?: string
}>(), {
  title: '暂无数据',
  description: '',
  icon: '📦',
})

defineEmits<{ action: [] }>()
</script>

<template>
  <div class="px-6 py-12 text-center">
    <div class="inline-flex items-center justify-center w-16 h-16 rounded-2xl bg-ink-100 text-3xl mb-4">
      {{ icon }}
    </div>
    <h3 class="text-base font-semibold text-ink-900">{{ title }}</h3>
    <p v-if="description" class="mt-1.5 text-sm text-ink-500 max-w-sm mx-auto">{{ description }}</p>
    <button
      v-if="actionLabel"
      type="button"
      class="mt-5 btn-primary"
      @click="$emit('action')"
    >
      {{ actionLabel }}
    </button>
    <slot />
  </div>
</template>
