<template>
  <footer class="footer">
    <div class="container">
      <div class="footer-content">
        <div class="footer-brand">
          <div class="logo">
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
          </div>
          <p class="footer-desc">企业级后台管理平台 · 应用中心 + RBAC + CMS · FastAPI + Vue3</p>
        </div>

        <div class="footer-links">
          <div class="link-group">
            <h4>产品</h4>
            <ul>
              <li><router-link to="/features">功能介绍</router-link></li>
              <li><router-link to="/advantages">技术优势</router-link></li>
              <li><router-link to="/deploy">私有部署</router-link></li>
            </ul>
          </div>

          <div class="link-group">
            <h4>文档</h4>
            <ul>
              <li><router-link to="/docs/guide">使用指南</router-link></li>
              <li><router-link to="/deploy">部署教程</router-link></li>
              <li><a :href="urls.github" target="_blank" rel="noopener">GitHub 仓库</a></li>
            </ul>
          </div>

          <div class="link-group">
            <h4>支持</h4>
            <ul>
              <li><a :href="urls.contact" target="_blank" rel="noopener">联系我们</a></li>
              <li v-if="contact.wechat">微信：{{ contact.wechat }}</li>
              <li v-if="contact.phone">电话：{{ contact.phone }}</li>
              <li><a :href="`mailto:${contact.email}`">{{ contact.email }}</a></li>
            </ul>
          </div>
        </div>
      </div>

      <div class="footer-bottom">
        <p>&copy; {{ new Date().getFullYear() }} 辰科科技 Cenkor Admin. 保留所有权利.</p>
      </div>
    </div>
  </footer>
</template>

<script setup lang="ts">
import { onMounted } from 'vue'
import { SITE_URLS } from '@/config/site'
import { useSiteConfig } from '@/composables/useSiteConfig'

const urls = SITE_URLS
const { contact, fetchContact } = useSiteConfig()

onMounted(() => {
  fetchContact()
})
</script>

<style lang="scss" scoped>
.footer {
  background: $gray-900;
  color: $gray-300;
  padding: $spacing-3xl 0 $spacing-xl;
  margin-top: $spacing-4xl;
}

.footer-content {
  display: grid;
  grid-template-columns: 1fr 2fr;
  gap: $spacing-3xl;
  margin-bottom: $spacing-2xl;

  @include mobile {
    grid-template-columns: 1fr;
    gap: $spacing-2xl;
  }
}

.footer-brand {
  .logo {
    display: flex;
    align-items: center;
    gap: $spacing-sm;
    margin-bottom: $spacing-md;
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
    color: $text-white;
  }

  .footer-desc {
    color: $gray-400;
    font-size: 14px;
    line-height: 1.6;
  }
}

.footer-links {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: $spacing-2xl;

  @include mobile {
    grid-template-columns: repeat(2, 1fr);
    gap: $spacing-xl;
  }
}

.link-group {
  h4 {
    color: $text-white;
    font-size: 14px;
    font-weight: 600;
    margin-bottom: $spacing-md;
    text-transform: uppercase;
    letter-spacing: 0.5px;
  }

  ul {
    list-style: none;
    padding: 0;
    margin: 0;
  }

  li {
    margin-bottom: $spacing-sm;
  }

  a {
    color: $gray-400;
    font-size: 14px;
    transition: color $transition-fast;

    &:hover {
      color: $text-white;
    }
  }
}

.footer-bottom {
  padding-top: $spacing-xl;
  border-top: 1px solid $gray-800;
  text-align: center;

  p {
    color: $gray-500;
    font-size: 13px;
    margin: 0;
  }
}
</style>
