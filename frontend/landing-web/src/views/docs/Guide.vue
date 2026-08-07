<template>
  <div class="guide-page">
    <section class="page-hero">
      <div class="container">
        <div class="page-hero-content">
          <span class="hero-tag">使用指南</span>
          <h1>Cenkor Admin 使用入门</h1>
          <p>从部署上线到应用安装，快速了解平台全貌</p>
        </div>
      </div>
    </section>

    <section class="section">
      <div class="container">
        <div class="guide-content">
          <div class="guide-nav">
            <div
              class="guide-nav-item"
              v-for="(sec, i) in sections"
              :key="sec.title"
              :class="{ active: activeSection === i }"
              @click="activeSection = i"
            >
              <span class="nav-icon">{{ sec.icon }}</span>
              <span>{{ sec.title }}</span>
            </div>
          </div>

          <div class="guide-body">
            <template v-for="(sec, i) in sections" :key="sec.title">
              <div v-show="activeSection === i" class="guide-section">
                <h2>{{ sec.title }}</h2>
                <div class="guide-text">
                  <p v-for="(p, j) in sec.paragraphs" :key="j">{{ p }}</p>
                </div>
                <div class="guide-tip" v-if="sec.tip">
                  <span class="tip-icon">💡</span>
                  <p>{{ sec.tip }}</p>
                </div>
              </div>
            </template>
          </div>
        </div>
      </div>
    </section>

    <section class="cta-section">
      <div class="container">
        <div class="cta-content">
          <h2>需要更详细的文档？</h2>
          <p>完整使用文档与技术支持随时为您提供</p>
          <div class="cta-actions">
            <a :href="urls.github" target="_blank" rel="noopener" class="btn btn-primary btn-large">GitHub 仓库</a>
            <router-link to="/deploy" class="btn btn-secondary btn-large">查看部署文档</router-link>
          </div>
        </div>
      </div>
    </section>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { useHead } from '@unhead/vue'
import { SITE_URLS } from '@/config/site'

const urls = SITE_URLS
const activeSection = ref(0)

useHead({
  title: '辰科Cenkor Admin - 使用指南 | 企业级后台管理平台',
  meta: [
    { name: 'description', content: '辰科Cenkor Admin 使用入门指南：系统登录、应用中心安装、RBAC 权限、CMS 内容管理、用户中心快速上手。' }
  ]
})

const sections = [
  {
    icon: '🔑',
    title: '系统登录',
    paragraphs: [
      '部署完成后，使用管理后台（admin-web）地址访问，用安装时设置的管理员账号登录。',
      '系统采用 JWT 双用户体系：后台（auth_users）管理员与前台（portal_users）终端用户完全隔离。'
    ],
    tip: '生产环境务必修改默认管理员密码，并为不同运营人员分配独立账号与角色权限。'
  },
  {
    icon: '🏪',
    title: '应用中心安装',
    paragraphs: [
      '进入后台「应用中心」，可查看所有已扫描的应用及其安装状态（已安装/未安装/待升级）。',
      '点击安装，应用会自动注册权限、菜单、内容类型与字段定义，安装后即可使用。'
    ],
    tip: '应用通过 manifest 声明业务数据，安装时自动注册，卸载时自动清理，即插即用。'
  },
  {
    icon: '📝',
    title: 'CMS 内容管理',
    paragraphs: [
      '使用通用内容引擎，后台即可创建内容类型、动态增删字段（支持 21+ 字段类型）。',
      '配置多级分类与标签，维护内容条目，前台通过公开只读 API 消费。'
    ],
    tip: 'CMS 提供 /api/v1/public/* 公开接口，任意前端（包括独立官网）都可直接调用。'
  },
  {
    icon: '🔐',
    title: 'RBAC 权限管理',
    paragraphs: [
      '配置角色、权限规则、数据权限，控制运营人员可访问的功能范围。',
      '应用安装时可自动注册权限点，并可对角色进行权限委派（permissions_grants）。'
    ],
    tip: '先定义角色与权限规则，再为用户分配角色，保证权限体系清晰可控。'
  },
  {
    icon: '👤',
    title: '用户中心',
    paragraphs: [
      'portal-web 提供 C 端用户注册、登录、资料管理能力，与后台用户体系完全隔离。',
      '终端用户通过用户中心管理自己的账号与订阅。'
    ],
    tip: '前后台用户隔离设计，避免安全边界混淆，适合平台化运营。'
  },
  {
    icon: '🛡️',
    title: '审计与安全',
    paragraphs: [
      '后台关键操作完整记录审计日志，平台运营可追溯、可审计。',
      '结合 JWT 双体系鉴权与 RBAC 权限控制，保障平台数据安全。'
    ],
    tip: '建议定期备份 PostgreSQL 数据库，并配置异地备份保障数据安全。'
  }
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

.guide-content {
  display: grid;
  grid-template-columns: 280px 1fr;
  gap: $spacing-2xl;
  max-width: 1000px;
  margin: 0 auto;
  align-items: start;

  @include mobile {
    grid-template-columns: 1fr;
  }
}

.guide-nav {
  position: sticky;
  top: 100px;
  display: flex;
  flex-direction: column;
  gap: $spacing-xs;
  background: $bg-white;
  border-radius: $radius-lg;
  padding: $spacing-md;
  border: 1px solid $border-light;

  @include mobile {
    position: static;
    flex-direction: row;
    flex-wrap: wrap;
  }
}

.guide-nav-item {
  display: flex;
  align-items: center;
  gap: $spacing-sm;
  padding: $spacing-sm $spacing-md;
  border-radius: $radius-sm;
  cursor: pointer;
  font-size: 0.9rem;
  color: $text-secondary;
  transition: all $transition-fast;

  &:hover {
    background: $gray-50;
    color: $text-primary;
  }

  &.active {
    background: rgba($primary, 0.1);
    color: $primary;
    font-weight: 600;
  }

  .nav-icon {
    font-size: 18px;
  }
}

.guide-body {
  background: $bg-white;
  border-radius: $radius-lg;
  padding: $spacing-2xl;
  border: 1px solid $border-light;
  min-height: 400px;

  @include mobile {
    padding: $spacing-xl;
  }
}

.guide-section {
  h2 {
    font-size: 1.5rem;
    color: $text-primary;
    margin-bottom: $spacing-lg;
  }
}

.guide-text {
  p {
    color: $text-secondary;
    font-size: 0.98rem;
    line-height: 1.9;
    margin-bottom: $spacing-md;
  }
}

.guide-tip {
  display: flex;
  gap: $spacing-md;
  padding: $spacing-md $spacing-lg;
  background: rgba($warning, 0.08);
  border-left: 3px solid $warning;
  border-radius: 0 $radius-md $radius-md 0;

  .tip-icon {
    font-size: 20px;
  }

  p {
    color: $text-secondary;
    font-size: 0.9rem;
    line-height: 1.7;
    margin: 0;
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
