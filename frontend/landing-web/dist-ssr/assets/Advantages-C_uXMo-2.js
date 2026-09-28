import { defineComponent, resolveComponent, mergeProps, withCtx, createVNode, toDisplayString, createTextVNode, useSSRContext } from "vue";
import { ssrRenderAttrs, ssrRenderList, ssrRenderComponent, ssrRenderStyle, ssrInterpolate } from "vue/server-renderer";
import { S as SectionTitle } from "./SectionTitle-NKY75B6X.js";
import { S as ScrollReveal } from "./ScrollReveal-BjFAJfMT.js";
import { _ as _export_sfc } from "../entry-server.js";
import "vue-router";
import "@unhead/vue";
import "pinia";
const _sfc_main = /* @__PURE__ */ defineComponent({
  __name: "Advantages",
  __ssrInlineRender: true,
  setup(__props) {
    const advantages = [
      {
        icon: "🏪",
        title: "应用中心生态",
        description: "应用 manifest 声明内容/字段/权限/菜单，安装时自动注册，卸载自动清理，业务模块即插即用。",
        bg: "rgba(16, 185, 129, 0.1)"
      },
      {
        icon: "📝",
        title: "通用内容引擎",
        description: "动态字段定义 + 21+ 字段类型 + 多级分类标签，后台 UI 即可扩字段，无需改代码。",
        bg: "rgba(245, 158, 11, 0.1)"
      },
      {
        icon: "⚡",
        title: "现代技术栈",
        description: "FastAPI 异步高性能 + Vue3 + SQLAlchemy 2，PostgreSQL/Redis/MinIO 标准中间件。",
        bg: "rgba(139, 92, 246, 0.1)"
      },
      {
        icon: "🔐",
        title: "安全可控",
        description: "JWT 前后台双体系鉴权 + RBAC 权限 + 审计日志，平台安全可追溯。",
        bg: "rgba(236, 72, 153, 0.1)"
      },
      {
        icon: "🏠",
        title: "灵活部署",
        description: "Docker Compose / 宝塔静态 dist / 裸机 systemd 三种模式，可独立运营不依赖官网。",
        bg: "rgba(37, 99, 235, 0.1)"
      },
      {
        icon: "🔗",
        title: "开放 API",
        description: "公开只读 API（/api/v1/public/*）供任意前端消费，生态开放可扩展。",
        bg: "rgba(6, 182, 212, 0.1)"
      }
    ];
    const techStack = [
      { name: "FastAPI", icon: "⚡", desc: "Python 异步 API 框架" },
      { name: "Vue 3 + Vite", icon: "💚", desc: "现代前端框架" },
      { name: "Tailwind", icon: "🎨", desc: "原子化样式" },
      { name: "PostgreSQL 16", icon: "🗄️", desc: "关系型数据库" },
      { name: "Redis 7", icon: "🔴", desc: "缓存与消息" },
      { name: "Docker", icon: "🐳", desc: "容器化部署" }
    ];
    return (_ctx, _push, _parent, _attrs) => {
      const _component_router_link = resolveComponent("router-link");
      _push(`<div${ssrRenderAttrs(mergeProps({ class: "advantages-page" }, _attrs))} data-v-61bf4607><section class="page-hero" data-v-61bf4607><div class="container" data-v-61bf4607><div class="page-hero-content" data-v-61bf4607><span class="hero-tag" data-v-61bf4607>技术优势</span><h1 data-v-61bf4607>为什么选择辰科Cenkor Admin</h1><p data-v-61bf4607>现代技术栈 + 应用中心生态 + 灵活部署，企业级后台管理平台首选</p></div></div></section><section class="section" data-v-61bf4607><div class="container" data-v-61bf4607><div class="advantages-grid" data-v-61bf4607><!--[-->`);
      ssrRenderList(advantages, (adv, index) => {
        _push(ssrRenderComponent(ScrollReveal, {
          key: adv.title,
          delay: index * 100
        }, {
          default: withCtx((_, _push2, _parent2, _scopeId) => {
            if (_push2) {
              _push2(`<div class="adv-card" data-v-61bf4607${_scopeId}><div class="adv-icon" style="${ssrRenderStyle({ background: adv.bg })}" data-v-61bf4607${_scopeId}>${ssrInterpolate(adv.icon)}</div><h3 data-v-61bf4607${_scopeId}>${ssrInterpolate(adv.title)}</h3><p data-v-61bf4607${_scopeId}>${ssrInterpolate(adv.description)}</p></div>`);
            } else {
              return [
                createVNode("div", { class: "adv-card" }, [
                  createVNode("div", {
                    class: "adv-icon",
                    style: { background: adv.bg }
                  }, toDisplayString(adv.icon), 5),
                  createVNode("h3", null, toDisplayString(adv.title), 1),
                  createVNode("p", null, toDisplayString(adv.description), 1)
                ])
              ];
            }
          }),
          _: 2
        }, _parent));
      });
      _push(`<!--]--></div></div></section><section class="section section-alt" data-v-61bf4607><div class="container" data-v-61bf4607>`);
      _push(ssrRenderComponent(SectionTitle, {
        tag: "技术栈",
        title: "现代技术栈",
        description: "FastAPI + Vue3 + PostgreSQL，异步高性能，容器化交付",
        center: true
      }, null, _parent));
      _push(`<div class="stack-grid" data-v-61bf4607><!--[-->`);
      ssrRenderList(techStack, (tech) => {
        _push(`<div class="stack-item" data-v-61bf4607><div class="stack-icon" data-v-61bf4607>${ssrInterpolate(tech.icon)}</div><div data-v-61bf4607><strong data-v-61bf4607>${ssrInterpolate(tech.name)}</strong><span data-v-61bf4607>${ssrInterpolate(tech.desc)}</span></div></div>`);
      });
      _push(`<!--]--></div></div></section><section class="section" data-v-61bf4607><div class="container" data-v-61bf4607>`);
      _push(ssrRenderComponent(SectionTitle, {
        tag: "对比优势",
        title: "Cenkor Admin 的核心竞争力",
        description: "应用中心生态 + 通用内容引擎 + 灵活部署，平台化交付",
        center: true
      }, null, _parent));
      _push(`<div class="compare-grid" data-v-61bf4607><div class="compare-card vs" data-v-61bf4607><h3 data-v-61bf4607>传统后台框架</h3><ul data-v-61bf4607><li class="no" data-v-61bf4607>业务功能需逐套开发</li><li class="no" data-v-61bf4607>内容字段改代码才能扩展</li><li class="no" data-v-61bf4607>应用难以按需安装</li><li class="no" data-v-61bf4607>前后台用户体系混杂</li><li class="no" data-v-61bf4607>部署方式单一</li></ul></div><div class="compare-card win" data-v-61bf4607><div class="win-badge" data-v-61bf4607>推荐</div><h3 data-v-61bf4607>辰科Cenkor Admin</h3><ul data-v-61bf4607><li class="yes" data-v-61bf4607>应用中心按需安装，即插即用</li><li class="yes" data-v-61bf4607>通用内容引擎，后台动态扩字段</li><li class="yes" data-v-61bf4607>应用安装自动注册权限/菜单</li><li class="yes" data-v-61bf4607>前后台双用户体系完全隔离</li><li class="yes" data-v-61bf4607>Docker/宝塔/裸机三种部署</li></ul></div></div></div></section><section class="cta-section" data-v-61bf4607><div class="container" data-v-61bf4607><div class="cta-content" data-v-61bf4607><h2 data-v-61bf4607>把时间花在业务上，而不是重复造后台</h2><p data-v-61bf4607>Cenkor Admin 让后台平台一次搭建，处处复用</p><div class="cta-actions" data-v-61bf4607>`);
      _push(ssrRenderComponent(_component_router_link, {
        to: "/features",
        class: "btn btn-primary btn-large"
      }, {
        default: withCtx((_, _push2, _parent2, _scopeId) => {
          if (_push2) {
            _push2(`查看功能`);
          } else {
            return [
              createTextVNode("查看功能")
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
            _push2(`私有部署`);
          } else {
            return [
              createTextVNode("私有部署")
            ];
          }
        }),
        _: 1
      }, _parent));
      _push(`</div></div></div></section></div>`);
    };
  }
});
const _sfc_setup = _sfc_main.setup;
_sfc_main.setup = (props, ctx) => {
  const ssrContext = useSSRContext();
  (ssrContext.modules || (ssrContext.modules = /* @__PURE__ */ new Set())).add("src/views/Advantages.vue");
  return _sfc_setup ? _sfc_setup(props, ctx) : void 0;
};
const Advantages = /* @__PURE__ */ _export_sfc(_sfc_main, [["__scopeId", "data-v-61bf4607"]]);
export {
  Advantages as default
};
