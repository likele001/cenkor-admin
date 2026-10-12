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
      { value: 8, label: "内置业务应用", suffix: "" },
      { value: 21, label: "CMS 字段类型", suffix: "+" },
      { value: 3, label: "部署模式", suffix: " 种" },
      { value: 100, label: "私有化部署", suffix: "%" }
    ];
    const features = [
      {
        icon: "🏪",
        title: "应用中心",
        description: "应用按需安装/卸载，自动注册权限、菜单、内容类型，业务模块即插即用",
        features: ["应用安装卸载", "权限自动注册", "菜单自动生成"],
        color: "#10b981"
      },
      {
        icon: "🔐",
        title: "RBAC 权限",
        description: "角色、权限规则、数据权限三级控制，后台/前台双用户体系隔离",
        features: ["角色管理", "数据权限", "双用户体系"],
        color: "#8b5cf6"
      },
      {
        icon: "📝",
        title: "通用内容引擎",
        description: "CMS 动态字段定义，21+ 字段类型，分类标签系统，后台即可改字段",
        features: ["动态字段", "分类标签", "内容类型"],
        color: "#f59e0b"
      },
      {
        icon: "👤",
        title: "用户中心",
        description: "C 端注册登录、个人资料、订阅管理，前后台用户完全隔离",
        features: ["注册登录", "资料管理", "订阅管理"],
        color: "#06b6d4"
      },
      {
        icon: "🛡️",
        title: "审计日志",
        description: "操作记录完整留痕，平台安全可追溯",
        features: ["操作记录", "安全追溯", "合规留痕"],
        color: "#ec4899"
      },
      {
        icon: "🏠",
        title: "私有化部署",
        description: "Docker Compose / 宝塔静态 / 裸机 systemd 三种模式，可独立运营",
        features: ["容器化部署", "宝塔静态", "裸机部署"],
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
      { icon: "📢", name: "公告", installed: true },
      { icon: "🎫", name: "工单", installed: true },
      { icon: "☁️", name: "云存储", installed: true },
      { icon: "🔗", name: "链接", installed: true },
      { icon: "📝", name: "记事", installed: true },
      { icon: "✅", name: "Todo", installed: true }
    ];
    const apps = [
      { icon: "📢", name: "公告管理", desc: "公告发布与通知" },
      { icon: "🎫", name: "工单系统", desc: "问题工单流转处理" },
      { icon: "☁️", name: "云存储", desc: "对象存储管理" },
      { icon: "🔗", name: "链接收藏", desc: "常用链接管理" },
      { icon: "📝", name: "Quick Notes", desc: "快速记事" },
      { icon: "✅", name: "My Todo", desc: "任务清单" },
      { icon: "🔔", name: "通知", desc: "系统通知推送" },
      { icon: "📰", name: "CMS", desc: "官网内容管理" }
    ];
    const openIndex = ref(-1);
    const faqs = [
      { q: "Cenkor Admin 是什么？适合哪些场景？", a: "Cenkor Admin 是一款企业级后台管理平台（FastAPI + Vue3），内置应用中心、RBAC 权限、通用内容引擎（CMS）、用户中心与审计日志。适合需要快速搭建内部管理系统、内容站点，或对既有系统做后台底座的企业与团队。" },
      { q: "支持哪些部署方式？", a: "支持三种：Docker Compose（一条命令拉起全栈）、宝塔静态、裸机 systemd。数据部署在自己服务器，完全私有化、自主可控。" },
      { q: "是开源的还是商业的？", a: "开源。代码托管在 GitHub（AGPL-3.0 协议），可自由下载部署使用；应用中心按需扩展，业务模块即插即用。" },
      { q: "应用中心是怎么工作的？", a: "每个应用通过 manifest 声明内容类型、字段、分类、权限与菜单，安装时自动注册到系统，卸载时自动清理，无需改代码。" },
      { q: "通用内容引擎（CMS）能做什么？", a: "后台即可动态增删字段，支持 21+ 字段类型、多级分类与标签，文章/页面/内容类型统一管理，官网内容也能在系统里维护。" },
      { q: "RBAC 权限如何隔离？", a: "角色、权限规则、数据权限三级控制；后台（运营）与前台（C 端用户）双用户体系完全隔离，各自独立登录与权限。" },
      { q: "需要哪些基础服务？", a: "PostgreSQL（主库）、Redis（缓存/队列）、MinIO（对象存储）以及 backend / admin-web / portal-web 三端服务，容器化一键编排。" },
      { q: "可以独立运营、不依赖官网吗？", a: "可以。Cenkor Admin 可独立部署运营，不依赖任何官网；支持多应用并行，适合作为自己的后台底座持续扩展。" }
    ];
    return (_ctx, _push, _parent, _attrs) => {
      const _component_router_link = resolveComponent("router-link");
      _push(`<div${ssrRenderAttrs(mergeProps({ class: "home" }, _attrs))} data-v-efb890b9><section class="hero" data-v-efb890b9><div class="hero-bg" data-v-efb890b9><div class="hero-grid" data-v-efb890b9></div><div class="hero-glow" data-v-efb890b9></div></div><div class="container" data-v-efb890b9><div class="hero-content" data-v-efb890b9><div class="hero-badge" data-v-efb890b9><span class="badge-dot" data-v-efb890b9></span> 辰科 · 企业级后台管理平台 </div><h1 data-v-efb890b9> 一套后台，<br data-v-efb890b9><span class="gradient-text" data-v-efb890b9>装下所有业务应用</span></h1><p class="hero-desc" data-v-efb890b9> FastAPI + Vue3 架构，应用中心 + RBAC 权限 + 通用内容引擎 + 用户中心开箱即用。<br data-v-efb890b9> 应用按需安装，支持私有化部署，可独立运营不依赖任何官网。 </p><div class="hero-actions" data-v-efb890b9>`);
      _push(ssrRenderComponent(_component_router_link, {
        to: "/features",
        class: "btn btn-primary btn-large"
      }, {
        default: withCtx((_, _push2, _parent2, _scopeId) => {
          if (_push2) {
            _push2(` 查看功能 <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="18" height="18" data-v-efb890b9${_scopeId}><line x1="5" y1="12" x2="19" y2="12" data-v-efb890b9${_scopeId}></line><polyline points="12 5 19 12 12 19" data-v-efb890b9${_scopeId}></polyline></svg>`);
          } else {
            return [
              createTextVNode(" 查看功能 "),
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
        class: "btn btn-secondary btn-large"
      }, {
        default: withCtx((_, _push2, _parent2, _scopeId) => {
          if (_push2) {
            _push2(` 私有部署 `);
          } else {
            return [
              createTextVNode(" 私有部署 ")
            ];
          }
        }),
        _: 1
      }, _parent));
      _push(`</div><div class="hero-trust" data-v-efb890b9><span data-v-efb890b9><i class="tick" data-v-efb890b9>✓</i> 开源 AGPL-3.0</span><span data-v-efb890b9><i class="tick" data-v-efb890b9>✓</i> Docker 一键部署</span><span data-v-efb890b9><i class="tick" data-v-efb890b9>✓</i> 8 个内置应用</span><span data-v-efb890b9><i class="tick" data-v-efb890b9>✓</i> 100% 私有化</span></div></div><div class="hero-visual" data-v-efb890b9><div class="hero-card" data-v-efb890b9><div class="card-header" data-v-efb890b9><div class="card-dots" data-v-efb890b9><span data-v-efb890b9></span><span data-v-efb890b9></span><span data-v-efb890b9></span></div><span class="card-title" data-v-efb890b9>应用中心</span></div><div class="card-body" data-v-efb890b9><div class="app-grid" data-v-efb890b9><!--[-->`);
      ssrRenderList(heroApps, (app) => {
        _push(`<div class="app-item" data-v-efb890b9><span class="app-icon" data-v-efb890b9>${ssrInterpolate(app.icon)}</span><span class="app-name" data-v-efb890b9>${ssrInterpolate(app.name)}</span><span class="${ssrRenderClass([{ installed: app.installed }, "app-badge"])}" data-v-efb890b9>${ssrInterpolate(app.installed ? "已装" : "安装")}</span></div>`);
      });
      _push(`<!--]--></div><div class="sys-row" data-v-efb890b9><div class="sys-item" data-v-efb890b9><span class="dot" data-v-efb890b9></span> RBAC 权限</div><div class="sys-item" data-v-efb890b9><span class="dot" data-v-efb890b9></span> CMS 内容引擎</div><div class="sys-item" data-v-efb890b9><span class="dot" data-v-efb890b9></span> 审计日志</div><div class="sys-item" data-v-efb890b9><span class="dot" data-v-efb890b9></span> 用户中心</div></div></div><div class="card-footer" data-v-efb890b9><span class="pulse-dot" data-v-efb890b9></span><span data-v-efb890b9>系统运行中 · 应用中心已就绪</span><span class="footer-ver" data-v-efb890b9>v2.1</span></div></div></div></div></section><section class="stats-section" data-v-efb890b9><div class="container" data-v-efb890b9><div class="stats-grid" data-v-efb890b9><!--[-->`);
      ssrRenderList(stats, (stat) => {
        _push(`<div class="stat-item" data-v-efb890b9><div class="stat-value" data-v-efb890b9>`);
        _push(ssrRenderComponent(CounterUp, {
          value: stat.value,
          suffix: stat.suffix
        }, null, _parent));
        _push(`</div><div class="stat-label" data-v-efb890b9>${ssrInterpolate(stat.label)}</div></div>`);
      });
      _push(`<!--]--></div></div></section><section class="section" data-v-efb890b9><div class="container" data-v-efb890b9>`);
      _push(ssrRenderComponent(SectionTitle, {
        tag: "核心能力",
        title: "企业级后台一站配齐",
        description: "应用中心 + 权限 + 内容 + 用户，从搭建到运营全流程覆盖",
        center: true
      }, null, _parent));
      _push(`<div class="features-grid" data-v-efb890b9><!--[-->`);
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
      _push(`<!--]--></div></div></section><section class="section section-alt" data-v-efb890b9><div class="container" data-v-efb890b9>`);
      _push(ssrRenderComponent(SectionTitle, {
        tag: "技术架构",
        title: "FastAPI + Vue3 现代架构",
        description: "前后端分离，容器化部署，支持 Docker Compose / 宝塔静态 / 裸机 systemd",
        center: true
      }, null, _parent));
      _push(`<div class="arch-grid" data-v-efb890b9>`);
      _push(ssrRenderComponent(ScrollReveal, { animation: "fade-left" }, {
        default: withCtx((_, _push2, _parent2, _scopeId) => {
          if (_push2) {
            _push2(`<div class="arch-services" data-v-efb890b9${_scopeId}><!--[-->`);
            ssrRenderList(services, (service) => {
              _push2(`<div class="arch-service" data-v-efb890b9${_scopeId}><div class="service-icon" style="${ssrRenderStyle({ background: service.color })}" data-v-efb890b9${_scopeId}>${ssrInterpolate(service.icon)}</div><div class="service-info" data-v-efb890b9${_scopeId}><h4 data-v-efb890b9${_scopeId}>${ssrInterpolate(service.name)}</h4><p data-v-efb890b9${_scopeId}>${ssrInterpolate(service.desc)}</p></div></div>`);
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
            _push2(`<div class="arch-stack" data-v-efb890b9${_scopeId}><h3 data-v-efb890b9${_scopeId}>技术栈</h3><div class="stack-list" data-v-efb890b9${_scopeId}><!--[-->`);
            ssrRenderList(techStack, (tech) => {
              _push2(`<div class="stack-item" data-v-efb890b9${_scopeId}><div class="stack-icon" data-v-efb890b9${_scopeId}>${ssrInterpolate(tech.icon)}</div><div data-v-efb890b9${_scopeId}><strong data-v-efb890b9${_scopeId}>${ssrInterpolate(tech.name)}</strong><span data-v-efb890b9${_scopeId}>${ssrInterpolate(tech.desc)}</span></div></div>`);
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
      _push(`</div></div></section><section class="section" data-v-efb890b9><div class="container" data-v-efb890b9>`);
      _push(ssrRenderComponent(SectionTitle, {
        tag: "内置应用",
        title: "开箱即用的业务应用",
        description: "公告、工单、云存储、链接、记事等，通过应用中心统一安装管理",
        center: true
      }, null, _parent));
      _push(`<div class="app-grid-lg" data-v-efb890b9><!--[-->`);
      ssrRenderList(apps, (app, index) => {
        _push(ssrRenderComponent(ScrollReveal, {
          key: app.name,
          delay: index * 60
        }, {
          default: withCtx((_, _push2, _parent2, _scopeId) => {
            if (_push2) {
              _push2(`<div class="app-card" data-v-efb890b9${_scopeId}><div class="app-icon" data-v-efb890b9${_scopeId}>${ssrInterpolate(app.icon)}</div><h4 data-v-efb890b9${_scopeId}>${ssrInterpolate(app.name)}</h4><p data-v-efb890b9${_scopeId}>${ssrInterpolate(app.desc)}</p></div>`);
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
      _push(`<!--]--></div></div></section><section class="section section-alt faq-section" data-v-efb890b9><div class="container" data-v-efb890b9>`);
      _push(ssrRenderComponent(SectionTitle, {
        tag: "常见问题",
        title: "关于 Cenkor Admin 你可能想知道的",
        description: "部署方式、开源授权、权限与内容引擎…… 一站式解答",
        center: true
      }, null, _parent));
      _push(`<div class="faq-list" data-v-efb890b9><!--[-->`);
      ssrRenderList(faqs, (faq, index) => {
        _push(`<div class="faq-item" data-v-efb890b9><button class="faq-question" data-v-efb890b9><span data-v-efb890b9>${ssrInterpolate(faq.q)}</span><span class="${ssrRenderClass([{ open: openIndex.value === index }, "faq-icon"])}" data-v-efb890b9><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="16" height="16" data-v-efb890b9><line x1="12" y1="5" x2="12" y2="19" data-v-efb890b9></line><line x1="5" y1="12" x2="19" y2="12" data-v-efb890b9></line></svg></span></button><div class="${ssrRenderClass([{ open: openIndex.value === index }, "faq-answer"])}" data-v-efb890b9><p data-v-efb890b9>${ssrInterpolate(faq.a)}</p></div></div>`);
      });
      _push(`<!--]--></div></div></section><section class="cta-section" data-v-efb890b9><div class="container" data-v-efb890b9><div class="cta-content" data-v-efb890b9>`);
      _push(ssrRenderComponent(ScrollReveal, null, {
        default: withCtx((_, _push2, _parent2, _scopeId) => {
          if (_push2) {
            _push2(`<h2 data-v-efb890b9${_scopeId}>准备好搭建你的后台管理平台了吗？</h2><p data-v-efb890b9${_scopeId}>开源平台，应用中心按需扩展，私有化部署数据自主可控</p><div class="cta-actions" data-v-efb890b9${_scopeId}>`);
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
            _push2(`<a${ssrRenderAttr("href", unref(urls).github)} target="_blank" rel="noopener" class="btn btn-secondary btn-large" data-v-efb890b9${_scopeId}>GitHub 仓库</a></div>`);
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
const Home = /* @__PURE__ */ _export_sfc(_sfc_main, [["__scopeId", "data-v-efb890b9"]]);
export {
  Home as default
};
