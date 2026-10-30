import { defineComponent, ref, onMounted, resolveComponent, mergeProps, unref, withCtx, createTextVNode, useSSRContext } from "vue";
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
        icon: "🤖",
        title: "AI CMS 内容管理",
        paragraphs: [
          "进入后台「内容管理」，用 AI 建模向导描述业务，生成内容类型与字段定义草案，确认后才真正落库（支持 21+ 字段类型）。",
          "配置多级分类与标签，维护内容条目；AI 起草的稿件强制为 draft，必须人工审核通过才能发布。",
          "内容完成审核后，可在发布渠道推到官网、Webhook、微信公众号草稿箱，或导出到第三方平台。"
        ],
        tip: "内容同时以 REST / GraphQL / MCP 三种协议对外输出，前端与 Agent 各取所需，数据只有一份。"
      },
      {
        icon: "🧠",
        title: "AI 模型接入",
        paragraphs: [
          "进入「AI 设置」，新增服务商（OpenAI 兼容协议，填 base_url 与密钥），保存后可用连通性测试发一次最小请求验证。",
          "把 chat / embedding / vision / image / rerank / asr / tts 七类能力分别绑定到服务商与模型，chat 与 embedding 可来自不同服务商。",
          "密钥出接口只返回掩码，编辑时原样回传即等于不修改；用量按输入 / 输出 / 缓存分段统计，配合价格表算真实成本。"
        ],
        tip: "不接模型也能用：AI 端点会返回明确的 503 提示，而建模、审核、REST / GraphQL / MCP 只读工具完全不受影响。"
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
    onMounted(() => {
      const items = document.querySelectorAll(".guide-nav-item");
      items.forEach((item, i) => {
        item.addEventListener("click", () => {
          activeSection.value = i;
        });
      });
    });
    return (_ctx, _push, _parent, _attrs) => {
      const _component_router_link = resolveComponent("router-link");
      _push(`<div${ssrRenderAttrs(mergeProps({ class: "guide-page" }, _attrs))} data-v-d10864c5><section class="page-hero" data-v-d10864c5><div class="container" data-v-d10864c5><div class="page-hero-content" data-v-d10864c5><span class="hero-tag" data-v-d10864c5>使用指南</span><h1 data-v-d10864c5>Cenkor Admin 使用入门</h1><p data-v-d10864c5>从部署上线到应用安装，快速了解平台全貌</p></div></div></section><section class="section" data-v-d10864c5><div class="container" data-v-d10864c5><div class="guide-content" data-v-d10864c5><div class="guide-nav" data-v-d10864c5><!--[-->`);
      ssrRenderList(sections, (sec, i) => {
        _push(`<button type="button" class="${ssrRenderClass([{ active: activeSection.value === i }, "guide-nav-item"])}" data-v-d10864c5><span class="nav-icon" data-v-d10864c5>${ssrInterpolate(sec.icon)}</span><span data-v-d10864c5>${ssrInterpolate(sec.title)}</span></button>`);
      });
      _push(`<!--]--></div><div class="guide-body" data-v-d10864c5><!--[-->`);
      ssrRenderList(sections, (sec, i) => {
        _push(`<div class="guide-section" style="${ssrRenderStyle(activeSection.value === i ? null : { display: "none" })}" data-v-d10864c5><h2 data-v-d10864c5>${ssrInterpolate(sec.title)}</h2><div class="guide-text" data-v-d10864c5><!--[-->`);
        ssrRenderList(sec.paragraphs, (p, j) => {
          _push(`<p data-v-d10864c5>${ssrInterpolate(p)}</p>`);
        });
        _push(`<!--]--></div>`);
        if (sec.tip) {
          _push(`<div class="guide-tip" data-v-d10864c5><span class="tip-icon" data-v-d10864c5>💡</span><p data-v-d10864c5>${ssrInterpolate(sec.tip)}</p></div>`);
        } else {
          _push(`<!---->`);
        }
        _push(`</div>`);
      });
      _push(`<!--]--></div></div></div></section><section class="cta-section" data-v-d10864c5><div class="container" data-v-d10864c5><div class="cta-content" data-v-d10864c5><h2 data-v-d10864c5>需要更详细的文档？</h2><p data-v-d10864c5>完整使用文档与技术支持随时为您提供</p><div class="cta-actions" data-v-d10864c5><a${ssrRenderAttr("href", unref(urls).github)} target="_blank" rel="noopener" class="btn btn-primary btn-large" data-v-d10864c5>GitHub 仓库</a>`);
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
const Guide = /* @__PURE__ */ _export_sfc(_sfc_main, [["__scopeId", "data-v-d10864c5"]]);
export {
  Guide as default
};
