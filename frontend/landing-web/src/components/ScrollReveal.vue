<template>
  <div ref="element" class="scroll-reveal" :class="[animation, { visible: isVisible }]" :style="delayStyle">
    <slot></slot>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'

const props = withDefaults(defineProps<{
  animation?: 'fade-up' | 'fade-left' | 'fade-right' | 'scale'
  delay?: number
}>(), {
  animation: 'fade-up',
  delay: 0
})

const element = ref<HTMLElement | null>(null)
const isVisible = ref(false)
let observer: IntersectionObserver | null = null

const delayStyle = computed(() => {
  return props.delay > 0 ? { transitionDelay: `${props.delay}ms` } : {}
})

onMounted(() => {
  observer = new IntersectionObserver(
    (entries) => {
      entries.forEach((entry) => {
        if (entry.isIntersecting) {
          isVisible.value = true
          observer?.unobserve(entry.target)
        }
      })
    },
    { threshold: 0.1 }
  )

  if (element.value) {
    observer.observe(element.value)
  }
})

onUnmounted(() => {
  observer?.disconnect()
})
</script>

<style lang="scss" scoped>
.scroll-reveal {
  opacity: 0;
  transition: opacity 0.6s ease, transform 0.6s ease;

  &.fade-up {
    transform: translateY(30px);

    &.visible {
      opacity: 1;
      transform: translateY(0);
    }
  }

  &.fade-left {
    transform: translateX(-30px);

    &.visible {
      opacity: 1;
      transform: translateX(0);
    }
  }

  &.fade-right {
    transform: translateX(30px);

    &.visible {
      opacity: 1;
      transform: translateX(0);
    }
  }

  &.scale {
    transform: scale(0.9);

    &.visible {
      opacity: 1;
      transform: scale(1);
    }
  }
}
</style>
