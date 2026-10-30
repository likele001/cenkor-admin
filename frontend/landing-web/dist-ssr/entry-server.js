import { defineComponent, ref, onMounted, onUnmounted, resolveComponent, withCtx, createVNode, openBlock, createBlock, unref, useSSRContext, mergeProps, createTextVNode, createSSRApp } from "vue";
import { ssrRenderClass, ssrRenderComponent, ssrRenderAttr, ssrRenderAttrs, ssrInterpolate, renderToString } from "vue/server-renderer";
import { useRouter, useRoute, createRouter, createMemoryHistory } from "vue-router";
import { useHead, createHead } from "@unhead/vue";
import { createPinia } from "pinia";
const SITE_URLS = {
  api: "https://admin.cenkor.cn",
  contact: "https://www.cenkor.cn/contact.html",
  github: "https://github.com/likele001/cenkor-admin"
};
const _sfc_main$2 = /* @__PURE__ */ defineComponent({
  __name: "Navbar",
  __ssrInlineRender: true,
  setup(__props) {
    const urls = SITE_URLS;
    useRouter();
    const isScrolled = ref(false);
    const mobileMenuOpen = ref(false);
    const handleScroll = () => {
      isScrolled.value = window.scrollY > 20;
    };
    const unlockScroll = () => {
      document.documentElement.style.overflow = "";
      document.body.style.overflow = "";
    };
    onMounted(() => {
      window.addEventListener("scroll", handleScroll);
    });
    onUnmounted(() => {
      window.removeEventListener("scroll", handleScroll);
      unlockScroll();
    });
    return (_ctx, _push, _parent, _attrs) => {
      const _component_router_link = resolveComponent("router-link");
      _push(`<!--[--><nav class="${ssrRenderClass([{ scrolled: isScrolled.value }, "navbar"])}" data-v-f51553a6><div class="container" data-v-f51553a6><div class="navbar-content" data-v-f51553a6>`);
      _push(ssrRenderComponent(_component_router_link, {
        to: "/",
        class: "logo"
      }, {
        default: withCtx((_, _push2, _parent2, _scopeId) => {
          if (_push2) {
            _push2(`<div class="logo-icon" data-v-f51553a6${_scopeId}><svg viewBox="0 0 32 32" fill="none" data-v-f51553a6${_scopeId}><rect width="32" height="32" rx="6" fill="#10b981" data-v-f51553a6${_scopeId}></rect><rect x="7" y="7" width="5" height="5" rx="1.5" fill="white" data-v-f51553a6${_scopeId}></rect><rect x="13.5" y="7" width="5" height="5" rx="1.5" fill="white" opacity="0.55" data-v-f51553a6${_scopeId}></rect><rect x="20" y="7" width="5" height="5" rx="1.5" fill="white" opacity="0.8" data-v-f51553a6${_scopeId}></rect><rect x="7" y="13.5" width="5" height="5" rx="1.5" fill="white" opacity="0.8" data-v-f51553a6${_scopeId}></rect><rect x="13.5" y="13.5" width="5" height="5" rx="1.5" fill="white" data-v-f51553a6${_scopeId}></rect><rect x="20" y="13.5" width="5" height="5" rx="1.5" fill="white" opacity="0.8" data-v-f51553a6${_scopeId}></rect><rect x="7" y="20" width="5" height="5" rx="1.5" fill="white" opacity="0.55" data-v-f51553a6${_scopeId}></rect><rect x="13.5" y="20" width="5" height="5" rx="1.5" fill="white" opacity="0.8" data-v-f51553a6${_scopeId}></rect><rect x="20" y="20" width="5" height="5" rx="1.5" fill="white" data-v-f51553a6${_scopeId}></rect></svg></div><span class="logo-text" data-v-f51553a6${_scopeId}>辰科 Cenkor Admin</span>`);
          } else {
            return [
              createVNode("div", { class: "logo-icon" }, [
                (openBlock(), createBlock("svg", {
                  viewBox: "0 0 32 32",
                  fill: "none"
                }, [
                  createVNode("rect", {
                    width: "32",
                    height: "32",
                    rx: "6",
                    fill: "#10b981"
                  }),
                  createVNode("rect", {
                    x: "7",
                    y: "7",
                    width: "5",
                    height: "5",
                    rx: "1.5",
                    fill: "white"
                  }),
                  createVNode("rect", {
                    x: "13.5",
                    y: "7",
                    width: "5",
                    height: "5",
                    rx: "1.5",
                    fill: "white",
                    opacity: "0.55"
                  }),
                  createVNode("rect", {
                    x: "20",
                    y: "7",
                    width: "5",
                    height: "5",
                    rx: "1.5",
                    fill: "white",
                    opacity: "0.8"
                  }),
                  createVNode("rect", {
                    x: "7",
                    y: "13.5",
                    width: "5",
                    height: "5",
                    rx: "1.5",
                    fill: "white",
                    opacity: "0.8"
                  }),
                  createVNode("rect", {
                    x: "13.5",
                    y: "13.5",
                    width: "5",
                    height: "5",
                    rx: "1.5",
                    fill: "white"
                  }),
                  createVNode("rect", {
                    x: "20",
                    y: "13.5",
                    width: "5",
                    height: "5",
                    rx: "1.5",
                    fill: "white",
                    opacity: "0.8"
                  }),
                  createVNode("rect", {
                    x: "7",
                    y: "20",
                    width: "5",
                    height: "5",
                    rx: "1.5",
                    fill: "white",
                    opacity: "0.55"
                  }),
                  createVNode("rect", {
                    x: "13.5",
                    y: "20",
                    width: "5",
                    height: "5",
                    rx: "1.5",
                    fill: "white",
                    opacity: "0.8"
                  }),
                  createVNode("rect", {
                    x: "20",
                    y: "20",
                    width: "5",
                    height: "5",
                    rx: "1.5",
                    fill: "white"
                  })
                ]))
              ]),
              createVNode("span", { class: "logo-text" }, "辰科 Cenkor Admin")
            ];
          }
        }),
        _: 1
      }, _parent));
      _push(`<div class="${ssrRenderClass([{ active: mobileMenuOpen.value }, "nav-links"])}" data-v-f51553a6><a data-v-f51553a6>首页</a><a class="nav-hot" data-v-f51553a6> AI CMS <span class="hot-dot" data-v-f51553a6></span></a><a data-v-f51553a6>功能</a><a data-v-f51553a6>优势</a><a data-v-f51553a6>私有部署</a><div class="dropdown" data-v-f51553a6><span class="dropdown-trigger" data-v-f51553a6>文档</span><div class="dropdown-menu" data-v-f51553a6><a data-v-f51553a6>使用指南</a><a data-v-f51553a6>部署教程</a></div></div></div><div class="nav-actions" data-v-f51553a6><a${ssrRenderAttr("href", unref(urls).contact)} target="_blank" rel="noopener" class="btn btn-ghost btn-small" data-v-f51553a6>联系我们</a><a${ssrRenderAttr("href", unref(urls).github)} target="_blank" rel="noopener" class="btn btn-primary btn-small" data-v-f51553a6>GitHub</a></div><button class="${ssrRenderClass([{ active: mobileMenuOpen.value }, "mobile-toggle"])}" data-v-f51553a6><span data-v-f51553a6></span><span data-v-f51553a6></span><span data-v-f51553a6></span></button></div></div></nav><div class="${ssrRenderClass([{ active: mobileMenuOpen.value }, "mobile-overlay"])}" data-v-f51553a6></div><!--]-->`);
    };
  }
});
const _export_sfc = (sfc, props) => {
  const target = sfc.__vccOpts || sfc;
  for (const [key, val] of props) {
    target[key] = val;
  }
  return target;
};
const _sfc_setup$2 = _sfc_main$2.setup;
_sfc_main$2.setup = (props, ctx) => {
  const ssrContext = useSSRContext();
  (ssrContext.modules || (ssrContext.modules = /* @__PURE__ */ new Set())).add("src/components/Navbar.vue");
  return _sfc_setup$2 ? _sfc_setup$2(props, ctx) : void 0;
};
const Navbar = /* @__PURE__ */ _export_sfc(_sfc_main$2, [["__scopeId", "data-v-f51553a6"]]);
const contact = ref({
  wechat: "",
  phone: "",
  email: "contact@cenkor.cn",
  bdEmail: "bd@cenkor.cn",
  supportEmail: "support@cenkor.cn"
});
let loaded = false;
const PUBLIC_SITE_API = "/api/v1/public/site";
function useSiteConfig() {
  async function fetchContact() {
    if (loaded) return contact.value;
    loaded = true;
    try {
      const res = await fetch(PUBLIC_SITE_API, { method: "GET" });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const json = await res.json();
      const cfg = (json == null ? void 0 : json.site_config) ?? {};
      contact.value = {
        wechat: cfg["contact.wechat"] ?? "",
        phone: cfg["contact.phone"] ?? "",
        email: cfg["contact.email"] ?? "contact@cenkor.cn",
        bdEmail: cfg["contact.bd_email"] ?? "bd@cenkor.cn",
        supportEmail: cfg["contact.support_email"] ?? "support@cenkor.cn"
      };
    } catch {
      loaded = false;
    }
    return contact.value;
  }
  return { contact, fetchContact };
}
const _sfc_main$1 = /* @__PURE__ */ defineComponent({
  __name: "Footer",
  __ssrInlineRender: true,
  setup(__props) {
    const urls = SITE_URLS;
    const { contact: contact2, fetchContact } = useSiteConfig();
    onMounted(() => {
      fetchContact();
    });
    return (_ctx, _push, _parent, _attrs) => {
      const _component_router_link = resolveComponent("router-link");
      _push(`<footer${ssrRenderAttrs(mergeProps({ class: "footer" }, _attrs))} data-v-10145ec2><div class="container" data-v-10145ec2><div class="footer-content" data-v-10145ec2><div class="footer-brand" data-v-10145ec2><div class="logo" data-v-10145ec2><div class="logo-icon" data-v-10145ec2><svg viewBox="0 0 32 32" fill="none" data-v-10145ec2><rect width="32" height="32" rx="6" fill="#10b981" data-v-10145ec2></rect><rect x="7" y="7" width="5" height="5" rx="1.5" fill="white" data-v-10145ec2></rect><rect x="13.5" y="7" width="5" height="5" rx="1.5" fill="white" opacity="0.55" data-v-10145ec2></rect><rect x="20" y="7" width="5" height="5" rx="1.5" fill="white" opacity="0.8" data-v-10145ec2></rect><rect x="7" y="13.5" width="5" height="5" rx="1.5" fill="white" opacity="0.8" data-v-10145ec2></rect><rect x="13.5" y="13.5" width="5" height="5" rx="1.5" fill="white" data-v-10145ec2></rect><rect x="20" y="13.5" width="5" height="5" rx="1.5" fill="white" opacity="0.8" data-v-10145ec2></rect><rect x="7" y="20" width="5" height="5" rx="1.5" fill="white" opacity="0.55" data-v-10145ec2></rect><rect x="13.5" y="20" width="5" height="5" rx="1.5" fill="white" opacity="0.8" data-v-10145ec2></rect><rect x="20" y="20" width="5" height="5" rx="1.5" fill="white" data-v-10145ec2></rect></svg></div><span class="logo-text" data-v-10145ec2>辰科 Cenkor Admin</span></div><p class="footer-desc" data-v-10145ec2>企业级平台 · 应用中心 + RBAC + 工作流 + AI CMS · FastAPI + Vue3</p></div><div class="footer-links" data-v-10145ec2><div class="link-group" data-v-10145ec2><h4 data-v-10145ec2>产品</h4><ul data-v-10145ec2><li data-v-10145ec2>`);
      _push(ssrRenderComponent(_component_router_link, { to: "/ai-cms" }, {
        default: withCtx((_, _push2, _parent2, _scopeId) => {
          if (_push2) {
            _push2(`AI CMS`);
          } else {
            return [
              createTextVNode("AI CMS")
            ];
          }
        }),
        _: 1
      }, _parent));
      _push(`</li><li data-v-10145ec2>`);
      _push(ssrRenderComponent(_component_router_link, { to: "/features" }, {
        default: withCtx((_, _push2, _parent2, _scopeId) => {
          if (_push2) {
            _push2(`功能介绍`);
          } else {
            return [
              createTextVNode("功能介绍")
            ];
          }
        }),
        _: 1
      }, _parent));
      _push(`</li><li data-v-10145ec2>`);
      _push(ssrRenderComponent(_component_router_link, { to: "/advantages" }, {
        default: withCtx((_, _push2, _parent2, _scopeId) => {
          if (_push2) {
            _push2(`技术优势`);
          } else {
            return [
              createTextVNode("技术优势")
            ];
          }
        }),
        _: 1
      }, _parent));
      _push(`</li><li data-v-10145ec2>`);
      _push(ssrRenderComponent(_component_router_link, { to: "/deploy" }, {
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
      _push(`</li></ul></div><div class="link-group" data-v-10145ec2><h4 data-v-10145ec2>文档</h4><ul data-v-10145ec2><li data-v-10145ec2>`);
      _push(ssrRenderComponent(_component_router_link, { to: "/docs/guide" }, {
        default: withCtx((_, _push2, _parent2, _scopeId) => {
          if (_push2) {
            _push2(`使用指南`);
          } else {
            return [
              createTextVNode("使用指南")
            ];
          }
        }),
        _: 1
      }, _parent));
      _push(`</li><li data-v-10145ec2>`);
      _push(ssrRenderComponent(_component_router_link, { to: "/deploy" }, {
        default: withCtx((_, _push2, _parent2, _scopeId) => {
          if (_push2) {
            _push2(`部署教程`);
          } else {
            return [
              createTextVNode("部署教程")
            ];
          }
        }),
        _: 1
      }, _parent));
      _push(`</li><li data-v-10145ec2><a${ssrRenderAttr("href", unref(urls).github)} target="_blank" rel="noopener" data-v-10145ec2>GitHub 仓库</a></li></ul></div><div class="link-group" data-v-10145ec2><h4 data-v-10145ec2>支持</h4><ul data-v-10145ec2><li data-v-10145ec2><a${ssrRenderAttr("href", unref(urls).contact)} target="_blank" rel="noopener" data-v-10145ec2>联系我们</a></li>`);
      if (unref(contact2).wechat) {
        _push(`<li data-v-10145ec2>微信：${ssrInterpolate(unref(contact2).wechat)}</li>`);
      } else {
        _push(`<!---->`);
      }
      if (unref(contact2).phone) {
        _push(`<li data-v-10145ec2>电话：${ssrInterpolate(unref(contact2).phone)}</li>`);
      } else {
        _push(`<!---->`);
      }
      _push(`<li data-v-10145ec2><a${ssrRenderAttr("href", `mailto:${unref(contact2).email}`)} data-v-10145ec2>${ssrInterpolate(unref(contact2).email)}</a></li></ul></div></div></div><div class="footer-bottom" data-v-10145ec2><p data-v-10145ec2>© ${ssrInterpolate((/* @__PURE__ */ new Date()).getFullYear())} 辰科科技 Cenkor Admin. 保留所有权利.</p></div></div></footer>`);
    };
  }
});
const _sfc_setup$1 = _sfc_main$1.setup;
_sfc_main$1.setup = (props, ctx) => {
  const ssrContext = useSSRContext();
  (ssrContext.modules || (ssrContext.modules = /* @__PURE__ */ new Set())).add("src/components/Footer.vue");
  return _sfc_setup$1 ? _sfc_setup$1(props, ctx) : void 0;
};
const Footer = /* @__PURE__ */ _export_sfc(_sfc_main$1, [["__scopeId", "data-v-10145ec2"]]);
const SITE_BASE = "https://admin.cenkor.cn/landing";
const SHARED_META = [
  { property: "og:type", content: "website" },
  { property: "og:site_name", content: "辰科 Cenkor Admin" },
  // og:image 必须是绝对 URL、位图格式（SVG 不被微信/微博/Twitter 采用），且 ≥1200x630
  { property: "og:image", content: `${SITE_BASE}/og-image.png` },
  { property: "og:image:width", content: "1200" },
  { property: "og:image:height", content: "630" },
  { property: "og:image:alt", content: "辰科 Cenkor Admin - 企业级后台管理平台" },
  { property: "og:locale", content: "zh_CN" },
  { name: "twitter:card", content: "summary_large_image" },
  { name: "twitter:image", content: `${SITE_BASE}/og-image.png` }
];
const SEO = {
  "/": {
    title: "辰科Cenkor Admin - 企业级平台 × AI CMS | 私有化部署",
    description: "辰科Cenkor Admin 企业级平台，FastAPI + Vue3 架构，内置应用中心、RBAC 权限、工作流审批、AI CMS 内容引擎、用户中心与审计日志。AI CMS 支持对话式建模、AI 起草翻译、语义检索，内容以 REST / GraphQL / MCP 三协议输出，支持私有化部署。"
  },
  "/ai-cms": {
    title: "辰科Cenkor Admin - AI CMS 内容引擎 | 对话式建模 · AI 起草 · MCP 出口",
    description: "辰科 AI CMS：用中文描述业务直接生成内容模型，AI 起草与批量翻译，语义检索带引用溯源，内容健康度体检、选题 Gap 分析、问答式站内搜索、AI 配图与视频、多渠道再分发。内容以 REST / GraphQL / MCP 三种协议供给任意前端与 Agent。"
  },
  "/features": {
    title: "辰科Cenkor Admin - 核心功能 | AI CMS 与应用中心",
    description: "辰科Cenkor Admin 核心功能：AI CMS 内容引擎、应用中心（12 个可插拔应用）、RBAC 三级权限、动态建模与多站点、工作流审批、多渠道发布与效果统计、REST / GraphQL / MCP 开放接口、在线升级、私有化部署。"
  },
  "/advantages": {
    title: "辰科Cenkor Admin - 技术优势 | AI 原生内容层",
    description: "辰科Cenkor Admin 技术优势：FastAPI + Vue3 现代架构、应用中心生态、动态建模、AI 原生内容层（可选增强）、三协议开放接口、在线升级、前后台双用户体系与三种部署模式。"
  },
  "/deploy": {
    title: "辰科Cenkor Admin - 私有部署 | 企业级平台",
    description: "辰科Cenkor Admin 私有化部署指南。Docker Compose、宝塔静态 dist、裸机 systemd 三种模式，PostgreSQL + Redis + MinIO + Backend + Admin + Portal；含 AI 模型接入与在线升级说明。"
  },
  "/docs/guide": {
    title: "辰科Cenkor Admin - 使用指南 | 企业级平台",
    description: "辰科Cenkor Admin 使用入门指南：系统登录、应用中心安装、RBAC 权限、AI CMS 建模与内容管理、工作流审批、用户中心快速上手。"
  }
};
function normalizePath(p) {
  const clean = (p || "/").split(/[?#]/)[0];
  const withSlash = clean.startsWith("/") ? clean : `/${clean}`;
  return withSlash.length > 1 ? withSlash.replace(/\/+$/, "") : "/";
}
function seoFor(path) {
  return SEO[normalizePath(path)] ?? SEO["/"];
}
function canonicalFor(path) {
  const p = normalizePath(path);
  return p === "/" ? `${SITE_BASE}/` : `${SITE_BASE}${p}`;
}
const _sfc_main = /* @__PURE__ */ defineComponent({
  __name: "App",
  __ssrInlineRender: true,
  setup(__props) {
    const route = useRoute();
    useHead(() => {
      const seo = seoFor(route.path);
      const canonical = canonicalFor(route.path);
      return {
        title: seo.title,
        link: [{ rel: "canonical", href: canonical }],
        meta: [
          { name: "description", content: seo.description },
          { property: "og:title", content: seo.title },
          { property: "og:description", content: seo.description },
          { property: "og:url", content: canonical },
          { name: "twitter:title", content: seo.title },
          { name: "twitter:description", content: seo.description },
          ...SHARED_META
        ]
      };
    });
    return (_ctx, _push, _parent, _attrs) => {
      const _component_router_view = resolveComponent("router-view");
      _push(`<div${ssrRenderAttrs(mergeProps({ class: "app-shell" }, _attrs))}>`);
      _push(ssrRenderComponent(Navbar, null, null, _parent));
      _push(`<main>`);
      _push(ssrRenderComponent(_component_router_view, null, null, _parent));
      _push(`</main>`);
      _push(ssrRenderComponent(Footer, null, null, _parent));
      _push(`</div>`);
    };
  }
});
const _sfc_setup = _sfc_main.setup;
_sfc_main.setup = (props, ctx) => {
  const ssrContext = useSSRContext();
  (ssrContext.modules || (ssrContext.modules = /* @__PURE__ */ new Set())).add("src/App.vue");
  return _sfc_setup ? _sfc_setup(props, ctx) : void 0;
};
const routes = [
  {
    path: "/",
    name: "Home",
    component: () => import("./assets/Home-BpgpkRsZ.js")
  },
  {
    path: "/ai-cms",
    name: "AiCms",
    component: () => import("./assets/AiCms-BugxrNJ6.js")
  },
  {
    path: "/features",
    name: "Features",
    component: () => import("./assets/Features-BJDi2yW9.js")
  },
  {
    path: "/advantages",
    name: "Advantages",
    component: () => import("./assets/Advantages-DavQ2Fz9.js")
  },
  {
    path: "/deploy",
    name: "Deploy",
    component: () => import("./assets/Deploy-yiVMAVTS.js")
  },
  {
    path: "/docs/guide",
    name: "Guide",
    component: () => import("./assets/Guide-CPqRGShC.js")
  }
];
const scrollBehavior = () => ({ top: 0 });
function createAppRouter(history) {
  return createRouter({ history, routes, scrollBehavior });
}
async function render(url) {
  const app = createSSRApp(_sfc_main);
  const router = createAppRouter(createMemoryHistory("/landing/"));
  app.use(createPinia());
  app.use(router);
  app.use(createHead());
  await router.push(url);
  await router.isReady();
  const html = await renderToString(app);
  return { html };
}
export {
  SITE_URLS as S,
  SEO,
  SHARED_META,
  SITE_BASE,
  _export_sfc as _,
  canonicalFor,
  normalizePath,
  render
};
