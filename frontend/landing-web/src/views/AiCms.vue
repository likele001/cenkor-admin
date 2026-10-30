<template>
  <div class="aicms-page">
    <!-- Hero -->
    <section class="page-hero">
      <div class="hero-bg">
        <div class="hero-grid"></div>
        <div class="hero-glow"></div>
      </div>
      <div class="container">
        <div class="hero-inner">
          <span class="hero-tag">AI CMS · 旗舰能力</span>
          <h1>
            说一句话建模型，<br>
            <span class="gradient-text">让内容自己长出来</span>
          </h1>
          <p class="hero-sub">
            对话式建模 · AI 起草与翻译 · 语义检索 · 内容生产线 · 多渠道分发。
            建好的内容以 <strong>REST / GraphQL / MCP</strong> 三种协议供给任意前端与 Agent 消费。
          </p>
          <div class="hero-actions">
            <router-link to="/deploy" class="btn btn-primary btn-large">开始部署</router-link>
            <router-link to="/features" class="btn btn-secondary btn-large">全部功能</router-link>
          </div>
          <div class="hero-trust">
            <span><i class="tick">✓</i> 21+ 字段类型动态建模</span>
            <span><i class="tick">✓</i> OpenAI 兼容，七类能力可绑定</span>
            <span><i class="tick">✓</i> 不配 AI 也能完整跑</span>
          </div>
        </div>

        <!-- 对话式建模可视化 -->
        <div class="hero-demo">
          <div class="demo-card">
            <div class="demo-head">
              <div class="dots"><span></span><span></span><span></span></div>
              <span class="demo-title">AI 建模向导</span>
              <span class="demo-badge">draft · 未落库</span>
            </div>
            <div class="demo-body">
              <div class="chat user">
                <span class="who">你</span>
                <p>做一个制造业客户案例库，字段有客户名、所属行业（离散制造/流程制造/新能源）、产线数量、节能率、项目周期、客户 logo、项目前后对比图，要能按行业筛选。</p>
              </div>
              <div class="chat ai">
                <span class="who">AI</span>
                <p>已生成草案 <code>customer_case</code>（客户案例）：7 个字段已就位，行业用下拉选择，节能率限定 0–100，分类支持按行业筛选。</p>
              </div>
              <div class="field-preview">
                <div class="field-row" v-for="f in demoFields" :key="f.key">
                  <span class="fk">{{ f.key }}</span>
                  <span class="ft">{{ f.type }}</span>
                  <span class="fx" v-if="f.note">{{ f.note }}</span>
                </div>
              </div>
              <div class="demo-foot">
                <span class="pill">生成草案不落库</span>
                <span class="pill">确认后才建表</span>
                <span class="pill">字段类型可改</span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </section>

    <!-- 三支柱 -->
    <section class="section">
      <div class="container">
        <SectionTitle
          tag="三大支柱"
          title="AI 不是加个对话框，是改造内容的整条链路"
          description="从「想写什么」到「谁在用」，每一步都有 AI 参与，每一步都留了人审的闸口"
          :center="true"
        />
        <div class="pillar-grid">
          <ScrollReveal v-for="(p, i) in pillars" :key="p.title" :delay="i * 100">
            <div class="pillar-card">
              <div class="pillar-no">{{ String(i + 1).padStart(2, '0') }}</div>
              <div class="pillar-icon">{{ p.icon }}</div>
              <h3>{{ p.title }}</h3>
              <p>{{ p.desc }}</p>
              <ul>
                <li v-for="pt in p.points" :key="pt">{{ pt }}</li>
              </ul>
            </div>
          </ScrollReveal>
        </div>
      </div>
    </section>

    <!-- AI 内容生产线 -->
    <section class="section section-alt">
      <div class="container">
        <SectionTitle
          tag="内容生产线"
          title="十道工序，覆盖内容从诞生到回收"
          description="批量生产、体检、质检、选题、问答、配图、视频、内链、影响分析、再分发 —— 每个都是一个独立端点，可单独用"
          :center="true"
        />
        <div class="line-grid">
          <ScrollReveal v-for="(item, i) in pipeline" :key="item.title" :delay="i * 50">
            <div class="line-card">
              <div class="line-icon">{{ item.icon }}</div>
              <h4>{{ item.title }}</h4>
              <p>{{ item.desc }}</p>
              <span class="line-tag">{{ item.tag }}</span>
            </div>
          </ScrollReveal>
        </div>
      </div>
    </section>

    <!-- 三协议出口 -->
    <section class="section">
      <div class="container">
        <SectionTitle
          tag="出口协议"
          title="一套内容，三种交付形态"
          description="人用 REST、前端用 GraphQL、Agent 用 MCP —— 复用同一套权限与检索底座，不做三套数据"
          :center="true"
        />
        <div class="proto-grid">
          <div class="proto-card" v-for="p in protocols" :key="p.name">
            <div class="proto-head">
              <span class="proto-name">{{ p.name }}</span>
              <span class="proto-for">{{ p.for }}</span>
            </div>
            <pre class="proto-code"><code>{{ p.code }}</code></pre>
            <p class="proto-note">{{ p.note }}</p>
          </div>
        </div>
        <p class="proto-foot">
          MCP 同时支持 <strong>Streamable HTTP</strong> 与 <strong>stdio</strong> 两种传输，
          自行实现以换取对鉴权、事务、错误码的完全控制 —— 交付物离线可部署，不多一个依赖。
        </p>
      </div>
    </section>

    <!-- 记忆 + 提示词 -->
    <section class="section section-alt">
      <div class="container">
        <SectionTitle
          tag="一致性"
          title="让 AI 越写越像「这家公司的笔」"
          description="记忆层管事实与风格，提示词层管措辞与结构 —— 两者都可在后台改，不用发版"
          :center="true"
        />
        <div class="memory-grid">
          <ScrollReveal animation="fade-left">
            <div class="panel">
              <h3>三层记忆体系</h3>
              <div class="mem-list">
                <div class="mem-item" v-for="m in memories" :key="m.title">
                  <span class="mem-dot" :style="{ background: m.color }"></span>
                  <div>
                    <strong>{{ m.title }}</strong>
                    <p>{{ m.desc }}</p>
                  </div>
                </div>
              </div>
            </div>
          </ScrollReveal>
          <ScrollReveal animation="fade-right">
            <div class="panel">
              <h3>提示词工程化</h3>
              <ul class="prompt-list">
                <li>数据库为真相源，代码常量仅作出厂默认</li>
                <li>后台可直接编辑，改错了回滚上一版</li>
                <li>版本 diff 对比，看得见到底改了什么</li>
                <li>查询异常自动回退常量，AI 功能不因表挂掉</li>
              </ul>
              <div class="code-mini"><code>prompt_registry · DB &gt; code · 30s TTL 缓存</code></div>
            </div>
          </ScrollReveal>
        </div>
      </div>
    </section>

    <!-- 落地页工作室 + 工作流 -->
    <section class="section">
      <div class="container">
        <SectionTitle
          tag="增长与自动化"
          title="落地页能生成，流程能画"
          description="营销页与内部审批不该各买一套工具"
          :center="true"
        />
        <div class="dual-grid">
          <ScrollReveal>
            <div class="dual-card">
              <div class="dual-badge">Landing Studio</div>
              <h3>落地页工作室</h3>
              <p>
                描述目标人群与卖点，生成整页落地页：白名单区块逐块校验，模型自创的区块直接丢弃并如实告知；
                表单一并生成且默认挂 CRM 线索池，提交即进线索，转化才有数据可算。
              </p>
              <div class="chips">
                <span>区块白名单校验</span>
                <span>表单 → CRM 线索</span>
                <span>页面预览</span>
                <span>一键发布</span>
              </div>
            </div>
          </ScrollReveal>
          <ScrollReveal>
            <div class="dual-card">
              <div class="dual-badge">Workflow Studio</div>
              <h3>可视化 AI 工作流</h3>
              <p>
                画布上连节点，拓扑序执行，画环当场拦住 —— 不检测就会死循环，而前端只表现为多了一条线。
                每个节点独立提交，run 到哪一步、哪步失败，都能回看。
              </p>
              <div class="chips">
                <span>拓扑序 + 环检测</span>
                <span>逐节点提交</span>
                <span>运行记录</span>
                <span>四种终态</span>
              </div>
            </div>
          </ScrollReveal>
        </div>
      </div>
    </section>

    <!-- 成本与边界 -->
    <section class="section section-alt">
      <div class="container">
        <SectionTitle
          tag="可控性"
          title="花多少钱、用哪个模型，都看得见"
          :center="true"
        />
        <div class="trust-grid">
          <div class="trust-card" v-for="t in controls" :key="t.title">
            <div class="trust-icon">{{ t.icon }}</div>
            <h4>{{ t.title }}</h4>
            <p>{{ t.desc }}</p>
          </div>
        </div>
        <div class="boundary">
          <div class="boundary-head">
            <span class="boundary-icon">🔌</span>
            <strong>AI 是可选增强，不是运行必需</strong>
          </div>
          <p>
            未接入模型时，AI 端点返回明确的 503 提示；而建模 UI、版本、多语言、审核、
            REST / GraphQL / MCP 只读工具等传统能力<strong>完全不受影响</strong>。
            内网离线环境也能先把内容骨架跑起来，模型随时再接。
          </p>
        </div>
      </div>
    </section>

    <section class="cta-section">
      <div class="container">
        <div class="cta-content">
          <ScrollReveal>
            <h2>先让内容跑起来，再让 AI 接管重复劳动</h2>
            <p>AI CMS 已随 v0.3.0 发布，私有化部署在自己服务器上</p>
            <div class="cta-actions">
              <router-link to="/deploy" class="btn btn-primary btn-large">查看部署方式</router-link>
              <router-link to="/docs/guide" class="btn btn-secondary btn-large">使用指南</router-link>
            </div>
          </ScrollReveal>
        </div>
      </div>
    </section>
  </div>
</template>

<script setup lang="ts">
import SectionTitle from '@/components/SectionTitle.vue'
import ScrollReveal from '@/components/ScrollReveal.vue'

const demoFields = [
  { key: 'customer_name', type: 'text', note: '必填' },
  { key: 'industry', type: 'select', note: '离散制造 / 流程制造 / 新能源' },
  { key: 'line_count', type: 'number', note: 'min 1' },
  { key: 'energy_saving', type: 'number', note: '0–100 %' },
  { key: 'project_period', type: 'text', note: '' },
  { key: 'customer_logo', type: 'image', note: '' },
  { key: 'before_after', type: 'images', note: '前后对比' }
]

const pillars = [
  {
    icon: '💬',
    title: '对话式建模',
    desc: '用中文描述业务，直接生成内容类型与字段定义。草案先给你看，确认了才落库 —— 说错一句话不会把库结构改坏。',
    points: ['自然语言 → 内容类型草案', '草案确认后才建表', '字段类型 / 校验 / 选项一并生成']
  },
  {
    icon: '✍️',
    title: 'AI 起草与翻译',
    desc: '按素材或大纲出草稿，强制 draft 状态必须人审；一条命令把内容批量翻译成多语言，保留原有格式与结构。',
    points: ['素材/大纲 → 条目草稿', '强制人工审核后发布', '多语言批量翻译']
  },
  {
    icon: '🔍',
    title: '语义检索增强',
    desc: '条目自动向量化，只给真正变了的条目付 embedding 的钱；检索接入 rerank 精排，命中片段连同出处一起进提示词。',
    points: ['增量向量化（内容指纹比对）', 'rerank 精排', '引用可回溯的 RAG']
  }
]

const pipeline = [
  { icon: '🏭', title: '批量生产', desc: '一次派一批选题，逐篇生成、逐篇落草稿，状态全落库，进程重启也不丢任务。', tag: 'batch' },
  { icon: '🩺', title: '内容健康度体检', desc: '12 项检查分三个维度，把「上线后没人再看」的腐烂内容一次算完列清单。', tag: 'health' },
  { icon: '⚖️', title: '抽样质检与 A/B', desc: '随机抽样 + 结构化打分，换模型、改提示词后的好坏变化有数据可比。', tag: 'quality' },
  { icon: '🎯', title: '选题 Gap 分析', desc: '摊开已有内容，按买家决策阶段指出缺哪层 —— 防模型编造不存在的文章。', tag: 'topic-gap' },
  { icon: '💡', title: '问答式站内搜索', desc: '访客提问 → 混合检索 → 带引用作答；查不到就明确说查不到，绝不编。', tag: 'qa' },
  { icon: '🖼️', title: 'AI 配图', desc: '从正文提炼提示词生成头图，直接落媒体库并自动填好 alt 与分享图。', tag: 'illustration' },
  { icon: '🎬', title: 'AI 视频', desc: '正文拆镜头提示，提交任务后后台轮询，产物转存云存储并抽帧做封面。', tag: 'video' },
  { icon: '🔗', title: '内链建议', desc: '只建议不自动插链，锚文本自然、可一键插入光标处、随时能撤。', tag: 'internal-link' },
  { icon: '🧩', title: '模型变更影响分析', desc: '改字段类型前先算清影响面：多少条已发布、多少条草稿、兼容性如何。', tag: 'schema-impact' },
  { icon: '📡', title: '多渠道再分发', desc: '一篇长文按渠道重塑体裁：公众号要小标题、小红书要短句和话题、LinkedIn 要第一人称观点。', tag: 'redistribute' }
]

const protocols = [
  {
    name: 'REST',
    for: '后台 / 自定义前端',
    code: 'GET /api/v1/cms/entries?content_type=news\nGET /api/v1/public/cms/entries/{slug}\nPOST /api/v1/cms/ai/draft-entry',
    note: '内容引擎 39 个端点 + 公开只读端点，权限按码细分到「读 / 写 / 审核」。'
  },
  {
    name: 'GraphQL',
    for: '现代前端按需取数',
    code: 'POST /api/v1/cms/graphql\n{\n  contentTypes { key name fields { key type } }\n  entries(contentType: "news") { title slug }\n}',
    note: '基于 strawberry，与 REST 并存互不影响，/graphiql 可直接调试。'
  },
  {
    name: 'MCP',
    for: 'Claude / Cursor / 自研 Agent',
    code: 'POST /api/v1/cms/mcp      # Streamable HTTP\ncms-mcp stdio             # 本地进程',
    note: '自实现 JSON-RPC 2.0 分发，写权限有独立开关，只读工具默认安全。'
  }
]

const memories = [
  { title: '站点记忆 · 硬事实', desc: '产品参数、公司口径、禁用词。错一条就是事故，因此只能人工写。', color: '#ef4444' },
  { title: '站点记忆 · 软风格', desc: '语言习惯与结构偏好，由 AI 归纳，随时可纠正。', color: '#f59e0b' },
  { title: '内容记忆 · 条目级', desc: '同一选题的历史写法与结论，避免一个月后自我矛盾。', color: '#10b981' },
  { title: '会话记忆 · 对话级', desc: '一次会话内的上下文与已确认取舍，追问不必从头解释。', color: '#06b6d4' }
]

const controls = [
  { icon: '🔐', title: '密钥永不明文出接口', desc: '接口只返回掩码，编辑时原样回传掩码即等于不修改；密钥加密落库。' },
  { icon: '🧪', title: '连通性真实测试', desc: '保存不报错 ≠ 能用。每个服务商都能发一次最小请求，把「配了但连不上」暴露在界面上。' },
  { icon: '🧮', title: '用量三段计费', desc: '按输入 / 输出 / 缓存分列统计，配合价格表算出真实成本，超预算一眼看到。' },
  { icon: '🧬', title: '七类能力分别绑定', desc: 'chat / embedding / vision / image / rerank / asr / tts 各绑各的模型，chat 与 embedding 可来自不同服务商。' },
  { icon: '🛡️', title: 'AI 权限独立收口', desc: '读配置要 cms:ai:read，改密钥要 cms:ai:manage —— 高危动作只给管理员。' },
  { icon: '🧯', title: '失败可降级', desc: '向量检索超时降级关键词，模型不可用降级人工流程，内容平台本身不跟着挂。' }
]
</script>

<style lang="scss" scoped>
.page-hero {
  position: relative;
  padding: 130px 0 80px;
  background: linear-gradient(180deg, $gray-50 0%, $bg-white 100%);
  border-bottom: 1px solid $border-light;
  overflow: hidden;
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
    top: -180px;
    right: -140px;
    width: 560px;
    height: 560px;
    background: radial-gradient(circle, rgba(139, 92, 246, 0.12) 0%, transparent 70%);
    border-radius: 50%;
  }
}

.hero-inner {
  position: relative;
  z-index: 1;
  max-width: 820px;
  margin: 0 auto;
  text-align: center;

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
    font-size: 3rem;
    font-weight: 800;
    line-height: 1.18;
    color: $text-primary;
    margin-bottom: $spacing-md;

    @include mobile {
      font-size: 2.1rem;
    }
  }

  .gradient-text {
    @include gradient-text($primary, #8b5cf6);
  }

  .hero-sub {
    font-size: 1.1rem;
    color: $text-secondary;
    line-height: 1.8;
    margin: 0 auto $spacing-xl;
    max-width: 660px;

    strong {
      color: $text-primary;
    }
  }

  .hero-actions {
    display: flex;
    justify-content: center;
    gap: $spacing-md;
    flex-wrap: wrap;
  }

  .hero-trust {
    display: flex;
    justify-content: center;
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

// 对话式建模演示
.hero-demo {
  position: relative;
  z-index: 1;
  max-width: 780px;
  margin: $spacing-3xl auto 0;
}

.demo-card {
  background: $bg-white;
  border-radius: $radius-xl;
  box-shadow: $shadow-xl;
  border: 1px solid $border-light;
  overflow: hidden;
}

.demo-head {
  display: flex;
  align-items: center;
  gap: $spacing-md;
  padding: $spacing-md $spacing-lg;
  background: $gray-50;
  border-bottom: 1px solid $border-light;

  .dots {
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

  .demo-title {
    font-size: 13px;
    color: $text-muted;
  }

  .demo-badge {
    margin-left: auto;
    font-size: 11px;
    padding: 2px 10px;
    border-radius: $radius-full;
    background: rgba($warning, 0.12);
    color: #b45309;
  }
}

.demo-body {
  padding: $spacing-lg;
}

.chat {
  display: flex;
  gap: $spacing-sm;
  margin-bottom: $spacing-md;

  .who {
    flex-shrink: 0;
    width: 30px;
    height: 30px;
    border-radius: $radius-md;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 11px;
    font-weight: 700;
    color: $text-white;
  }

  p {
    flex: 1;
    margin: 0;
    padding: $spacing-sm $spacing-md;
    border-radius: $radius-md;
    font-size: 0.88rem;
    line-height: 1.7;
    color: $text-secondary;
  }

  code {
    font-family: $font-mono;
    font-size: 0.8rem;
    background: rgba($primary, 0.1);
    color: $primary-dark;
    padding: 1px 6px;
    border-radius: $radius-sm;
  }

  &.user .who { background: $text-muted; }
  &.user p { background: $gray-100; }
  &.ai .who { background: linear-gradient(135deg, $primary, #8b5cf6); }
  &.ai p { background: rgba($primary, 0.06); }
}

.field-preview {
  border: 1px solid $border-light;
  border-radius: $radius-md;
  overflow: hidden;
  margin-bottom: $spacing-md;
}

.field-row {
  display: grid;
  grid-template-columns: 1.1fr 0.6fr 1.4fr;
  gap: $spacing-sm;
  padding: 9px $spacing-md;
  font-size: 0.78rem;
  border-bottom: 1px solid $border-light;

  &:last-child { border-bottom: none; }
  &:nth-child(odd) { background: $gray-50; }

  .fk { font-family: $font-mono; color: $text-primary; }
  .ft { color: $primary-dark; font-weight: 600; }
  .fx { color: $text-muted; }

  @include mobile {
    grid-template-columns: 1fr 0.8fr;
    .fx { display: none; }
  }
}

.demo-foot {
  display: flex;
  gap: $spacing-sm;
  flex-wrap: wrap;

  .pill {
    font-size: 11px;
    padding: 4px 10px;
    border-radius: $radius-full;
    background: $gray-100;
    color: $text-secondary;

    &::before {
      content: '✓ ';
      color: $success;
      font-weight: 700;
    }
  }
}

// 三支柱
.pillar-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: $spacing-lg;

  @include tablet {
    grid-template-columns: 1fr;
  }

  @include mobile {
    grid-template-columns: 1fr;
  }
}

.pillar-card {
  position: relative;
  background: $bg-white;
  border: 1px solid $border-light;
  border-radius: $radius-xl;
  padding: $spacing-xl;
  height: 100%;
  transition: all $transition-normal;

  &:hover {
    transform: translateY(-4px);
    box-shadow: $shadow-lg;
    border-color: transparent;
  }

  .pillar-no {
    position: absolute;
    top: $spacing-lg;
    right: $spacing-lg;
    font-family: $font-display;
    font-size: 2rem;
    font-weight: 800;
    color: rgba($primary, 0.12);
  }

  .pillar-icon {
    font-size: 34px;
    margin-bottom: $spacing-md;
  }

  h3 {
    font-size: 1.2rem;
    color: $text-primary;
    margin-bottom: $spacing-sm;
  }

  p {
    font-size: 0.92rem;
    color: $text-secondary;
    line-height: 1.8;
    margin-bottom: $spacing-md;
  }

  ul {
    list-style: none;
    padding: 0;
    margin: 0;
    display: flex;
    flex-direction: column;
    gap: 8px;

    li {
      position: relative;
      padding-left: 18px;
      font-size: 0.85rem;
      color: $text-secondary;

      &::before {
        content: '✓';
        position: absolute;
        left: 0;
        top: 0;
        color: $success;
        font-weight: 700;
        font-size: 0.8rem;
      }
    }
  }
}

// 生产线
.line-grid {
  display: grid;
  grid-template-columns: repeat(5, 1fr);
  gap: $spacing-md;

  @include tablet {
    grid-template-columns: repeat(2, 1fr);
  }

  @include mobile {
    grid-template-columns: 1fr;
  }
}

.line-card {
  position: relative;
  background: $bg-white;
  border: 1px solid $border-light;
  border-radius: $radius-lg;
  padding: $spacing-lg;
  height: 100%;
  transition: all $transition-normal;

  &:hover {
    border-color: rgba($primary, 0.4);
    box-shadow: $shadow-md;
  }

  .line-icon {
    font-size: 26px;
    margin-bottom: $spacing-sm;
  }

  h4 {
    font-size: 0.95rem;
    color: $text-primary;
    margin-bottom: 6px;
  }

  p {
    font-size: 0.8rem;
    color: $text-muted;
    line-height: 1.7;
    margin: 0 0 $spacing-sm;
  }

  .line-tag {
    display: inline-block;
    font-family: $font-mono;
    font-size: 10px;
    color: $primary-dark;
    background: rgba($primary, 0.08);
    padding: 2px 8px;
    border-radius: $radius-sm;
  }
}

// 协议
.proto-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: $spacing-lg;

  @include tablet {
    grid-template-columns: 1fr;
  }

  @include mobile {
    grid-template-columns: 1fr;
  }
}

.proto-card {
  background: $dark-900;
  border-radius: $radius-lg;
  padding: $spacing-lg;
  border: 1px solid $dark-700;

  .proto-head {
    display: flex;
    align-items: baseline;
    gap: $spacing-sm;
    margin-bottom: $spacing-md;

    .proto-name {
      font-family: $font-mono;
      font-size: 1rem;
      font-weight: 700;
      color: $primary-light;
    }

    .proto-for {
      font-size: 0.76rem;
      color: $gray-400;
    }
  }

  .proto-code {
    background: rgba(0, 0, 0, 0.35);
    border-radius: $radius-sm;
    padding: $spacing-md;
    margin: 0 0 $spacing-md;
    overflow-x: auto;

    code {
      font-family: $font-mono;
      font-size: 0.72rem;
      line-height: 1.7;
      color: $gray-300;
      white-space: pre;
    }
  }

  .proto-note {
    margin: 0;
    font-size: 0.8rem;
    color: $gray-400;
    line-height: 1.7;
  }
}

.proto-foot {
  text-align: center;
  margin: $spacing-xl auto 0;
  max-width: 720px;
  font-size: 0.9rem;
  color: $text-secondary;

  strong { color: $text-primary; }
}

// 记忆 + 提示词
.memory-grid {
  display: grid;
  grid-template-columns: 1.1fr 0.9fr;
  gap: $spacing-lg;

  @include tablet {
    grid-template-columns: 1fr;
  }

  @include mobile {
    grid-template-columns: 1fr;
  }
}

.panel {
  background: $bg-white;
  border: 1px solid $border-light;
  border-radius: $radius-xl;
  padding: $spacing-xl;
  height: 100%;

  h3 {
    font-size: 1.15rem;
    color: $text-primary;
    margin-bottom: $spacing-lg;
  }
}

.mem-list {
  display: flex;
  flex-direction: column;
  gap: $spacing-md;
}

.mem-item {
  display: flex;
  gap: $spacing-md;

  .mem-dot {
    flex-shrink: 0;
    width: 8px;
    height: 8px;
    border-radius: 50%;
    margin-top: 7px;
  }

  strong {
    display: block;
    font-size: 0.9rem;
    color: $text-primary;
    margin-bottom: 2px;
  }

  p {
    margin: 0;
    font-size: 0.82rem;
    color: $text-secondary;
    line-height: 1.7;
  }
}

.prompt-list {
  list-style: none;
  padding: 0;
  margin: 0 0 $spacing-lg;
  display: flex;
  flex-direction: column;
  gap: $spacing-sm;

  li {
    position: relative;
    padding-left: 20px;
    font-size: 0.88rem;
    color: $text-secondary;
    line-height: 1.7;

    &::before {
      content: '›';
      position: absolute;
      left: 4px;
      color: $primary;
      font-weight: 700;
    }
  }
}

.code-mini {
  background: $gray-900;
  border-radius: $radius-sm;
  padding: $spacing-md;

  code {
    font-family: $font-mono;
    font-size: 0.72rem;
    color: $primary-light;
  }
}

// 双卡
.dual-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: $spacing-lg;

  @include tablet {
    grid-template-columns: 1fr;
  }

  @include mobile {
    grid-template-columns: 1fr;
  }
}

.dual-card {
  background: linear-gradient(160deg, $bg-white 0%, $gray-50 100%);
  border: 1px solid $border-light;
  border-radius: $radius-xl;
  padding: $spacing-xl;

  .dual-badge {
    display: inline-block;
    font-family: $font-mono;
    font-size: 11px;
    color: #8b5cf6;
    background: rgba(139, 92, 246, 0.1);
    padding: 4px 10px;
    border-radius: $radius-full;
    margin-bottom: $spacing-sm;
  }

  h3 {
    font-size: 1.25rem;
    color: $text-primary;
    margin-bottom: $spacing-sm;
  }

  p {
    font-size: 0.9rem;
    color: $text-secondary;
    line-height: 1.85;
    margin: 0 0 $spacing-md;
  }

  .chips {
    display: flex;
    flex-wrap: wrap;
    gap: 8px;

    span {
      font-size: 0.78rem;
      padding: 5px 12px;
      background: $bg-white;
      border: 1px solid $border-light;
      border-radius: $radius-full;
      color: $text-secondary;
    }
  }
}

// 可控性
.trust-grid {
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

.trust-card {
  background: $bg-white;
  border: 1px solid $border-light;
  border-radius: $radius-lg;
  padding: $spacing-lg;

  .trust-icon {
    font-size: 22px;
    margin-bottom: $spacing-sm;
  }

  h4 {
    font-size: 0.95rem;
    color: $text-primary;
    margin-bottom: 6px;
  }

  p {
    margin: 0;
    font-size: 0.82rem;
    color: $text-muted;
    line-height: 1.7;
  }
}

.boundary {
  margin-top: $spacing-xl;
  background: rgba($primary, 0.05);
  border: 1px dashed rgba($primary, 0.35);
  border-radius: $radius-lg;
  padding: $spacing-lg $spacing-xl;

  .boundary-head {
    display: flex;
    align-items: center;
    gap: $spacing-sm;
    margin-bottom: $spacing-sm;

    .boundary-icon { font-size: 18px; }

    strong {
      font-size: 1rem;
      color: $text-primary;
    }
  }

  p {
    margin: 0;
    font-size: 0.9rem;
    color: $text-secondary;
    line-height: 1.85;

    strong { color: $text-primary; }
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
    left: -10%;
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
    font-size: 2.4rem;
    color: $text-white;
    margin-bottom: $spacing-md;

    @include mobile {
      font-size: 1.9rem;
    }
  }

  p {
    font-size: 1.05rem;
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
