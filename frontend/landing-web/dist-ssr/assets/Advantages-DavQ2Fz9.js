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
        icon: "🤖",
        title: "AI 原生内容层",
        description: "对话式建模、AI 起草翻译、语义检索、内容生产线。AI 是可选增强 —— 不配模型时传统能力照常工作。",
        bg: "rgba(139, 92, 246, 0.1)"
      },
      {
        icon: "🏪",
        title: "应用中心生态",
        description: "应用 manifest 声明内容/字段/权限/菜单，安装时自动注册，卸载自动清理，业务模块即插即用。",
        bg: "rgba(16, 185, 129, 0.1)"
      },
      {
        icon: "🧩",
        title: "动态建模与多站点",
        description: "动态字段定义 + 21+ 字段类型 + 多级分类标签，后台 UI 即可扩字段；多站点站群会话级隔离。",
        bg: "rgba(245, 158, 11, 0.1)"
      },
      {
        icon: "⚡",
        title: "现代技术栈",
        description: "FastAPI 异步高性能 + Vue3 + SQLAlchemy 2，PostgreSQL 16 / Redis 7 / MinIO 标准中间件。",
        bg: "rgba(6, 182, 212, 0.1)"
      },
      {
        icon: "🔐",
        title: "安全可控",
        description: "JWT 前后台双体系鉴权 + RBAC 三级权限 + 审计日志；AI 密钥只出掩码，读配置与改密钥分权。",
        bg: "rgba(236, 72, 153, 0.1)"
      },
      {
        icon: "🔌",
        title: "三协议开放",
        description: "REST / GraphQL / MCP 三种出口共享同一套权限与检索底座，Agent 可直接消费内容。",
        bg: "rgba(99, 102, 241, 0.1)"
      },
      {
        icon: "🚀",
        title: "在线升级",
        description: "核心平台发现新版本即在工作台提示，升级脚本自动备份与迁移；可插拔应用授权码 OTA，免重启。",
        bg: "rgba(20, 184, 166, 0.1)"
      },
      {
        icon: "📊",
        title: "可观测",
        description: "内容埋点、效果统计、AI 用量三段计费与操作审计，效果与成本都能落到数字上。",
        bg: "rgba(234, 88, 12, 0.1)"
      },
      {
        icon: "🏠",
        title: "灵活部署",
        description: "Docker Compose / 宝塔静态 dist / 裸机 systemd 三种模式，可独立运营不依赖官网。",
        bg: "rgba(37, 99, 235, 0.1)"
      }
    ];
    const techStack = [
      { name: "FastAPI", icon: "⚡", desc: "Python 异步 API 框架" },
      { name: "Vue 3 + Vite", icon: "💚", desc: "现代前端框架" },
      { name: "Tailwind", icon: "🎨", desc: "原子化样式" },
      { name: "PostgreSQL 16", icon: "🗄️", desc: "关系型数据库" },
      { name: "Redis 7", icon: "🔴", desc: "缓存与消息" },
      { name: "OpenAI 兼容", icon: "🧠", desc: "任意模型服务可接" },
      { name: "MCP", icon: "🔌", desc: "Agent 内容协议" },
      { name: "Docker", icon: "🐳", desc: "容器化部署" }
    ];
    return (_ctx, _push, _parent, _attrs) => {
      const _component_router_link = resolveComponent("router-link");
      _push(`<div${ssrRenderAttrs(mergeProps({ class: "advantages-page" }, _attrs))} data-v-fdd231a8><section class="page-hero" data-v-fdd231a8><div class="container" data-v-fdd231a8><div class="page-hero-content" data-v-fdd231a8><span class="hero-tag" data-v-fdd231a8>技术优势</span><h1 data-v-fdd231a8>为什么选择辰科Cenkor Admin</h1><p data-v-fdd231a8>现代技术栈 + 应用中心生态 + AI 原生内容层，企业级平台与内容引擎双主线</p></div></div></section><section class="section" data-v-fdd231a8><div class="container" data-v-fdd231a8><div class="advantages-grid" data-v-fdd231a8><!--[-->`);
      ssrRenderList(advantages, (adv, index) => {
        _push(ssrRenderComponent(ScrollReveal, {
          key: adv.title,
          delay: index * 100
        }, {
          default: withCtx((_, _push2, _parent2, _scopeId) => {
            if (_push2) {
              _push2(`<div class="adv-card" data-v-fdd231a8${_scopeId}><div class="adv-icon" style="${ssrRenderStyle({ background: adv.bg })}" data-v-fdd231a8${_scopeId}>${ssrInterpolate(adv.icon)}</div><h3 data-v-fdd231a8${_scopeId}>${ssrInterpolate(adv.title)}</h3><p data-v-fdd231a8${_scopeId}>${ssrInterpolate(adv.description)}</p></div>`);
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
      _push(`<!--]--></div></div></section><section class="section section-alt" data-v-fdd231a8><div class="container" data-v-fdd231a8>`);
      _push(ssrRenderComponent(SectionTitle, {
        tag: "技术栈",
        title: "现代技术栈",
        description: "FastAPI + Vue3 + PostgreSQL，异步高性能，容器化交付",
        center: true
      }, null, _parent));
      _push(`<div class="stack-grid" data-v-fdd231a8><!--[-->`);
      ssrRenderList(techStack, (tech) => {
        _push(`<div class="stack-item" data-v-fdd231a8><div class="stack-icon" data-v-fdd231a8>${ssrInterpolate(tech.icon)}</div><div data-v-fdd231a8><strong data-v-fdd231a8>${ssrInterpolate(tech.name)}</strong><span data-v-fdd231a8>${ssrInterpolate(tech.desc)}</span></div></div>`);
      });
      _push(`<!--]--></div></div></section><section class="section" data-v-fdd231a8><div class="container" data-v-fdd231a8>`);
      _push(ssrRenderComponent(SectionTitle, {
        tag: "对比优势",
        title: "Cenkor Admin 的核心竞争力",
        description: "应用中心生态 + AI 原生内容层 + 三协议开放，平台化交付",
        center: true
      }, null, _parent));
      _push(`<div class="compare-grid" data-v-fdd231a8><div class="compare-card vs" data-v-fdd231a8><h3 data-v-fdd231a8>传统后台框架</h3><ul data-v-fdd231a8><li class="no" data-v-fdd231a8>业务功能需逐套开发</li><li class="no" data-v-fdd231a8>内容字段改代码才能扩展</li><li class="no" data-v-fdd231a8>应用难以按需安装</li><li class="no" data-v-fdd231a8>内容只能人写人读，AI 接不进来</li><li class="no" data-v-fdd231a8>只给前端用，Agent 无接口</li><li class="no" data-v-fdd231a8>升级靠手工拉代码、跑迁移</li></ul></div><div class="compare-card win" data-v-fdd231a8><div class="win-badge" data-v-fdd231a8>推荐</div><h3 data-v-fdd231a8>辰科Cenkor Admin</h3><ul data-v-fdd231a8><li class="yes" data-v-fdd231a8>应用中心按需安装，即插即用</li><li class="yes" data-v-fdd231a8>动态建模，后台即可扩字段（21+ 类型）</li><li class="yes" data-v-fdd231a8>AI CMS：说一句话建模型、起草、翻译</li><li class="yes" data-v-fdd231a8>REST / GraphQL / MCP 三协议出口</li><li class="yes" data-v-fdd231a8>在线升级：版本提示 + 应用 OTA 免重启</li><li class="yes" data-v-fdd231a8>Docker / 宝塔 / 裸机三种部署</li></ul></div></div></div></section><section class="cta-section" data-v-fdd231a8><div class="container" data-v-fdd231a8><div class="cta-content" data-v-fdd231a8><h2 data-v-fdd231a8>把时间花在业务上，而不是重复造后台</h2><p data-v-fdd231a8>Cenkor Admin 让后台平台一次搭建，处处复用</p><div class="cta-actions" data-v-fdd231a8>`);
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
const Advantages = /* @__PURE__ */ _export_sfc(_sfc_main, [["__scopeId", "data-v-fdd231a8"]]);
export {
  Advantages as default
};
