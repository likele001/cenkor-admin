import { defineComponent, resolveComponent, mergeProps, withCtx, createVNode, toDisplayString, openBlock, createBlock, Fragment, renderList, createTextVNode, useSSRContext } from "vue";
import { ssrRenderAttrs, ssrRenderList, ssrRenderComponent, ssrInterpolate } from "vue/server-renderer";
import { S as SectionTitle } from "./SectionTitle-NKY75B6X.js";
import { S as ScrollReveal } from "./ScrollReveal-BjFAJfMT.js";
import { _ as _export_sfc } from "../entry-server.js";
import "vue-router";
import "@unhead/vue";
import "pinia";
const _sfc_main = /* @__PURE__ */ defineComponent({
  __name: "Features",
  __ssrInlineRender: true,
  setup(__props) {
    const featureItems = [
      {
        icon: "🏪",
        title: "应用中心",
        description: "应用通过 manifest 声明内容类型、字段、分类、权限与菜单，安装时自动注册到系统，卸载时自动清理，即插即用。",
        points: ["应用安装/卸载/升级", "权限与菜单自动注册", "内容字段自动生成"]
      },
      {
        icon: "🔐",
        title: "RBAC 权限",
        description: "角色、权限规则、数据权限三级控制。后台（auth_users）与前台（portal_users）双用户体系完全隔离。",
        points: ["角色与权限规则", "数据权限范围控制", "前后台双用户隔离"]
      },
      {
        icon: "📝",
        title: "通用内容引擎",
        description: "V2 通用 cms_entries + 动态字段定义，后台 UI 即可增删改字段，支持 21+ 字段类型、3+ 级分类树、标签系统。",
        points: ["动态字段增删改", "21+ 字段类型", "多级分类与标签"]
      },
      {
        icon: "👤",
        title: "用户中心",
        description: "portal-web 独立 SPA，C 端用户注册、登录、资料管理，与后台用户体系完全隔离。",
        points: ["C 端注册登录", "个人资料管理", "独立用户体系"]
      },
      {
        icon: "🛡️",
        title: "审计日志",
        description: "后台关键操作完整留痕，平台运营可追溯、可审计，安全合规。",
        points: ["操作日志留痕", "可追溯审计", "安全合规"]
      },
      {
        icon: "🏠",
        title: "私有化部署",
        description: "Docker Compose、宝塔静态 dist、裸机 systemd 三种部署模式，可独立运营，不依赖任何官网。",
        points: ["Docker Compose", "宝塔静态部署", "裸机 systemd"]
      }
    ];
    const apps = [
      { icon: "📢", name: "公告管理", desc: "公告发布与通知" },
      { icon: "🎫", name: "工单系统", desc: "问题工单流转" },
      { icon: "☁️", name: "云存储", desc: "对象存储管理" },
      { icon: "🔗", name: "链接收藏", desc: "常用链接管理" },
      { icon: "📝", name: "Quick Notes", desc: "快速记事" },
      { icon: "✅", name: "My Todo", desc: "任务清单" },
      { icon: "🔔", name: "通知", desc: "系统通知" },
      { icon: "📰", name: "CMS", desc: "官网内容管理" }
    ];
    const fields = [
      "文本",
      "多行文本",
      "富文本",
      "数字",
      "日期",
      "时间",
      "日期时间",
      "单选",
      "多选",
      "下拉选择",
      "多级下拉",
      "开关",
      "颜色",
      "图片",
      "图片多选",
      "文件",
      "视频",
      "URL",
      "Email",
      "电话",
      "JSON"
    ];
    return (_ctx, _push, _parent, _attrs) => {
      const _component_router_link = resolveComponent("router-link");
      _push(`<div${ssrRenderAttrs(mergeProps({ class: "features-page" }, _attrs))} data-v-8e140b67><section class="page-hero" data-v-8e140b67><div class="container" data-v-8e140b67><div class="page-hero-content" data-v-8e140b67><span class="hero-tag" data-v-8e140b67>核心功能</span><h1 data-v-8e140b67>后台管理平台全功能一览</h1><p data-v-8e140b67>应用中心、RBAC 权限、通用内容引擎、用户中心、审计日志，一站配齐</p></div></div></section><section class="section" data-v-8e140b67><div class="container" data-v-8e140b67><div class="feature-list" data-v-8e140b67><!--[-->`);
      ssrRenderList(featureItems, (item, index) => {
        _push(ssrRenderComponent(ScrollReveal, {
          key: item.title,
          delay: index * 80
        }, {
          default: withCtx((_, _push2, _parent2, _scopeId) => {
            if (_push2) {
              _push2(`<div class="feature-row" data-v-8e140b67${_scopeId}><div class="feature-icon" data-v-8e140b67${_scopeId}>${ssrInterpolate(item.icon)}</div><div class="feature-content" data-v-8e140b67${_scopeId}><h2 data-v-8e140b67${_scopeId}>${ssrInterpolate(item.title)}</h2><p data-v-8e140b67${_scopeId}>${ssrInterpolate(item.description)}</p><ul data-v-8e140b67${_scopeId}><!--[-->`);
              ssrRenderList(item.points, (point) => {
                _push2(`<li data-v-8e140b67${_scopeId}>${ssrInterpolate(point)}</li>`);
              });
              _push2(`<!--]--></ul></div></div>`);
            } else {
              return [
                createVNode("div", { class: "feature-row" }, [
                  createVNode("div", { class: "feature-icon" }, toDisplayString(item.icon), 1),
                  createVNode("div", { class: "feature-content" }, [
                    createVNode("h2", null, toDisplayString(item.title), 1),
                    createVNode("p", null, toDisplayString(item.description), 1),
                    createVNode("ul", null, [
                      (openBlock(true), createBlock(Fragment, null, renderList(item.points, (point) => {
                        return openBlock(), createBlock("li", { key: point }, toDisplayString(point), 1);
                      }), 128))
                    ])
                  ])
                ])
              ];
            }
          }),
          _: 2
        }, _parent));
      });
      _push(`<!--]--></div></div></section><section class="section section-alt" data-v-8e140b67><div class="container" data-v-8e140b67>`);
      _push(ssrRenderComponent(SectionTitle, {
        tag: "应用中心",
        title: "应用按需安装",
        description: "每个应用声明内容类型、字段、权限、菜单，安装时自动注册",
        center: true
      }, null, _parent));
      _push(`<div class="app-grid" data-v-8e140b67><!--[-->`);
      ssrRenderList(apps, (app, index) => {
        _push(ssrRenderComponent(ScrollReveal, {
          key: app.name,
          delay: index * 50
        }, {
          default: withCtx((_, _push2, _parent2, _scopeId) => {
            if (_push2) {
              _push2(`<div class="app-card" data-v-8e140b67${_scopeId}><div class="app-icon" data-v-8e140b67${_scopeId}>${ssrInterpolate(app.icon)}</div><h4 data-v-8e140b67${_scopeId}>${ssrInterpolate(app.name)}</h4><p data-v-8e140b67${_scopeId}>${ssrInterpolate(app.desc)}</p></div>`);
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
      _push(`<!--]--></div></div></section><section class="section" data-v-8e140b67><div class="container" data-v-8e140b67>`);
      _push(ssrRenderComponent(SectionTitle, {
        tag: "内容引擎",
        title: "21+ 字段类型的通用 CMS",
        description: "后台即可动态增删字段，无需改代码",
        center: true
      }, null, _parent));
      _push(`<div class="field-grid" data-v-8e140b67><!--[-->`);
      ssrRenderList(fields, (field) => {
        _push(`<div class="field-item" data-v-8e140b67><span class="field-check" data-v-8e140b67>✓</span> ${ssrInterpolate(field)}</div>`);
      });
      _push(`<!--]--></div></div></section><section class="cta-section" data-v-8e140b67><div class="container" data-v-8e140b67><div class="cta-content" data-v-8e140b67><h2 data-v-8e140b67>需要一个开箱即用的后台管理平台？</h2><p data-v-8e140b67>Cenkor Admin 让你跳过从零搭建，直接聚焦业务</p><div class="cta-actions" data-v-8e140b67>`);
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
        to: "/advantages",
        class: "btn btn-secondary btn-large"
      }, {
        default: withCtx((_, _push2, _parent2, _scopeId) => {
          if (_push2) {
            _push2(`了解技术优势`);
          } else {
            return [
              createTextVNode("了解技术优势")
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
  (ssrContext.modules || (ssrContext.modules = /* @__PURE__ */ new Set())).add("src/views/Features.vue");
  return _sfc_setup ? _sfc_setup(props, ctx) : void 0;
};
const Features = /* @__PURE__ */ _export_sfc(_sfc_main, [["__scopeId", "data-v-8e140b67"]]);
export {
  Features as default
};
