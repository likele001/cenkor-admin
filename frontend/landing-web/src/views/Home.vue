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
            辰科 · 企业级平台 × AI 原生内容引擎
          </div>
          <h1>
            一套后台，<br>
            <span class="gradient-text">装下所有业务应用</span>
          </h1>
          <p class="hero-desc">
            FastAPI + Vue3 架构，应用中心 + RBAC 权限 + 工作流 + 用户中心开箱即用。<br>
            内置 <strong>AI CMS</strong>：说一句话建内容模型，AI 起草翻译，以 REST / GraphQL / MCP 供给任意前端与 Agent。
          </p>
          <div class="hero-actions">
            <router-link to="/ai-cms" class="btn btn-primary btn-large">
              AI CMS 能力
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="18" height="18">
                <line x1="5" y1="12" x2="19" y2="12"></line>
                <polyline points="12 5 19 12 12 19"></polyline>
              </svg>
            </router-link>
            <router-link to="/features" class="btn btn-secondary btn-large">
              查看全部功能
            </router-link>
          </div>
          <div class="hero-trust">
            <span><i class="tick">✓</i> 开源 AGPL-3.0</span>
            <span><i class="tick">✓</i> 12 个可插拔应用</span>
            <span><i class="tick">✓</i> AI CMS v0.3.0</span>
            <span><i class="tick">✓</i> 100% 私有化</span>
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
                <div class="sys-item"><span class="dot"></span> AI 对话建模</div>
                <div class="sys-item"><span class="dot"></span> 语义检索</div>
                <div class="sys-item"><span class="dot"></span> 审批工作流</div>
              </div>
            </div>
            <div class="card-footer">
              <span class="pulse-dot"></span>
              <span>系统运行中 · AI CMS 已就绪</span>
              <span class="footer-ver">v0.3.0</span>
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

    <!-- AI CMS Flagship Section -->
    <section class="section ai-section">
      <div class="container">
        <div class="ai-wrap">
          <div class="ai-copy">
            <span class="ai-tag">旗舰能力 · v0.3.0 新增</span>
            <h2>
              AI CMS：<br>
              <span class="ai-gradient">说一句话，建一个内容模型</span>
            </h2>
            <p>
              用中文描述业务，直接生成内容类型与字段定义，草案确认后才落库；
              AI 起草、批量翻译、语义检索、内容体检、多渠道再分发一条链做完。
              建好的内容以 REST / GraphQL / MCP 三种协议交给任何前端与 Agent 消费。
            </p>
            <div class="ai-highlights">
              <div class="hl" v-for="h in aiHighlights" :key="h.title">
                <span class="hl-icon">{{ h.icon }}</span>
                <div>
                  <strong>{{ h.title }}</strong>
                  <span>{{ h.desc }}</span>
                </div>
              </div>
            </div>
            <div class="ai-actions">
              <router-link to="/ai-cms" class="btn btn-primary btn-large">
                AI CMS 完整能力
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="18" height="18">
                  <line x1="5" y1="12" x2="19" y2="12"></line>
                  <polyline points="12 5 19 12 12 19"></polyline>
                </svg>
              </router-link>
              <router-link to="/deploy" class="btn btn-ghost btn-large">如何接入模型</router-link>
            </div>
            <p class="ai-note">AI 是可选增强 —— 不配模型时，建模、审核、REST / GraphQL / MCP 全部照常工作。</p>
          </div>

          <div class="ai-visual">
            <div class="ai-console">
              <div class="console-head">
                <div class="console-dots"><span></span><span></span><span></span></div>
                <span>AI 内容生产线</span>
              </div>
              <div class="console-body">
                <div class="step" v-for="(s, i) in aiSteps" :key="s.name" :style="{ animationDelay: `${i * 0.12}s` }">
                  <span class="step-no">{{ String(i + 1).padStart(2, '0') }}</span>
                  <span class="step-icon">{{ s.icon }}</span>
                  <span class="step-name">{{ s.name }}</span>
                  <span class="step-state" :class="s.state">{{ s.state === 'done' ? '已完成' : '运行中' }}</span>
                </div>
              </div>
              <div class="console-foot">
                <span class="pill">10 道工序</span>
                <span class="pill">逐条留痕</span>
                <span class="pill">人工闸口</span>
              </div>
            </div>
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
          description="AI 内容引擎 + 应用中心 + 权限 + 工作流 + 开放接口，从搭建到运营全流程覆盖"
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
          title="12 个可插拔业务应用"
          description="CRM、ERP、MES、工作流、CMS、工单、云存储等，通过应用中心统一安装，支持授权码 OTA 升级"
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

    <!-- FAQ Section -->
    <section class="section section-alt faq-section">
      <div class="container">
        <SectionTitle
          tag="常见问题"
          title="关于 Cenkor Admin 你可能想知道的"
          description="部署方式、开源授权、权限与内容引擎…… 一站式解答"
          :center="true"
        />
        <div class="faq-list">
          <div class="faq-item" v-for="(faq, index) in faqs" :key="faq.q">
            <button class="faq-question" @click="toggleFaq(index)">
              <span>{{ faq.q }}</span>
              <span class="faq-icon" :class="{ open: openIndex === index }">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="16" height="16"><line x1="12" y1="5" x2="12" y2="19"></line><line x1="5" y1="12" x2="19" y2="12"></line></svg>
              </span>
            </button>
            <div class="faq-answer" :class="{ open: openIndex === index }">
              <p>{{ faq.a }}</p>
            </div>
          </div>
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
import { ref } from 'vue'
import SectionTitle from '@/components/SectionTitle.vue'
import FeatureCard from '@/components/FeatureCard.vue'
import ScrollReveal from '@/components/ScrollReveal.vue'
import CounterUp from '@/components/CounterUp.vue'
import { SITE_URLS } from '@/config/site'

const urls = SITE_URLS

const stats = [
  { value: 12, label: '可插拔业务应用', suffix: '' },
  { value: 21, label: 'CMS 字段类型', suffix: '+' },
  { value: 10, label: '道 AI 内容工序', suffix: '' },
  { value: 3, label: '内容出口协议', suffix: ' 种' }
]

const aiHighlights = [
  { icon: '💬', title: '对话式建模', desc: '中文描述 → 内容类型草案，确认才落库' },
  { icon: '✍️', title: '起草与翻译', desc: '草稿强制人审，多语言一条命令批量出' },
  { icon: '🏭', title: '内容生产线', desc: '批量生产、体检、质检、选题、问答、配图' },
  { icon: '🔌', title: '三协议出口', desc: 'REST / GraphQL / MCP，Agent 直接消费' }
]

const aiSteps = [
  { icon: '🎯', name: '选题 Gap 分析', state: 'done' },
  { icon: '📝', name: '条目起草', state: 'done' },
  { icon: '🔍', name: '语义检索命中知识库', state: 'done' },
  { icon: '🖼️', name: '配图生成并落媒体库', state: 'running' },
  { icon: '🌐', name: '多语言翻译', state: 'queued' },
  { icon: '🩺', name: '发布前健康度体检', state: 'queued' }
]

const features = [
  {
    icon: '🤖',
    title: 'AI CMS 内容引擎',
    description: '对话式建模、AI 起草翻译、语义检索、内容生产线，内容以 REST / GraphQL / MCP 三协议出口',
    features: ['对话式建模', 'AI 起草与翻译', 'MCP / GraphQL 出口'],
    color: '#8b5cf6'
  },
  {
    icon: '🏪',
    title: '应用中心',
    description: '应用按需安装/卸载，自动注册权限、菜单、内容类型，业务模块即插即用',
    features: ['应用安装卸载', '权限自动注册', '授权码 OTA 升级'],
    color: '#10b981'
  },
  {
    icon: '🔐',
    title: 'RBAC 权限',
    description: '角色、权限规则、数据权限三级控制，后台/前台双用户体系隔离',
    features: ['角色管理', '数据权限', '双用户体系'],
    color: '#0ea5e9'
  },
  {
    icon: '📝',
    title: '动态建模与多站点',
    description: '21+ 字段类型后台即可增删，多级分类标签，多站点站群会话级隔离',
    features: ['动态字段', '多级分类标签', '多站点站群'],
    color: '#f59e0b'
  },
  {
    icon: '🔀',
    title: '工作流审批',
    description: '可视化流程编排，待办/已办/抄送/单据齐全，AI 工作流按拓扑序执行并检测环',
    features: ['可视化编排', '待办已办抄送', 'AI 工作流引擎'],
    color: '#ec4899'
  },
  {
    icon: '📡',
    title: '发布与统计',
    description: '官网、Webhook、微信公众号草稿箱、导出多渠道分发；内容埋点与效果分析内置',
    features: ['多渠道发布', '内容埋点', '停留与跳出分析'],
    color: '#14b8a6'
  },
  {
    icon: '🔌',
    title: '开放接口',
    description: 'REST 内容引擎、GraphQL 查询、MCP Server 三种协议并存，权限同一套底座',
    features: ['REST 内容引擎', 'GraphQL', 'MCP Server'],
    color: '#6366f1'
  },
  {
    icon: '👤',
    title: '用户中心',
    description: 'C 端注册登录、个人资料、订阅管理，前后台用户完全隔离',
    features: ['注册登录', '资料管理', '订阅管理'],
    color: '#06b6d4'
  },
  {
    icon: '🚀',
    title: '私有化与在线升级',
    description: '三种部署模式；核心平台发现新版本即提示，应用支持免重启 OTA 升级',
    features: ['Docker / 宝塔 / 裸机', '版本检查提示', '应用 OTA 升级'],
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
  { icon: '🤖', name: 'AI CMS', installed: true },
  { icon: '📢', name: '公告', installed: true },
  { icon: '🎫', name: '工单', installed: true },
  { icon: '🔀', name: '工作流', installed: true },
  { icon: '📇', name: 'CRM', installed: true },
  { icon: '☁️', name: '云存储', installed: true }
]

const apps = [
  { icon: '🤖', name: 'AI CMS', desc: 'AI 原生内容引擎' },
  { icon: '📇', name: 'CRM 销售', desc: '线索到回款全流程' },
  { icon: '🏭', name: 'ERP 管理', desc: '客户/供应商/进销存' },
  { icon: '⚙️', name: 'MES 制造', desc: '订单/排产/报工' },
  { icon: '🔀', name: '工作流审批', desc: '可视化流程编排' },
  { icon: '🎫', name: '工单系统', desc: '问题工单流转处理' },
  { icon: '☁️', name: '云存储', desc: '多驱动对象存储' },
  { icon: '📢', name: '公告管理', desc: '公告发布与通知' },
  { icon: '🔔', name: '通知中心', desc: '多渠道通知推送' },
  { icon: '🔗', name: '链接收藏', desc: '常用链接管理' },
  { icon: '📝', name: 'Quick Notes', desc: '快速记事' },
  { icon: '✅', name: 'My Todo', desc: '任务清单' }
]

const openIndex = ref(-1)

const toggleFaq = (index: number) => {
  openIndex.value = openIndex.value === index ? -1 : index
}

const faqs = [
  { q: 'Cenkor Admin 是什么？适合哪些场景？', a: 'Cenkor Admin 是一款企业级平台（FastAPI + Vue3），内置应用中心、RBAC 权限、工作流审批、AI CMS 内容引擎、用户中心与审计日志。适合需要快速搭建内部管理系统、内容站点与官网，或对既有系统做后台底座的企业与团队。' },
  { q: 'AI CMS 和普通 CMS 有什么不同？', a: '普通 CMS 是先有模型再填内容；AI CMS 是「说人话建模型」——用中文描述业务需求，直接生成内容类型与字段定义（草案先给你看，确认才落库）。再加 AI 起草、批量翻译、语义检索、内容体检与多渠道再分发，最后以 REST / GraphQL / MCP 三种协议交给任意前端与 Agent 消费。' },
  { q: '不接 AI 能用吗？', a: '能，而且是刻意设计的。AI 是可选增强不是运行必需：未配置模型时 AI 端点返回明确的 503 提示，而建模 UI、版本管理、多语言、审核、REST / GraphQL / MCP 只读工具完全不受影响。内网离线环境也能先把内容骨架跑起来。' },
  { q: 'AI 怎么写、用哪个模型？数据会外传吗？', a: '任何 OpenAI 兼容协议的服务都能接：OpenAI、DeepSeek、通义千问、Moonshot、智谱、本地 vLLM / Ollama 或自建网关，改 base_url 与模型名即可，chat 与 embedding 还能绑不同服务商。数据只发往你自己配置的模型服务，平台不中转、不代建账号。' },
  { q: 'AI 会不会乱写内容？', a: '三道闸口：起草强制 draft 状态必须人审才可发布；知识库把产品手册、FAQ、历史方案变成可检索依据，让模型引用事实而不是编事实；问答检索查不到时明确返回「查不到」，宁可空着也不编。另外还有抽样质检与模型 A/B，好坏有数据可比。' },
  { q: '支持哪些部署方式？怎么升级？', a: '三种：Docker Compose（一条命令拉起全栈）、宝塔静态、裸机 systemd。核心平台有新版本时后台顶部会出现升级横幅，用 upgrade.sh 或拉新镜像完成；可插拔应用在应用中心用授权码 OTA 升级，免重启。' },
  { q: '是开源的还是商业的？', a: '开源。代码托管在 GitHub（AGPL-3.0 协议），可自由下载部署使用；应用中心按需扩展，业务模块即插即用。' },
  { q: '应用中心是怎么工作的？', a: '每个应用通过 manifest 声明内容类型、字段、分类、权限与菜单，安装时自动注册到系统，卸载时自动清理，无需改代码。当前内置 12 个可插拔应用。' },
  { q: 'RBAC 权限如何隔离？', a: '角色、权限规则、数据权限三级控制；后台（运营）与前台（C 端用户）双用户体系完全隔离。CMS 与 AI 能力还做了细分权限：读配置与改密钥是两码事，审核动作也独立于编辑。' },
  { q: '需要哪些基础服务？', a: 'PostgreSQL（主库）、Redis（缓存/队列）、MinIO（对象存储）以及 backend / admin-web / portal-web 三端服务，容器化一键编排。' }
]
</script>

<style lang="scss" scoped>
// Hero
.hero {
  position: relative;
  padding: 100px 0 64px;
  overflow: hidden;
  min-height: 72vh;
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

    strong {
      color: $primary-dark;
      font-weight: 700;
    }
  }

  .hero-actions {
    display: flex;
    gap: $spacing-md;
    flex-wrap: wrap;
  }

  .hero-trust {
    display: flex;
    gap: $spacing-lg;
    flex-wrap: wrap;
    margin-top: $spacing-lg;

    span {
      display: inline-flex;
      align-items: center;
      gap: 6px;
      font-size: 13px;
      color: $text-muted;

      .tick {
        width: 18px;
        height: 18px;
        border-radius: 50%;
        background: rgba($success, 0.12);
        color: $success;
        font-style: normal;
        font-size: 11px;
        font-weight: 600;
        display: inline-flex;
        align-items: center;
        justify-content: center;
      }
    }
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

  .card-footer {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: $spacing-sm $spacing-lg;
    background: $gray-50;
    border-top: 1px solid $border-light;
    font-size: 12px;
    color: $text-muted;

    .pulse-dot {
      width: 8px;
      height: 8px;
      border-radius: 50%;
      background: $success;
      animation: pulse 2s infinite;
    }

    .footer-ver {
      margin-left: auto;
      font-size: 11px;
      color: $text-muted;
    }
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

// AI CMS 旗舰板块
.ai-section {
  background: linear-gradient(160deg, #0f172a 0%, #1e293b 55%, #0f172a 100%);
  position: relative;
  overflow: hidden;

  &::before {
    content: '';
    position: absolute;
    top: -240px;
    right: -160px;
    width: 620px;
    height: 620px;
    background: radial-gradient(circle, rgba(139, 92, 246, 0.22) 0%, transparent 70%);
    border-radius: 50%;
  }

  &::after {
    content: '';
    position: absolute;
    bottom: -260px;
    left: -180px;
    width: 560px;
    height: 560px;
    background: radial-gradient(circle, rgba($primary, 0.16) 0%, transparent 70%);
    border-radius: 50%;
  }
}

.ai-wrap {
  position: relative;
  z-index: 1;
  display: grid;
  grid-template-columns: 1.05fr 0.95fr;
  gap: $spacing-3xl;
  align-items: center;

  @include tablet {
    grid-template-columns: 1fr;
    gap: $spacing-2xl;
  }

  @include mobile {
    grid-template-columns: 1fr;
    gap: $spacing-2xl;
  }
}

.ai-copy {
  .ai-tag {
    display: inline-block;
    padding: 6px 14px;
    background: rgba(139, 92, 246, 0.16);
    border: 1px solid rgba(139, 92, 246, 0.35);
    color: #c4b5fd;
    font-size: 12px;
    font-weight: 600;
    border-radius: $radius-full;
    margin-bottom: $spacing-md;
  }

  h2 {
    font-size: 2.4rem;
    font-weight: 800;
    line-height: 1.25;
    color: $text-white;
    margin-bottom: $spacing-md;

    @include mobile {
      font-size: 1.85rem;
    }
  }

  .ai-gradient {
    background: linear-gradient(135deg, #a78bfa 0%, $primary-light 100%);
    -webkit-background-clip: text;
    background-clip: text;
    -webkit-text-fill-color: transparent;
  }

  > p {
    font-size: 1rem;
    color: $gray-400;
    line-height: 1.9;
    margin-bottom: $spacing-lg;
  }
}

.ai-highlights {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: $spacing-md;
  margin-bottom: $spacing-xl;

  @include mobile {
    grid-template-columns: 1fr;
  }
}

.hl {
  display: flex;
  gap: $spacing-sm;
  padding: $spacing-md;
  background: rgba(255, 255, 255, 0.04);
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: $radius-md;

  .hl-icon {
    font-size: 20px;
    line-height: 1.2;
  }

  strong {
    display: block;
    font-size: 0.88rem;
    color: $text-white;
    margin-bottom: 2px;
  }

  span {
    font-size: 0.78rem;
    color: $gray-400;
    line-height: 1.6;
  }
}

.ai-actions {
  display: flex;
  gap: $spacing-md;
  flex-wrap: wrap;
  align-items: center;
}

.ai-note {
  margin: $spacing-lg 0 0;
  font-size: 0.8rem;
  color: $gray-500;
}

.ai-visual {
  @include tablet {
    order: -1;
  }
}

.ai-console {
  background: rgba(15, 23, 42, 0.75);
  border: 1px solid rgba(148, 163, 184, 0.18);
  border-radius: $radius-xl;
  box-shadow: 0 24px 60px rgba(0, 0, 0, 0.45);
  overflow: hidden;
  backdrop-filter: blur(8px);
}

.console-head {
  display: flex;
  align-items: center;
  gap: $spacing-md;
  padding: $spacing-md $spacing-lg;
  border-bottom: 1px solid rgba(148, 163, 184, 0.14);
  font-size: 12px;
  color: $gray-400;

  .console-dots {
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
}

.console-body {
  padding: $spacing-md $spacing-lg;
}

.step {
  display: grid;
  grid-template-columns: 28px 24px 1fr auto;
  align-items: center;
  gap: $spacing-sm;
  padding: 11px 0;
  border-bottom: 1px dashed rgba(148, 163, 184, 0.12);
  animation: stepIn 0.5s ease both;

  &:last-child {
    border-bottom: none;
  }

  .step-no {
    font-family: $font-mono;
    font-size: 11px;
    color: $gray-500;
  }

  .step-icon {
    font-size: 15px;
  }

  .step-name {
    font-size: 0.85rem;
    color: $gray-300;
  }

  .step-state {
    font-size: 10px;
    padding: 2px 8px;
    border-radius: $radius-full;

    &.done {
      background: rgba($success, 0.15);
      color: $primary-light;
    }

    &.running {
      background: rgba(139, 92, 246, 0.18);
      color: #c4b5fd;
    }

    &.queued {
      background: rgba(148, 163, 184, 0.12);
      color: $gray-400;
    }
  }
}

@keyframes stepIn {
  from {
    opacity: 0;
    transform: translateX(-8px);
  }
  to {
    opacity: 1;
    transform: translateX(0);
  }
}

.console-foot {
  display: flex;
  gap: $spacing-sm;
  flex-wrap: wrap;
  padding: $spacing-md $spacing-lg;
  border-top: 1px solid rgba(148, 163, 184, 0.14);

  .pill {
    font-size: 11px;
    padding: 4px 10px;
    border-radius: $radius-full;
    background: rgba($primary, 0.12);
    color: $primary-light;
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

// FAQ
.faq-section {
  background: $bg-white;
}

.faq-list {
  max-width: 760px;
  margin: 0 auto;
  display: flex;
  flex-direction: column;
  gap: $spacing-sm;
}

.faq-item {
  background: $bg-white;
  border: 1px solid $border-light;
  border-radius: $radius-md;
  overflow: hidden;
  transition: border-color $transition-fast;

  &:hover {
    border-color: rgba($primary, 0.3);
  }
}

.faq-question {
  width: 100%;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: $spacing-md;
  padding: $spacing-md $spacing-lg;
  background: none;
  border: none;
  cursor: pointer;
  text-align: left;
  font-size: 1rem;
  font-weight: 500;
  color: $text-primary;
  font-family: inherit;

  &:hover {
    color: $primary;
  }
}

.faq-icon {
  flex-shrink: 0;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  border-radius: $radius-full;
  background: $gray-100;
  color: $text-secondary;
  transition: all $transition-fast;

  svg {
    transition: transform $transition-fast;
  }

  &.open {
    background: rgba($primary, 0.1);
    color: $primary;

    svg {
      transform: rotate(135deg);
    }
  }
}

.faq-answer {
  max-height: 0;
  overflow: hidden;
  transition: max-height $transition-normal;

  &.open {
    max-height: 320px;
  }

  p {
    margin: 0;
    padding: 0 $spacing-lg $spacing-lg;
    color: $text-secondary;
    font-size: 0.95rem;
    line-height: 1.75;
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
