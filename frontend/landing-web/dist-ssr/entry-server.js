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
      _push(`<!--[--><nav class="${ssrRenderClass([{ scrolled: isScrolled.value }, "navbar"])}" data-v-dd9bc3fb><div class="container" data-v-dd9bc3fb><div class="navbar-content" data-v-dd9bc3fb>`);
      _push(ssrRenderComponent(_component_router_link, {
        to: "/",
        class: "logo"
      }, {
        default: withCtx((_, _push2, _parent2, _scopeId) => {
          if (_push2) {
            _push2(`<div class="logo-icon" data-v-dd9bc3fb${_scopeId}><svg viewBox="0 0 32 32" fill="none" data-v-dd9bc3fb${_scopeId}><rect width="32" height="32" rx="6" fill="#10b981" data-v-dd9bc3fb${_scopeId}></rect><rect x="7" y="7" width="5" height="5" rx="1.5" fill="white" data-v-dd9bc3fb${_scopeId}></rect><rect x="13.5" y="7" width="5" height="5" rx="1.5" fill="white" opacity="0.55" data-v-dd9bc3fb${_scopeId}></rect><rect x="20" y="7" width="5" height="5" rx="1.5" fill="white" opacity="0.8" data-v-dd9bc3fb${_scopeId}></rect><rect x="7" y="13.5" width="5" height="5" rx="1.5" fill="white" opacity="0.8" data-v-dd9bc3fb${_scopeId}></rect><rect x="13.5" y="13.5" width="5" height="5" rx="1.5" fill="white" data-v-dd9bc3fb${_scopeId}></rect><rect x="20" y="13.5" width="5" height="5" rx="1.5" fill="white" opacity="0.8" data-v-dd9bc3fb${_scopeId}></rect><rect x="7" y="20" width="5" height="5" rx="1.5" fill="white" opacity="0.55" data-v-dd9bc3fb${_scopeId}></rect><rect x="13.5" y="20" width="5" height="5" rx="1.5" fill="white" opacity="0.8" data-v-dd9bc3fb${_scopeId}></rect><rect x="20" y="20" width="5" height="5" rx="1.5" fill="white" data-v-dd9bc3fb${_scopeId}></rect></svg></div><span class="logo-text" data-v-dd9bc3fb${_scopeId}>辰科 Cenkor Admin</span>`);
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
      _push(`<div class="${ssrRenderClass([{ active: mobileMenuOpen.value }, "nav-links"])}" data-v-dd9bc3fb><a data-v-dd9bc3fb>首页</a><a data-v-dd9bc3fb>功能</a><a data-v-dd9bc3fb>优势</a><a data-v-dd9bc3fb>私有部署</a><div class="dropdown" data-v-dd9bc3fb><span class="dropdown-trigger" data-v-dd9bc3fb>文档</span><div class="dropdown-menu" data-v-dd9bc3fb><a data-v-dd9bc3fb>使用指南</a><a data-v-dd9bc3fb>部署教程</a></div></div></div><div class="nav-actions" data-v-dd9bc3fb><a${ssrRenderAttr("href", unref(urls).contact)} target="_blank" rel="noopener" class="btn btn-ghost btn-small" data-v-dd9bc3fb>联系我们</a><a${ssrRenderAttr("href", unref(urls).github)} target="_blank" rel="noopener" class="btn btn-primary btn-small" data-v-dd9bc3fb>GitHub</a></div><button class="${ssrRenderClass([{ active: mobileMenuOpen.value }, "mobile-toggle"])}" data-v-dd9bc3fb><span data-v-dd9bc3fb></span><span data-v-dd9bc3fb></span><span data-v-dd9bc3fb></span></button></div></div></nav><div class="${ssrRenderClass([{ active: mobileMenuOpen.value }, "mobile-overlay"])}" data-v-dd9bc3fb></div><!--]-->`);
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
const Navbar = /* @__PURE__ */ _export_sfc(_sfc_main$2, [["__scopeId", "data-v-dd9bc3fb"]]);
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
      _push(`<footer${ssrRenderAttrs(mergeProps({ class: "footer" }, _attrs))} data-v-b5198d54><div class="container" data-v-b5198d54><div class="footer-content" data-v-b5198d54><div class="footer-brand" data-v-b5198d54><div class="logo" data-v-b5198d54><div class="logo-icon" data-v-b5198d54><svg viewBox="0 0 32 32" fill="none" data-v-b5198d54><rect width="32" height="32" rx="6" fill="#10b981" data-v-b5198d54></rect><rect x="7" y="7" width="5" height="5" rx="1.5" fill="white" data-v-b5198d54></rect><rect x="13.5" y="7" width="5" height="5" rx="1.5" fill="white" opacity="0.55" data-v-b5198d54></rect><rect x="20" y="7" width="5" height="5" rx="1.5" fill="white" opacity="0.8" data-v-b5198d54></rect><rect x="7" y="13.5" width="5" height="5" rx="1.5" fill="white" opacity="0.8" data-v-b5198d54></rect><rect x="13.5" y="13.5" width="5" height="5" rx="1.5" fill="white" data-v-b5198d54></rect><rect x="20" y="13.5" width="5" height="5" rx="1.5" fill="white" opacity="0.8" data-v-b5198d54></rect><rect x="7" y="20" width="5" height="5" rx="1.5" fill="white" opacity="0.55" data-v-b5198d54></rect><rect x="13.5" y="20" width="5" height="5" rx="1.5" fill="white" opacity="0.8" data-v-b5198d54></rect><rect x="20" y="20" width="5" height="5" rx="1.5" fill="white" data-v-b5198d54></rect></svg></div><span class="logo-text" data-v-b5198d54>辰科 Cenkor Admin</span></div><p class="footer-desc" data-v-b5198d54>企业级后台管理平台 · 应用中心 + RBAC + CMS · FastAPI + Vue3</p></div><div class="footer-links" data-v-b5198d54><div class="link-group" data-v-b5198d54><h4 data-v-b5198d54>产品</h4><ul data-v-b5198d54><li data-v-b5198d54>`);
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
      _push(`</li><li data-v-b5198d54>`);
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
      _push(`</li><li data-v-b5198d54>`);
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
      _push(`</li></ul></div><div class="link-group" data-v-b5198d54><h4 data-v-b5198d54>文档</h4><ul data-v-b5198d54><li data-v-b5198d54>`);
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
      _push(`</li><li data-v-b5198d54>`);
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
      _push(`</li><li data-v-b5198d54><a${ssrRenderAttr("href", unref(urls).github)} target="_blank" rel="noopener" data-v-b5198d54>GitHub 仓库</a></li></ul></div><div class="link-group" data-v-b5198d54><h4 data-v-b5198d54>支持</h4><ul data-v-b5198d54><li data-v-b5198d54><a${ssrRenderAttr("href", unref(urls).contact)} target="_blank" rel="noopener" data-v-b5198d54>联系我们</a></li>`);
      if (unref(contact2).wechat) {
        _push(`<li data-v-b5198d54>微信：${ssrInterpolate(unref(contact2).wechat)}</li>`);
      } else {
        _push(`<!---->`);
      }
      if (unref(contact2).phone) {
        _push(`<li data-v-b5198d54>电话：${ssrInterpolate(unref(contact2).phone)}</li>`);
      } else {
        _push(`<!---->`);
      }
      _push(`<li data-v-b5198d54><a${ssrRenderAttr("href", `mailto:${unref(contact2).email}`)} data-v-b5198d54>${ssrInterpolate(unref(contact2).email)}</a></li></ul></div></div></div><div class="footer-bottom" data-v-b5198d54><p data-v-b5198d54>© ${ssrInterpolate((/* @__PURE__ */ new Date()).getFullYear())} 辰科科技 Cenkor Admin. 保留所有权利.</p></div></div></footer>`);
    };
  }
});
const _sfc_setup$1 = _sfc_main$1.setup;
_sfc_main$1.setup = (props, ctx) => {
  const ssrContext = useSSRContext();
  (ssrContext.modules || (ssrContext.modules = /* @__PURE__ */ new Set())).add("src/components/Footer.vue");
  return _sfc_setup$1 ? _sfc_setup$1(props, ctx) : void 0;
};
const Footer = /* @__PURE__ */ _export_sfc(_sfc_main$1, [["__scopeId", "data-v-b5198d54"]]);
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
    title: "辰科Cenkor Admin - 企业级后台管理平台 | 私有化部署",
    description: "辰科Cenkor Admin 企业级后台管理平台，FastAPI + Vue3 架构，内置应用中心、RBAC 权限、通用内容引擎、用户中心、审计日志，应用按需安装，支持私有化部署。"
  },
  "/features": {
    title: "辰科Cenkor Admin - 核心功能 | 企业级后台管理平台",
    description: "辰科Cenkor Admin 核心功能：应用中心、RBAC 权限、通用内容引擎（21+ 字段类型）、用户中心、审计日志、私有化部署。"
  },
  "/advantages": {
    title: "辰科Cenkor Admin - 技术优势 | 企业级后台管理平台",
    description: "辰科Cenkor Admin 技术优势：FastAPI + Vue3 现代架构、应用中心生态、通用内容引擎、前后台双用户体系、三种部署模式。"
  },
  "/deploy": {
    title: "辰科Cenkor Admin - 私有部署 | 企业级后台管理平台",
    description: "辰科Cenkor Admin 私有化部署指南。Docker Compose、宝塔静态 dist、裸机 systemd 三种模式，PostgreSQL + Redis + MinIO + Backend + Admin + Portal。"
  },
  "/docs/guide": {
    title: "辰科Cenkor Admin - 使用指南 | 企业级后台管理平台",
    description: "辰科Cenkor Admin 使用入门指南：系统登录、应用中心安装、RBAC 权限、CMS 内容管理、用户中心快速上手。"
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
    component: () => import("./assets/Home-DFGm43MU.js")
  },
  {
    path: "/features",
    name: "Features",
    component: () => import("./assets/Features-CCJp-Dg9.js")
  },
  {
    path: "/advantages",
    name: "Advantages",
    component: () => import("./assets/Advantages-C_uXMo-2.js")
  },
  {
    path: "/deploy",
    name: "Deploy",
    component: () => import("./assets/Deploy-B6_e8Srq.js")
  },
  {
    path: "/docs/guide",
    name: "Guide",
    component: () => import("./assets/Guide-Dhv65LrA.js")
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
