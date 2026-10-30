<template>
  <div class="features-page">
    <section class="page-hero">
      <div class="container">
        <div class="page-hero-content">
          <span class="hero-tag">核心功能</span>
          <h1>平台全功能一览</h1>
          <p>AI CMS + 应用中心 + RBAC 权限 + 工作流审批 + 开放接口，一站配齐</p>
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
          tag="AI CMS 生产线"
          title="十道 AI 工序，每道都能单独用"
          description="不是一个大而全的「AI 按钮」，而是十个独立端点：用到哪个开哪个"
          :center="true"
        />
        <div class="ai-line">
          <div class="ai-line-item" v-for="a in aiCapabilities" :key="a.name">
            <span class="ai-line-icon">{{ a.icon }}</span>
            <div>
              <strong>{{ a.name }}</strong>
              <span>{{ a.desc }}</span>
            </div>
          </div>
        </div>
        <div class="ai-line-more">
          <router-link to="/ai-cms" class="btn btn-primary">查看 AI CMS 完整能力</router-link>
        </div>
      </div>
    </section>

    <section class="section">
      <div class="container">
        <SectionTitle
          tag="应用中心"
          title="应用按需安装"
          description="每个应用声明内容类型、字段、权限、菜单，安装时自动注册，支持授权码 OTA 升级"
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

    <section class="section section-alt">
      <div class="container">
        <SectionTitle
          tag="内容引擎"
          title="21+ 字段类型的通用建模"
          description="后台即可动态增删字段，无需改代码；字段改名改类型前先算影响面"
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
import SectionTitle from '@/components/SectionTitle.vue'
import ScrollReveal from '@/components/ScrollReveal.vue'

const featureItems = [
  {
    icon: '🤖',
    title: 'AI CMS 内容引擎',
    description: '用中文描述业务直接生成内容类型与字段定义，草案确认后才落库；AI 起草强制人审，多语言一条命令批量翻译，检索接入 rerank 精排并保留出处。',
    points: ['对话式建模（草案 → 落库）', 'AI 起草与批量翻译', '语义检索 + 引用可回溯']
  },
  {
    icon: '🏪',
    title: '应用中心',
    description: '应用通过 manifest 声明内容类型、字段、分类、权限与菜单，安装时自动注册到系统，卸载时自动清理，即插即用。',
    points: ['应用安装/卸载/升级', '权限与菜单自动注册', '授权码 OTA 免重启升级']
  },
  {
    icon: '🔐',
    title: 'RBAC 权限',
    description: '角色、权限规则、数据权限三级控制。后台（auth_users）与前台（portal_users）双用户体系完全隔离，CMS 与 AI 能力还做了细分权限。',
    points: ['角色与权限规则', '数据权限范围控制', '审核独立于编辑']
  },
  {
    icon: '📝',
    title: '动态建模与多站点',
    description: 'V2 通用 cms_entries + 动态字段定义，后台 UI 即可增删改字段，支持 21+ 字段类型、多级分类树、标签系统与多站点站群。',
    points: ['动态字段增删改', '21+ 字段类型', '多站点会话级隔离']
  },
  {
    icon: '🔀',
    title: '工作流审批',
    description: '可视化流程编排，我的待办 / 我发起的 / 我的已办 / 抄送我的 / 单据管理齐全；AI 工作流按拓扑序执行，画环当场拦住。',
    points: ['可视化流程编排', '待办已办抄送', 'AI 工作流引擎']
  },
  {
    icon: '📡',
    title: '发布与效果统计',
    description: '官网、Webhook、微信公众号草稿箱、导出四个渠道分发；内容埋点一行脚本接入，停留时长与跳出判定按会话归并后统计。',
    points: ['多渠道分发', '零改造内容埋点', '效果分析看板']
  },
  {
    icon: '🔌',
    title: '开放接口',
    description: 'REST 内容引擎、GraphQL 只读查询、MCP Server 三种协议并存，共享同一套权限与检索底座，不做三份数据。',
    points: ['REST 内容引擎', 'GraphQL（strawberry）', 'MCP HTTP / stdio']
  },
  {
    icon: '🚀',
    title: '在线升级',
    description: '核心平台主动查询最新版本并在工作台提示，upgrade.sh 完成备份→覆盖→迁移→重启→健康检查；应用侧走授权码 OTA。',
    points: ['版本检查与提示', '升级脚本自动迁移', '应用免重启 OTA']
  },
  {
    icon: '🏠',
    title: '私有化部署',
    description: 'Docker Compose、宝塔静态 dist、裸机 systemd 三种部署模式，可独立运营，不依赖任何官网。',
    points: ['Docker Compose', '宝塔静态部署', '裸机 systemd']
  }
]

const aiCapabilities = [
  { icon: '🏭', name: '批量生产', desc: '一次派一批选题，逐篇落草稿，状态全落库' },
  { icon: '🩺', name: '内容健康度体检', desc: '12 项检查三维度，腐烂内容列清单' },
  { icon: '⚖️', name: '抽样质检与 A/B', desc: '结构化打分，模型与提示词效果可比' },
  { icon: '🎯', name: '选题 Gap 分析', desc: '按决策阶段指出内容缺口，防编造' },
  { icon: '💡', name: '问答式站内搜索', desc: '混合检索带引用作答，查不到就说查不到' },
  { icon: '🖼️', name: 'AI 配图', desc: '正文提炼提示词，落媒体库并填好 alt' },
  { icon: '🎬', name: 'AI 视频', desc: '镜头提示 → 后台轮询 → 转存云存储' },
  { icon: '🔗', name: '内链建议', desc: '只建议不自动插链，锚文本自然可撤' },
  { icon: '🧩', name: '模型变更影响分析', desc: '改字段前先算清影响面与兼容性' },
  { icon: '📡', name: '多渠道再分发', desc: '长文按渠道重塑体裁，不是复制粘贴' }
]

const apps = [
  { icon: '🤖', name: 'AI CMS', desc: 'AI 原生内容引擎' },
  { icon: '📇', name: 'CRM 销售', desc: '线索到回款' },
  { icon: '🏭', name: 'ERP 管理', desc: '进销存与往来' },
  { icon: '⚙️', name: 'MES 制造', desc: '排产与报工' },
  { icon: '🔀', name: '工作流审批', desc: '可视化流程' },
  { icon: '🎫', name: '工单系统', desc: '工单流转处理' },
  { icon: '☁️', name: '云存储', desc: '多驱动对象存储' },
  { icon: '📢', name: '公告管理', desc: '公告与通知' },
  { icon: '🔔', name: '通知中心', desc: '多渠道推送' },
  { icon: '🔗', name: '链接收藏', desc: '常用链接管理' },
  { icon: '📝', name: 'Quick Notes', desc: '快速记事' },
  { icon: '✅', name: 'My Todo', desc: '任务清单' }
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

// AI 生产线
.ai-line {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: $spacing-md;
  max-width: 960px;
  margin: 0 auto;

  @include mobile {
    grid-template-columns: 1fr;
  }
}

.ai-line-item {
  display: flex;
  align-items: flex-start;
  gap: $spacing-md;
  padding: $spacing-md $spacing-lg;
  background: $bg-white;
  border: 1px solid $border-light;
  border-radius: $radius-md;
  transition: all $transition-fast;

  &:hover {
    border-color: rgba($primary, 0.4);
    box-shadow: $shadow-sm;
  }

  .ai-line-icon {
    font-size: 22px;
    line-height: 1.2;
  }

  strong {
    display: block;
    font-size: 0.92rem;
    color: $text-primary;
    margin-bottom: 2px;
  }

  span {
    font-size: 0.82rem;
    color: $text-muted;
    line-height: 1.6;
  }
}

.ai-line-more {
  text-align: center;
  margin-top: $spacing-xl;
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
