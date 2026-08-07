<template>
  <div class="deploy-page">
    <section class="page-hero">
      <div class="container">
        <div class="page-hero-content">
          <span class="hero-tag">私有部署</span>
          <h1>Cenkor Admin 私有化部署</h1>
          <p>Docker Compose / 宝塔静态 / 裸机 systemd 三种模式，快速上线</p>
        </div>
      </div>
    </section>

    <section class="section">
      <div class="container">
        <div class="deploy-content">
          <SectionTitle
            tag="部署模式"
            title="三种部署方式可选"
            description="根据您的环境选择最合适的交付模式"
          />
          <div class="mode-grid">
            <div class="mode-item" v-for="mode in modes" :key="mode.title">
              <div class="mode-icon">{{ mode.icon }}</div>
              <h4>{{ mode.title }}</h4>
              <p>{{ mode.desc }}</p>
            </div>
          </div>
        </div>
      </div>
    </section>

    <section class="section section-alt">
      <div class="container">
        <SectionTitle
          tag="服务栈"
          title="所需服务"
          description="PostgreSQL + Redis + MinIO + Backend + Admin-Web + Portal-Web"
          :center="true"
        />
        <div class="service-grid">
          <div class="service-item" v-for="svc in services" :key="svc.name">
            <div class="service-icon">{{ svc.icon }}</div>
            <strong>{{ svc.name }}</strong>
            <span>{{ svc.desc }}</span>
          </div>
        </div>
      </div>
    </section>

    <section class="section">
      <div class="container">
        <div class="deploy-content">
          <SectionTitle
            tag="快速开始"
            title="开发环境一分钟启动"
            description="Docker Compose 一键拉起全栈"
          />
          <div class="code-block">
            <pre><code>cp .env.example .env
docker compose up -d
docker compose exec backend alembic upgrade head
docker compose exec backend python -m cenkor_admin.scripts.seed</code></pre>
          </div>
          <div class="env-grid">
            <div class="env-item" v-for="env in envs" :key="env.label">
              <div class="env-icon">{{ env.icon }}</div>
              <div>
                <strong>{{ env.label }}</strong>
                <span>{{ env.value }}</span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </section>

    <section class="cta-section">
      <div class="container">
        <div class="cta-content">
          <h2>准备好部署 Cenkor Admin 了吗？</h2>
          <p>获取完整部署文档与技术指导</p>
          <div class="cta-actions">
            <a :href="urls.github" target="_blank" rel="noopener" class="btn btn-primary btn-large">GitHub 仓库</a>
            <a :href="urls.contact" target="_blank" rel="noopener" class="btn btn-secondary btn-large">联系我们</a>
          </div>
        </div>
      </div>
    </section>
  </div>
</template>

<script setup lang="ts">
import { useHead } from '@unhead/vue'
import SectionTitle from '@/components/SectionTitle.vue'
import { SITE_URLS } from '@/config/site'

const urls = SITE_URLS

useHead({
  title: '辰科Cenkor Admin - 私有部署 | 企业级后台管理平台',
  meta: [
    { name: 'description', content: '辰科Cenkor Admin 私有化部署指南。Docker Compose、宝塔静态 dist、裸机 systemd 三种模式，PostgreSQL + Redis + MinIO + Backend + Admin + Portal。' }
  ]
})

const modes = [
  { icon: '🐳', title: 'Docker Compose', desc: '容器化一键部署，开发生产一致' },
  { icon: '🖥️', title: '宝塔静态 dist', desc: '构建静态前端 + 反代后端，推荐生产' },
  { icon: '⚙️', title: '裸机 systemd', desc: '直接运行后端服务，轻量部署' }
]

const services = [
  { icon: '🗄️', name: 'PostgreSQL 16', desc: '关系型数据库' },
  { icon: '🔴', name: 'Redis 7', desc: '缓存与消息队列' },
  { icon: '☁️', name: 'MinIO', desc: '对象存储' },
  { icon: '⚡', name: 'Backend', desc: 'FastAPI 后端' },
  { icon: '🖥️', name: 'Admin-Web', desc: '运营后台 SPA' },
  { icon: '👤', name: 'Portal-Web', desc: '用户中心 SPA' }
]

const envs = [
  { icon: '🖥️', label: '管理后台', value: 'http://localhost:5173' },
  { icon: '👤', label: '用户中心', value: 'http://localhost:5175' },
  { icon: '⚡', label: 'API 文档', value: 'http://localhost:8000/api/docs' },
  { icon: '🔑', label: '默认账号', value: 'admin@cenkor.cn / admin123' }
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

.deploy-content {
  max-width: 960px;
  margin: 0 auto;
}

.mode-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: $spacing-md;

  @include mobile {
    grid-template-columns: 1fr;
  }
}

.mode-item {
  background: $bg-white;
  border-radius: $radius-md;
  padding: $spacing-xl;
  border: 1px solid $border-light;
  text-align: center;

  .mode-icon {
    font-size: 40px;
    margin-bottom: $spacing-sm;
  }

  h4 {
    font-size: 1.1rem;
    color: $text-primary;
    margin-bottom: $spacing-sm;
  }

  p {
    font-size: 0.85rem;
    color: $text-muted;
    margin: 0;
  }
}

.service-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: $spacing-md;

  @include tablet {
    grid-template-columns: repeat(2, 1fr);
  }

  @include mobile {
    grid-template-columns: 1fr;
  }
}

.service-item {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: $spacing-sm;
  padding: $spacing-lg;
  background: $bg-white;
  border-radius: $radius-md;
  border: 1px solid $border-light;
  text-align: center;

  .service-icon {
    font-size: 28px;
  }

  strong {
    font-size: 0.95rem;
    color: $text-primary;
  }

  span {
    font-size: 0.8rem;
    color: $text-muted;
  }
}

.code-block {
  background: $gray-900;
  border-radius: $radius-md;
  padding: $spacing-lg;
  margin-bottom: $spacing-xl;
  overflow-x: auto;

  pre {
    margin: 0;
    background: none;
    padding: 0;
    color: $gray-100;
    font-size: 0.9rem;
    line-height: 1.7;
  }
}

.env-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: $spacing-md;

  @include mobile {
    grid-template-columns: 1fr;
  }
}

.env-item {
  display: flex;
  align-items: center;
  gap: $spacing-md;
  padding: $spacing-lg;
  background: $bg-white;
  border-radius: $radius-md;
  border: 1px solid $border-light;

  .env-icon {
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
    font-size: 0.85rem;
    color: $text-muted;
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
