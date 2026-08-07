<template>
  <div class="features-page">
    <section class="page-hero">
      <div class="container">
        <div class="page-hero-content">
          <span class="hero-tag">核心功能</span>
          <h1>后台管理平台全功能一览</h1>
          <p>应用中心、RBAC 权限、通用内容引擎、用户中心、审计日志，一站配齐</p>
        </div>
      </div>
    </section>

    <section class="section">
      <div class="container">
        <div class="feature-list">
          <ScrollReveal v-for="(item, index) in featureItems" :key="item.title" :delay="index * 80">
            <div class="feature-row">
              <div class="feature-icon">{{ item.icon }}</div>
              <div class="feature-content">
                <h2>{{ item.title }}</h2>
                <p>{{ item.description }}</p>
                <ul>
                  <li v-for="point in item.points" :key="point">{{ point }}</li>
                </ul>
              </div>
            </div>
          </ScrollReveal>
        </div>
      </div>
    </section>

    <section class="section section-alt">
      <div class="container">
        <SectionTitle
          tag="应用中心"
          title="应用按需安装"
          description="每个应用声明内容类型、字段、权限、菜单，安装时自动注册"
          :center="true"
        />
        <div class="app-grid">
          <ScrollReveal v-for="(app, index) in apps" :key="app.name" :delay="index * 50">
            <div class="app-card">
              <div class="app-icon">{{ app.icon }}</div>
              <h4>{{ app.name }}</h4>
              <p>{{ app.desc }}</p>
            </div>
          </ScrollReveal>
        </div>
      </div>
    </section>

    <section class="section">
      <div class="container">
        <SectionTitle
          tag="内容引擎"
          title="21+ 字段类型的通用 CMS"
          description="后台即可动态增删字段，无需改代码"
          :center="true"
        />
        <div class="field-grid">
          <div class="field-item" v-for="field in fields" :key="field">
            <span class="field-check">✓</span>
            {{ field }}
          </div>
        </div>
      </div>
    </section>

    <section class="cta-section">
      <div class="container">
        <div class="cta-content">
          <h2>需要一个开箱即用的后台管理平台？</h2>
          <p>Cenkor Admin 让你跳过从零搭建，直接聚焦业务</p>
          <div class="cta-actions">
            <router-link to="/deploy" class="btn btn-primary btn-large">开始部署</router-link>
            <router-link to="/advantages" class="btn btn-secondary btn-large">了解技术优势</router-link>
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
  title: '辰科Cenkor Admin - 核心功能 | 企业级后台管理平台',
  meta: [
    { name: 'description', content: '辰科Cenkor Admin 核心功能：应用中心、RBAC 权限、通用内容引擎（21+ 字段类型）、用户中心、审计日志、私有化部署。' }
  ]
})

const featureItems = [
  {
    icon: '🏪',
    title: '应用中心',
    description: '应用通过 manifest 声明内容类型、字段、分类、权限与菜单，安装时自动注册到系统，卸载时自动清理，即插即用。',
    points: ['应用安装/卸载/升级', '权限与菜单自动注册', '内容字段自动生成']
  },
  {
    icon: '🔐',
    title: 'RBAC 权限',
    description: '角色、权限规则、数据权限三级控制。后台（auth_users）与前台（portal_users）双用户体系完全隔离。',
    points: ['角色与权限规则', '数据权限范围控制', '前后台双用户隔离']
  },
  {
    icon: '📝',
    title: '通用内容引擎',
    description: 'V2 通用 cms_entries + 动态字段定义，后台 UI 即可增删改字段，支持 21+ 字段类型、3+ 级分类树、标签系统。',
    points: ['动态字段增删改', '21+ 字段类型', '多级分类与标签']
  },
  {
    icon: '👤',
    title: '用户中心',
    description: 'portal-web 独立 SPA，C 端用户注册、登录、资料管理，与后台用户体系完全隔离。',
    points: ['C 端注册登录', '个人资料管理', '独立用户体系']
  },
  {
    icon: '🛡️',
    title: '审计日志',
    description: '后台关键操作完整留痕，平台运营可追溯、可审计，安全合规。',
    points: ['操作日志留痕', '可追溯审计', '安全合规']
  },
  {
    icon: '🏠',
    title: '私有化部署',
    description: 'Docker Compose、宝塔静态 dist、裸机 systemd 三种部署模式，可独立运营，不依赖任何官网。',
    points: ['Docker Compose', '宝塔静态部署', '裸机 systemd']
  }
]

const apps = [
  { icon: '📢', name: '公告管理', desc: '公告发布与通知' },
  { icon: '🎫', name: '工单系统', desc: '问题工单流转' },
  { icon: '☁️', name: '云存储', desc: '对象存储管理' },
  { icon: '🔗', name: '链接收藏', desc: '常用链接管理' },
  { icon: '📝', name: 'Quick Notes', desc: '快速记事' },
  { icon: '✅', name: 'My Todo', desc: '任务清单' },
  { icon: '🔔', name: '通知', desc: '系统通知' },
  { icon: '📰', name: 'CMS', desc: '官网内容管理' }
]

const fields = [
  '文本', '多行文本', '富文本', '数字', '日期', '时间', '日期时间',
  '单选', '多选', '下拉选择', '多级下拉', '开关', '颜色',
  '图片', '图片多选', '文件', '视频', 'URL', 'Email', '电话', 'JSON'
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

.feature-list {
  display: flex;
  flex-direction: column;
  gap: $spacing-2xl;
  max-width: 960px;
  margin: 0 auto;
}

.feature-row {
  display: grid;
  grid-template-columns: 120px 1fr;
  gap: $spacing-xl;
  align-items: start;
  padding: $spacing-2xl;
  background: $bg-white;
  border-radius: $radius-xl;
  border: 1px solid $border-light;
  transition: all $transition-normal;

  &:hover {
    box-shadow: $shadow-lg;
    border-color: transparent;
    transform: translateY(-2px);
  }

  .feature-icon {
    font-size: 56px;
    width: 100px;
    height: 100px;
    background: rgba($primary, 0.08);
    border-radius: $radius-lg;
    display: flex;
    align-items: center;
    justify-content: center;
  }

  .feature-content {
    h2 {
      font-size: 1.5rem;
      color: $text-primary;
      margin-bottom: $spacing-sm;
    }

    p {
      color: $text-secondary;
      font-size: 0.95rem;
      line-height: 1.8;
      margin-bottom: $spacing-md;
    }

    ul {
      list-style: none;
      padding: 0;
      margin: 0;
      display: flex;
      flex-wrap: wrap;
      gap: $spacing-sm;

      li {
        display: inline-flex;
        align-items: center;
        gap: 6px;
        padding: 6px 14px;
        background: $gray-50;
        border-radius: $radius-full;
        font-size: 0.85rem;
        color: $text-secondary;

        &::before {
          content: '✓';
          color: $success;
          font-weight: 700;
        }
      }
    }
  }

  @include mobile {
    grid-template-columns: 1fr;
    padding: $spacing-xl;

    .feature-icon {
      width: 72px;
      height: 72px;
      font-size: 40px;
    }
  }
}

.app-grid {
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
  padding: $spacing-xl;
  text-align: center;
  border: 1px solid $border-light;
  transition: all $transition-normal;

  &:hover {
    transform: translateY(-4px);
    box-shadow: $shadow-md;
    border-color: transparent;
  }

  .app-icon {
    font-size: 40px;
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

.field-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: $spacing-sm;
  max-width: 900px;
  margin: 0 auto;

  @include tablet {
    grid-template-columns: repeat(3, 1fr);
  }

  @include mobile {
    grid-template-columns: repeat(2, 1fr);
  }
}

.field-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: $spacing-md;
  background: $bg-white;
  border-radius: $radius-md;
  border: 1px solid $border-light;
  font-size: 0.9rem;
  color: $text-secondary;

  .field-check {
    color: $success;
    font-weight: 700;
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
