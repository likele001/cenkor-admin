import { defineComponent, mergeProps, unref, useSSRContext } from "vue";
import { ssrRenderAttrs, ssrRenderComponent, ssrRenderList, ssrInterpolate, ssrRenderAttr } from "vue/server-renderer";
import { S as SectionTitle } from "./SectionTitle-NKY75B6X.js";
import { S as SITE_URLS, _ as _export_sfc } from "../entry-server.js";
import "vue-router";
import "@unhead/vue";
import "pinia";
const _sfc_main = /* @__PURE__ */ defineComponent({
  __name: "Deploy",
  __ssrInlineRender: true,
  setup(__props) {
    const urls = SITE_URLS;
    const modes = [
      { icon: "🐳", title: "Docker Compose", desc: "容器化一键部署，开发生产一致" },
      { icon: "🖥️", title: "宝塔静态 dist", desc: "构建静态前端 + 反代后端，推荐生产" },
      { icon: "⚙️", title: "裸机 systemd", desc: "直接运行后端服务，轻量部署" }
    ];
    const services = [
      { icon: "🗄️", name: "PostgreSQL 16", desc: "关系型数据库" },
      { icon: "🔴", name: "Redis 7", desc: "缓存与消息队列" },
      { icon: "☁️", name: "MinIO", desc: "对象存储" },
      { icon: "⚡", name: "Backend", desc: "FastAPI 后端" },
      { icon: "🖥️", name: "Admin-Web", desc: "运营后台 SPA" },
      { icon: "👤", name: "Portal-Web", desc: "用户中心 SPA" }
    ];
    const envs = [
      { icon: "🖥️", label: "管理后台", value: "http://localhost:5173" },
      { icon: "👤", label: "用户中心", value: "http://localhost:5175" },
      { icon: "⚡", label: "API 文档", value: "http://localhost:8000/api/docs" },
      { icon: "🔑", label: "初始账号", value: "由 seed 脚本生成，首次登录后请立即修改密码" }
    ];
    return (_ctx, _push, _parent, _attrs) => {
      _push(`<div${ssrRenderAttrs(mergeProps({ class: "deploy-page" }, _attrs))} data-v-40414084><section class="page-hero" data-v-40414084><div class="container" data-v-40414084><div class="page-hero-content" data-v-40414084><span class="hero-tag" data-v-40414084>私有部署</span><h1 data-v-40414084>Cenkor Admin 私有化部署</h1><p data-v-40414084>Docker Compose / 宝塔静态 / 裸机 systemd 三种模式，快速上线</p></div></div></section><section class="section" data-v-40414084><div class="container" data-v-40414084><div class="deploy-content" data-v-40414084>`);
      _push(ssrRenderComponent(SectionTitle, {
        tag: "部署模式",
        title: "三种部署方式可选",
        description: "根据您的环境选择最合适的交付模式"
      }, null, _parent));
      _push(`<div class="mode-grid" data-v-40414084><!--[-->`);
      ssrRenderList(modes, (mode) => {
        _push(`<div class="mode-item" data-v-40414084><div class="mode-icon" data-v-40414084>${ssrInterpolate(mode.icon)}</div><h4 data-v-40414084>${ssrInterpolate(mode.title)}</h4><p data-v-40414084>${ssrInterpolate(mode.desc)}</p></div>`);
      });
      _push(`<!--]--></div></div></div></section><section class="section section-alt" data-v-40414084><div class="container" data-v-40414084>`);
      _push(ssrRenderComponent(SectionTitle, {
        tag: "服务栈",
        title: "所需服务",
        description: "PostgreSQL + Redis + MinIO + Backend + Admin-Web + Portal-Web",
        center: true
      }, null, _parent));
      _push(`<div class="service-grid" data-v-40414084><!--[-->`);
      ssrRenderList(services, (svc) => {
        _push(`<div class="service-item" data-v-40414084><div class="service-icon" data-v-40414084>${ssrInterpolate(svc.icon)}</div><strong data-v-40414084>${ssrInterpolate(svc.name)}</strong><span data-v-40414084>${ssrInterpolate(svc.desc)}</span></div>`);
      });
      _push(`<!--]--></div></div></section><section class="section" data-v-40414084><div class="container" data-v-40414084><div class="deploy-content" data-v-40414084>`);
      _push(ssrRenderComponent(SectionTitle, {
        tag: "快速开始",
        title: "开发环境一分钟启动",
        description: "Docker Compose 一键拉起全栈"
      }, null, _parent));
      _push(`<div class="code-block" data-v-40414084><pre data-v-40414084><code data-v-40414084>cp .env.example .env
docker compose up -d
docker compose exec backend alembic upgrade head
docker compose exec backend python -m cenkor_admin.scripts.seed</code></pre></div><div class="env-grid" data-v-40414084><!--[-->`);
      ssrRenderList(envs, (env) => {
        _push(`<div class="env-item" data-v-40414084><div class="env-icon" data-v-40414084>${ssrInterpolate(env.icon)}</div><div data-v-40414084><strong data-v-40414084>${ssrInterpolate(env.label)}</strong><span data-v-40414084>${ssrInterpolate(env.value)}</span></div></div>`);
      });
      _push(`<!--]--></div></div></div></section><section class="cta-section" data-v-40414084><div class="container" data-v-40414084><div class="cta-content" data-v-40414084><h2 data-v-40414084>准备好部署 Cenkor Admin 了吗？</h2><p data-v-40414084>获取完整部署文档与技术指导</p><div class="cta-actions" data-v-40414084><a${ssrRenderAttr("href", unref(urls).github)} target="_blank" rel="noopener" class="btn btn-primary btn-large" data-v-40414084>GitHub 仓库</a><a${ssrRenderAttr("href", unref(urls).contact)} target="_blank" rel="noopener" class="btn btn-secondary btn-large" data-v-40414084>联系我们</a></div></div></div></section></div>`);
    };
  }
});
const _sfc_setup = _sfc_main.setup;
_sfc_main.setup = (props, ctx) => {
  const ssrContext = useSSRContext();
  (ssrContext.modules || (ssrContext.modules = /* @__PURE__ */ new Set())).add("src/views/Deploy.vue");
  return _sfc_setup ? _sfc_setup(props, ctx) : void 0;
};
const Deploy = /* @__PURE__ */ _export_sfc(_sfc_main, [["__scopeId", "data-v-40414084"]]);
export {
  Deploy as default
};
