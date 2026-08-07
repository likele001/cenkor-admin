<template>
  <div class="home">
    <!-- Hero Section -->
    <section class="hero">
      <div class="hero-bg">
        <div class="hero-grid"></div>
        <div class="hero-glow"></div>
      </div>
      <div class="container">
        <div class="hero-content">
          <div class="hero-badge">
            <span class="badge-dot"></span>
            辰科 · 企业级后台管理平台
          </div>
          <h1>
            一套后台，<br>
            <span class="gradient-text">装下所有业务应用</span>
          </h1>
          <p class="hero-desc">
            FastAPI + Vue3 架构，应用中心 + RBAC 权限 + 通用内容引擎 + 用户中心开箱即用。<br>
            应用按需安装，支持私有化部署，可独立运营不依赖任何官网。
          </p>
          <div class="hero-actions">
            <router-link to="/features" class="btn btn-primary btn-large">
              查看功能
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="18" height="18">
                <line x1="5" y1="12" x2="19" y2="12"></line>
                <polyline points="12 5 19 12 12 19"></polyline>
              </svg>
            </router-link>
            <router-link to="/deploy" class="btn btn-secondary btn-large">
              私有部署
            </router-link>
          </div>
        </div>
        <div class="hero-visual">
          <div class="hero-card">
            <div class="card-header">
              <div class="card-dots">
                <span></span><span></span><span></span>
              </div>
              <span class="card-title">应用中心</span>
            </div>
            <div class="card-body">
              <div class="app-grid">
                <div class="app-item" v-for="app in heroApps" :key="app.name">
                  <span class="app-icon">{{ app.icon }}</span>
                  <span class="app-name">{{ app.name }}</span>
                  <span class="app-badge" :class="{ installed: app.installed }">{{ app.installed ? '已装' : '安装' }}</span>
                </div>
              </div>
              <div class="sys-row">
                <div class="sys-item"><span class="dot"></span> RBAC 权限</div>
                <div class="sys-item"><span class="dot"></span> CMS 内容引擎</div>
                <div class="sys-item"><span class="dot"></span> 审计日志</div>
                <div class="sys-item"><span class="dot"></span> 用户中心</div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </section>

    <!-- Stats Section -->
    <section class="stats-section">
      <div class="container">
        <div class="stats-grid">
          <div class="stat-item" v-for="stat in stats" :key="stat.label">
            <div class="stat-value">
              <CounterUp :value="stat.value" :suffix="stat.suffix" />
            </div>
            <div class="stat-label">{{ stat.label }}</div>
          </div>
        </div>
      </div>
    </section>

    <!-- Features Section -->
    <section class="section">
      <div class="container">
        <SectionTitle
          tag="核心能力"
          title="企业级后台一站配齐"
          description="应用中心 + 权限 + 内容 + 用户，从搭建到运营全流程覆盖"
          :center="true"
        />
        <div class="features-grid">
          <ScrollReveal v-for="(feature, index) in features" :key="feature.title" :delay="index * 100">
            <FeatureCard
              :icon="feature.icon"
              :title="feature.title"
              :description="feature.description"
              :features="feature.features"
              :color="feature.color"
            />
          </ScrollReveal>
        </div>
      </div>
    </section>

    <!-- Architecture Section -->
    <section class="section section-alt">
      <div class="container">
        <SectionTitle
          tag="技术架构"
          title="FastAPI + Vue3 现代架构"
          description="前后端分离，容器化部署，支持 Docker Compose / 宝塔静态 / 裸机 systemd"
          :center="true"
        />
        <div class="arch-grid">
          <ScrollReveal animation="fade-left">
            <div class="arch-services">
              <div class="arch-service" v-for="service in services" :key="service.name">
                <div class="service-icon" :style="{ background: service.color }">{{ service.icon }}</div>
                <div class="service-info">
                  <h4>{{ service.name }}</h4>
                  <p>{{ service.desc }}</p>
                </div>
              </div>
            </div>
          </ScrollReveal>
          <ScrollReveal animation="fade-right">
            <div class="arch-stack">
              <h3>技术栈</h3>
              <div class="stack-list">
                <div class="stack-item" v-for="tech in techStack" :key="tech.name">
                  <div class="stack-icon">{{ tech.icon }}</div>
                  <div>
                    <strong>{{ tech.name }}</strong>
                    <span>{{ tech.desc }}</span>
                  </div>
                </div>
              </div>
            </div>
          </ScrollReveal>
        </div>
      </div>
    </section>

    <!-- Applications Section -->
    <section class="section">
      <div class="container">
        <SectionTitle
          tag="内置应用"
          title="开箱即用的业务应用"
          description="公告、工单、云存储、链接、记事等，通过应用中心统一安装管理"
          :center="true"
        />
        <div class="app-grid-lg">
          <ScrollReveal v-for="(app, index) in apps" :key="app.name" :delay="index * 60">
            <div class="app-card">
              <div class="app-icon">{{ app.icon }}</div>
              <h4>{{ app.name }}</h4>
              <p>{{ app.desc }}</p>
            </div>
          </ScrollReveal>
        </div>
      </div>
    </section>

    <!-- CTA Section -->
    <section class="cta-section">
      <div class="container">
        <div class="cta-content">
          <ScrollReveal>
            <h2>准备好搭建你的后台管理平台了吗？</h2>
            <p>开源平台，应用中心按需扩展，私有化部署数据自主可控</p>
            <div class="cta-actions">
              <router-link to="/features" class="btn btn-primary btn-large">查看功能</router-link>
              <a :href="urls.github" target="_blank" rel="noopener" class="btn btn-secondary btn-large">GitHub 仓库</a>
            </div>
          </ScrollReveal>
        </div>
      </div>
    </section>
  </div>
</template>

<script setup lang="ts">
import { useHead } from '@unhead/vue'
import SectionTitle from '@/components/SectionTitle.vue'
import FeatureCard from '@/components/FeatureCard.vue'
import ScrollReveal from '@/components/ScrollReveal.vue'
import CounterUp from '@/components/CounterUp.vue'
import { SITE_URLS } from '@/config/site'

const urls = SITE_URLS

useHead({
  title: '辰科Cenkor Admin - 企业级后台管理平台 | 私有化部署',
  meta: [
    { name: 'description', content: '辰科Cenkor Admin 企业级后台管理平台，FastAPI + Vue3 架构，内置应用中心、RBAC 权限、通用内容引擎、用户中心、审计日志，应用按需安装，支持私有化部署。' }
  ]
})

const stats = [
  { value: 8, label: '内置业务应用', suffix: '' },
  { value: 21, label: 'CMS 字段类型', suffix: '+' },
  { value: 3, label: '部署模式', suffix: ' 种' },
  { value: 100, label: '私有化部署', suffix: '%' }
]

const features = [
  {
    icon: '🏪',
    title: '应用中心',
    description: '应用按需安装/卸载，自动注册权限、菜单、内容类型，业务模块即插即用',
    features: ['应用安装卸载', '权限自动注册', '菜单自动生成'],
    color: '#10b981'
  },
  {
    icon: '🔐',
    title: 'RBAC 权限',
    description: '角色、权限规则、数据权限三级控制，后台/前台双用户体系隔离',
    features: ['角色管理', '数据权限', '双用户体系'],
    color: '#8b5cf6'
  },
  {
    icon: '📝',
    title: '通用内容引擎',
    description: 'CMS 动态字段定义，21+ 字段类型，分类标签系统，后台即可改字段',
    features: ['动态字段', '分类标签', '内容类型'],
    color: '#f59e0b'
  },
  {
    icon: '👤',
    title: '用户中心',
    description: 'C 端注册登录、个人资料、订阅管理，前后台用户完全隔离',
    features: ['注册登录', '资料管理', '订阅管理'],
    color: '#06b6d4'
  },
  {
    icon: '🛡️',
    title: '审计日志',
    description: '操作记录完整留痕，平台安全可追溯',
    features: ['操作记录', '安全追溯', '合规留痕'],
    color: '#ec4899'
  },
  {
    icon: '🏠',
    title: '私有化部署',
    description: 'Docker Compose / 宝塔静态 / 裸机 systemd 三种模式，可独立运营',
    features: ['容器化部署', '宝塔静态', '裸机部署'],
    color: '#2563eb'
  }
]

const services = [
  { name: 'admin-web', icon: '🖥️', color: '#10b981', desc: '运营后台 SPA（Vue3）' },
  { name: 'portal-web', icon: '👤', color: '#8b5cf6', desc: '用户中心 SPA（Vue3）' },
  { name: 'backend', icon: '⚡', color: '#f59e0b', desc: 'FastAPI + SQLAlchemy + Celery' },
  { name: 'PostgreSQL', icon: '🗄️', color: '#06b6d4', desc: '关系型数据库 16' },
  { name: 'Redis', icon: '🔴', color: '#ef4444', desc: '缓存与消息队列 7' },
  { name: 'MinIO', icon: '☁️', color: '#2563eb', desc: '对象存储' }
]

const techStack = [
  { name: 'FastAPI', icon: '⚡', desc: '高性能 Python API 框架' },
  { name: 'Vue 3 + Vite', icon: '💚', desc: '现代前端框架' },
  { name: 'Tailwind', icon: '🎨', desc: '原子化样式' },
  { name: 'SQLAlchemy 2', icon: '🗄️', desc: '异步 ORM' },
  { name: 'Docker', icon: '🐳', desc: '容器化部署' },
  { name: 'JWT', icon: '🔐', desc: '前后台双体系鉴权' }
]

const heroApps = [
  { icon: '📢', name: '公告', installed: true },
  { icon: '🎫', name: '工单', installed: true },
  { icon: '☁️', name: '云存储', installed: true },
  { icon: '🔗', name: '链接', installed: true },
  { icon: '📝', name: '记事', installed: true },
  { icon: '✅', name: 'Todo', installed: true }
]

const apps = [
  { icon: '📢', name: '公告管理', desc: '公告发布与通知' },
  { icon: '🎫', name: '工单系统', desc: '问题工单流转处理' },
  { icon: '☁️', name: '云存储', desc: '对象存储管理' },
  { icon: '🔗', name: '链接收藏', desc: '常用链接管理' },
  { icon: '📝', name: 'Quick Notes', desc: '快速记事' },
  { icon: '✅', name: 'My Todo', desc: '任务清单' },
  { icon: '🔔', name: '通知', desc: '系统通知推送' },
  { icon: '📰', name: 'CMS', desc: '官网内容管理' }
]
</script>

<style lang="scss" scoped>
// Hero
.hero {
  position: relative;
  padding: 140px 0 80px;
  overflow: hidden;
  min-height: 90vh;
  display: flex;
  align-items: center;
}

.hero-bg {
  position: absolute;
  inset: 0;
  z-index: 0;

  .hero-grid {
    position: absolute;
    inset: 0;
    background-image:
      linear-gradient(rgba($primary, 0.03) 1px, transparent 1px),
      linear-gradient(90deg, rgba($primary, 0.03) 1px, transparent 1px);
    background-size: 60px 60px;
  }

  .hero-glow {
    position: absolute;
    top: -200px;
    right: -200px;
    width: 600px;
    height: 600px;
    background: radial-gradient(circle, rgba($primary, 0.08) 0%, transparent 70%);
    border-radius: 50%;
  }
}

.hero .container {
  position: relative;
  z-index: 1;
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: $spacing-3xl;
  align-items: center;

  @include mobile {
    grid-template-columns: 1fr;
  }
}

.hero-content {
  .hero-badge {
    display: inline-flex;
    align-items: center;
    gap: 8px;
    padding: 8px 16px;
    background: rgba($primary, 0.08);
    border: 1px solid rgba($primary, 0.15);
    border-radius: $radius-full;
    font-size: 14px;
    color: $primary;
    font-weight: 500;
    margin-bottom: $spacing-lg;

    .badge-dot {
      width: 8px;
      height: 8px;
      background: $primary;
      border-radius: 50%;
      animation: pulse 2s infinite;
    }
  }

  h1 {
    font-size: 3.2rem;
    font-weight: 800;
    line-height: 1.15;
    margin-bottom: $spacing-lg;
    color: $text-primary;

    @include mobile {
      font-size: 2.3rem;
    }
  }

  .gradient-text {
    @include gradient-text($primary, #8b5cf6);
  }

  .hero-desc {
    font-size: 1.125rem;
    color: $text-secondary;
    line-height: 1.8;
    margin-bottom: $spacing-xl;
  }

  .hero-actions {
    display: flex;
    gap: $spacing-md;
    flex-wrap: wrap;
  }
}

.hero-visual {
  @include mobile {
    display: none;
  }
}

.hero-card {
  background: $bg-white;
  border-radius: $radius-xl;
  box-shadow: $shadow-xl;
  overflow: hidden;
  border: 1px solid $border-light;

  .card-header {
    display: flex;
    align-items: center;
    gap: $spacing-md;
    padding: $spacing-md $spacing-lg;
    background: $gray-50;
    border-bottom: 1px solid $border-light;

    .card-dots {
      display: flex;
      gap: 6px;

      span {
        width: 10px;
        height: 10px;
        border-radius: 50%;

        &:nth-child(1) { background: #ef4444; }
        &:nth-child(2) { background: #f59e0b; }
        &:nth-child(3) { background: #10b981; }
      }
    }

    .card-title {
      font-size: 13px;
      color: $text-muted;
    }
  }

  .card-body {
    padding: $spacing-lg;
  }

  .app-grid {
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: $spacing-sm;
    margin-bottom: $spacing-lg;

    .app-item {
      position: relative;
      display: flex;
      flex-direction: column;
      align-items: center;
      gap: 6px;
      padding: $spacing-md $spacing-sm;
      background: $gray-50;
      border-radius: $radius-md;
      border: 1px solid transparent;
      transition: all $transition-fast;

      &:hover {
        border-color: rgba($primary, 0.3);
        background: rgba($primary, 0.05);
      }

      .app-icon {
        font-size: 22px;
      }

      .app-name {
        font-size: 11px;
        color: $text-secondary;
        white-space: nowrap;
      }

      .app-badge {
        position: absolute;
        top: 4px;
        right: 4px;
        padding: 1px 6px;
        border-radius: $radius-full;
        font-size: 9px;
        background: $gray-200;
        color: $text-muted;

        &.installed {
          background: rgba($success, 0.15);
          color: $success;
        }
      }
    }
  }

  .sys-row {
    display: grid;
    grid-template-columns: repeat(2, 1fr);
    gap: $spacing-sm;

    .sys-item {
      display: flex;
      align-items: center;
      gap: 6px;
      padding: $spacing-sm $spacing-md;
      background: $gray-50;
      border-radius: $radius-sm;
      font-size: 12px;
      color: $text-secondary;

      .dot {
        width: 6px;
        height: 6px;
        border-radius: 50%;
        background: $success;
      }
    }
  }
}

// Stats
.stats-section {
  padding: $spacing-3xl 0;
  background: $bg-white;
  border-bottom: 1px solid $border-light;
}

.stats-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: $spacing-xl;
  text-align: center;

  @include mobile {
    grid-template-columns: repeat(2, 1fr);
    gap: $spacing-lg;
  }
}

.stat-item {
  .stat-value {
    font-size: 2.5rem;
    font-weight: 800;
    color: $primary;
    font-family: $font-display;

    @include mobile {
      font-size: 2rem;
    }
  }

  .stat-label {
    font-size: 0.95rem;
    color: $text-secondary;
    margin-top: 4px;
  }
}

// Features
.features-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: $spacing-lg;

  @include tablet {
    grid-template-columns: repeat(2, 1fr);
  }

  @include mobile {
    grid-template-columns: 1fr;
  }
}

// Architecture
.arch-grid {
  display: grid;
  grid-template-columns: 1.2fr 0.8fr;
  gap: $spacing-2xl;
  align-items: start;

  @include mobile {
    grid-template-columns: 1fr;
  }
}

.arch-services {
  display: flex;
  flex-direction: column;
  gap: $spacing-md;
}

.arch-service {
  display: flex;
  align-items: center;
  gap: $spacing-md;
  padding: $spacing-md;
  background: $bg-white;
  border-radius: $radius-md;
  border: 1px solid $border-light;
  transition: all $transition-fast;

  &:hover {
    box-shadow: $shadow-md;
    border-color: transparent;
  }

  .service-icon {
    width: 44px;
    height: 44px;
    border-radius: $radius-md;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 20px;
    flex-shrink: 0;
  }

  .service-info {
    h4 {
      font-size: 0.95rem;
      font-weight: 600;
      color: $text-primary;
    }

    p {
      font-size: 0.85rem;
      color: $text-secondary;
      margin: 2px 0 0;
    }
  }
}

.arch-stack {
  background: $bg-white;
  border-radius: $radius-lg;
  padding: $spacing-xl;
  border: 1px solid $border-light;

  h3 {
    font-size: 1.25rem;
    margin-bottom: $spacing-lg;
    color: $text-primary;
  }
}

.stack-list {
  display: flex;
  flex-direction: column;
  gap: $spacing-md;
}

.stack-item {
  display: flex;
  align-items: center;
  gap: $spacing-md;

  .stack-icon {
    font-size: 24px;
    width: 40px;
    text-align: center;
  }

  strong {
    display: block;
    font-size: 0.9rem;
    color: $text-primary;
  }

  span {
    font-size: 0.8rem;
    color: $text-muted;
  }
}

// Applications
.app-grid-lg {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: $spacing-md;

  @include tablet {
    grid-template-columns: repeat(3, 1fr);
  }

  @include mobile {
    grid-template-columns: repeat(2, 1fr);
  }
}

.app-card {
  background: $bg-white;
  border-radius: $radius-md;
  padding: $spacing-lg;
  border: 1px solid $border-light;
  transition: all $transition-normal;

  &:hover {
    transform: translateY(-4px);
    box-shadow: $shadow-md;
    border-color: transparent;
  }

  .app-icon {
    font-size: 32px;
    margin-bottom: $spacing-sm;
  }

  h4 {
    font-size: 1rem;
    color: $text-primary;
    margin-bottom: 4px;
  }

  p {
    font-size: 0.85rem;
    color: $text-muted;
    margin: 0;
  }
}

// CTA
.cta-section {
  padding: $spacing-4xl 0;
  background: linear-gradient(135deg, $dark-900 0%, $dark-800 100%);
  position: relative;
  overflow: hidden;

  &::before {
    content: '';
    position: absolute;
    top: -50%;
    right: -20%;
    width: 500px;
    height: 500px;
    background: radial-gradient(circle, rgba($primary, 0.15) 0%, transparent 70%);
    border-radius: 50%;
  }
}

.cta-content {
  text-align: center;
  position: relative;
  z-index: 1;

  h2 {
    font-size: 2.5rem;
    color: $text-white;
    margin-bottom: $spacing-md;

    @include mobile {
      font-size: 2rem;
    }
  }

  p {
    font-size: 1.125rem;
    color: $gray-400;
    margin-bottom: $spacing-xl;
  }

  .cta-actions {
    display: flex;
    justify-content: center;
    gap: $spacing-md;
    flex-wrap: wrap;
  }
}
</style>
