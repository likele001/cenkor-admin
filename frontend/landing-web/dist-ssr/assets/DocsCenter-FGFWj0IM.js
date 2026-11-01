import { defineComponent, ref, computed, watch, onMounted, resolveComponent, mergeProps, withCtx, createTextVNode, toDisplayString, createVNode, openBlock, createBlock, createCommentVNode, useSSRContext } from "vue";
import { ssrRenderAttrs, ssrInterpolate, ssrRenderAttr, ssrRenderList, ssrRenderComponent } from "vue/server-renderer";
import { useRoute, useRouter } from "vue-router";
import { useHead } from "@unhead/vue";
import MarkdownIt from "markdown-it";
import hljs from "highlight.js/lib/common";
import { _ as _export_sfc } from "../entry-server.js";
import "pinia";
const DOCS_GROUPS = [
  {
    "key": "",
    "label": "总览与指南",
    "items": [
      {
        "path": "ai-settings.md",
        "title": "AI 配置 · 后台可视化管理",
        "desc": "入口：后台「CMS → AI 设置」（/cms/ai-settings），仅管理员可见。",
        "dir": ""
      },
      {
        "path": "baota_static_deploy.md",
        "title": "Cenkor Admin · 宝塔面板完整部署指南",
        "desc": "⚠️ 本文描述的不是本机生产架构。",
        "dir": ""
      },
      {
        "path": "cms-ai.md",
        "title": "CMS AI 能力",
        "desc": "Mosaic CMS 的 AI 层。四项能力：对话式建模 · AI 起草 · AI 翻译 · 语义检索。",
        "dir": ""
      },
      {
        "path": "core_platform.md",
        "title": "Cenkor Admin · 核心平台（不含官网）",
        "desc": "本仓库的可独立部署产品，由以下部分组成，不依赖任何外部营销站或 /www/wwwroot/website。",
        "dir": ""
      },
      {
        "path": "database-migrations.md",
        "title": "cenkor-admin 数据库迁移规范（开发者必读）",
        "desc": "状态基线：2026-10-30 实测。适用于 cenkor-admin（hub）后端全部开发者。",
        "dir": ""
      },
      {
        "path": "deploy.md",
        "title": "Cenkor Admin · 部署方案（权威）",
        "desc": "本文是 cenkor-admin 的唯一权威部署文档。 其他文档只做引用，不重复端口与路径，",
        "dir": ""
      },
      {
        "path": "dev_guide.md",
        "title": "Cenkor Platform V2 — 开发者指南",
        "desc": "面向新接入 Cenkor Platform V2 的开发者。",
        "dir": ""
      },
      {
        "path": "domain_setup.md",
        "title": "Cenkor Admin · 域名绑定 + SSL",
        "desc": "本文只讲域名解析、宝塔建站、SSL 证书三件事。",
        "dir": ""
      },
      {
        "path": "fullstack_deploy.md",
        "title": "Cenkor Admin · 全栈容器化部署（含前端，一条命令）",
        "desc": "⚠️ 本文描述的不是本机生产架构。",
        "dir": ""
      },
      {
        "path": "index.md",
        "title": "文档索引",
        "desc": "Cenkor Admin 文档目录。按用途选择。",
        "dir": ""
      },
      {
        "path": "mcp.md",
        "title": "MCP 接入指南",
        "desc": "Mosaic CMS 内置 MCP（Model Context Protocol）服务端，让 Claude Desktop、Cursor、",
        "dir": ""
      },
      {
        "path": "migrations.md",
        "title": "数据库迁移：两条链、一个挂载点",
        "desc": "🔴 本文是 2026-10-27 的历史记录与事故复盘，不是操作手册。",
        "dir": ""
      },
      {
        "path": "native_deploy.md",
        "title": "Cenkor Admin · 裸机部署（systemd + 宝塔反代）",
        "desc": "ℹ️ 本机生产未采用本文方案。",
        "dir": ""
      },
      {
        "path": "relaunch-ai-cms.md",
        "title": "Cenkor Mosaic · 重定位方案",
        "desc": "AI 原生内容平台 ｜ 2026-10-27 ｜ 从 cenkor-admin monorepo 孵化的独立产品线",
        "dir": ""
      },
      {
        "path": "roadmap.md",
        "title": "Cenkor Platform V2 — 企业级通用后台 + CMS 改造路线图",
        "desc": "📌 本文档由三份规划合并而来（2026-09-25）。",
        "dir": ""
      },
      {
        "path": "template-guide.md",
        "title": "主题模板开发",
        "desc": "前台 HTML 由 Jinja2 主题渲染，模板存在数据库里，在后台「CMS → 模板工作台」直接改、实时预览、一键回滚。",
        "dir": ""
      },
      {
        "path": "upgrade.md",
        "title": "升级指南（UPGRADE）",
        "desc": "本文说明 Cenkor Admin 核心平台 发布新版本后，不同部署方式如何升级，以及维护者如何发版。",
        "dir": ""
      }
    ]
  },
  {
    "key": "addons",
    "label": "插件与扩展",
    "items": [
      {
        "path": "addons/website_cms.md",
        "title": "可选扩展 · 官网 CMS 对接",
        "desc": "ℹ️ 可选扩展。 本机生产未启用本文描述的容器叠加方案；",
        "dir": "addons"
      }
    ]
  },
  {
    "key": "release",
    "label": "发布记录",
    "items": [
      {
        "path": "release/changelog.md",
        "title": "发布记录",
        "desc": "本目录用于存放打包产物说明与发版日志。压缩包文件本身在仓库根目录 release/（已 .gitignore，不提交 git）。",
        "dir": "release"
      },
      {
        "path": "release/latest.md",
        "title": "当前发布产物",
        "desc": "压缩包存放在服务器 release/ 目录，不纳入 git。本文档记录最近一次打包信息。",
        "dir": "release"
      }
    ]
  },
  {
    "key": "template",
    "label": "模板标签参考",
    "items": [
      {
        "path": "template/article.md",
        "title": "内容标签",
        "desc": "取内容数据的四个 API。全部只读、绑定当前站点。",
        "dir": "template"
      },
      {
        "path": "template/comment.md",
        "title": "评论 · 表单 · 媒体 · 多语言",
        "desc": "四个「其他」类的 API。每个标签统一按 语法 → 参数 → 返回 → 示例 四段说明。",
        "dir": "template"
      },
      {
        "path": "template/config.md",
        "title": "站点与配置",
        "desc": "站点信息、页面元信息、URL 生成、分页、静态资源。",
        "dir": "template"
      },
      {
        "path": "template/develop.md",
        "title": "自定义标签开发",
        "desc": "模板能力不够时，两条路：模板内 macro（零后端代码，解决重复片段）",
        "dir": "template"
      },
      {
        "path": "template/index.md",
        "title": "模板标签总览",
        "desc": "主题模板里能用的东西分四类：预注入变量、数据 API（只读函数）、过滤器、App 注册标签。",
        "dir": "template"
      },
      {
        "path": "template/methods.md",
        "title": "全量速查",
        "desc": "一页查全：数据 API、过滤器、预注入变量、App 注册标签。",
        "dir": "template"
      },
      {
        "path": "template/tag.md",
        "title": "结构标签：分类 · 标签 · 菜单 · 友链",
        "desc": "给页面搭骨架的数据源。全部只读、绑定当前站点。",
        "dir": "template"
      }
    ]
  },
  {
    "key": "apps",
    "label": "应用开发",
    "items": [
      {
        "path": "apps/development_guide.md",
        "title": "Cenkor Admin 应用开发规范",
        "desc": "版本：1.2.0",
        "dir": "apps"
      },
      {
        "path": "apps/market_ai_extensions.md",
        "title": "AI 体系扩展应用 · 上架说明（cenkormes）",
        "desc": "给谁看：在 hub（cenkor-admin）这一侧做发布、定价、发卡、排查商店展示的人。",
        "dir": "apps"
      }
    ]
  },
  {
    "key": "05-用户手册",
    "label": "用户手册",
    "items": [
      {
        "path": "05-用户手册/announcements_操作手册.md",
        "title": "公告管理 · 操作手册",
        "desc": "给谁看：负责发布公司公告、通知的人，以及需要查阅公告的普通同事。",
        "dir": "05-用户手册"
      },
      {
        "path": "05-用户手册/cloud_storage_操作手册.md",
        "title": "云存储 · 操作手册",
        "desc": "给谁看：要把平台的图片 / 附件从「服务器本地」搬到云厂商对象存储的管理员。",
        "dir": "05-用户手册"
      },
      {
        "path": "05-用户手册/cms_操作手册.md",
        "title": "内容管理（CMS）· 操作手册",
        "desc": "给谁看：往官网放内容的人 —— 发新闻、更新产品、传案例图、改首页文案、用 AI 批量出稿。",
        "dir": "05-用户手册"
      },
      {
        "path": "05-用户手册/crm_操作手册.md",
        "title": "CRM 销售管理 · 操作手册",
        "desc": "给谁看：跑客户的销售、管销售的销售主管、维护客户资料的销售助理。",
        "dir": "05-用户手册"
      },
      {
        "path": "05-用户手册/erp_操作手册.md",
        "title": "ERP 管理系统 · 操作手册",
        "desc": "给谁看：工厂 / 贸易公司的业务人员 —— 业务员、采购、仓管、财务、生产、老板。",
        "dir": "05-用户手册"
      },
      {
        "path": "05-用户手册/index.md",
        "title": "用户手册总目录",
        "desc": "给谁看：每天用这套系统干活的人。不是给开发看的。",
        "dir": "05-用户手册"
      },
      {
        "path": "05-用户手册/links_操作手册.md",
        "title": "链接收藏 · 操作手册",
        "desc": "给谁看：想给团队攒一份常用网址清单的人。",
        "dir": "05-用户手册"
      },
      {
        "path": "05-用户手册/mes_操作手册.md",
        "title": "MES 制造执行 · 操作手册",
        "desc": "给谁看：车间主任、计划员、调度/班组长、质检员、一线报工工人，以及维护基础数据的工艺员。",
        "dir": "05-用户手册"
      },
      {
        "path": "05-用户手册/my_todo_操作手册.md",
        "title": "My Todo · 操作手册",
        "desc": "给谁看：想快速记一条待办、勾掉一条待办的人。",
        "dir": "05-用户手册"
      },
      {
        "path": "05-用户手册/notification_操作手册.md",
        "title": "通知 · 操作手册",
        "desc": "给谁看：所有登录后台的人。通知是系统「主动告诉你」的通道。",
        "dir": "05-用户手册"
      },
      {
        "path": "05-用户手册/payment_操作手册.md",
        "title": "支付中心 · 操作手册",
        "desc": "给谁看：负责开通收款、盯流水、给客户退款的人（一般是财务或运营）。",
        "dir": "05-用户手册"
      },
      {
        "path": "05-用户手册/quick_notes_操作手册.md",
        "title": "Quick Notes · 操作手册",
        "desc": "给谁看：随手记点东西、过后能搜到的人。",
        "dir": "05-用户手册"
      },
      {
        "path": "05-用户手册/tickets_操作手册.md",
        "title": "工单管理 · 操作手册",
        "desc": "给谁看：提问题 / 提需求的人，和负责处理工单的人。",
        "dir": "05-用户手册"
      },
      {
        "path": "05-用户手册/workflow_操作手册.md",
        "title": "工作流审批 · 操作手册",
        "desc": "给谁看：日常发起单据的人、要审批的人、负责画流程的管理员。",
        "dir": "05-用户手册"
      }
    ]
  }
];
const DOCS_FLAT = [
  {
    "path": "05-用户手册/announcements_操作手册.md",
    "title": "公告管理 · 操作手册",
    "desc": "给谁看：负责发布公司公告、通知的人，以及需要查阅公告的普通同事。",
    "dir": "05-用户手册"
  },
  {
    "path": "05-用户手册/cloud_storage_操作手册.md",
    "title": "云存储 · 操作手册",
    "desc": "给谁看：要把平台的图片 / 附件从「服务器本地」搬到云厂商对象存储的管理员。",
    "dir": "05-用户手册"
  },
  {
    "path": "05-用户手册/cms_操作手册.md",
    "title": "内容管理（CMS）· 操作手册",
    "desc": "给谁看：往官网放内容的人 —— 发新闻、更新产品、传案例图、改首页文案、用 AI 批量出稿。",
    "dir": "05-用户手册"
  },
  {
    "path": "05-用户手册/crm_操作手册.md",
    "title": "CRM 销售管理 · 操作手册",
    "desc": "给谁看：跑客户的销售、管销售的销售主管、维护客户资料的销售助理。",
    "dir": "05-用户手册"
  },
  {
    "path": "05-用户手册/erp_操作手册.md",
    "title": "ERP 管理系统 · 操作手册",
    "desc": "给谁看：工厂 / 贸易公司的业务人员 —— 业务员、采购、仓管、财务、生产、老板。",
    "dir": "05-用户手册"
  },
  {
    "path": "05-用户手册/index.md",
    "title": "用户手册总目录",
    "desc": "给谁看：每天用这套系统干活的人。不是给开发看的。",
    "dir": "05-用户手册"
  },
  {
    "path": "05-用户手册/links_操作手册.md",
    "title": "链接收藏 · 操作手册",
    "desc": "给谁看：想给团队攒一份常用网址清单的人。",
    "dir": "05-用户手册"
  },
  {
    "path": "05-用户手册/mes_操作手册.md",
    "title": "MES 制造执行 · 操作手册",
    "desc": "给谁看：车间主任、计划员、调度/班组长、质检员、一线报工工人，以及维护基础数据的工艺员。",
    "dir": "05-用户手册"
  },
  {
    "path": "05-用户手册/my_todo_操作手册.md",
    "title": "My Todo · 操作手册",
    "desc": "给谁看：想快速记一条待办、勾掉一条待办的人。",
    "dir": "05-用户手册"
  },
  {
    "path": "05-用户手册/notification_操作手册.md",
    "title": "通知 · 操作手册",
    "desc": "给谁看：所有登录后台的人。通知是系统「主动告诉你」的通道。",
    "dir": "05-用户手册"
  },
  {
    "path": "05-用户手册/payment_操作手册.md",
    "title": "支付中心 · 操作手册",
    "desc": "给谁看：负责开通收款、盯流水、给客户退款的人（一般是财务或运营）。",
    "dir": "05-用户手册"
  },
  {
    "path": "05-用户手册/quick_notes_操作手册.md",
    "title": "Quick Notes · 操作手册",
    "desc": "给谁看：随手记点东西、过后能搜到的人。",
    "dir": "05-用户手册"
  },
  {
    "path": "05-用户手册/tickets_操作手册.md",
    "title": "工单管理 · 操作手册",
    "desc": "给谁看：提问题 / 提需求的人，和负责处理工单的人。",
    "dir": "05-用户手册"
  },
  {
    "path": "05-用户手册/workflow_操作手册.md",
    "title": "工作流审批 · 操作手册",
    "desc": "给谁看：日常发起单据的人、要审批的人、负责画流程的管理员。",
    "dir": "05-用户手册"
  },
  {
    "path": "addons/website_cms.md",
    "title": "可选扩展 · 官网 CMS 对接",
    "desc": "ℹ️ 可选扩展。 本机生产未启用本文描述的容器叠加方案；",
    "dir": "addons"
  },
  {
    "path": "ai-settings.md",
    "title": "AI 配置 · 后台可视化管理",
    "desc": "入口：后台「CMS → AI 设置」（/cms/ai-settings），仅管理员可见。",
    "dir": ""
  },
  {
    "path": "apps/development_guide.md",
    "title": "Cenkor Admin 应用开发规范",
    "desc": "版本：1.2.0",
    "dir": "apps"
  },
  {
    "path": "apps/market_ai_extensions.md",
    "title": "AI 体系扩展应用 · 上架说明（cenkormes）",
    "desc": "给谁看：在 hub（cenkor-admin）这一侧做发布、定价、发卡、排查商店展示的人。",
    "dir": "apps"
  },
  {
    "path": "baota_static_deploy.md",
    "title": "Cenkor Admin · 宝塔面板完整部署指南",
    "desc": "⚠️ 本文描述的不是本机生产架构。",
    "dir": ""
  },
  {
    "path": "cms-ai.md",
    "title": "CMS AI 能力",
    "desc": "Mosaic CMS 的 AI 层。四项能力：对话式建模 · AI 起草 · AI 翻译 · 语义检索。",
    "dir": ""
  },
  {
    "path": "core_platform.md",
    "title": "Cenkor Admin · 核心平台（不含官网）",
    "desc": "本仓库的可独立部署产品，由以下部分组成，不依赖任何外部营销站或 /www/wwwroot/website。",
    "dir": ""
  },
  {
    "path": "database-migrations.md",
    "title": "cenkor-admin 数据库迁移规范（开发者必读）",
    "desc": "状态基线：2026-10-30 实测。适用于 cenkor-admin（hub）后端全部开发者。",
    "dir": ""
  },
  {
    "path": "deploy.md",
    "title": "Cenkor Admin · 部署方案（权威）",
    "desc": "本文是 cenkor-admin 的唯一权威部署文档。 其他文档只做引用，不重复端口与路径，",
    "dir": ""
  },
  {
    "path": "dev_guide.md",
    "title": "Cenkor Platform V2 — 开发者指南",
    "desc": "面向新接入 Cenkor Platform V2 的开发者。",
    "dir": ""
  },
  {
    "path": "domain_setup.md",
    "title": "Cenkor Admin · 域名绑定 + SSL",
    "desc": "本文只讲域名解析、宝塔建站、SSL 证书三件事。",
    "dir": ""
  },
  {
    "path": "fullstack_deploy.md",
    "title": "Cenkor Admin · 全栈容器化部署（含前端，一条命令）",
    "desc": "⚠️ 本文描述的不是本机生产架构。",
    "dir": ""
  },
  {
    "path": "index.md",
    "title": "文档索引",
    "desc": "Cenkor Admin 文档目录。按用途选择。",
    "dir": ""
  },
  {
    "path": "mcp.md",
    "title": "MCP 接入指南",
    "desc": "Mosaic CMS 内置 MCP（Model Context Protocol）服务端，让 Claude Desktop、Cursor、",
    "dir": ""
  },
  {
    "path": "migrations.md",
    "title": "数据库迁移：两条链、一个挂载点",
    "desc": "🔴 本文是 2026-10-27 的历史记录与事故复盘，不是操作手册。",
    "dir": ""
  },
  {
    "path": "native_deploy.md",
    "title": "Cenkor Admin · 裸机部署（systemd + 宝塔反代）",
    "desc": "ℹ️ 本机生产未采用本文方案。",
    "dir": ""
  },
  {
    "path": "relaunch-ai-cms.md",
    "title": "Cenkor Mosaic · 重定位方案",
    "desc": "AI 原生内容平台 ｜ 2026-10-27 ｜ 从 cenkor-admin monorepo 孵化的独立产品线",
    "dir": ""
  },
  {
    "path": "release/changelog.md",
    "title": "发布记录",
    "desc": "本目录用于存放打包产物说明与发版日志。压缩包文件本身在仓库根目录 release/（已 .gitignore，不提交 git）。",
    "dir": "release"
  },
  {
    "path": "release/latest.md",
    "title": "当前发布产物",
    "desc": "压缩包存放在服务器 release/ 目录，不纳入 git。本文档记录最近一次打包信息。",
    "dir": "release"
  },
  {
    "path": "roadmap.md",
    "title": "Cenkor Platform V2 — 企业级通用后台 + CMS 改造路线图",
    "desc": "📌 本文档由三份规划合并而来（2026-09-25）。",
    "dir": ""
  },
  {
    "path": "template/article.md",
    "title": "内容标签",
    "desc": "取内容数据的四个 API。全部只读、绑定当前站点。",
    "dir": "template"
  },
  {
    "path": "template/comment.md",
    "title": "评论 · 表单 · 媒体 · 多语言",
    "desc": "四个「其他」类的 API。每个标签统一按 语法 → 参数 → 返回 → 示例 四段说明。",
    "dir": "template"
  },
  {
    "path": "template/config.md",
    "title": "站点与配置",
    "desc": "站点信息、页面元信息、URL 生成、分页、静态资源。",
    "dir": "template"
  },
  {
    "path": "template/develop.md",
    "title": "自定义标签开发",
    "desc": "模板能力不够时，两条路：模板内 macro（零后端代码，解决重复片段）",
    "dir": "template"
  },
  {
    "path": "template/index.md",
    "title": "模板标签总览",
    "desc": "主题模板里能用的东西分四类：预注入变量、数据 API（只读函数）、过滤器、App 注册标签。",
    "dir": "template"
  },
  {
    "path": "template/methods.md",
    "title": "全量速查",
    "desc": "一页查全：数据 API、过滤器、预注入变量、App 注册标签。",
    "dir": "template"
  },
  {
    "path": "template/tag.md",
    "title": "结构标签：分类 · 标签 · 菜单 · 友链",
    "desc": "给页面搭骨架的数据源。全部只读、绑定当前站点。",
    "dir": "template"
  },
  {
    "path": "template-guide.md",
    "title": "主题模板开发",
    "desc": "前台 HTML 由 Jinja2 主题渲染，模板存在数据库里，在后台「CMS → 模板工作台」直接改、实时预览、一键回滚。",
    "dir": ""
  },
  {
    "path": "upgrade.md",
    "title": "升级指南（UPGRADE）",
    "desc": "本文说明 Cenkor Admin 核心平台 发布新版本后，不同部署方式如何升级，以及维护者如何发版。",
    "dir": ""
  }
];
const _sfc_main = /* @__PURE__ */ defineComponent({
  __name: "DocsCenter",
  __ssrInlineRender: true,
  setup(__props) {
    const route = useRoute();
    useRouter();
    const query = ref("");
    const loading = ref(false);
    const error = ref("");
    const rawMd = ref("");
    const rendered = ref("");
    const currentDocPath = computed(() => {
      const raw = route.params.pathMatch;
      const path = Array.isArray(raw) ? raw.join("/") : raw || "";
      return path === "index" ? "" : path;
    });
    const currentDoc = computed(
      () => DOCS_FLAT.find((d) => stripMd(d.path) === currentDocPath.value)
    );
    const prevDoc = computed(() => {
      const i = DOCS_FLAT.findIndex((d) => stripMd(d.path) === currentDocPath.value);
      return i > 0 ? DOCS_FLAT[i - 1] : void 0;
    });
    const nextDoc = computed(() => {
      const i = DOCS_FLAT.findIndex((d) => stripMd(d.path) === currentDocPath.value);
      return i >= 0 && i < DOCS_FLAT.length - 1 ? DOCS_FLAT[i + 1] : void 0;
    });
    const visibleGroups = computed(() => {
      const q = query.value.trim().toLowerCase();
      if (!q) return DOCS_GROUPS;
      return DOCS_GROUPS.map((g) => ({
        ...g,
        items: g.items.filter(
          (d) => d.title.toLowerCase().includes(q) || d.desc.toLowerCase().includes(q)
        )
      })).filter((g) => g.items.length);
    });
    function stripMd(p) {
      return p.endsWith("/index.md") || p === "index.md" ? p.replace(/index\.md$/, "").replace(/\/$/, "") : p.replace(/\.md$/, "");
    }
    function docUrl(doc) {
      const p = stripMd(doc.path);
      return p === "" ? "/docs" : `/docs/${p}`;
    }
    const md = new MarkdownIt({
      html: false,
      linkify: true,
      breaks: false,
      highlight(code, lang) {
        if (lang && hljs.getLanguage(lang)) {
          try {
            return `<pre class="hljs"><code>${hljs.highlight(code, { language: lang }).value}</code></pre>`;
          } catch {
          }
        }
        return `<pre class="hljs"><code>${md.utils.escapeHtml(code)}</code></pre>`;
      }
    });
    function rewriteHref(href, dir) {
      if (/^(https?:)?\/\//.test(href) || href.startsWith("mailto:")) return { href };
      if (href.startsWith("#")) return { href };
      let h = href;
      if (h.startsWith("/cenkor-admin/")) {
        h = h.slice("/cenkor-admin/".length);
      } else if (h.startsWith("/")) {
        return { href };
      }
      const hashIdx = h.indexOf("#");
      let anchor = "";
      if (hashIdx >= 0) {
        anchor = h.slice(hashIdx);
        h = h.slice(0, hashIdx);
      }
      if (!h) return { href };
      if (h.endsWith(".md")) {
        const parts = dir ? dir.split("/") : [];
        for (const seg of h.split("/")) {
          if (seg === "." || seg === "") continue;
          if (seg === "..") parts.pop();
          else parts.push(seg);
        }
        const resolved = stripMd(parts.join("/"));
        return { href: `${"/landing/"}docs/${resolved}${anchor}` };
      }
      return { dead: true };
    }
    md.renderer.rules.link_open = (tokens, idx, options, env, self) => {
      const token = tokens[idx];
      const raw = token.attrGet("href") || "";
      const r = rewriteHref(raw, env.dir || "");
      if (r.dead) {
        token.attrJoin("class", "docs-dead");
        token.attrSet("title", "该文件在仓库源码里，见 GitHub");
      } else if (r.href) {
        token.attrSet("href", r.href);
      }
      return self.renderToken(tokens, idx, options);
    };
    function renderDoc(source, dir) {
      return md.render(source, { dir });
    }
    async function loadDoc(path) {
      loading.value = true;
      error.value = "";
      rawMd.value = "";
      rendered.value = "";
      try {
        const url = "/landing/docs-content/" + path.split("/").map(encodeURIComponent).join("/") + ".md";
        const res = await fetch(url);
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        rawMd.value = await res.text();
        const dir = path.includes("/") ? path.slice(0, path.lastIndexOf("/")) : "";
        rendered.value = renderDoc(rawMd.value, dir);
      } catch (e) {
        error.value = e instanceof Error ? e.message : String(e);
      } finally {
        loading.value = false;
      }
    }
    useHead({
      title: computed(
        () => currentDoc.value ? `${currentDoc.value.title} - 辰科 Cenkor Admin` : "辰科 Cenkor Admin - 文档中心"
      )
    });
    watch(currentDocPath, (p, old) => {
      if (p === old) return;
      if (p) loadDoc(p);
      window.scrollTo({ top: 0 });
    });
    onMounted(() => {
      if (currentDocPath.value) loadDoc(currentDocPath.value);
    });
    return (_ctx, _push, _parent, _attrs) => {
      const _component_router_link = resolveComponent("router-link");
      _push(`<div${ssrRenderAttrs(mergeProps({ class: "docs-page" }, _attrs))} data-v-eb81c0ae><section class="page-hero" data-v-eb81c0ae><div class="container" data-v-eb81c0ae><div class="page-hero-content" data-v-eb81c0ae><span class="hero-tag" data-v-eb81c0ae>文档中心</span><h1 data-v-eb81c0ae>${ssrInterpolate(currentDoc.value ? currentDoc.value.title : "Cenkor Admin 文档")}</h1><p data-v-eb81c0ae>用户教程 · 模板标签参考 · 二次开发指南</p></div></div></section><section class="section" data-v-eb81c0ae><div class="container" data-v-eb81c0ae><div class="docs-layout" data-v-eb81c0ae><aside class="docs-sidebar" data-v-eb81c0ae><input${ssrRenderAttr("value", query.value)} type="search" class="docs-search" placeholder="搜索文档…" data-v-eb81c0ae><nav class="docs-nav" data-v-eb81c0ae><!--[-->`);
      ssrRenderList(visibleGroups.value, (group) => {
        _push(`<div class="docs-group" data-v-eb81c0ae><div class="docs-group-title" data-v-eb81c0ae>${ssrInterpolate(group.label)}</div><!--[-->`);
        ssrRenderList(group.items, (doc) => {
          _push(ssrRenderComponent(_component_router_link, {
            key: doc.path,
            to: docUrl(doc),
            class: ["docs-item", { active: currentDocPath.value === doc.path }]
          }, {
            default: withCtx((_, _push2, _parent2, _scopeId) => {
              if (_push2) {
                _push2(`${ssrInterpolate(doc.title)}`);
              } else {
                return [
                  createTextVNode(toDisplayString(doc.title), 1)
                ];
              }
            }),
            _: 2
          }, _parent));
        });
        _push(`<!--]--></div>`);
      });
      _push(`<!--]-->`);
      if (!visibleGroups.value.length) {
        _push(`<p class="docs-empty" data-v-eb81c0ae>没有匹配的文档</p>`);
      } else {
        _push(`<!---->`);
      }
      _push(`</nav></aside><article class="docs-article" data-v-eb81c0ae>`);
      if (!currentDocPath.value) {
        _push(`<!--[-->`);
        ssrRenderList(visibleGroups.value, (group) => {
          _push(`<div class="docs-card-group" data-v-eb81c0ae><h2 class="docs-card-group-title" data-v-eb81c0ae>${ssrInterpolate(group.label)}</h2><div class="docs-cards" data-v-eb81c0ae><!--[-->`);
          ssrRenderList(group.items, (doc) => {
            _push(ssrRenderComponent(_component_router_link, {
              key: doc.path,
              to: docUrl(doc),
              class: "doc-card"
            }, {
              default: withCtx((_, _push2, _parent2, _scopeId) => {
                if (_push2) {
                  _push2(`<h3 data-v-eb81c0ae${_scopeId}>${ssrInterpolate(doc.title)}</h3>`);
                  if (doc.desc) {
                    _push2(`<p data-v-eb81c0ae${_scopeId}>${ssrInterpolate(doc.desc)}</p>`);
                  } else {
                    _push2(`<!---->`);
                  }
                } else {
                  return [
                    createVNode("h3", null, toDisplayString(doc.title), 1),
                    doc.desc ? (openBlock(), createBlock("p", { key: 0 }, toDisplayString(doc.desc), 1)) : createCommentVNode("", true)
                  ];
                }
              }),
              _: 2
            }, _parent));
          });
          _push(`<!--]--></div></div>`);
        });
        _push(`<!--]-->`);
      } else {
        _push(`<!--[-->`);
        if (loading.value) {
          _push(`<p class="docs-state" data-v-eb81c0ae>加载中…</p>`);
        } else if (error.value) {
          _push(`<div class="docs-state docs-error" data-v-eb81c0ae><p data-v-eb81c0ae>文档加载失败（${ssrInterpolate(error.value)}）。</p>`);
          _push(ssrRenderComponent(_component_router_link, {
            to: "/docs",
            class: "btn btn-secondary btn-small"
          }, {
            default: withCtx((_, _push2, _parent2, _scopeId) => {
              if (_push2) {
                _push2(`返回文档中心`);
              } else {
                return [
                  createTextVNode("返回文档中心")
                ];
              }
            }),
            _: 1
          }, _parent));
          _push(`</div>`);
        } else {
          _push(`<!--[--><div class="markdown-body" data-v-eb81c0ae>${rendered.value ?? ""}</div><div class="docs-pager" data-v-eb81c0ae>`);
          if (prevDoc.value) {
            _push(ssrRenderComponent(_component_router_link, {
              to: docUrl(prevDoc.value),
              class: "docs-pager-link"
            }, {
              default: withCtx((_, _push2, _parent2, _scopeId) => {
                if (_push2) {
                  _push2(`<span data-v-eb81c0ae${_scopeId}>上一篇</span>${ssrInterpolate(prevDoc.value.title)}`);
                } else {
                  return [
                    createVNode("span", null, "上一篇"),
                    createTextVNode(toDisplayString(prevDoc.value.title), 1)
                  ];
                }
              }),
              _: 1
            }, _parent));
          } else {
            _push(`<span data-v-eb81c0ae></span>`);
          }
          if (nextDoc.value) {
            _push(ssrRenderComponent(_component_router_link, {
              to: docUrl(nextDoc.value),
              class: "docs-pager-link next"
            }, {
              default: withCtx((_, _push2, _parent2, _scopeId) => {
                if (_push2) {
                  _push2(`<span data-v-eb81c0ae${_scopeId}>下一篇</span>${ssrInterpolate(nextDoc.value.title)}`);
                } else {
                  return [
                    createVNode("span", null, "下一篇"),
                    createTextVNode(toDisplayString(nextDoc.value.title), 1)
                  ];
                }
              }),
              _: 1
            }, _parent));
          } else {
            _push(`<!---->`);
          }
          _push(`</div><!--]-->`);
        }
        _push(`<!--]-->`);
      }
      _push(`</article></div></div></section></div>`);
    };
  }
});
const _sfc_setup = _sfc_main.setup;
_sfc_main.setup = (props, ctx) => {
  const ssrContext = useSSRContext();
  (ssrContext.modules || (ssrContext.modules = /* @__PURE__ */ new Set())).add("src/views/docs/DocsCenter.vue");
  return _sfc_setup ? _sfc_setup(props, ctx) : void 0;
};
const DocsCenter = /* @__PURE__ */ _export_sfc(_sfc_main, [["__scopeId", "data-v-eb81c0ae"]]);
export {
  DocsCenter as default
};
