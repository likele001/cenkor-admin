<template>
  <nav class="navbar" :class="{ scrolled: isScrolled }">
    <div class="container">
      <div class="navbar-content">
        <router-link to="/" class="logo">
          <div class="logo-icon">
            <svg viewBox="0 0 32 32" fill="none">
              <rect width="32" height="32" rx="6" fill="#10b981"/>
              <rect x="7" y="7" width="5" height="5" rx="1.5" fill="white"/>
              <rect x="13.5" y="7" width="5" height="5" rx="1.5" fill="white" opacity="0.55"/>
              <rect x="20" y="7" width="5" height="5" rx="1.5" fill="white" opacity="0.8"/>
              <rect x="7" y="13.5" width="5" height="5" rx="1.5" fill="white" opacity="0.8"/>
              <rect x="13.5" y="13.5" width="5" height="5" rx="1.5" fill="white"/>
              <rect x="20" y="13.5" width="5" height="5" rx="1.5" fill="white" opacity="0.8"/>
              <rect x="7" y="20" width="5" height="5" rx="1.5" fill="white" opacity="0.55"/>
              <rect x="13.5" y="20" width="5" height="5" rx="1.5" fill="white" opacity="0.8"/>
              <rect x="20" y="20" width="5" height="5" rx="1.5" fill="white"/>
            </svg>
          </div>
          <span class="logo-text">辰科 Cenkor Admin</span>
        </router-link>

        <div class="nav-links" :class="{ active: mobileMenuOpen }">
          <a @click.prevent="navigate('/')">首页</a>
          <a @click.prevent="navigate('/features')">功能</a>
          <a @click.prevent="navigate('/advantages')">优势</a>
          <a @click.prevent="navigate('/deploy')">私有部署</a>
          <div class="dropdown">
            <span class="dropdown-trigger">文档</span>
            <div class="dropdown-menu">
              <a @click.prevent="navigate('/docs/guide')">使用指南</a>
              <a @click.prevent="navigate('/deploy')">部署教程</a>
            </div>
          </div>
        </div>

        <div class="nav-actions">
          <a :href="urls.contact" target="_blank" rel="noopener" class="btn btn-ghost btn-small">联系我们</a>
          <a :href="urls.github" target="_blank" rel="noopener" class="btn btn-primary btn-small">GitHub</a>
        </div>

        <button class="mobile-toggle" @click="toggleMobile" :class="{ active: mobileMenuOpen }">
          <span></span>
          <span></span>
          <span></span>
        </button>
      </div>
    </div>
  </nav>

  <div class="mobile-overlay" :class="{ active: mobileMenuOpen }" @click="closeMobile"></div>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted, nextTick } from 'vue'
import { useRouter } from 'vue-router'
import { SITE_URLS } from '@/config/site'

const urls = SITE_URLS
const router = useRouter()
const isScrolled = ref(false)
const mobileMenuOpen = ref(false)

const handleScroll = () => {
  isScrolled.value = window.scrollY > 20
}

const lockScroll = () => {
  document.documentElement.style.overflow = 'hidden'
  document.body.style.overflow = 'hidden'
}

const unlockScroll = () => {
  document.documentElement.style.overflow = ''
  document.body.style.overflow = ''
}

const toggleMobile = () => {
  mobileMenuOpen.value = !mobileMenuOpen.value
  if (mobileMenuOpen.value) {
    lockScroll()
  } else {
    unlockScroll()
  }
}

const closeMobile = () => {
  if (!mobileMenuOpen.value) return
  mobileMenuOpen.value = false
  unlockScroll()
}

const navigate = (path: string) => {
  closeMobile()
  nextTick(() => {
    router.push(path)
  })
}

onMounted(() => {
  window.addEventListener('scroll', handleScroll)
})

onUnmounted(() => {
  window.removeEventListener('scroll', handleScroll)
  unlockScroll()
})
</script>

<style lang="scss" scoped>
.navbar {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  z-index: $z-modal;
  background: #ffffff;
  border-bottom: 1px solid $border-light;
  transition: all $transition-normal;

  &.scrolled {
    box-shadow: $shadow-md;
    border-bottom-color: transparent;
  }
}

.navbar-content {
  @include flex-between;
  height: 72px;
}

.logo {
  display: flex;
  align-items: center;
  gap: $spacing-sm;
  text-decoration: none;
}

.logo-icon {
  width: 36px;
  height: 36px;

  svg {
    width: 100%;
    height: 100%;
  }
}

.logo-text {
  font-family: $font-display;
  font-size: 18px;
  font-weight: 600;
  color: $text-primary;
}

.nav-links {
  display: flex;
  align-items: center;
  gap: $spacing-xl;

  a {
    color: $text-secondary;
    font-size: 15px;
    font-weight: 500;
    transition: color $transition-fast;

    &:hover,
    &.router-link-active {
      color: $primary;
    }
  }
}

.dropdown {
  position: relative;

  .dropdown-trigger {
    color: $text-secondary;
    font-size: 15px;
    font-weight: 500;
    cursor: pointer;
    display: flex;
    align-items: center;
    gap: 4px;

    &::after {
      content: '';
      width: 0;
      height: 0;
      border-left: 4px solid transparent;
      border-right: 4px solid transparent;
      border-top: 4px solid currentColor;
    }

    &:hover {
      color: $primary;
    }
  }

  .dropdown-menu {
    position: absolute;
    top: 100%;
    left: 50%;
    transform: translateX(-50%) translateY(10px);
    background: $bg-white;
    border-radius: $radius-md;
    box-shadow: $shadow-lg;
    padding: $spacing-sm;
    min-width: 160px;
    opacity: 0;
    visibility: hidden;
    transition: all $transition-fast;

    a {
      display: block;
      padding: $spacing-sm $spacing-md;
      border-radius: $radius-sm;
      white-space: nowrap;

      &:hover {
        background: $gray-100;
      }
    }
  }

  &:hover .dropdown-menu {
    opacity: 1;
    visibility: visible;
    transform: translateX(-50%) translateY(0);
  }
}

.nav-actions {
  display: flex;
  align-items: center;
  gap: $spacing-md;
}

.mobile-toggle {
  display: none;
  flex-direction: column;
  justify-content: center;
  gap: 5px;
  width: 28px;
  height: 28px;
  background: none;
  border: none;
  cursor: pointer;
  padding: 0;
  position: relative;
  z-index: $z-modal + 1;

  span {
    display: block;
    width: 100%;
    height: 2px;
    background: $text-primary;
    border-radius: 2px;
    transition: all $transition-fast;
  }

  &.active {
    span:nth-child(1) {
      transform: translateY(7px) rotate(45deg);
    }

    span:nth-child(2) {
      opacity: 0;
    }

    span:nth-child(3) {
      transform: translateY(-7px) rotate(-45deg);
    }
  }
}

.mobile-overlay {
  display: none;
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(0, 0, 0, 0.4);
  z-index: $z-modal - 1;
  opacity: 0;
  transition: opacity $transition-normal;
  -webkit-tap-highlight-color: transparent;

  &.active {
    opacity: 1;
  }
}

@include mobile {
  .nav-links {
    position: fixed;
    top: 72px;
    left: 0;
    right: 0;
    bottom: 0;
    z-index: $z-modal;
    background: #ffffff;
    flex-direction: column;
    align-items: stretch;
    padding: $spacing-xl;
    gap: $spacing-lg;
    transform: translateX(100%);
    transition: transform $transition-normal;
    touch-action: manipulation;
    -webkit-overflow-scrolling: touch;
    overflow-y: auto;

    &.active {
      transform: translateX(0);
    }

    a {
      font-size: 18px;
      padding: $spacing-md 0;
      border-bottom: 1px solid $border-light;
      cursor: pointer;
      user-select: none;
      -webkit-tap-highlight-color: transparent;
    }
  }

  .dropdown {
    .dropdown-trigger {
      font-size: 18px;
      padding: $spacing-md 0;
      display: block;
      border-bottom: 1px solid $border-light;
      cursor: pointer;
      user-select: none;
      -webkit-tap-highlight-color: transparent;
    }

    .dropdown-menu {
      position: static;
      transform: none;
      box-shadow: none;
      padding: 0 0 0 $spacing-md;
      opacity: 1;
      visibility: visible;

      a {
        font-size: 16px;
        border-bottom: 1px dashed $border-light;
      }
    }
  }

  .nav-actions {
    display: none;
  }

  .mobile-toggle {
    display: flex;
  }

  .mobile-overlay {
    display: block;
  }
}
</style>
