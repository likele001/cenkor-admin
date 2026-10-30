import { defineComponent, computed, mergeProps, useSSRContext, ref, onMounted, onUnmounted, resolveComponent, withCtx, createTextVNode, openBlock, createBlock, createVNode, Fragment, renderList, toDisplayString, unref } from "vue";
import { ssrRenderAttrs, ssrRenderStyle, ssrInterpolate, ssrRenderList, ssrRenderComponent, ssrRenderClass, ssrRenderAttr } from "vue/server-renderer";
import { S as SectionTitle } from "./SectionTitle-NKY75B6X.js";
import { _ as _export_sfc, S as SITE_URLS } from "../entry-server.js";
import { S as ScrollReveal } from "./ScrollReveal-BjFAJfMT.js";
import "vue-router";
import "@unhead/vue";
import "pinia";
const _sfc_main$2 = /* @__PURE__ */ defineComponent({
  __name: "FeatureCard",
  __ssrInlineRender: true,
  props: {
    icon: {},
    title: {},
    description: {},
    features: { default: () => [] },
    color: { default: "#3b82f6" }
  },
  setup(__props) {
    const props = __props;
    const iconBg = computed(() => `rgba(${hexToRgb(props.color)}, 0.1)`);
    function hexToRgb(hex) {
      const result = /^#?([a-f\d]{2})([a-f\d]{2})([a-f\d]{2})$/i.exec(hex);
      if (!result) return "59, 130, 246";
      return `${parseInt(result[1], 16)}, ${parseInt(result[2], 16)}, ${parseInt(result[3], 16)}`;
    }
    return (_ctx, _push, _parent, _attrs) => {
      _push(`<div${ssrRenderAttrs(mergeProps({ class: "feature-card" }, _attrs))} data-v-4423f287><div class="icon-wrapper" style="${ssrRenderStyle({ background: iconBg.value })}" data-v-4423f287><span class="icon" data-v-4423f287>${ssrInterpolate(__props.icon)}</span></div><h3 data-v-4423f287>${ssrInterpolate(__props.title)}</h3><p data-v-4423f287>${ssrInterpolate(__props.description)}</p>`);
      if (__props.features.length) {
        _push(`<ul class="features-list" data-v-4423f287><!--[-->`);
        ssrRenderList(__props.features, (feature, index) => {
          _push(`<li data-v-4423f287><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" data-v-4423f287><polyline points="20 6 9 17 4 12" data-v-4423f287></polyline></svg> ${ssrInterpolate(feature)}</li>`);
        });
        _push(`<!--]--></ul>`);
      } else {
        _push(`<!---->`);
      }
      _push(`</div>`);
    };
  }
});
const _sfc_setup$2 = _sfc_main$2.setup;
_sfc_main$2.setup = (props, ctx) => {
  const ssrContext = useSSRContext();
  (ssrContext.modules || (ssrContext.modules = /* @__PURE__ */ new Set())).add("src/components/FeatureCard.vue");
  return _sfc_setup$2 ? _sfc_setup$2(props, ctx) : void 0;
};
const FeatureCard = /* @__PURE__ */ _export_sfc(_sfc_main$2, [["__scopeId", "data-v-4423f287"]]);
const _sfc_main$1 = /* @__PURE__ */ defineComponent({
  __name: "CounterUp",
  __ssrInlineRender: true,
  props: {
    value: {},
    duration: { default: 2e3 },
    suffix: { default: "" }
  },
  setup(__props) {
    const props = __props;
    const currentValue = ref(props.value);
    const isVisible = ref(false);
    const elRef = ref(null);
    let observer = null;
    let animationFrame = null;
    const displayValue = computed(() => {
      if (props.value >= 1e6) {
        return (currentValue.value / 1e6).toFixed(1) + "M";
      }
      if (props.value >= 1e3) {
        return (currentValue.value / 1e3).toFixed(1) + "K";
      }
      return Math.floor(currentValue.value).toString();
    });
    function animate() {
      const startTime = performance.now();
      const startValue = 0;
      const endValue = props.value;
      function step(currentTime) {
        const elapsed = currentTime - startTime;
        const progress = Math.min(elapsed / props.duration, 1);
        const easeProgress = 1 - Math.pow(1 - progress, 3);
        currentValue.value = startValue + (endValue - startValue) * easeProgress;
        if (progress < 1) {
          animationFrame = requestAnimationFrame(step);
        }
      }
      animationFrame = requestAnimationFrame(step);
    }
    onMounted(() => {
      if (typeof IntersectionObserver === "undefined") {
        currentValue.value = props.value;
        return;
      }
      currentValue.value = 0;
      observer = new IntersectionObserver(
        (entries) => {
          entries.forEach((entry) => {
            if (entry.isIntersecting && !isVisible.value) {
              isVisible.value = true;
              animate();
              observer == null ? void 0 : observer.unobserve(entry.target);
            }
          });
        },
        { threshold: 0.5 }
      );
      if (elRef.value) {
        observer.observe(elRef.value);
      }
    });
    onUnmounted(() => {
      observer == null ? void 0 : observer.disconnect();
      if (animationFrame) {
        cancelAnimationFrame(animationFrame);
      }
    });
    return (_ctx, _push, _parent, _attrs) => {
      _push(`<span${ssrRenderAttrs(mergeProps({
        ref_key: "elRef",
        ref: elRef,
        class: "counter-up"
      }, _attrs))} data-v-14b6261c>${ssrInterpolate(displayValue.value)}${ssrInterpolate(__props.suffix)}</span>`);
    };
  }
});
const _sfc_setup$1 = _sfc_main$1.setup;
_sfc_main$1.setup = (props, ctx) => {
  const ssrContext = useSSRContext();
  (ssrContext.modules || (ssrContext.modules = /* @__PURE__ */ new Set())).add("src/components/CounterUp.vue");
  return _sfc_setup$1 ? _sfc_setup$1(props, ctx) : void 0;
};
const CounterUp = /* @__PURE__ */ _export_sfc(_sfc_main$1, [["__scopeId", "data-v-14b6261c"]]);
const _sfc_main = /* @__PURE__ */ defineComponent({
  __name: "Home",
  __ssrInlineRender: true,
  setup(__props) {
    const urls = SITE_URLS;
    const stats = [
      { value: 12, label: "可插拔业务应用", suffix: "" },
      { value: 21, label: "CMS 字段类型", suffix: "+" },
      { value: 10, label: "道 AI 内容工序", suffix: "" },
      { value: 3, label: "内容出口协议", suffix: " 种" }
    ];
    const aiHighlights = [
      { icon: "💬", title: "对话式建模", desc: "中文描述 → 内容类型草案，确认才落库" },
      { icon: "✍️", title: "起草与翻译", desc: "草稿强制人审，多语言一条命令批量出" },
      { icon: "🏭", title: "内容生产线", desc: "批量生产、体检、质检、选题、问答、配图" },
      { icon: "🔌", title: "三协议出口", desc: "REST / GraphQL / MCP，Agent 直接消费" }
    ];
    const aiSteps = [
      { icon: "🎯", name: "选题 Gap 分析", state: "done" },
      { icon: "📝", name: "条目起草", state: "done" },
      { icon: "🔍", name: "语义检索命中知识库", state: "done" },
      { icon: "🖼️", name: "配图生成并落媒体库", state: "running" },
      { icon: "🌐", name: "多语言翻译", state: "queued" },
      { icon: "🩺", name: "发布前健康度体检", state: "queued" }
    ];
    const features = [
      {
        icon: "🤖",
        title: "AI CMS 内容引擎",
        description: "对话式建模、AI 起草翻译、语义检索、内容生产线，内容以 REST / GraphQL / MCP 三协议出口",
        features: ["对话式建模", "AI 起草与翻译", "MCP / GraphQL 出口"],
        color: "#8b5cf6"
      },
      {
        icon: "🏪",
        title: "应用中心",
        description: "应用按需安装/卸载，自动注册权限、菜单、内容类型，业务模块即插即用",
        features: ["应用安装卸载", "权限自动注册", "授权码 OTA 升级"],
        color: "#10b981"
      },
      {
        icon: "🔐",
        title: "RBAC 权限",
        description: "角色、权限规则、数据权限三级控制，后台/前台双用户体系隔离",
        features: ["角色管理", "数据权限", "双用户体系"],
        color: "#0ea5e9"
      },
      {
        icon: "📝",
        title: "动态建模与多站点",
        description: "21+ 字段类型后台即可增删，多级分类标签，多站点站群会话级隔离",
        features: ["动态字段", "多级分类标签", "多站点站群"],
        color: "#f59e0b"
      },
      {
        icon: "🔀",
        title: "工作流审批",
        description: "可视化流程编排，待办/已办/抄送/单据齐全，AI 工作流按拓扑序执行并检测环",
        features: ["可视化编排", "待办已办抄送", "AI 工作流引擎"],
        color: "#ec4899"
      },
      {
        icon: "📡",
        title: "发布与统计",
        description: "官网、Webhook、微信公众号草稿箱、导出多渠道分发；内容埋点与效果分析内置",
        features: ["多渠道发布", "内容埋点", "停留与跳出分析"],
        color: "#14b8a6"
      },
      {
        icon: "🔌",
        title: "开放接口",
        description: "REST 内容引擎、GraphQL 查询、MCP Server 三种协议并存，权限同一套底座",
        features: ["REST 内容引擎", "GraphQL", "MCP Server"],
        color: "#6366f1"
      },
      {
        icon: "👤",
        title: "用户中心",
        description: "C 端注册登录、个人资料、订阅管理，前后台用户完全隔离",
        features: ["注册登录", "资料管理", "订阅管理"],
        color: "#06b6d4"
      },
      {
        icon: "🚀",
        title: "私有化与在线升级",
        description: "三种部署模式；核心平台发现新版本即提示，应用支持免重启 OTA 升级",
        features: ["Docker / 宝塔 / 裸机", "版本检查提示", "应用 OTA 升级"],
        color: "#2563eb"
      }
    ];
    const services = [
      { name: "admin-web", icon: "🖥️", color: "#10b981", desc: "运营后台 SPA（Vue3）" },
      { name: "portal-web", icon: "👤", color: "#8b5cf6", desc: "用户中心 SPA（Vue3）" },
      { name: "backend", icon: "⚡", color: "#f59e0b", desc: "FastAPI + SQLAlchemy + Celery" },
      { name: "PostgreSQL", icon: "🗄️", color: "#06b6d4", desc: "关系型数据库 16" },
      { name: "Redis", icon: "🔴", color: "#ef4444", desc: "缓存与消息队列 7" },
      { name: "MinIO", icon: "☁️", color: "#2563eb", desc: "对象存储" }
    ];
    const techStack = [
      { name: "FastAPI", icon: "⚡", desc: "高性能 Python API 框架" },
      { name: "Vue 3 + Vite", icon: "💚", desc: "现代前端框架" },
      { name: "Tailwind", icon: "🎨", desc: "原子化样式" },
      { name: "SQLAlchemy 2", icon: "🗄️", desc: "异步 ORM" },
      { name: "Docker", icon: "🐳", desc: "容器化部署" },
      { name: "JWT", icon: "🔐", desc: "前后台双体系鉴权" }
    ];
    const heroApps = [
      { icon: "🤖", name: "AI CMS", installed: true },
      { icon: "📢", name: "公告", installed: true },
      { icon: "🎫", name: "工单", installed: true },
      { icon: "🔀", name: "工作流", installed: true },
      { icon: "📇", name: "CRM", installed: true },
      { icon: "☁️", name: "云存储", installed: true }
    ];
    const apps = [
      { icon: "🤖", name: "AI CMS", desc: "AI 原生内容引擎" },
      { icon: "📇", name: "CRM 销售", desc: "线索到回款全流程" },
      { icon: "🏭", name: "ERP 管理", desc: "客户/供应商/进销存" },
      { icon: "⚙️", name: "MES 制造", desc: "订单/排产/报工" },
      { icon: "🔀", name: "工作流审批", desc: "可视化流程编排" },
      { icon: "🎫", name: "工单系统", desc: "问题工单流转处理" },
      { icon: "☁️", name: "云存储", desc: "多驱动对象存储" },
      { icon: "📢", name: "公告管理", desc: "公告发布与通知" },
      { icon: "🔔", name: "通知中心", desc: "多渠道通知推送" },
      { icon: "🔗", name: "链接收藏", desc: "常用链接管理" },
      { icon: "📝", name: "Quick Notes", desc: "快速记事" },
      { icon: "✅", name: "My Todo", desc: "任务清单" }
    ];
    const openIndex = ref(-1);
    const faqs = [
      { q: "Cenkor Admin 是什么？适合哪些场景？", a: "Cenkor Admin 是一款企业级平台（FastAPI + Vue3），内置应用中心、RBAC 权限、工作流审批、AI CMS 内容引擎、用户中心与审计日志。适合需要快速搭建内部管理系统、内容站点与官网，或对既有系统做后台底座的企业与团队。" },
      { q: "AI CMS 和普通 CMS 有什么不同？", a: "普通 CMS 是先有模型再填内容；AI CMS 是「说人话建模型」——用中文描述业务需求，直接生成内容类型与字段定义（草案先给你看，确认才落库）。再加 AI 起草、批量翻译、语义检索、内容体检与多渠道再分发，最后以 REST / GraphQL / MCP 三种协议交给任意前端与 Agent 消费。" },
      { q: "不接 AI 能用吗？", a: "能，而且是刻意设计的。AI 是可选增强不是运行必需：未配置模型时 AI 端点返回明确的 503 提示，而建模 UI、版本管理、多语言、审核、REST / GraphQL / MCP 只读工具完全不受影响。内网离线环境也能先把内容骨架跑起来。" },
      { q: "AI 怎么写、用哪个模型？数据会外传吗？", a: "任何 OpenAI 兼容协议的服务都能接：OpenAI、DeepSeek、通义千问、Moonshot、智谱、本地 vLLM / Ollama 或自建网关，改 base_url 与模型名即可，chat 与 embedding 还能绑不同服务商。数据只发往你自己配置的模型服务，平台不中转、不代建账号。" },
      { q: "AI 会不会乱写内容？", a: "三道闸口：起草强制 draft 状态必须人审才可发布；知识库把产品手册、FAQ、历史方案变成可检索依据，让模型引用事实而不是编事实；问答检索查不到时明确返回「查不到」，宁可空着也不编。另外还有抽样质检与模型 A/B，好坏有数据可比。" },
      { q: "支持哪些部署方式？怎么升级？", a: "三种：Docker Compose（一条命令拉起全栈）、宝塔静态、裸机 systemd。核心平台有新版本时后台顶部会出现升级横幅，用 upgrade.sh 或拉新镜像完成；可插拔应用在应用中心用授权码 OTA 升级，免重启。" },
      { q: "是开源的还是商业的？", a: "开源。代码托管在 GitHub（AGPL-3.0 协议），可自由下载部署使用；应用中心按需扩展，业务模块即插即用。" },
      { q: "应用中心是怎么工作的？", a: "每个应用通过 manifest 声明内容类型、字段、分类、权限与菜单，安装时自动注册到系统，卸载时自动清理，无需改代码。当前内置 12 个可插拔应用。" },
      { q: "RBAC 权限如何隔离？", a: "角色、权限规则、数据权限三级控制；后台（运营）与前台（C 端用户）双用户体系完全隔离。CMS 与 AI 能力还做了细分权限：读配置与改密钥是两码事，审核动作也独立于编辑。" },
      { q: "需要哪些基础服务？", a: "PostgreSQL（主库）、Redis（缓存/队列）、MinIO（对象存储）以及 backend / admin-web / portal-web 三端服务，容器化一键编排。" }
    ];
    return (_ctx, _push, _parent, _attrs) => {
      const _component_router_link = resolveComponent("router-link");
      _push(`<div${ssrRenderAttrs(mergeProps({ class: "home" }, _attrs))} data-v-991868a8><section class="hero" data-v-991868a8><div class="hero-bg" data-v-991868a8><div class="hero-grid" data-v-991868a8></div><div class="hero-glow" data-v-991868a8></div></div><div class="container" data-v-991868a8><div class="hero-content" data-v-991868a8><div class="hero-badge" data-v-991868a8><span class="badge-dot" data-v-991868a8></span> 辰科 · 企业级平台 × AI 原生内容引擎 </div><h1 data-v-991868a8> 一套后台，<br data-v-991868a8><span class="gradient-text" data-v-991868a8>装下所有业务应用</span></h1><p class="hero-desc" data-v-991868a8> FastAPI + Vue3 架构，应用中心 + RBAC 权限 + 工作流 + 用户中心开箱即用。<br data-v-991868a8> 内置 <strong data-v-991868a8>AI CMS</strong>：说一句话建内容模型，AI 起草翻译，以 REST / GraphQL / MCP 供给任意前端与 Agent。 </p><div class="hero-actions" data-v-991868a8>`);
      _push(ssrRenderComponent(_component_router_link, {
        to: "/ai-cms",
        class: "btn btn-primary btn-large"
      }, {
        default: withCtx((_, _push2, _parent2, _scopeId) => {
          if (_push2) {
            _push2(` AI CMS 能力 <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="18" height="18" data-v-991868a8${_scopeId}><line x1="5" y1="12" x2="19" y2="12" data-v-991868a8${_scopeId}></line><polyline points="12 5 19 12 12 19" data-v-991868a8${_scopeId}></polyline></svg>`);
          } else {
            return [
              createTextVNode(" AI CMS 能力 "),
              (openBlock(), createBlock("svg", {
                viewBox: "0 0 24 24",
                fill: "none",
                stroke: "currentColor",
                "stroke-width": "2",
                width: "18",
                height: "18"
              }, [
                createVNode("line", {
                  x1: "5",
                  y1: "12",
                  x2: "19",
                  y2: "12"
                }),
                createVNode("polyline", { points: "12 5 19 12 12 19" })
              ]))
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
            _push2(` 查看全部功能 `);
          } else {
            return [
              createTextVNode(" 查看全部功能 ")
            ];
          }
        }),
        _: 1
      }, _parent));
      _push(`</div><div class="hero-trust" data-v-991868a8><span data-v-991868a8><i class="tick" data-v-991868a8>✓</i> 开源 AGPL-3.0</span><span data-v-991868a8><i class="tick" data-v-991868a8>✓</i> 12 个可插拔应用</span><span data-v-991868a8><i class="tick" data-v-991868a8>✓</i> AI CMS v0.3.0</span><span data-v-991868a8><i class="tick" data-v-991868a8>✓</i> 100% 私有化</span></div></div><div class="hero-visual" data-v-991868a8><div class="hero-card" data-v-991868a8><div class="card-header" data-v-991868a8><div class="card-dots" data-v-991868a8><span data-v-991868a8></span><span data-v-991868a8></span><span data-v-991868a8></span></div><span class="card-title" data-v-991868a8>应用中心</span></div><div class="card-body" data-v-991868a8><div class="app-grid" data-v-991868a8><!--[-->`);
      ssrRenderList(heroApps, (app) => {
        _push(`<div class="app-item" data-v-991868a8><span class="app-icon" data-v-991868a8>${ssrInterpolate(app.icon)}</span><span class="app-name" data-v-991868a8>${ssrInterpolate(app.name)}</span><span class="${ssrRenderClass([{ installed: app.installed }, "app-badge"])}" data-v-991868a8>${ssrInterpolate(app.installed ? "已装" : "安装")}</span></div>`);
      });
      _push(`<!--]--></div><div class="sys-row" data-v-991868a8><div class="sys-item" data-v-991868a8><span class="dot" data-v-991868a8></span> RBAC 权限</div><div class="sys-item" data-v-991868a8><span class="dot" data-v-991868a8></span> AI 对话建模</div><div class="sys-item" data-v-991868a8><span class="dot" data-v-991868a8></span> 语义检索</div><div class="sys-item" data-v-991868a8><span class="dot" data-v-991868a8></span> 审批工作流</div></div></div><div class="card-footer" data-v-991868a8><span class="pulse-dot" data-v-991868a8></span><span data-v-991868a8>系统运行中 · AI CMS 已就绪</span><span class="footer-ver" data-v-991868a8>v0.3.0</span></div></div></div></div></section><section class="stats-section" data-v-991868a8><div class="container" data-v-991868a8><div class="stats-grid" data-v-991868a8><!--[-->`);
      ssrRenderList(stats, (stat) => {
        _push(`<div class="stat-item" data-v-991868a8><div class="stat-value" data-v-991868a8>`);
        _push(ssrRenderComponent(CounterUp, {
          value: stat.value,
          suffix: stat.suffix
        }, null, _parent));
        _push(`</div><div class="stat-label" data-v-991868a8>${ssrInterpolate(stat.label)}</div></div>`);
      });
      _push(`<!--]--></div></div></section><section class="section ai-section" data-v-991868a8><div class="container" data-v-991868a8><div class="ai-wrap" data-v-991868a8><div class="ai-copy" data-v-991868a8><span class="ai-tag" data-v-991868a8>旗舰能力 · v0.3.0 新增</span><h2 data-v-991868a8> AI CMS：<br data-v-991868a8><span class="ai-gradient" data-v-991868a8>说一句话，建一个内容模型</span></h2><p data-v-991868a8> 用中文描述业务，直接生成内容类型与字段定义，草案确认后才落库； AI 起草、批量翻译、语义检索、内容体检、多渠道再分发一条链做完。 建好的内容以 REST / GraphQL / MCP 三种协议交给任何前端与 Agent 消费。 </p><div class="ai-highlights" data-v-991868a8><!--[-->`);
      ssrRenderList(aiHighlights, (h) => {
        _push(`<div class="hl" data-v-991868a8><span class="hl-icon" data-v-991868a8>${ssrInterpolate(h.icon)}</span><div data-v-991868a8><strong data-v-991868a8>${ssrInterpolate(h.title)}</strong><span data-v-991868a8>${ssrInterpolate(h.desc)}</span></div></div>`);
      });
      _push(`<!--]--></div><div class="ai-actions" data-v-991868a8>`);
      _push(ssrRenderComponent(_component_router_link, {
        to: "/ai-cms",
        class: "btn btn-primary btn-large"
      }, {
        default: withCtx((_, _push2, _parent2, _scopeId) => {
          if (_push2) {
            _push2(` AI CMS 完整能力 <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="18" height="18" data-v-991868a8${_scopeId}><line x1="5" y1="12" x2="19" y2="12" data-v-991868a8${_scopeId}></line><polyline points="12 5 19 12 12 19" data-v-991868a8${_scopeId}></polyline></svg>`);
          } else {
            return [
              createTextVNode(" AI CMS 完整能力 "),
              (openBlock(), createBlock("svg", {
                viewBox: "0 0 24 24",
                fill: "none",
                stroke: "currentColor",
                "stroke-width": "2",
                width: "18",
                height: "18"
              }, [
                createVNode("line", {
                  x1: "5",
                  y1: "12",
                  x2: "19",
                  y2: "12"
                }),
                createVNode("polyline", { points: "12 5 19 12 12 19" })
              ]))
            ];
          }
        }),
        _: 1
      }, _parent));
      _push(ssrRenderComponent(_component_router_link, {
        to: "/deploy",
        class: "btn btn-ghost btn-large"
      }, {
        default: withCtx((_, _push2, _parent2, _scopeId) => {
          if (_push2) {
            _push2(`如何接入模型`);
          } else {
            return [
              createTextVNode("如何接入模型")
            ];
          }
        }),
        _: 1
      }, _parent));
      _push(`</div><p class="ai-note" data-v-991868a8>AI 是可选增强 —— 不配模型时，建模、审核、REST / GraphQL / MCP 全部照常工作。</p></div><div class="ai-visual" data-v-991868a8><div class="ai-console" data-v-991868a8><div class="console-head" data-v-991868a8><div class="console-dots" data-v-991868a8><span data-v-991868a8></span><span data-v-991868a8></span><span data-v-991868a8></span></div><span data-v-991868a8>AI 内容生产线</span></div><div class="console-body" data-v-991868a8><!--[-->`);
      ssrRenderList(aiSteps, (s, i) => {
        _push(`<div class="step" style="${ssrRenderStyle({ animationDelay: `${i * 0.12}s` })}" data-v-991868a8><span class="step-no" data-v-991868a8>${ssrInterpolate(String(i + 1).padStart(2, "0"))}</span><span class="step-icon" data-v-991868a8>${ssrInterpolate(s.icon)}</span><span class="step-name" data-v-991868a8>${ssrInterpolate(s.name)}</span><span class="${ssrRenderClass([s.state, "step-state"])}" data-v-991868a8>${ssrInterpolate(s.state === "done" ? "已完成" : "运行中")}</span></div>`);
      });
      _push(`<!--]--></div><div class="console-foot" data-v-991868a8><span class="pill" data-v-991868a8>10 道工序</span><span class="pill" data-v-991868a8>逐条留痕</span><span class="pill" data-v-991868a8>人工闸口</span></div></div></div></div></div></section><section class="section" data-v-991868a8><div class="container" data-v-991868a8>`);
      _push(ssrRenderComponent(SectionTitle, {
        tag: "核心能力",
        title: "企业级后台一站配齐",
        description: "AI 内容引擎 + 应用中心 + 权限 + 工作流 + 开放接口，从搭建到运营全流程覆盖",
        center: true
      }, null, _parent));
      _push(`<div class="features-grid" data-v-991868a8><!--[-->`);
      ssrRenderList(features, (feature, index) => {
        _push(ssrRenderComponent(ScrollReveal, {
          key: feature.title,
          delay: index * 100
        }, {
          default: withCtx((_, _push2, _parent2, _scopeId) => {
            if (_push2) {
              _push2(ssrRenderComponent(FeatureCard, {
                icon: feature.icon,
                title: feature.title,
                description: feature.description,
                features: feature.features,
                color: feature.color
              }, null, _parent2, _scopeId));
            } else {
              return [
                createVNode(FeatureCard, {
                  icon: feature.icon,
                  title: feature.title,
                  description: feature.description,
                  features: feature.features,
                  color: feature.color
                }, null, 8, ["icon", "title", "description", "features", "color"])
              ];
            }
          }),
          _: 2
        }, _parent));
      });
      _push(`<!--]--></div></div></section><section class="section section-alt" data-v-991868a8><div class="container" data-v-991868a8>`);
      _push(ssrRenderComponent(SectionTitle, {
        tag: "技术架构",
        title: "FastAPI + Vue3 现代架构",
        description: "前后端分离，容器化部署，支持 Docker Compose / 宝塔静态 / 裸机 systemd",
        center: true
      }, null, _parent));
      _push(`<div class="arch-grid" data-v-991868a8>`);
      _push(ssrRenderComponent(ScrollReveal, { animation: "fade-left" }, {
        default: withCtx((_, _push2, _parent2, _scopeId) => {
          if (_push2) {
            _push2(`<div class="arch-services" data-v-991868a8${_scopeId}><!--[-->`);
            ssrRenderList(services, (service) => {
              _push2(`<div class="arch-service" data-v-991868a8${_scopeId}><div class="service-icon" style="${ssrRenderStyle({ background: service.color })}" data-v-991868a8${_scopeId}>${ssrInterpolate(service.icon)}</div><div class="service-info" data-v-991868a8${_scopeId}><h4 data-v-991868a8${_scopeId}>${ssrInterpolate(service.name)}</h4><p data-v-991868a8${_scopeId}>${ssrInterpolate(service.desc)}</p></div></div>`);
            });
            _push2(`<!--]--></div>`);
          } else {
            return [
              createVNode("div", { class: "arch-services" }, [
                (openBlock(), createBlock(Fragment, null, renderList(services, (service) => {
                  return createVNode("div", {
                    class: "arch-service",
                    key: service.name
                  }, [
                    createVNode("div", {
                      class: "service-icon",
                      style: { background: service.color }
                    }, toDisplayString(service.icon), 5),
                    createVNode("div", { class: "service-info" }, [
                      createVNode("h4", null, toDisplayString(service.name), 1),
                      createVNode("p", null, toDisplayString(service.desc), 1)
                    ])
                  ]);
                }), 64))
              ])
            ];
          }
        }),
        _: 1
      }, _parent));
      _push(ssrRenderComponent(ScrollReveal, { animation: "fade-right" }, {
        default: withCtx((_, _push2, _parent2, _scopeId) => {
          if (_push2) {
            _push2(`<div class="arch-stack" data-v-991868a8${_scopeId}><h3 data-v-991868a8${_scopeId}>技术栈</h3><div class="stack-list" data-v-991868a8${_scopeId}><!--[-->`);
            ssrRenderList(techStack, (tech) => {
              _push2(`<div class="stack-item" data-v-991868a8${_scopeId}><div class="stack-icon" data-v-991868a8${_scopeId}>${ssrInterpolate(tech.icon)}</div><div data-v-991868a8${_scopeId}><strong data-v-991868a8${_scopeId}>${ssrInterpolate(tech.name)}</strong><span data-v-991868a8${_scopeId}>${ssrInterpolate(tech.desc)}</span></div></div>`);
            });
            _push2(`<!--]--></div></div>`);
          } else {
            return [
              createVNode("div", { class: "arch-stack" }, [
                createVNode("h3", null, "技术栈"),
                createVNode("div", { class: "stack-list" }, [
                  (openBlock(), createBlock(Fragment, null, renderList(techStack, (tech) => {
                    return createVNode("div", {
                      class: "stack-item",
                      key: tech.name
                    }, [
                      createVNode("div", { class: "stack-icon" }, toDisplayString(tech.icon), 1),
                      createVNode("div", null, [
                        createVNode("strong", null, toDisplayString(tech.name), 1),
                        createVNode("span", null, toDisplayString(tech.desc), 1)
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
      _push(`</div></div></section><section class="section" data-v-991868a8><div class="container" data-v-991868a8>`);
      _push(ssrRenderComponent(SectionTitle, {
        tag: "内置应用",
        title: "12 个可插拔业务应用",
        description: "CRM、ERP、MES、工作流、CMS、工单、云存储等，通过应用中心统一安装，支持授权码 OTA 升级",
        center: true
      }, null, _parent));
      _push(`<div class="app-grid-lg" data-v-991868a8><!--[-->`);
      ssrRenderList(apps, (app, index) => {
        _push(ssrRenderComponent(ScrollReveal, {
          key: app.name,
          delay: index * 60
        }, {
          default: withCtx((_, _push2, _parent2, _scopeId) => {
            if (_push2) {
              _push2(`<div class="app-card" data-v-991868a8${_scopeId}><div class="app-icon" data-v-991868a8${_scopeId}>${ssrInterpolate(app.icon)}</div><h4 data-v-991868a8${_scopeId}>${ssrInterpolate(app.name)}</h4><p data-v-991868a8${_scopeId}>${ssrInterpolate(app.desc)}</p></div>`);
            } else {
              return [
                createVNode("div", { class: "app-card" }, [
                  createVNode("div", { class: "app-icon" }, toDisplayString(app.icon), 1),
                  createVNode("h4", null, toDisplayString(app.name), 1),
                  createVNode("p", null, toDisplayString(app.desc), 1)
                ])
              ];
            }
          }),
          _: 2
        }, _parent));
      });
      _push(`<!--]--></div></div></section><section class="section section-alt faq-section" data-v-991868a8><div class="container" data-v-991868a8>`);
      _push(ssrRenderComponent(SectionTitle, {
        tag: "常见问题",
        title: "关于 Cenkor Admin 你可能想知道的",
        description: "部署方式、开源授权、权限与内容引擎…… 一站式解答",
        center: true
      }, null, _parent));
      _push(`<div class="faq-list" data-v-991868a8><!--[-->`);
      ssrRenderList(faqs, (faq, index) => {
        _push(`<div class="faq-item" data-v-991868a8><button class="faq-question" data-v-991868a8><span data-v-991868a8>${ssrInterpolate(faq.q)}</span><span class="${ssrRenderClass([{ open: openIndex.value === index }, "faq-icon"])}" data-v-991868a8><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="16" height="16" data-v-991868a8><line x1="12" y1="5" x2="12" y2="19" data-v-991868a8></line><line x1="5" y1="12" x2="19" y2="12" data-v-991868a8></line></svg></span></button><div class="${ssrRenderClass([{ open: openIndex.value === index }, "faq-answer"])}" data-v-991868a8><p data-v-991868a8>${ssrInterpolate(faq.a)}</p></div></div>`);
      });
      _push(`<!--]--></div></div></section><section class="cta-section" data-v-991868a8><div class="container" data-v-991868a8><div class="cta-content" data-v-991868a8>`);
      _push(ssrRenderComponent(ScrollReveal, null, {
        default: withCtx((_, _push2, _parent2, _scopeId) => {
          if (_push2) {
            _push2(`<h2 data-v-991868a8${_scopeId}>准备好搭建你的后台管理平台了吗？</h2><p data-v-991868a8${_scopeId}>开源平台，应用中心按需扩展，私有化部署数据自主可控</p><div class="cta-actions" data-v-991868a8${_scopeId}>`);
            _push2(ssrRenderComponent(_component_router_link, {
              to: "/features",
              class: "btn btn-primary btn-large"
            }, {
              default: withCtx((_2, _push3, _parent3, _scopeId2) => {
                if (_push3) {
                  _push3(`查看功能`);
                } else {
                  return [
                    createTextVNode("查看功能")
                  ];
                }
              }),
              _: 1
            }, _parent2, _scopeId));
            _push2(`<a${ssrRenderAttr("href", unref(urls).github)} target="_blank" rel="noopener" class="btn btn-secondary btn-large" data-v-991868a8${_scopeId}>GitHub 仓库</a></div>`);
          } else {
            return [
              createVNode("h2", null, "准备好搭建你的后台管理平台了吗？"),
              createVNode("p", null, "开源平台，应用中心按需扩展，私有化部署数据自主可控"),
              createVNode("div", { class: "cta-actions" }, [
                createVNode(_component_router_link, {
                  to: "/features",
                  class: "btn btn-primary btn-large"
                }, {
                  default: withCtx(() => [
                    createTextVNode("查看功能")
                  ]),
                  _: 1
                }),
                createVNode("a", {
                  href: unref(urls).github,
                  target: "_blank",
                  rel: "noopener",
                  class: "btn btn-secondary btn-large"
                }, "GitHub 仓库", 8, ["href"])
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
  (ssrContext.modules || (ssrContext.modules = /* @__PURE__ */ new Set())).add("src/views/Home.vue");
  return _sfc_setup ? _sfc_setup(props, ctx) : void 0;
};
const Home = /* @__PURE__ */ _export_sfc(_sfc_main, [["__scopeId", "data-v-991868a8"]]);
export {
  Home as default
};
