<template>
  <div class="advantages-page">
    <section class="page-hero">
      <div class="container">
        <div class="page-hero-content">
          <span class="hero-tag">技术优势</span>
          <h1>为什么选择辰科Cenkor Admin</h1>
          <p>现代技术栈 + 应用中心生态 + 灵活部署，企业级后台管理平台首选</p>
        </div>
      </div>
    </section>

    <section class="section">
      <div class="container">
        <div class="advantages-grid">
          <ScrollReveal v-for="(adv, index) in advantages" :key="adv.title" :delay="index * 100">
            <div class="adv-card">
              <div class="adv-icon" :style="{ background: adv.bg }">{{ adv.icon }}</div>
              <h3>{{ adv.title }}</h3>
              <p>{{ adv.description }}</p>
            </div>
          </ScrollReveal>
        </div>
      </div>
    </section>

    <section class="section section-alt">
      <div class="container">
        <SectionTitle
          tag="技术栈"
          title="现代技术栈"
          description="FastAPI + Vue3 + PostgreSQL，异步高性能，容器化交付"
          :center="true"
        />
        <div class="stack-grid">
          <div class="stack-item" v-for="tech in techStack" :key="tech.name">
            <div class="stack-icon">{{ tech.icon }}</div>
            <div>
              <strong>{{ tech.name }}</strong>
              <span>{{ tech.desc }}</span>
            </div>
          </div>
        </div>
      </div>
    </section>

    <section class="section">
      <div class="container">
        <SectionTitle
          tag="对比优势"
          title="Cenkor Admin 的核心竞争力"
          description="应用中心生态 + 通用内容引擎 + 灵活部署，平台化交付"
          :center="true"
        />
        <div class="compare-grid">
          <div class="compare-card vs">
            <h3>传统后台框架</h3>
            <ul>
              <li class="no">业务功能需逐套开发</li>
              <li class="no">内容字段改代码才能扩展</li>
              <li class="no">应用难以按需安装</li>
              <li class="no">前后台用户体系混杂</li>
              <li class="no">部署方式单一</li>
            </ul>
          </div>
          <div class="compare-card win">
            <div class="win-badge">推荐</div>
            <h3>辰科Cenkor Admin</h3>
            <ul>
              <li class="yes">应用中心按需安装，即插即用</li>
              <li class="yes">通用内容引擎，后台动态扩字段</li>
              <li class="yes">应用安装自动注册权限/菜单</li>
              <li class="yes">前后台双用户体系完全隔离</li>
              <li class="yes">Docker/宝塔/裸机三种部署</li>
            </ul>
          </div>
        </div>
      </div>
    </section>

    <section class="cta-section">
      <div class="container">
        <div class="cta-content">
          <h2>把时间花在业务上，而不是重复造后台</h2>
          <p>Cenkor Admin 让后台平台一次搭建，处处复用</p>
          <div class="cta-actions">
            <router-link to="/features" class="btn btn-primary btn-large">查看功能</router-link>
            <router-link to="/deploy" class="btn btn-secondary btn-large">私有部署</router-link>
          </div>
        </div>
      </div>
    </section>
  </div>
</template>

<script setup lang="ts">
import { useHead } from '@unhead/vue'
import SectionTitle from '@/components/SectionTitle.vue'
import ScrollReveal from '@/components/ScrollReveal.vue'

useHead({
  title: '辰科Cenkor Admin - 技术优势 | 企业级后台管理平台',
  meta: [
    { name: 'description', content: '辰科Cenkor Admin 技术优势：FastAPI + Vue3 现代架构、应用中心生态、通用内容引擎、前后台双用户体系、三种部署模式。' }
  ]
})

const advantages = [
  {
    icon: '🏪',
    title: '应用中心生态',
    description: '应用 manifest 声明内容/字段/权限/菜单，安装时自动注册，卸载自动清理，业务模块即插即用。',
    bg: 'rgba(16, 185, 129, 0.1)'
  },
  {
    icon: '📝',
    title: '通用内容引擎',
    description: '动态字段定义 + 21+ 字段类型 + 多级分类标签，后台 UI 即可扩字段，无需改代码。',
    bg: 'rgba(245, 158, 11, 0.1)'
  },
  {
    icon: '⚡',
    title: '现代技术栈',
    description: 'FastAPI 异步高性能 + Vue3 + SQLAlchemy 2，PostgreSQL/Redis/MinIO 标准中间件。',
    bg: 'rgba(139, 92, 246, 0.1)'
  },
  {
    icon: '🔐',
    title: '安全可控',
    description: 'JWT 前后台双体系鉴权 + RBAC 权限 + 审计日志，平台安全可追溯。',
    bg: 'rgba(236, 72, 153, 0.1)'
  },
  {
    icon: '🏠',
    title: '灵活部署',
    description: 'Docker Compose / 宝塔静态 dist / 裸机 systemd 三种模式，可独立运营不依赖官网。',
    bg: 'rgba(37, 99, 235, 0.1)'
  },
  {
    icon: '🔗',
    title: '开放 API',
    description: '公开只读 API（/api/v1/public/*）供任意前端消费，生态开放可扩展。',
    bg: 'rgba(6, 182, 212, 0.1)'
  }
]

const techStack = [
  { name: 'FastAPI', icon: '⚡', desc: 'Python 异步 API 框架' },
  { name: 'Vue 3 + Vite', icon: '💚', desc: '现代前端框架' },
  { name: 'Tailwind', icon: '🎨', desc: '原子化样式' },
  { name: 'PostgreSQL 16', icon: '🗄️', desc: '关系型数据库' },
  { name: 'Redis 7', icon: '🔴', desc: '缓存与消息' },
  { name: 'Docker', icon: '🐳', desc: '容器化部署' }
]
</script>

<style lang="scss" scoped>
.page-hero {
  padding: 140px 0 60px;
  background: linear-gradient(180deg, $gray-50 0%, $bg-white 100%);
  border-bottom: 1px solid $border-light;
}

.page-hero-content {
  text-align: center;
  max-width: 720px;
  margin: 0 auto;

  .hero-tag {
    display: inline-block;
    padding: 6px 16px;
    background: rgba($primary, 0.1);
    color: $primary;
    font-size: 13px;
    font-weight: 600;
    border-radius: $radius-full;
    margin-bottom: $spacing-md;
  }

  h1 {
    font-size: 2.5rem;
    font-weight: 800;
    color: $text-primary;
    margin-bottom: $spacing-md;

    @include mobile {
      font-size: 1.9rem;
    }
  }

  p {
    font-size: 1.125rem;
    color: $text-secondary;
    margin: 0;
  }
}

.advantages-grid {
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

.adv-card {
  background: $bg-white;
  border-radius: $radius-lg;
  padding: $spacing-xl;
  border: 1px solid $border-light;
  transition: all $transition-normal;

  &:hover {
    transform: translateY(-4px);
    box-shadow: $shadow-lg;
    border-color: transparent;
  }

  .adv-icon {
    width: 56px;
    height: 56px;
    border-radius: $radius-md;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 28px;
    margin-bottom: $spacing-md;
  }

  h3 {
    font-size: 1.25rem;
    color: $text-primary;
    margin-bottom: $spacing-sm;
  }

  p {
    color: $text-secondary;
    font-size: 0.95rem;
    line-height: 1.7;
    margin: 0;
  }
}

.stack-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: $spacing-md;
  max-width: 900px;
  margin: 0 auto;

  @include mobile {
    grid-template-columns: 1fr;
  }
}

.stack-item {
  display: flex;
  align-items: center;
  gap: $spacing-md;
  padding: $spacing-lg;
  background: $bg-white;
  border-radius: $radius-md;
  border: 1px solid $border-light;

  .stack-icon {
    font-size: 28px;
    width: 48px;
    text-align: center;
  }

  strong {
    display: block;
    font-size: 0.95rem;
    color: $text-primary;
  }

  span {
    font-size: 0.8rem;
    color: $text-muted;
  }
}

.compare-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: $spacing-2xl;
  max-width: 900px;
  margin: 0 auto;

  @include mobile {
    grid-template-columns: 1fr;
  }
}

.compare-card {
  border-radius: $radius-xl;
  padding: $spacing-xl;
  border: 1px solid $border-light;
  background: $bg-white;
  position: relative;

  &.win {
    border-color: $success;
    box-shadow: 0 0 0 1px $success, $shadow-md;
  }

  .win-badge {
    position: absolute;
    top: -12px;
    left: $spacing-xl;
    background: $success;
    color: white;
    font-size: 12px;
    font-weight: 600;
    padding: 4px 14px;
    border-radius: $radius-full;
  }

  h3 {
    font-size: 1.25rem;
    color: $text-primary;
    margin-bottom: $spacing-lg;
    text-align: center;
  }

  ul {
    list-style: none;
    padding: 0;
    margin: 0;

    li {
      padding: $spacing-sm 0;
      color: $text-secondary;
      display: flex;
      align-items: center;
      gap: $spacing-sm;
      font-size: 0.95rem;

      &.no::before {
        content: '✕';
        color: $error;
        font-weight: 700;
      }

      &.yes::before {
        content: '✓';
        color: $success;
        font-weight: 700;
      }
    }
  }
}

.cta-section {
  padding: $spacing-4xl 0;
  background: linear-gradient(135deg, $dark-900 0%, $dark-800 100%);
}

.cta-content {
  text-align: center;

  h2 {
    font-size: 2.5rem;
    color: $text-white;
    margin-bottom: $spacing-md;

    @include mobile {
      font-size: 1.9rem;
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
