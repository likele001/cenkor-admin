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
      { icon: "🖥️", label: "管理后台", value: "http://<服务器IP>:5185" },
      { icon: "👤", label: "用户中心", value: "http://<服务器IP>:5192" },
      { icon: "⚡", label: "API 文档", value: "http://<服务器IP>:8001/api/docs" },
      { icon: "🔑", label: "管理员账号", value: "admin@cenkor.cn（初始密码见下方说明）" }
    ];
    const pwSteps = [
      {
        tag: "推荐",
        title: "部署脚本跑完，直接看终端输出",
        desc: "bash scripts/bootstrap-fullstack.sh 收尾时会打印管理员账号与初始密码。⚠️ 只显示这一次，请立即保存。",
        code: `====================================================================
  已创建管理员：admin@cenkor.cn
  初始密码    ：xxxxxxxxxxxxxxxx
  ⚠️ 此口令只显示这一次，请立即登录并修改
====================================================================`
      },
      {
        tag: "找回",
        title: "当时没记下来 → 翻服务端日志",
        desc: "口令唯一留痕在容器日志里。注意：容器重建（docker compose down 不带 -v 也会重建容器）后日志会清空，届时只能走第 3 步。",
        code: `docker compose -f docker-compose.fullstack.yml logs backend | grep -A3 已创建管理员`
      },
      {
        tag: "重置",
        title: "日志也没了 → 用重置脚本（同时踢掉旧会话）",
        desc: "不传参数则随机生成并打印；传 --password 则设为指定值。Docker 与宝塔裸机两种部署会自动识别。",
        code: `bash scripts/reset-admin-password.sh                      # 随机生成新口令
bash scripts/reset-admin-password.sh --password '你的新口令'   # 指定口令`
      }
    ];
    return (_ctx, _push, _parent, _attrs) => {
      _push(`<div${ssrRenderAttrs(mergeProps({ class: "deploy-page" }, _attrs))} data-v-d529d71d><section class="page-hero" data-v-d529d71d><div class="container" data-v-d529d71d><div class="page-hero-content" data-v-d529d71d><span class="hero-tag" data-v-d529d71d>私有部署</span><h1 data-v-d529d71d>Cenkor Admin 私有化部署</h1><p data-v-d529d71d>Docker Compose / 宝塔静态 / 裸机 systemd 三种模式，快速上线</p></div></div></section><section class="section" data-v-d529d71d><div class="container" data-v-d529d71d><div class="deploy-content" data-v-d529d71d>`);
      _push(ssrRenderComponent(SectionTitle, {
        tag: "部署模式",
        title: "三种部署方式可选",
        description: "根据您的环境选择最合适的交付模式"
      }, null, _parent));
      _push(`<div class="mode-grid" data-v-d529d71d><!--[-->`);
      ssrRenderList(modes, (mode) => {
        _push(`<div class="mode-item" data-v-d529d71d><div class="mode-icon" data-v-d529d71d>${ssrInterpolate(mode.icon)}</div><h4 data-v-d529d71d>${ssrInterpolate(mode.title)}</h4><p data-v-d529d71d>${ssrInterpolate(mode.desc)}</p></div>`);
      });
      _push(`<!--]--></div></div></div></section><section class="section section-alt" data-v-d529d71d><div class="container" data-v-d529d71d>`);
      _push(ssrRenderComponent(SectionTitle, {
        tag: "服务栈",
        title: "所需服务",
        description: "PostgreSQL + Redis + MinIO + Backend + Admin-Web + Portal-Web",
        center: true
      }, null, _parent));
      _push(`<div class="service-grid" data-v-d529d71d><!--[-->`);
      ssrRenderList(services, (svc) => {
        _push(`<div class="service-item" data-v-d529d71d><div class="service-icon" data-v-d529d71d>${ssrInterpolate(svc.icon)}</div><strong data-v-d529d71d>${ssrInterpolate(svc.name)}</strong><span data-v-d529d71d>${ssrInterpolate(svc.desc)}</span></div>`);
      });
      _push(`<!--]--></div></div></section><section class="section" data-v-d529d71d><div class="container" data-v-d529d71d><div class="deploy-content" data-v-d529d71d>`);
      _push(ssrRenderComponent(SectionTitle, {
        tag: "快速开始",
        title: "一条命令拉起全栈",
        description: "前置只需 Docker + Compose v2，其余交给脚本"
      }, null, _parent));
      _push(`<div class="code-block" data-v-d529d71d><pre data-v-d529d71d><code data-v-d529d71d>git clone https://github.com/likele001/cenkor-admin.git
cd cenkor-admin
bash scripts/bootstrap-fullstack.sh</code></pre></div><p class="code-note" data-v-d529d71d> 脚本会自动生成 <code data-v-d529d71d>.env</code>（随机密钥）→ 构建并拉起全部容器 → 等待后端就绪 → 执行数据库迁移与种子数据 → 在终端打印访问地址与<strong data-v-d529d71d>初始管理员密码</strong>。 中途无需干预。 </p><div class="env-grid" data-v-d529d71d><!--[-->`);
      ssrRenderList(envs, (env) => {
        _push(`<div class="env-item" data-v-d529d71d><div class="env-icon" data-v-d529d71d>${ssrInterpolate(env.icon)}</div><div data-v-d529d71d><strong data-v-d529d71d>${ssrInterpolate(env.label)}</strong><span data-v-d529d71d>${ssrInterpolate(env.value)}</span></div></div>`);
      });
      _push(`<!--]--></div></div></div></section><section class="section section-alt" data-v-d529d71d><div class="container" data-v-d529d71d><div class="deploy-content" data-v-d529d71d>`);
      _push(ssrRenderComponent(SectionTitle, {
        tag: "首次登录",
        title: "初始管理员密码怎么拿",
        description: "仓库不设任何默认口令，密码在首次初始化时随机生成"
      }, null, _parent));
      _push(`<div class="pw-panel" data-v-d529d71d><div class="pw-alert" data-v-d529d71d><strong data-v-d529d71d>⚠️ 本仓库没有任何默认口令</strong><p data-v-d529d71d> 诸如 <code data-v-d529d71d>admin123</code>、<code data-v-d529d71d>admin@123</code> 这类「常见默认密码」<strong data-v-d529d71d>一律无效</strong>。 管理员的初始口令在首次初始化时<strong data-v-d529d71d>随机生成</strong>，并且<strong data-v-d529d71d>只完整显示一次</strong>—— 数据库里只存 bcrypt 哈希，事后推不回来。 </p></div><ol class="pw-steps" data-v-d529d71d><!--[-->`);
      ssrRenderList(pwSteps, (s, i) => {
        _push(`<li data-v-d529d71d><div class="pw-step-head" data-v-d529d71d><span class="pw-step-no" data-v-d529d71d>${ssrInterpolate(i + 1)}</span><span class="pw-step-tag" data-v-d529d71d>${ssrInterpolate(s.tag)}</span><strong data-v-d529d71d>${ssrInterpolate(s.title)}</strong></div><p data-v-d529d71d>${ssrInterpolate(s.desc)}</p>`);
        if (s.code) {
          _push(`<div class="code-block" data-v-d529d71d><pre data-v-d529d71d><code data-v-d529d71d>${ssrInterpolate(s.code)}</code></pre></div>`);
        } else {
          _push(`<!---->`);
        }
        _push(`</li>`);
      });
      _push(`<!--]--></ol><p class="pw-tip" data-v-d529d71d> 账号固定为 <code data-v-d529d71d>admin@cenkor.cn</code>（用户名 <code data-v-d529d71d>admin</code> 同样可登录）。 登录时按提示完成滑块验证；<strong data-v-d529d71d>首次登录后请立即修改为只有你知道的口令</strong>。 想一开始就自己定：部署前在 <code data-v-d529d71d>.env</code> 里写 <code data-v-d529d71d>CENKOR_ADMIN_PASSWORD=你的口令</code>（设置后不再随机、也不再打印）。 </p></div></div></div></section><section class="cta-section" data-v-d529d71d><div class="container" data-v-d529d71d><div class="cta-content" data-v-d529d71d><h2 data-v-d529d71d>准备好部署 Cenkor Admin 了吗？</h2><p data-v-d529d71d>获取完整部署文档与技术指导</p><div class="cta-actions" data-v-d529d71d><a${ssrRenderAttr("href", unref(urls).github)} target="_blank" rel="noopener" class="btn btn-primary btn-large" data-v-d529d71d>GitHub 仓库</a><a${ssrRenderAttr("href", unref(urls).contact)} target="_blank" rel="noopener" class="btn btn-secondary btn-large" data-v-d529d71d>联系我们</a></div></div></div></section></div>`);
    };
  }
});
const _sfc_setup = _sfc_main.setup;
_sfc_main.setup = (props, ctx) => {
  const ssrContext = useSSRContext();
  (ssrContext.modules || (ssrContext.modules = /* @__PURE__ */ new Set())).add("src/views/Deploy.vue");
  return _sfc_setup ? _sfc_setup(props, ctx) : void 0;
};
const Deploy = /* @__PURE__ */ _export_sfc(_sfc_main, [["__scopeId", "data-v-d529d71d"]]);
export {
  Deploy as default
};
