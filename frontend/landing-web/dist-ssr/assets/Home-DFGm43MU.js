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
    return (_ctx, _push, _parent, _attrs) => {
      const _component_router_link = resolveComponent("router-link");
      _push(`<div${ssrRenderAttrs(mergeProps({ class: "home" }, _attrs))} data-v-c60bf1ef><section class="hero" data-v-c60bf1ef><div class="hero-bg" data-v-c60bf1ef><div class="hero-grid" data-v-c60bf1ef></div><div class="hero-glow" data-v-c60bf1ef></div></div><div class="container" data-v-c60bf1ef><div class="hero-content" data-v-c60bf1ef><div class="hero-badge" data-v-c60bf1ef><span class="badge-dot" data-v-c60bf1ef></span> 辰科 · 企业级后台管理平台 </div><h1 data-v-c60bf1ef> 一套后台，<br data-v-c60bf1ef><span class="gradient-text" data-v-c60bf1ef>装下所有业务应用</span></h1><p class="hero-desc" data-v-c60bf1ef> FastAPI + Vue3 架构，应用中心 + RBAC 权限 + 通用内容引擎 + 用户中心开箱即用。<br data-v-c60bf1ef> 应用按需安装，支持私有化部署，可独立运营不依赖任何官网。 </p><div class="hero-actions" data-v-c60bf1ef>`);
      _push(ssrRenderComponent(_component_router_link, {
        to: "/features",
        class: "btn btn-primary btn-large"
      }, {
        default: withCtx((_, _push2, _parent2, _scopeId) => {
          if (_push2) {
            _push2(` 查看功能 <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="18" height="18" data-v-c60bf1ef${_scopeId}><line x1="5" y1="12" x2="19" y2="12" data-v-c60bf1ef${_scopeId}></line><polyline points="12 5 19 12 12 19" data-v-c60bf1ef${_scopeId}></polyline></svg>`);
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
      _push(`</div></div><div class="hero-visual" data-v-c60bf1ef><div class="hero-card" data-v-c60bf1ef><div class="card-header" data-v-c60bf1ef><div class="card-dots" data-v-c60bf1ef><span data-v-c60bf1ef></span><span data-v-c60bf1ef></span><span data-v-c60bf1ef></span></div><span class="card-title" data-v-c60bf1ef>应用中心</span></div><div class="card-body" data-v-c60bf1ef><div class="app-grid" data-v-c60bf1ef><!--[-->`);
      ssrRenderList(heroApps, (app) => {
        _push(`<div class="app-item" data-v-c60bf1ef><span class="app-icon" data-v-c60bf1ef>${ssrInterpolate(app.icon)}</span><span class="app-name" data-v-c60bf1ef>${ssrInterpolate(app.name)}</span><span class="${ssrRenderClass([{ installed: app.installed }, "app-badge"])}" data-v-c60bf1ef>${ssrInterpolate(app.installed ? "已装" : "安装")}</span></div>`);
      });
      _push(`<!--]--></div><div class="sys-row" data-v-c60bf1ef><div class="sys-item" data-v-c60bf1ef><span class="dot" data-v-c60bf1ef></span> RBAC 权限</div><div class="sys-item" data-v-c60bf1ef><span class="dot" data-v-c60bf1ef></span> CMS 内容引擎</div><div class="sys-item" data-v-c60bf1ef><span class="dot" data-v-c60bf1ef></span> 审计日志</div><div class="sys-item" data-v-c60bf1ef><span class="dot" data-v-c60bf1ef></span> 用户中心</div></div></div></div></div></div></section><section class="stats-section" data-v-c60bf1ef><div class="container" data-v-c60bf1ef><div class="stats-grid" data-v-c60bf1ef><!--[-->`);
      ssrRenderList(stats, (stat) => {
        _push(`<div class="stat-item" data-v-c60bf1ef><div class="stat-value" data-v-c60bf1ef>`);
        _push(ssrRenderComponent(CounterUp, {
          value: stat.value,
          suffix: stat.suffix
        }, null, _parent));
        _push(`</div><div class="stat-label" data-v-c60bf1ef>${ssrInterpolate(stat.label)}</div></div>`);
      });
      _push(`<!--]--></div></div></section><section class="section" data-v-c60bf1ef><div class="container" data-v-c60bf1ef>`);
      _push(ssrRenderComponent(SectionTitle, {
        tag: "核心能力",
        title: "企业级后台一站配齐",
        description: "应用中心 + 权限 + 内容 + 用户，从搭建到运营全流程覆盖",
        center: true
      }, null, _parent));
      _push(`<div class="features-grid" data-v-c60bf1ef><!--[-->`);
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
      _push(`<!--]--></div></div></section><section class="section section-alt" data-v-c60bf1ef><div class="container" data-v-c60bf1ef>`);
      _push(ssrRenderComponent(SectionTitle, {
        tag: "技术架构",
        title: "FastAPI + Vue3 现代架构",
        description: "前后端分离，容器化部署，支持 Docker Compose / 宝塔静态 / 裸机 systemd",
        center: true
      }, null, _parent));
      _push(`<div class="arch-grid" data-v-c60bf1ef>`);
      _push(ssrRenderComponent(ScrollReveal, { animation: "fade-left" }, {
        default: withCtx((_, _push2, _parent2, _scopeId) => {
          if (_push2) {
            _push2(`<div class="arch-services" data-v-c60bf1ef${_scopeId}><!--[-->`);
            ssrRenderList(services, (service) => {
              _push2(`<div class="arch-service" data-v-c60bf1ef${_scopeId}><div class="service-icon" style="${ssrRenderStyle({ background: service.color })}" data-v-c60bf1ef${_scopeId}>${ssrInterpolate(service.icon)}</div><div class="service-info" data-v-c60bf1ef${_scopeId}><h4 data-v-c60bf1ef${_scopeId}>${ssrInterpolate(service.name)}</h4><p data-v-c60bf1ef${_scopeId}>${ssrInterpolate(service.desc)}</p></div></div>`);
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
            _push2(`<div class="arch-stack" data-v-c60bf1ef${_scopeId}><h3 data-v-c60bf1ef${_scopeId}>技术栈</h3><div class="stack-list" data-v-c60bf1ef${_scopeId}><!--[-->`);
            ssrRenderList(techStack, (tech) => {
              _push2(`<div class="stack-item" data-v-c60bf1ef${_scopeId}><div class="stack-icon" data-v-c60bf1ef${_scopeId}>${ssrInterpolate(tech.icon)}</div><div data-v-c60bf1ef${_scopeId}><strong data-v-c60bf1ef${_scopeId}>${ssrInterpolate(tech.name)}</strong><span data-v-c60bf1ef${_scopeId}>${ssrInterpolate(tech.desc)}</span></div></div>`);
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
      _push(`</div></div></section><section class="section" data-v-c60bf1ef><div class="container" data-v-c60bf1ef>`);
      _push(ssrRenderComponent(SectionTitle, {
        tag: "内置应用",
        title: "开箱即用的业务应用",
        description: "公告、工单、云存储、链接、记事等，通过应用中心统一安装管理",
        center: true
      }, null, _parent));
      _push(`<div class="app-grid-lg" data-v-c60bf1ef><!--[-->`);
      ssrRenderList(apps, (app, index) => {
        _push(ssrRenderComponent(ScrollReveal, {
          key: app.name,
          delay: index * 60
        }, {
          default: withCtx((_, _push2, _parent2, _scopeId) => {
            if (_push2) {
              _push2(`<div class="app-card" data-v-c60bf1ef${_scopeId}><div class="app-icon" data-v-c60bf1ef${_scopeId}>${ssrInterpolate(app.icon)}</div><h4 data-v-c60bf1ef${_scopeId}>${ssrInterpolate(app.name)}</h4><p data-v-c60bf1ef${_scopeId}>${ssrInterpolate(app.desc)}</p></div>`);
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
      _push(`<!--]--></div></div></section><section class="cta-section" data-v-c60bf1ef><div class="container" data-v-c60bf1ef><div class="cta-content" data-v-c60bf1ef>`);
      _push(ssrRenderComponent(ScrollReveal, null, {
        default: withCtx((_, _push2, _parent2, _scopeId) => {
          if (_push2) {
            _push2(`<h2 data-v-c60bf1ef${_scopeId}>准备好搭建你的后台管理平台了吗？</h2><p data-v-c60bf1ef${_scopeId}>开源平台，应用中心按需扩展，私有化部署数据自主可控</p><div class="cta-actions" data-v-c60bf1ef${_scopeId}>`);
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
            _push2(`<a${ssrRenderAttr("href", unref(urls).github)} target="_blank" rel="noopener" class="btn btn-secondary btn-large" data-v-c60bf1ef${_scopeId}>GitHub 仓库</a></div>`);
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
const Home = /* @__PURE__ */ _export_sfc(_sfc_main, [["__scopeId", "data-v-c60bf1ef"]]);
export {
  Home as default
};
