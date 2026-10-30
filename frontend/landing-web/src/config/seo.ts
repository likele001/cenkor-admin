/**
 * 全站 SEO 元数据的**唯一来源**。
 *
 * 为什么单独抽出来：
 * - 原先 title / description 硬编码在 5 个 view 各自的 useHead() 里，
 *   而 nginx 对所有路由都回退同一个 index.html 外壳 → 抓取器看到的
 *   4 个页面 title/description 完全相同，易被判重复内容、且无法区分。
 * - 现在 App.vue 统一按当前路由读这里；构建期预渲染脚本（scripts/prerender.mjs）
 *   也读同一份数据来生成 each 路由的静态 HTML head。
 *   一份数据两处使用，不会漂移。
 */

export interface SeoEntry {
  /** <title> */
  title: string
  /** meta[name=description] */
  description: string
  /** 预渲染时是否把该页面渲染进静态 HTML（默认 true） */
  prerender?: boolean
}

/** 站点根（与 vite base `base: '/landing/'` 保持一致，末尾无斜杠） */
export const SITE_BASE = 'https://admin.cenkor.cn/landing'

export interface MetaTag {
  name?: string
  property?: string
  content: string
  /** 兼容 unhead Meta 的扩展属性（data-* 等），vue-tsc 才收得下 */
  [key: string]: string | undefined
}

/**
 * 全站固定、不随路由变化的 head 标签。
 *
 * ⚠️ 必须同时满足两处，否则会出现**重复标签**：
 * - 预渲染时由 scripts/prerender.mjs 写进静态 HTML（爬虫读这一份）
 * - 客户端由 App.vue 的 useHead 重新声明（main.ts 挂载前会移除静态那一份）
 * 只在一处声明 → 客户端会出现两份 canonical/description，Google 见到多个 canonical 会整体忽略。
 */
export const SHARED_META: MetaTag[] = [
  { property: 'og:type', content: 'website' },
  { property: 'og:site_name', content: '辰科 Cenkor Admin' },
  // og:image 必须是绝对 URL、位图格式（SVG 不被微信/微博/Twitter 采用），且 ≥1200x630
  { property: 'og:image', content: `${SITE_BASE}/og-image.png` },
  { property: 'og:image:width', content: '1200' },
  { property: 'og:image:height', content: '630' },
  { property: 'og:image:alt', content: '辰科 Cenkor Admin - 企业级后台管理平台' },
  { property: 'og:locale', content: 'zh_CN' },
  { name: 'twitter:card', content: 'summary_large_image' },
  { name: 'twitter:image', content: `${SITE_BASE}/og-image.png` },
]

/** 客户端挂载前要移除的「预渲染遗留 head 标签」选择器（随后由 unhead 接管重建） */
export const PRERENDERED_HEAD_SELECTOR =
  'meta[name="description"], meta[property^="og:"], meta[name^="twitter:"], link[rel="canonical"]'

/** 路由 path → SEO 元数据 */
export const SEO: Record<string, SeoEntry> = {
  '/': {
    title: '辰科Cenkor Admin - 企业级平台 × AI CMS | 私有化部署',
    description:
      '辰科Cenkor Admin 企业级平台，FastAPI + Vue3 架构，内置应用中心、RBAC 权限、工作流审批、AI CMS 内容引擎、用户中心与审计日志。AI CMS 支持对话式建模、AI 起草翻译、语义检索，内容以 REST / GraphQL / MCP 三协议输出，支持私有化部署。',
  },
  '/ai-cms': {
    title: '辰科Cenkor Admin - AI CMS 内容引擎 | 对话式建模 · AI 起草 · MCP 出口',
    description:
      '辰科 AI CMS：用中文描述业务直接生成内容模型，AI 起草与批量翻译，语义检索带引用溯源，内容健康度体检、选题 Gap 分析、问答式站内搜索、AI 配图与视频、多渠道再分发。内容以 REST / GraphQL / MCP 三种协议供给任意前端与 Agent。',
  },
  '/features': {
    title: '辰科Cenkor Admin - 核心功能 | AI CMS 与应用中心',
    description:
      '辰科Cenkor Admin 核心功能：AI CMS 内容引擎、应用中心（12 个可插拔应用）、RBAC 三级权限、动态建模与多站点、工作流审批、多渠道发布与效果统计、REST / GraphQL / MCP 开放接口、在线升级、私有化部署。',
  },
  '/advantages': {
    title: '辰科Cenkor Admin - 技术优势 | AI 原生内容层',
    description:
      '辰科Cenkor Admin 技术优势：FastAPI + Vue3 现代架构、应用中心生态、动态建模、AI 原生内容层（可选增强）、三协议开放接口、在线升级、前后台双用户体系与三种部署模式。',
  },
  '/deploy': {
    title: '辰科Cenkor Admin - 私有部署 | 企业级平台',
    description:
      '辰科Cenkor Admin 私有化部署指南。Docker Compose、宝塔静态 dist、裸机 systemd 三种模式，PostgreSQL + Redis + MinIO + Backend + Admin + Portal；含 AI 模型接入与在线升级说明。',
  },
  '/docs/guide': {
    title: '辰科Cenkor Admin - 使用指南 | 企业级平台',
    description:
      '辰科Cenkor Admin 使用入门指南：系统登录、应用中心安装、RBAC 权限、AI CMS 建模与内容管理、工作流审批、用户中心快速上手。',
  },
}

/** 规范化路由 path（去掉 hash/query、补前导斜杠、去掉尾部斜杠，根路径保留 '/'） */
export function normalizePath(p: string): string {
  const clean = (p || '/').split(/[?#]/)[0]
  const withSlash = clean.startsWith('/') ? clean : `/${clean}`
  return withSlash.length > 1 ? withSlash.replace(/\/+$/, '') : '/'
}

/** 取某路由的 SEO 元数据；未登记的路径回落到首页 */
export function seoFor(path: string): SeoEntry {
  return SEO[normalizePath(path)] ?? SEO['/']
}

/** 该路由的 canonical / og:url 绝对地址 */
export function canonicalFor(path: string): string {
  const p = normalizePath(path)
  return p === '/' ? `${SITE_BASE}/` : `${SITE_BASE}${p}`
}
