import { defineComponent, resolveComponent, mergeProps, withCtx, createTextVNode, createVNode, toDisplayString, openBlock, createBlock, Fragment, renderList, useSSRContext } from "vue";
import { ssrRenderAttrs, ssrRenderComponent, ssrRenderList, ssrInterpolate, ssrRenderStyle } from "vue/server-renderer";
import { S as SectionTitle } from "./SectionTitle-NKY75B6X.js";
import { S as ScrollReveal } from "./ScrollReveal-BjFAJfMT.js";
import { _ as _export_sfc } from "../entry-server.js";
import "vue-router";
import "@unhead/vue";
import "pinia";
const _sfc_main = /* @__PURE__ */ defineComponent({
  __name: "AiCms",
  __ssrInlineRender: true,
  setup(__props) {
    const demoFields = [
      { key: "customer_name", type: "text", note: "必填" },
      { key: "industry", type: "select", note: "离散制造 / 流程制造 / 新能源" },
      { key: "line_count", type: "number", note: "min 1" },
      { key: "energy_saving", type: "number", note: "0–100 %" },
      { key: "project_period", type: "text", note: "" },
      { key: "customer_logo", type: "image", note: "" },
      { key: "before_after", type: "images", note: "前后对比" }
    ];
    const pillars = [
      {
        icon: "💬",
        title: "对话式建模",
        desc: "用中文描述业务，直接生成内容类型与字段定义。草案先给你看，确认了才落库 —— 说错一句话不会把库结构改坏。",
        points: ["自然语言 → 内容类型草案", "草案确认后才建表", "字段类型 / 校验 / 选项一并生成"]
      },
      {
        icon: "✍️",
        title: "AI 起草与翻译",
        desc: "按素材或大纲出草稿，强制 draft 状态必须人审；一条命令把内容批量翻译成多语言，保留原有格式与结构。",
        points: ["素材/大纲 → 条目草稿", "强制人工审核后发布", "多语言批量翻译"]
      },
      {
        icon: "🔍",
        title: "语义检索增强",
        desc: "条目自动向量化，只给真正变了的条目付 embedding 的钱；检索接入 rerank 精排，命中片段连同出处一起进提示词。",
        points: ["增量向量化（内容指纹比对）", "rerank 精排", "引用可回溯的 RAG"]
      }
    ];
    const pipeline = [
      { icon: "🏭", title: "批量生产", desc: "一次派一批选题，逐篇生成、逐篇落草稿，状态全落库，进程重启也不丢任务。", tag: "batch" },
      { icon: "🩺", title: "内容健康度体检", desc: "12 项检查分三个维度，把「上线后没人再看」的腐烂内容一次算完列清单。", tag: "health" },
      { icon: "⚖️", title: "抽样质检与 A/B", desc: "随机抽样 + 结构化打分，换模型、改提示词后的好坏变化有数据可比。", tag: "quality" },
      { icon: "🎯", title: "选题 Gap 分析", desc: "摊开已有内容，按买家决策阶段指出缺哪层 —— 防模型编造不存在的文章。", tag: "topic-gap" },
      { icon: "💡", title: "问答式站内搜索", desc: "访客提问 → 混合检索 → 带引用作答；查不到就明确说查不到，绝不编。", tag: "qa" },
      { icon: "🖼️", title: "AI 配图", desc: "从正文提炼提示词生成头图，直接落媒体库并自动填好 alt 与分享图。", tag: "illustration" },
      { icon: "🎬", title: "AI 视频", desc: "正文拆镜头提示，提交任务后后台轮询，产物转存云存储并抽帧做封面。", tag: "video" },
      { icon: "🔗", title: "内链建议", desc: "只建议不自动插链，锚文本自然、可一键插入光标处、随时能撤。", tag: "internal-link" },
      { icon: "🧩", title: "模型变更影响分析", desc: "改字段类型前先算清影响面：多少条已发布、多少条草稿、兼容性如何。", tag: "schema-impact" },
      { icon: "📡", title: "多渠道再分发", desc: "一篇长文按渠道重塑体裁：公众号要小标题、小红书要短句和话题、LinkedIn 要第一人称观点。", tag: "redistribute" }
    ];
    const protocols = [
      {
        name: "REST",
        for: "后台 / 自定义前端",
        code: "GET /api/v1/cms/entries?content_type=news\nGET /api/v1/public/cms/entries/{slug}\nPOST /api/v1/cms/ai/draft-entry",
        note: "内容引擎 39 个端点 + 公开只读端点，权限按码细分到「读 / 写 / 审核」。"
      },
      {
        name: "GraphQL",
        for: "现代前端按需取数",
        code: 'POST /api/v1/cms/graphql\n{\n  contentTypes { key name fields { key type } }\n  entries(contentType: "news") { title slug }\n}',
        note: "基于 strawberry，与 REST 并存互不影响，/graphiql 可直接调试。"
      },
      {
        name: "MCP",
        for: "Claude / Cursor / 自研 Agent",
        code: "POST /api/v1/cms/mcp      # Streamable HTTP\ncms-mcp stdio             # 本地进程",
        note: "自实现 JSON-RPC 2.0 分发，写权限有独立开关，只读工具默认安全。"
      }
    ];
    const memories = [
      { title: "站点记忆 · 硬事实", desc: "产品参数、公司口径、禁用词。错一条就是事故，因此只能人工写。", color: "#ef4444" },
      { title: "站点记忆 · 软风格", desc: "语言习惯与结构偏好，由 AI 归纳，随时可纠正。", color: "#f59e0b" },
      { title: "内容记忆 · 条目级", desc: "同一选题的历史写法与结论，避免一个月后自我矛盾。", color: "#10b981" },
      { title: "会话记忆 · 对话级", desc: "一次会话内的上下文与已确认取舍，追问不必从头解释。", color: "#06b6d4" }
    ];
    const controls = [
      { icon: "🔐", title: "密钥永不明文出接口", desc: "接口只返回掩码，编辑时原样回传掩码即等于不修改；密钥加密落库。" },
      { icon: "🧪", title: "连通性真实测试", desc: "保存不报错 ≠ 能用。每个服务商都能发一次最小请求，把「配了但连不上」暴露在界面上。" },
      { icon: "🧮", title: "用量三段计费", desc: "按输入 / 输出 / 缓存分列统计，配合价格表算出真实成本，超预算一眼看到。" },
      { icon: "🧬", title: "七类能力分别绑定", desc: "chat / embedding / vision / image / rerank / asr / tts 各绑各的模型，chat 与 embedding 可来自不同服务商。" },
      { icon: "🛡️", title: "AI 权限独立收口", desc: "读配置要 cms:ai:read，改密钥要 cms:ai:manage —— 高危动作只给管理员。" },
      { icon: "🧯", title: "失败可降级", desc: "向量检索超时降级关键词，模型不可用降级人工流程，内容平台本身不跟着挂。" }
    ];
    return (_ctx, _push, _parent, _attrs) => {
      const _component_router_link = resolveComponent("router-link");
      _push(`<div${ssrRenderAttrs(mergeProps({ class: "aicms-page" }, _attrs))} data-v-c5f42d7c><section class="page-hero" data-v-c5f42d7c><div class="hero-bg" data-v-c5f42d7c><div class="hero-grid" data-v-c5f42d7c></div><div class="hero-glow" data-v-c5f42d7c></div></div><div class="container" data-v-c5f42d7c><div class="hero-inner" data-v-c5f42d7c><span class="hero-tag" data-v-c5f42d7c>AI CMS · 旗舰能力</span><h1 data-v-c5f42d7c> 说一句话建模型，<br data-v-c5f42d7c><span class="gradient-text" data-v-c5f42d7c>让内容自己长出来</span></h1><p class="hero-sub" data-v-c5f42d7c> 对话式建模 · AI 起草与翻译 · 语义检索 · 内容生产线 · 多渠道分发。 建好的内容以 <strong data-v-c5f42d7c>REST / GraphQL / MCP</strong> 三种协议供给任意前端与 Agent 消费。 </p><div class="hero-actions" data-v-c5f42d7c>`);
      _push(ssrRenderComponent(_component_router_link, {
        to: "/deploy",
        class: "btn btn-primary btn-large"
      }, {
        default: withCtx((_, _push2, _parent2, _scopeId) => {
          if (_push2) {
            _push2(`开始部署`);
          } else {
            return [
              createTextVNode("开始部署")
            ];
          }
        }),
        _: 1
      }, _parent));
      _push(ssrRenderComponent(_component_router_link, {
        to: "/features",
        class: "btn btn-secondary btn-large"
      }, {
        default: withCtx((_, _push2, _parent2, _scopeId) => {
          if (_push2) {
            _push2(`全部功能`);
          } else {
            return [
              createTextVNode("全部功能")
            ];
          }
        }),
        _: 1
      }, _parent));
      _push(`</div><div class="hero-trust" data-v-c5f42d7c><span data-v-c5f42d7c><i class="tick" data-v-c5f42d7c>✓</i> 21+ 字段类型动态建模</span><span data-v-c5f42d7c><i class="tick" data-v-c5f42d7c>✓</i> OpenAI 兼容，七类能力可绑定</span><span data-v-c5f42d7c><i class="tick" data-v-c5f42d7c>✓</i> 不配 AI 也能完整跑</span></div></div><div class="hero-demo" data-v-c5f42d7c><div class="demo-card" data-v-c5f42d7c><div class="demo-head" data-v-c5f42d7c><div class="dots" data-v-c5f42d7c><span data-v-c5f42d7c></span><span data-v-c5f42d7c></span><span data-v-c5f42d7c></span></div><span class="demo-title" data-v-c5f42d7c>AI 建模向导</span><span class="demo-badge" data-v-c5f42d7c>draft · 未落库</span></div><div class="demo-body" data-v-c5f42d7c><div class="chat user" data-v-c5f42d7c><span class="who" data-v-c5f42d7c>你</span><p data-v-c5f42d7c>做一个制造业客户案例库，字段有客户名、所属行业（离散制造/流程制造/新能源）、产线数量、节能率、项目周期、客户 logo、项目前后对比图，要能按行业筛选。</p></div><div class="chat ai" data-v-c5f42d7c><span class="who" data-v-c5f42d7c>AI</span><p data-v-c5f42d7c>已生成草案 <code data-v-c5f42d7c>customer_case</code>（客户案例）：7 个字段已就位，行业用下拉选择，节能率限定 0–100，分类支持按行业筛选。</p></div><div class="field-preview" data-v-c5f42d7c><!--[-->`);
      ssrRenderList(demoFields, (f) => {
        _push(`<div class="field-row" data-v-c5f42d7c><span class="fk" data-v-c5f42d7c>${ssrInterpolate(f.key)}</span><span class="ft" data-v-c5f42d7c>${ssrInterpolate(f.type)}</span>`);
        if (f.note) {
          _push(`<span class="fx" data-v-c5f42d7c>${ssrInterpolate(f.note)}</span>`);
        } else {
          _push(`<!---->`);
        }
        _push(`</div>`);
      });
      _push(`<!--]--></div><div class="demo-foot" data-v-c5f42d7c><span class="pill" data-v-c5f42d7c>生成草案不落库</span><span class="pill" data-v-c5f42d7c>确认后才建表</span><span class="pill" data-v-c5f42d7c>字段类型可改</span></div></div></div></div></div></section><section class="section" data-v-c5f42d7c><div class="container" data-v-c5f42d7c>`);
      _push(ssrRenderComponent(SectionTitle, {
        tag: "三大支柱",
        title: "AI 不是加个对话框，是改造内容的整条链路",
        description: "从「想写什么」到「谁在用」，每一步都有 AI 参与，每一步都留了人审的闸口",
        center: true
      }, null, _parent));
      _push(`<div class="pillar-grid" data-v-c5f42d7c><!--[-->`);
      ssrRenderList(pillars, (p, i) => {
        _push(ssrRenderComponent(ScrollReveal, {
          key: p.title,
          delay: i * 100
        }, {
          default: withCtx((_, _push2, _parent2, _scopeId) => {
            if (_push2) {
              _push2(`<div class="pillar-card" data-v-c5f42d7c${_scopeId}><div class="pillar-no" data-v-c5f42d7c${_scopeId}>${ssrInterpolate(String(i + 1).padStart(2, "0"))}</div><div class="pillar-icon" data-v-c5f42d7c${_scopeId}>${ssrInterpolate(p.icon)}</div><h3 data-v-c5f42d7c${_scopeId}>${ssrInterpolate(p.title)}</h3><p data-v-c5f42d7c${_scopeId}>${ssrInterpolate(p.desc)}</p><ul data-v-c5f42d7c${_scopeId}><!--[-->`);
              ssrRenderList(p.points, (pt) => {
                _push2(`<li data-v-c5f42d7c${_scopeId}>${ssrInterpolate(pt)}</li>`);
              });
              _push2(`<!--]--></ul></div>`);
            } else {
              return [
                createVNode("div", { class: "pillar-card" }, [
                  createVNode("div", { class: "pillar-no" }, toDisplayString(String(i + 1).padStart(2, "0")), 1),
                  createVNode("div", { class: "pillar-icon" }, toDisplayString(p.icon), 1),
                  createVNode("h3", null, toDisplayString(p.title), 1),
                  createVNode("p", null, toDisplayString(p.desc), 1),
                  createVNode("ul", null, [
                    (openBlock(true), createBlock(Fragment, null, renderList(p.points, (pt) => {
                      return openBlock(), createBlock("li", { key: pt }, toDisplayString(pt), 1);
                    }), 128))
                  ])
                ])
              ];
            }
          }),
          _: 2
        }, _parent));
      });
      _push(`<!--]--></div></div></section><section class="section section-alt" data-v-c5f42d7c><div class="container" data-v-c5f42d7c>`);
      _push(ssrRenderComponent(SectionTitle, {
        tag: "内容生产线",
        title: "十道工序，覆盖内容从诞生到回收",
        description: "批量生产、体检、质检、选题、问答、配图、视频、内链、影响分析、再分发 —— 每个都是一个独立端点，可单独用",
        center: true
      }, null, _parent));
      _push(`<div class="line-grid" data-v-c5f42d7c><!--[-->`);
      ssrRenderList(pipeline, (item, i) => {
        _push(ssrRenderComponent(ScrollReveal, {
          key: item.title,
          delay: i * 50
        }, {
          default: withCtx((_, _push2, _parent2, _scopeId) => {
            if (_push2) {
              _push2(`<div class="line-card" data-v-c5f42d7c${_scopeId}><div class="line-icon" data-v-c5f42d7c${_scopeId}>${ssrInterpolate(item.icon)}</div><h4 data-v-c5f42d7c${_scopeId}>${ssrInterpolate(item.title)}</h4><p data-v-c5f42d7c${_scopeId}>${ssrInterpolate(item.desc)}</p><span class="line-tag" data-v-c5f42d7c${_scopeId}>${ssrInterpolate(item.tag)}</span></div>`);
            } else {
              return [
                createVNode("div", { class: "line-card" }, [
                  createVNode("div", { class: "line-icon" }, toDisplayString(item.icon), 1),
                  createVNode("h4", null, toDisplayString(item.title), 1),
                  createVNode("p", null, toDisplayString(item.desc), 1),
                  createVNode("span", { class: "line-tag" }, toDisplayString(item.tag), 1)
                ])
              ];
            }
          }),
          _: 2
        }, _parent));
      });
      _push(`<!--]--></div></div></section><section class="section" data-v-c5f42d7c><div class="container" data-v-c5f42d7c>`);
      _push(ssrRenderComponent(SectionTitle, {
        tag: "出口协议",
        title: "一套内容，三种交付形态",
        description: "人用 REST、前端用 GraphQL、Agent 用 MCP —— 复用同一套权限与检索底座，不做三套数据",
        center: true
      }, null, _parent));
      _push(`<div class="proto-grid" data-v-c5f42d7c><!--[-->`);
      ssrRenderList(protocols, (p) => {
        _push(`<div class="proto-card" data-v-c5f42d7c><div class="proto-head" data-v-c5f42d7c><span class="proto-name" data-v-c5f42d7c>${ssrInterpolate(p.name)}</span><span class="proto-for" data-v-c5f42d7c>${ssrInterpolate(p.for)}</span></div><pre class="proto-code" data-v-c5f42d7c><code data-v-c5f42d7c>${ssrInterpolate(p.code)}</code></pre><p class="proto-note" data-v-c5f42d7c>${ssrInterpolate(p.note)}</p></div>`);
      });
      _push(`<!--]--></div><p class="proto-foot" data-v-c5f42d7c> MCP 同时支持 <strong data-v-c5f42d7c>Streamable HTTP</strong> 与 <strong data-v-c5f42d7c>stdio</strong> 两种传输， 自行实现以换取对鉴权、事务、错误码的完全控制 —— 交付物离线可部署，不多一个依赖。 </p></div></section><section class="section section-alt" data-v-c5f42d7c><div class="container" data-v-c5f42d7c>`);
      _push(ssrRenderComponent(SectionTitle, {
        tag: "一致性",
        title: "让 AI 越写越像「这家公司的笔」",
        description: "记忆层管事实与风格，提示词层管措辞与结构 —— 两者都可在后台改，不用发版",
        center: true
      }, null, _parent));
      _push(`<div class="memory-grid" data-v-c5f42d7c>`);
      _push(ssrRenderComponent(ScrollReveal, { animation: "fade-left" }, {
        default: withCtx((_, _push2, _parent2, _scopeId) => {
          if (_push2) {
            _push2(`<div class="panel" data-v-c5f42d7c${_scopeId}><h3 data-v-c5f42d7c${_scopeId}>三层记忆体系</h3><div class="mem-list" data-v-c5f42d7c${_scopeId}><!--[-->`);
            ssrRenderList(memories, (m) => {
              _push2(`<div class="mem-item" data-v-c5f42d7c${_scopeId}><span class="mem-dot" style="${ssrRenderStyle({ background: m.color })}" data-v-c5f42d7c${_scopeId}></span><div data-v-c5f42d7c${_scopeId}><strong data-v-c5f42d7c${_scopeId}>${ssrInterpolate(m.title)}</strong><p data-v-c5f42d7c${_scopeId}>${ssrInterpolate(m.desc)}</p></div></div>`);
            });
            _push2(`<!--]--></div></div>`);
          } else {
            return [
              createVNode("div", { class: "panel" }, [
                createVNode("h3", null, "三层记忆体系"),
                createVNode("div", { class: "mem-list" }, [
                  (openBlock(), createBlock(Fragment, null, renderList(memories, (m) => {
                    return createVNode("div", {
                      class: "mem-item",
                      key: m.title
                    }, [
                      createVNode("span", {
                        class: "mem-dot",
                        style: { background: m.color }
                      }, null, 4),
                      createVNode("div", null, [
                        createVNode("strong", null, toDisplayString(m.title), 1),
                        createVNode("p", null, toDisplayString(m.desc), 1)
                      ])
                    ]);
                  }), 64))
                ])
              ])
            ];
          }
        }),
        _: 1
      }, _parent));
      _push(ssrRenderComponent(ScrollReveal, { animation: "fade-right" }, {
        default: withCtx((_, _push2, _parent2, _scopeId) => {
          if (_push2) {
            _push2(`<div class="panel" data-v-c5f42d7c${_scopeId}><h3 data-v-c5f42d7c${_scopeId}>提示词工程化</h3><ul class="prompt-list" data-v-c5f42d7c${_scopeId}><li data-v-c5f42d7c${_scopeId}>数据库为真相源，代码常量仅作出厂默认</li><li data-v-c5f42d7c${_scopeId}>后台可直接编辑，改错了回滚上一版</li><li data-v-c5f42d7c${_scopeId}>版本 diff 对比，看得见到底改了什么</li><li data-v-c5f42d7c${_scopeId}>查询异常自动回退常量，AI 功能不因表挂掉</li></ul><div class="code-mini" data-v-c5f42d7c${_scopeId}><code data-v-c5f42d7c${_scopeId}>prompt_registry · DB &gt; code · 30s TTL 缓存</code></div></div>`);
          } else {
            return [
              createVNode("div", { class: "panel" }, [
                createVNode("h3", null, "提示词工程化"),
                createVNode("ul", { class: "prompt-list" }, [
                  createVNode("li", null, "数据库为真相源，代码常量仅作出厂默认"),
                  createVNode("li", null, "后台可直接编辑，改错了回滚上一版"),
                  createVNode("li", null, "版本 diff 对比，看得见到底改了什么"),
                  createVNode("li", null, "查询异常自动回退常量，AI 功能不因表挂掉")
                ]),
                createVNode("div", { class: "code-mini" }, [
                  createVNode("code", null, "prompt_registry · DB > code · 30s TTL 缓存")
                ])
              ])
            ];
          }
        }),
        _: 1
      }, _parent));
      _push(`</div></div></section><section class="section" data-v-c5f42d7c><div class="container" data-v-c5f42d7c>`);
      _push(ssrRenderComponent(SectionTitle, {
        tag: "增长与自动化",
        title: "落地页能生成，流程能画",
        description: "营销页与内部审批不该各买一套工具",
        center: true
      }, null, _parent));
      _push(`<div class="dual-grid" data-v-c5f42d7c>`);
      _push(ssrRenderComponent(ScrollReveal, null, {
        default: withCtx((_, _push2, _parent2, _scopeId) => {
          if (_push2) {
            _push2(`<div class="dual-card" data-v-c5f42d7c${_scopeId}><div class="dual-badge" data-v-c5f42d7c${_scopeId}>Landing Studio</div><h3 data-v-c5f42d7c${_scopeId}>落地页工作室</h3><p data-v-c5f42d7c${_scopeId}> 描述目标人群与卖点，生成整页落地页：白名单区块逐块校验，模型自创的区块直接丢弃并如实告知； 表单一并生成且默认挂 CRM 线索池，提交即进线索，转化才有数据可算。 </p><div class="chips" data-v-c5f42d7c${_scopeId}><span data-v-c5f42d7c${_scopeId}>区块白名单校验</span><span data-v-c5f42d7c${_scopeId}>表单 → CRM 线索</span><span data-v-c5f42d7c${_scopeId}>页面预览</span><span data-v-c5f42d7c${_scopeId}>一键发布</span></div></div>`);
          } else {
            return [
              createVNode("div", { class: "dual-card" }, [
                createVNode("div", { class: "dual-badge" }, "Landing Studio"),
                createVNode("h3", null, "落地页工作室"),
                createVNode("p", null, " 描述目标人群与卖点，生成整页落地页：白名单区块逐块校验，模型自创的区块直接丢弃并如实告知； 表单一并生成且默认挂 CRM 线索池，提交即进线索，转化才有数据可算。 "),
                createVNode("div", { class: "chips" }, [
                  createVNode("span", null, "区块白名单校验"),
                  createVNode("span", null, "表单 → CRM 线索"),
                  createVNode("span", null, "页面预览"),
                  createVNode("span", null, "一键发布")
                ])
              ])
            ];
          }
        }),
        _: 1
      }, _parent));
      _push(ssrRenderComponent(ScrollReveal, null, {
        default: withCtx((_, _push2, _parent2, _scopeId) => {
          if (_push2) {
            _push2(`<div class="dual-card" data-v-c5f42d7c${_scopeId}><div class="dual-badge" data-v-c5f42d7c${_scopeId}>Workflow Studio</div><h3 data-v-c5f42d7c${_scopeId}>可视化 AI 工作流</h3><p data-v-c5f42d7c${_scopeId}> 画布上连节点，拓扑序执行，画环当场拦住 —— 不检测就会死循环，而前端只表现为多了一条线。 每个节点独立提交，run 到哪一步、哪步失败，都能回看。 </p><div class="chips" data-v-c5f42d7c${_scopeId}><span data-v-c5f42d7c${_scopeId}>拓扑序 + 环检测</span><span data-v-c5f42d7c${_scopeId}>逐节点提交</span><span data-v-c5f42d7c${_scopeId}>运行记录</span><span data-v-c5f42d7c${_scopeId}>四种终态</span></div></div>`);
          } else {
            return [
              createVNode("div", { class: "dual-card" }, [
                createVNode("div", { class: "dual-badge" }, "Workflow Studio"),
                createVNode("h3", null, "可视化 AI 工作流"),
                createVNode("p", null, " 画布上连节点，拓扑序执行，画环当场拦住 —— 不检测就会死循环，而前端只表现为多了一条线。 每个节点独立提交，run 到哪一步、哪步失败，都能回看。 "),
                createVNode("div", { class: "chips" }, [
                  createVNode("span", null, "拓扑序 + 环检测"),
                  createVNode("span", null, "逐节点提交"),
                  createVNode("span", null, "运行记录"),
                  createVNode("span", null, "四种终态")
                ])
              ])
            ];
          }
        }),
        _: 1
      }, _parent));
      _push(`</div></div></section><section class="section section-alt" data-v-c5f42d7c><div class="container" data-v-c5f42d7c>`);
      _push(ssrRenderComponent(SectionTitle, {
        tag: "可控性",
        title: "花多少钱、用哪个模型，都看得见",
        center: true
      }, null, _parent));
      _push(`<div class="trust-grid" data-v-c5f42d7c><!--[-->`);
      ssrRenderList(controls, (t) => {
        _push(`<div class="trust-card" data-v-c5f42d7c><div class="trust-icon" data-v-c5f42d7c>${ssrInterpolate(t.icon)}</div><h4 data-v-c5f42d7c>${ssrInterpolate(t.title)}</h4><p data-v-c5f42d7c>${ssrInterpolate(t.desc)}</p></div>`);
      });
      _push(`<!--]--></div><div class="boundary" data-v-c5f42d7c><div class="boundary-head" data-v-c5f42d7c><span class="boundary-icon" data-v-c5f42d7c>🔌</span><strong data-v-c5f42d7c>AI 是可选增强，不是运行必需</strong></div><p data-v-c5f42d7c> 未接入模型时，AI 端点返回明确的 503 提示；而建模 UI、版本、多语言、审核、 REST / GraphQL / MCP 只读工具等传统能力<strong data-v-c5f42d7c>完全不受影响</strong>。 内网离线环境也能先把内容骨架跑起来，模型随时再接。 </p></div></div></section><section class="cta-section" data-v-c5f42d7c><div class="container" data-v-c5f42d7c><div class="cta-content" data-v-c5f42d7c>`);
      _push(ssrRenderComponent(ScrollReveal, null, {
        default: withCtx((_, _push2, _parent2, _scopeId) => {
          if (_push2) {
            _push2(`<h2 data-v-c5f42d7c${_scopeId}>先让内容跑起来，再让 AI 接管重复劳动</h2><p data-v-c5f42d7c${_scopeId}>AI CMS 已随 v0.3.0 发布，私有化部署在自己服务器上</p><div class="cta-actions" data-v-c5f42d7c${_scopeId}>`);
            _push2(ssrRenderComponent(_component_router_link, {
              to: "/deploy",
              class: "btn btn-primary btn-large"
            }, {
              default: withCtx((_2, _push3, _parent3, _scopeId2) => {
                if (_push3) {
                  _push3(`查看部署方式`);
                } else {
                  return [
                    createTextVNode("查看部署方式")
                  ];
                }
              }),
              _: 1
            }, _parent2, _scopeId));
            _push2(ssrRenderComponent(_component_router_link, {
              to: "/docs/guide",
              class: "btn btn-secondary btn-large"
            }, {
              default: withCtx((_2, _push3, _parent3, _scopeId2) => {
                if (_push3) {
                  _push3(`使用指南`);
                } else {
                  return [
                    createTextVNode("使用指南")
                  ];
                }
              }),
              _: 1
            }, _parent2, _scopeId));
            _push2(`</div>`);
          } else {
            return [
              createVNode("h2", null, "先让内容跑起来，再让 AI 接管重复劳动"),
              createVNode("p", null, "AI CMS 已随 v0.3.0 发布，私有化部署在自己服务器上"),
              createVNode("div", { class: "cta-actions" }, [
                createVNode(_component_router_link, {
                  to: "/deploy",
                  class: "btn btn-primary btn-large"
                }, {
                  default: withCtx(() => [
                    createTextVNode("查看部署方式")
                  ]),
                  _: 1
                }),
                createVNode(_component_router_link, {
                  to: "/docs/guide",
                  class: "btn btn-secondary btn-large"
                }, {
                  default: withCtx(() => [
                    createTextVNode("使用指南")
                  ]),
                  _: 1
                })
              ])
            ];
          }
        }),
        _: 1
      }, _parent));
      _push(`</div></div></section></div>`);
    };
  }
});
const _sfc_setup = _sfc_main.setup;
_sfc_main.setup = (props, ctx) => {
  const ssrContext = useSSRContext();
  (ssrContext.modules || (ssrContext.modules = /* @__PURE__ */ new Set())).add("src/views/AiCms.vue");
  return _sfc_setup ? _sfc_setup(props, ctx) : void 0;
};
const AiCms = /* @__PURE__ */ _export_sfc(_sfc_main, [["__scopeId", "data-v-c5f42d7c"]]);
export {
  AiCms as default
};
