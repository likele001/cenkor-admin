<script setup lang="ts">
withDefaults(defineProps<{
  rows?: number
  variant?: 'card' | 'list' | 'table'
}>(), {
  rows: 4,
  variant: 'list',
})
</script>

<template>
  <div class="space-y-3 animate-pulse">
    <template v-if="variant === 'table'">
      <div class="card overflow-hidden p-0">
        <div class="h-10 bg-ink-100 border-b border-ink-200" />
        <div v-for="i in rows" :key="i" class="px-4 py-3 border-b border-ink-100 last:border-0 flex items-center gap-4">
          <div class="h-3 w-1/4 bg-ink-200 rounded" />
          <div class="h-3 w-1/5 bg-ink-200 rounded" />
          <div class="h-3 w-1/6 bg-ink-200 rounded" />
          <div class="h-3 w-1/12 bg-ink-200 rounded ml-auto" />
        </div>
      </div>
    </template>
    <template v-else-if="variant === 'card'">
      <div class="grid md:grid-cols-2 gap-4">
        <div v-for="i in rows" :key="i" class="card space-y-2">
          <div class="h-4 w-1/3 bg-ink-200 rounded" />
          <div class="h-3 w-full bg-ink-200 rounded" />
          <div class="h-3 w-2/3 bg-ink-200 rounded" />
        </div>
      </div>
    </template>
    <template v-else>
      <div v-for="i in rows" :key="i" class="card space-y-2">
        <div class="h-4 w-1/3 bg-ink-200 rounded" />
        <div class="h-3 w-full bg-ink-200 rounded" />
        <div class="h-3 w-2/3 bg-ink-200 rounded" />
      </div>
    </template>
  </div>
</template>
