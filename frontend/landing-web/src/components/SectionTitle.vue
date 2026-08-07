<template>
  <div class="section-title" :class="{ 'text-center': center }">
    <span v-if="tag" class="tag">{{ tag }}</span>
    <h2>{{ title }}</h2>
    <p v-if="description">{{ description }}</p>
  </div>
</template>

<script setup lang="ts">
defineProps<{
  title: string
  description?: string
  tag?: string
  center?: boolean
}>()
</script>

<style lang="scss" scoped>
.section-title {
  margin-bottom: $spacing-3xl;

  &.text-center {
    text-align: center;
  }

  .tag {
    display: inline-block;
    padding: 6px 16px;
    background: rgba($primary, 0.1);
    color: $primary;
    font-size: 13px;
    font-weight: 600;
    border-radius: $radius-full;
    margin-bottom: $spacing-md;
    text-transform: uppercase;
    letter-spacing: 0.5px;
  }

  h2 {
    font-size: 2.5rem;
    font-weight: 700;
    color: $text-primary;
    margin-bottom: $spacing-md;
    line-height: 1.2;

    @include mobile {
      font-size: 2rem;
    }
  }

  p {
    font-size: 1.125rem;
    color: $text-secondary;
    max-width: 600px;
    margin: 0 auto;

    @include mobile {
      font-size: 1rem;
    }
  }

  &:not(.text-center) p {
    margin-left: 0;
  }
}
</style>
