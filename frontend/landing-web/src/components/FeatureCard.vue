<template>
  <div class="feature-card">
    <div class="icon-wrapper" :style="{ background: iconBg }">
      <span class="icon">{{ icon }}</span>
    </div>
    <h3>{{ title }}</h3>
    <p>{{ description }}</p>
    <ul v-if="features.length" class="features-list">
      <li v-for="(feature, index) in features" :key="index">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <polyline points="20 6 9 17 4 12"></polyline>
        </svg>
        {{ feature }}
      </li>
    </ul>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'

const props = withDefaults(defineProps<{
  icon: string
  title: string
  description: string
  features?: string[]
  color?: string
}>(), {
  features: () => [],
  color: '#3b82f6'
})

const iconBg = computed(() => `rgba(${hexToRgb(props.color)}, 0.1)`)

function hexToRgb(hex: string): string {
  const result = /^#?([a-f\d]{2})([a-f\d]{2})([a-f\d]{2})$/i.exec(hex)
  if (!result) return '59, 130, 246'
  return `${parseInt(result[1], 16)}, ${parseInt(result[2], 16)}, ${parseInt(result[3], 16)}`
}
</script>

<style lang="scss" scoped>
.feature-card {
  background: $bg-white;
  border-radius: $radius-lg;
  padding: $spacing-xl;
  transition: all $transition-normal;
  border: 1px solid $border-light;

  &:hover {
    transform: translateY(-4px);
    box-shadow: $shadow-lg;
    border-color: transparent;
  }

  .icon-wrapper {
    width: 56px;
    height: 56px;
    border-radius: $radius-md;
    display: flex;
    align-items: center;
    justify-content: center;
    margin-bottom: $spacing-lg;

    .icon {
      font-size: 28px;
    }
  }

  h3 {
    font-size: 1.25rem;
    font-weight: 600;
    color: $text-primary;
    margin-bottom: $spacing-sm;
  }

  p {
    color: $text-secondary;
    font-size: 0.95rem;
    line-height: 1.6;
    margin-bottom: $spacing-md;
  }

  .features-list {
    list-style: none;
    padding: 0;
    margin: 0;

    li {
      display: flex;
      align-items: center;
      gap: $spacing-sm;
      color: $text-secondary;
      font-size: 0.9rem;
      margin-bottom: $spacing-sm;

      svg {
        width: 16px;
        height: 16px;
        color: $success;
        flex-shrink: 0;
      }
    }
  }
}
</style>
