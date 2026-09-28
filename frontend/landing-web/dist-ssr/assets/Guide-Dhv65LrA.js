import { defineComponent, ref, resolveComponent, mergeProps, unref, withCtx, createTextVNode, useSSRContext } from "vue";
import { ssrRenderAttrs, ssrRenderList, ssrRenderClass, ssrInterpolate, ssrRenderStyle, ssrRenderAttr, ssrRenderComponent } from "vue/server-renderer";
import { S as SITE_URLS, _ as _export_sfc } from "../entry-server.js";
import "vue-router";
import "@unhead/vue";
import "pinia";
const _sfc_main = /* @__PURE__ */ defineComponent({
  __name: "Guide",
  __ssrInlineRender: true,
  setup(__props) {
    const urls = SITE_URLS;
    const activeSection = ref(0);
    const sections = [
      {
        icon: "🔑",
        title: "系统登录",
        paragraphs: [
          "部署完成后，使用管理后台（admin-web）地址访问，用安装时设置的管理员账号登录。",
          "系统采用 JWT 双用户体系：后台（auth_users）管理员与前台（portal_users）终端用户完全隔离。"
        ],
        tip: "生产环境务必修改默认管理员密码，并为不同运营人员分配独立账号与角色权限。"
      },
      {
        icon: "🏪",
        title: "应用中心安装",
        paragraphs: [
          "进入后台「应用中心」，可查看所有已扫描的应用及其安装状态（已安装/未安装/待升级）。",
          "点击安装，应用会自动注册权限、菜单、内容类型与字段定义，安装后即可使用。"
        ],
        tip: "应用通过 manifest 声明业务数据，安装时自动注册，卸载时自动清理，即插即用。"
      },
      {
        icon: "📝",
        title: "CMS 内容管理",
        paragraphs: [
          "使用通用内容引擎，后台即可创建内容类型、动态增删字段（支持 21+ 字段类型）。",
          "配置多级分类与标签，维护内容条目，前台通过公开只读 API 消费。"
        ],
        tip: "CMS 提供 /api/v1/public/* 公开接口，任意前端（包括独立官网）都可直接调用。"
      },
      {
        icon: "🔐",
        title: "RBAC 权限管理",
        paragraphs: [
          "配置角色、权限规则、数据权限，控制运营人员可访问的功能范围。",
          "应用安装时可自动注册权限点，并可对角色进行权限委派（permissions_grants）。"
        ],
        tip: "先定义角色与权限规则，再为用户分配角色，保证权限体系清晰可控。"
      },
      {
        icon: "👤",
        title: "用户中心",
        paragraphs: [
          "portal-web 提供 C 端用户注册、登录、资料管理能力，与后台用户体系完全隔离。",
          "终端用户通过用户中心管理自己的账号与订阅。"
        ],
        tip: "前后台用户隔离设计，避免安全边界混淆，适合平台化运营。"
      },
      {
        icon: "🛡️",
        title: "审计与安全",
        paragraphs: [
          "后台关键操作完整记录审计日志，平台运营可追溯、可审计。",
          "结合 JWT 双体系鉴权与 RBAC 权限控制，保障平台数据安全。"
        ],
        tip: "建议定期备份 PostgreSQL 数据库，并配置异地备份保障数据安全。"
      }
    ];
    return (_ctx, _push, _parent, _attrs) => {
      const _component_router_link = resolveComponent("router-link");
      _push(`<div${ssrRenderAttrs(mergeProps({ class: "guide-page" }, _attrs))} data-v-07d69f63><section class="page-hero" data-v-07d69f63><div class="container" data-v-07d69f63><div class="page-hero-content" data-v-07d69f63><span class="hero-tag" data-v-07d69f63>使用指南</span><h1 data-v-07d69f63>Cenkor Admin 使用入门</h1><p data-v-07d69f63>从部署上线到应用安装，快速了解平台全貌</p></div></div></section><section class="section" data-v-07d69f63><div class="container" data-v-07d69f63><div class="guide-content" data-v-07d69f63><div class="guide-nav" data-v-07d69f63><!--[-->`);
      ssrRenderList(sections, (sec, i) => {
        _push(`<div class="${ssrRenderClass([{ active: activeSection.value === i }, "guide-nav-item"])}" data-v-07d69f63><span class="nav-icon" data-v-07d69f63>${ssrInterpolate(sec.icon)}</span><span data-v-07d69f63>${ssrInterpolate(sec.title)}</span></div>`);
      });
      _push(`<!--]--></div><div class="guide-body" data-v-07d69f63><!--[-->`);
      ssrRenderList(sections, (sec, i) => {
        _push(`<div class="guide-section" style="${ssrRenderStyle(activeSection.value === i ? null : { display: "none" })}" data-v-07d69f63><h2 data-v-07d69f63>${ssrInterpolate(sec.title)}</h2><div class="guide-text" data-v-07d69f63><!--[-->`);
        ssrRenderList(sec.paragraphs, (p, j) => {
          _push(`<p data-v-07d69f63>${ssrInterpolate(p)}</p>`);
        });
        _push(`<!--]--></div>`);
        if (sec.tip) {
          _push(`<div class="guide-tip" data-v-07d69f63><span class="tip-icon" data-v-07d69f63>💡</span><p data-v-07d69f63>${ssrInterpolate(sec.tip)}</p></div>`);
        } else {
          _push(`<!---->`);
        }
        _push(`</div>`);
      });
      _push(`<!--]--></div></div></div></section><section class="cta-section" data-v-07d69f63><div class="container" data-v-07d69f63><div class="cta-content" data-v-07d69f63><h2 data-v-07d69f63>需要更详细的文档？</h2><p data-v-07d69f63>完整使用文档与技术支持随时为您提供</p><div class="cta-actions" data-v-07d69f63><a${ssrRenderAttr("href", unref(urls).github)} target="_blank" rel="noopener" class="btn btn-primary btn-large" data-v-07d69f63>GitHub 仓库</a>`);
      _push(ssrRenderComponent(_component_router_link, {
        to: "/deploy",
        class: "btn btn-secondary btn-large"
      }, {
        default: withCtx((_, _push2, _parent2, _scopeId) => {
          if (_push2) {
            _push2(`查看部署文档`);
          } else {
            return [
              createTextVNode("查看部署文档")
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
  (ssrContext.modules || (ssrContext.modules = /* @__PURE__ */ new Set())).add("src/views/docs/Guide.vue");
  return _sfc_setup ? _sfc_setup(props, ctx) : void 0;
};
const Guide = /* @__PURE__ */ _export_sfc(_sfc_main, [["__scopeId", "data-v-07d69f63"]]);
export {
  Guide as default
};
