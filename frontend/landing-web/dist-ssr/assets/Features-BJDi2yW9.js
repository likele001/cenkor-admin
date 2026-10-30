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
        icon: "🤖",
        title: "AI CMS 内容引擎",
        description: "用中文描述业务直接生成内容类型与字段定义，草案确认后才落库；AI 起草强制人审，多语言一条命令批量翻译，检索接入 rerank 精排并保留出处。",
        points: ["对话式建模（草案 → 落库）", "AI 起草与批量翻译", "语义检索 + 引用可回溯"]
      },
      {
        icon: "🏪",
        title: "应用中心",
        description: "应用通过 manifest 声明内容类型、字段、分类、权限与菜单，安装时自动注册到系统，卸载时自动清理，即插即用。",
        points: ["应用安装/卸载/升级", "权限与菜单自动注册", "授权码 OTA 免重启升级"]
      },
      {
        icon: "🔐",
        title: "RBAC 权限",
        description: "角色、权限规则、数据权限三级控制。后台（auth_users）与前台（portal_users）双用户体系完全隔离，CMS 与 AI 能力还做了细分权限。",
        points: ["角色与权限规则", "数据权限范围控制", "审核独立于编辑"]
      },
      {
        icon: "📝",
        title: "动态建模与多站点",
        description: "V2 通用 cms_entries + 动态字段定义，后台 UI 即可增删改字段，支持 21+ 字段类型、多级分类树、标签系统与多站点站群。",
        points: ["动态字段增删改", "21+ 字段类型", "多站点会话级隔离"]
      },
      {
        icon: "🔀",
        title: "工作流审批",
        description: "可视化流程编排，我的待办 / 我发起的 / 我的已办 / 抄送我的 / 单据管理齐全；AI 工作流按拓扑序执行，画环当场拦住。",
        points: ["可视化流程编排", "待办已办抄送", "AI 工作流引擎"]
      },
      {
        icon: "📡",
        title: "发布与效果统计",
        description: "官网、Webhook、微信公众号草稿箱、导出四个渠道分发；内容埋点一行脚本接入，停留时长与跳出判定按会话归并后统计。",
        points: ["多渠道分发", "零改造内容埋点", "效果分析看板"]
      },
      {
        icon: "🔌",
        title: "开放接口",
        description: "REST 内容引擎、GraphQL 只读查询、MCP Server 三种协议并存，共享同一套权限与检索底座，不做三份数据。",
        points: ["REST 内容引擎", "GraphQL（strawberry）", "MCP HTTP / stdio"]
      },
      {
        icon: "🚀",
        title: "在线升级",
        description: "核心平台主动查询最新版本并在工作台提示，upgrade.sh 完成备份→覆盖→迁移→重启→健康检查；应用侧走授权码 OTA。",
        points: ["版本检查与提示", "升级脚本自动迁移", "应用免重启 OTA"]
      },
      {
        icon: "🏠",
        title: "私有化部署",
        description: "Docker Compose、宝塔静态 dist、裸机 systemd 三种部署模式，可独立运营，不依赖任何官网。",
        points: ["Docker Compose", "宝塔静态部署", "裸机 systemd"]
      }
    ];
    const aiCapabilities = [
      { icon: "🏭", name: "批量生产", desc: "一次派一批选题，逐篇落草稿，状态全落库" },
      { icon: "🩺", name: "内容健康度体检", desc: "12 项检查三维度，腐烂内容列清单" },
      { icon: "⚖️", name: "抽样质检与 A/B", desc: "结构化打分，模型与提示词效果可比" },
      { icon: "🎯", name: "选题 Gap 分析", desc: "按决策阶段指出内容缺口，防编造" },
      { icon: "💡", name: "问答式站内搜索", desc: "混合检索带引用作答，查不到就说查不到" },
      { icon: "🖼️", name: "AI 配图", desc: "正文提炼提示词，落媒体库并填好 alt" },
      { icon: "🎬", name: "AI 视频", desc: "镜头提示 → 后台轮询 → 转存云存储" },
      { icon: "🔗", name: "内链建议", desc: "只建议不自动插链，锚文本自然可撤" },
      { icon: "🧩", name: "模型变更影响分析", desc: "改字段前先算清影响面与兼容性" },
      { icon: "📡", name: "多渠道再分发", desc: "长文按渠道重塑体裁，不是复制粘贴" }
    ];
    const apps = [
      { icon: "🤖", name: "AI CMS", desc: "AI 原生内容引擎" },
      { icon: "📇", name: "CRM 销售", desc: "线索到回款" },
      { icon: "🏭", name: "ERP 管理", desc: "进销存与往来" },
      { icon: "⚙️", name: "MES 制造", desc: "排产与报工" },
      { icon: "🔀", name: "工作流审批", desc: "可视化流程" },
      { icon: "🎫", name: "工单系统", desc: "工单流转处理" },
      { icon: "☁️", name: "云存储", desc: "多驱动对象存储" },
      { icon: "📢", name: "公告管理", desc: "公告与通知" },
      { icon: "🔔", name: "通知中心", desc: "多渠道推送" },
      { icon: "🔗", name: "链接收藏", desc: "常用链接管理" },
      { icon: "📝", name: "Quick Notes", desc: "快速记事" },
      { icon: "✅", name: "My Todo", desc: "任务清单" }
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
      _push(`<div${ssrRenderAttrs(mergeProps({ class: "features-page" }, _attrs))} data-v-005e9edb><section class="page-hero" data-v-005e9edb><div class="container" data-v-005e9edb><div class="page-hero-content" data-v-005e9edb><span class="hero-tag" data-v-005e9edb>核心功能</span><h1 data-v-005e9edb>平台全功能一览</h1><p data-v-005e9edb>AI CMS + 应用中心 + RBAC 权限 + 工作流审批 + 开放接口，一站配齐</p></div></div></section><section class="section" data-v-005e9edb><div class="container" data-v-005e9edb><div class="feature-list" data-v-005e9edb><!--[-->`);
      ssrRenderList(featureItems, (item, index) => {
        _push(ssrRenderComponent(ScrollReveal, {
          key: item.title,
          delay: index * 80
        }, {
          default: withCtx((_, _push2, _parent2, _scopeId) => {
            if (_push2) {
              _push2(`<div class="feature-row" data-v-005e9edb${_scopeId}><div class="feature-icon" data-v-005e9edb${_scopeId}>${ssrInterpolate(item.icon)}</div><div class="feature-content" data-v-005e9edb${_scopeId}><h2 data-v-005e9edb${_scopeId}>${ssrInterpolate(item.title)}</h2><p data-v-005e9edb${_scopeId}>${ssrInterpolate(item.description)}</p><ul data-v-005e9edb${_scopeId}><!--[-->`);
              ssrRenderList(item.points, (point) => {
                _push2(`<li data-v-005e9edb${_scopeId}>${ssrInterpolate(point)}</li>`);
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
      _push(`<!--]--></div></div></section><section class="section section-alt" data-v-005e9edb><div class="container" data-v-005e9edb>`);
      _push(ssrRenderComponent(SectionTitle, {
        tag: "AI CMS 生产线",
        title: "十道 AI 工序，每道都能单独用",
        description: "不是一个大而全的「AI 按钮」，而是十个独立端点：用到哪个开哪个",
        center: true
      }, null, _parent));
      _push(`<div class="ai-line" data-v-005e9edb><!--[-->`);
      ssrRenderList(aiCapabilities, (a) => {
        _push(`<div class="ai-line-item" data-v-005e9edb><span class="ai-line-icon" data-v-005e9edb>${ssrInterpolate(a.icon)}</span><div data-v-005e9edb><strong data-v-005e9edb>${ssrInterpolate(a.name)}</strong><span data-v-005e9edb>${ssrInterpolate(a.desc)}</span></div></div>`);
      });
      _push(`<!--]--></div><div class="ai-line-more" data-v-005e9edb>`);
      _push(ssrRenderComponent(_component_router_link, {
        to: "/ai-cms",
        class: "btn btn-primary"
      }, {
        default: withCtx((_, _push2, _parent2, _scopeId) => {
          if (_push2) {
            _push2(`查看 AI CMS 完整能力`);
          } else {
            return [
              createTextVNode("查看 AI CMS 完整能力")
            ];
          }
        }),
        _: 1
      }, _parent));
      _push(`</div></div></section><section class="section" data-v-005e9edb><div class="container" data-v-005e9edb>`);
      _push(ssrRenderComponent(SectionTitle, {
        tag: "应用中心",
        title: "应用按需安装",
        description: "每个应用声明内容类型、字段、权限、菜单，安装时自动注册，支持授权码 OTA 升级",
        center: true
      }, null, _parent));
      _push(`<div class="app-grid" data-v-005e9edb><!--[-->`);
      ssrRenderList(apps, (app, index) => {
        _push(ssrRenderComponent(ScrollReveal, {
          key: app.name,
          delay: index * 50
        }, {
          default: withCtx((_, _push2, _parent2, _scopeId) => {
            if (_push2) {
              _push2(`<div class="app-card" data-v-005e9edb${_scopeId}><div class="app-icon" data-v-005e9edb${_scopeId}>${ssrInterpolate(app.icon)}</div><h4 data-v-005e9edb${_scopeId}>${ssrInterpolate(app.name)}</h4><p data-v-005e9edb${_scopeId}>${ssrInterpolate(app.desc)}</p></div>`);
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
      _push(`<!--]--></div></div></section><section class="section section-alt" data-v-005e9edb><div class="container" data-v-005e9edb>`);
      _push(ssrRenderComponent(SectionTitle, {
        tag: "内容引擎",
        title: "21+ 字段类型的通用建模",
        description: "后台即可动态增删字段，无需改代码；字段改名改类型前先算影响面",
        center: true
      }, null, _parent));
      _push(`<div class="field-grid" data-v-005e9edb><!--[-->`);
      ssrRenderList(fields, (field) => {
        _push(`<div class="field-item" data-v-005e9edb><span class="field-check" data-v-005e9edb>✓</span> ${ssrInterpolate(field)}</div>`);
      });
      _push(`<!--]--></div></div></section><section class="cta-section" data-v-005e9edb><div class="container" data-v-005e9edb><div class="cta-content" data-v-005e9edb><h2 data-v-005e9edb>需要一个开箱即用的后台管理平台？</h2><p data-v-005e9edb>Cenkor Admin 让你跳过从零搭建，直接聚焦业务</p><div class="cta-actions" data-v-005e9edb>`);
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
const Features = /* @__PURE__ */ _export_sfc(_sfc_main, [["__scopeId", "data-v-005e9edb"]]);
export {
  Features as default
};
