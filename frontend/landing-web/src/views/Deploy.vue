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
            title="一条命令拉起全栈"
            description="前置只需 Docker + Compose v2，其余交给脚本"
          />
          <div class="code-block">
            <pre><code>git clone https://github.com/likele001/cenkor-admin.git
cd cenkor-admin
bash scripts/bootstrap-fullstack.sh</code></pre>
          </div>
          <p class="code-note">
            脚本会自动生成 <code>.env</code>（随机密钥）→ 构建并拉起全部容器 → 等待后端就绪 →
            执行数据库迁移与种子数据 → 在终端打印访问地址与<strong>初始管理员密码</strong>。
            中途无需干预。
          </p>
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

    <section class="section section-alt">
      <div class="container">
        <div class="deploy-content">
          <SectionTitle
            tag="首次登录"
            title="初始管理员密码怎么拿"
            description="仓库不设任何默认口令，密码在首次初始化时随机生成"
          />
          <div class="pw-panel">
            <div class="pw-alert">
              <strong>⚠️ 本仓库没有任何默认口令</strong>
              <p>
                诸如 <code>admin123</code>、<code>admin@123</code> 这类「常见默认密码」<strong>一律无效</strong>。
                管理员的初始口令在首次初始化时<strong>随机生成</strong>，并且<strong>只完整显示一次</strong>——
                数据库里只存 bcrypt 哈希，事后推不回来。
              </p>
            </div>
            <ol class="pw-steps">
              <li v-for="(s, i) in pwSteps" :key="s.title">
                <div class="pw-step-head">
                  <span class="pw-step-no">{{ i + 1 }}</span>
                  <span class="pw-step-tag">{{ s.tag }}</span>
                  <strong>{{ s.title }}</strong>
                </div>
                <p>{{ s.desc }}</p>
                <div v-if="s.code" class="code-block">
                  <pre><code>{{ s.code }}</code></pre>
                </div>
              </li>
            </ol>
            <p class="pw-tip">
              账号固定为 <code>admin@cenkor.cn</code>（用户名 <code>admin</code> 同样可登录）。
              登录时按提示完成滑块验证；<strong>首次登录后请立即修改为只有你知道的口令</strong>。
              想一开始就自己定：部署前在 <code>.env</code> 里写
              <code>CENKOR_ADMIN_PASSWORD=你的口令</code>（设置后不再随机、也不再打印）。
            </p>
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
import SectionTitle from '@/components/SectionTitle.vue'
import { SITE_URLS } from '@/config/site'

const urls = SITE_URLS

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
  { icon: '🖥️', label: '管理后台', value: 'http://<服务器IP>:5185' },
  { icon: '👤', label: '用户中心', value: 'http://<服务器IP>:5192' },
  { icon: '⚡', label: 'API 文档', value: 'http://<服务器IP>:8001/api/docs' },
  { icon: '🔑', label: '管理员账号', value: 'admin@cenkor.cn（初始密码见下方说明）' }
]

const pwSteps = [
  {
    tag: '推荐',
    title: '部署脚本跑完，直接看终端输出',
    desc: 'bash scripts/bootstrap-fullstack.sh 收尾时会打印管理员账号与初始密码。⚠️ 只显示这一次，请立即保存。',
    code: `====================================================================
  已创建管理员：admin@cenkor.cn
  初始密码    ：xxxxxxxxxxxxxxxx
  ⚠️ 此口令只显示这一次，请立即登录并修改
====================================================================`
  },
  {
    tag: '找回',
    title: '当时没记下来 → 翻服务端日志',
    desc: '口令唯一留痕在容器日志里。注意：容器重建（docker compose down 不带 -v 也会重建容器）后日志会清空，届时只能走第 3 步。',
    code: `docker compose -f docker-compose.fullstack.yml logs backend | grep -A3 已创建管理员`
  },
  {
    tag: '重置',
    title: '日志也没了 → 用重置脚本（同时踢掉旧会话）',
    desc: '不传参数则随机生成并打印；传 --password 则设为指定值。Docker 与宝塔裸机两种部署会自动识别。',
    code: `bash scripts/reset-admin-password.sh                      # 随机生成新口令
bash scripts/reset-admin-password.sh --password '你的新口令'   # 指定口令`
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

.code-note {
  margin: calc(-1 * #{$spacing-md}) 0 0;
  font-size: 0.85rem;
  line-height: 1.8;
  color: $text-muted;

  code {
    padding: 2px 6px;
    border-radius: 4px;
    background: $gray-50;
    border: 1px solid $border-light;
    font-size: 0.85em;
  }

  strong {
    color: $text-primary;
  }
}

// —— 初始管理员密码说明 ——
.pw-panel {
  display: flex;
  flex-direction: column;
  gap: $spacing-lg;
}

.pw-alert {
  padding: $spacing-lg;
  border-radius: $radius-md;
  border: 1px solid rgba(217, 119, 6, 0.35);
  background: rgba(217, 119, 6, 0.08);

  strong {
    display: block;
    margin-bottom: $spacing-sm;
    color: #b45309;
    font-size: 1rem;
  }

  p {
    margin: 0;
    font-size: 0.875rem;
    line-height: 1.8;
    color: $text-secondary;
  }

  code {
    padding: 2px 6px;
    border-radius: 4px;
    background: rgba(0, 0, 0, 0.06);
    font-size: 0.85em;
  }
}

.pw-steps {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: $spacing-md;

  > li {
    padding: $spacing-lg;
    background: $bg-white;
    border: 1px solid $border-light;
    border-radius: $radius-md;
  }

  .pw-step-head {
    display: flex;
    align-items: center;
    gap: $spacing-sm;
    margin-bottom: $spacing-sm;
    flex-wrap: wrap;
  }

  .pw-step-no {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 22px;
    height: 22px;
    flex: 0 0 22px;
    border-radius: $radius-full;
    background: $primary;
    color: $text-white;
    font-size: 12px;
    font-weight: 700;
  }

  .pw-step-tag {
    padding: 2px 10px;
    border-radius: $radius-full;
    background: rgba($primary, 0.1);
    color: $primary;
    font-size: 12px;
    font-weight: 600;
  }

  strong {
    font-size: 0.95rem;
    color: $text-primary;
  }

  p {
    margin: 0 0 $spacing-sm;
    font-size: 0.85rem;
    line-height: 1.8;
    color: $text-muted;
  }

  // 步骤内的代码块收紧间距
  .code-block {
    margin-bottom: 0;
    padding: $spacing-md;
  }
}

.pw-tip {
  margin: 0;
  padding: $spacing-md $spacing-lg;
  border-left: 3px solid $primary;
  border-radius: 0 $radius-md $radius-md 0;
  background: $gray-50;
  font-size: 0.85rem;
  line-height: 1.8;
  color: $text-secondary;

  code {
    padding: 2px 6px;
    border-radius: 4px;
    background: $bg-white;
    border: 1px solid $border-light;
    font-size: 0.85em;
  }

  strong {
    color: $text-primary;
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
