#!/usr/bin/env node
/**
 * 构建期预渲染：把每个路由渲染成带真实正文 + 独立 head 的静态 HTML。
 *
 *   vite build                                  → dist/      （SPA 外壳）
 *   vite build --config vite.config.ssr.ts      → dist-ssr/  （Node 侧渲染器）
 *   node scripts/prerender.mjs                  → dist/*.html（注入正文与 SEO）
 *
 * 产物命名：/ → index.html，/features → features.html，/docs/guide → docs/guide.html
 * 线上 nginx 的 try_files 已补 `$uri.html`，因此 /landing/features 能直接命中文件。
 *
 * ⚠️ 必须在**干净的** vite build 之后运行：脚本要从 dist/index.html 里找
 *    `<!--app-html-->` 注入点，而这个注释在预渲染产物中已被替换掉。
 */
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath, pathToFileURL } from 'node:url'

const __dirname = path.dirname(fileURLToPath(import.meta.url))
const ROOT = path.resolve(__dirname, '..')
const DIST = path.join(ROOT, 'dist')
const SSR_ENTRY = path.join(ROOT, 'dist-ssr', 'entry-server.js')

const APP_SLOT = '<!--app-html-->'
const APP_EMPTY = '<div id="app"></div>'
const SEO_BLOCK = /<!--seo:start-->[\s\S]*?<!--seo:end-->/

const esc = (s) =>
  String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;')

/**
 * 只生成**随路由变化**的那一批标签。
 * 全站固定标签（og:image、twitter:card…）留在 index.html 的 seo 块之外，这里不要重复写，
 * 否则产物里会出现两份 —— 客户端 main.ts 清理时会全部删除再交给 unhead 重建，
 * 但爬虫读到的那份就已经是脏的（多个 canonical/og:image）。
 */
function buildSeoBlock(seo, canonical) {
  const tags = [
    `<title>${esc(seo.title)}</title>`,
    `<meta name="description" content="${esc(seo.description)}" />`,
    `<link rel="canonical" href="${canonical}" />`,
    `<meta property="og:title" content="${esc(seo.title)}" />`,
    `<meta property="og:description" content="${esc(seo.description)}" />`,
    `<meta property="og:url" content="${canonical}" />`,
    `<meta name="twitter:title" content="${esc(seo.title)}" />`,
    `<meta name="twitter:description" content="${esc(seo.description)}" />`
  ]
  return `<!--seo:start-->\n    ${tags.join('\n    ')}\n    <!--seo:end-->`
}

async function main() {
  const templateFile = path.join(DIST, 'index.html')

  if (!fs.existsSync(SSR_ENTRY)) {
    console.error(`✗ 找不到 ${path.relative(ROOT, SSR_ENTRY)}`)
    console.error('  请先执行：vite build --config vite.config.ssr.ts --base=/landing/')
    process.exit(1)
  }
  if (!fs.existsSync(templateFile)) {
    console.error(`✗ 找不到 ${path.relative(ROOT, templateFile)}，请先执行 vite build`)
    process.exit(1)
  }

  const template = fs.readFileSync(templateFile, 'utf-8')

  const hasSlot = template.includes(APP_SLOT)
  const hasEmpty = template.includes(APP_EMPTY)
  if (!hasSlot && !hasEmpty) {
    console.error('✗ dist/index.html 里既没有 <!--app-html--> 也没有空的 <div id="app"></div>。')
    console.error('  说明它已经被预渲染过（或 index.html 被改坏了）。请先重新执行 vite build。')
    process.exit(1)
  }
  if (!SEO_BLOCK.test(template)) {
    console.error('✗ dist/index.html 里找不到 <!--seo:start--> / <!--seo:end--> 标记。')
    process.exit(1)
  }

  const { render, SEO, canonicalFor, normalizePath } = await import(pathToFileURL(SSR_ENTRY).href)

  const routes = Object.entries(SEO).filter(([, seo]) => seo.prerender !== false)
  const rows = []

  for (const [routePath, seo] of routes) {
    const normal = normalizePath(routePath)
    const { html } = await render(normal)
    const canonical = canonicalFor(normal)

    let out = template.replace(SEO_BLOCK, buildSeoBlock(seo, canonical))
    out = out.includes(APP_SLOT)
      ? out.replace(APP_SLOT, html)
      : out.replace(APP_EMPTY, `<div id="app">${html}</div>`)

    const rel = normal === '/' ? 'index.html' : `${normal.replace(/^\//, '')}.html`
    const file = path.join(DIST, rel)
    fs.mkdirSync(path.dirname(file), { recursive: true })
    fs.writeFileSync(file, out, 'utf-8')

    // 正文可见字符数（去标签），用来确认不是空壳
    const text = html.replace(/<[^>]+>/g, ' ').replace(/\s+/g, ' ').trim()
    rows.push({
      route: normal,
      file: rel,
      bytes: Buffer.byteLength(out),
      textLen: text.length,
      titleOk: out.includes(`<title>${seo.title}</title>`),
      bodyPreview: text.slice(0, 60)
    })
  }

  console.log('\n预渲染完成：\n')
  console.log('  路由'.padEnd(16) + '输出文件'.padEnd(22) + 'HTML 大小'.padEnd(12) + '正文字符'.padEnd(10) + 'title')
  console.log('  ' + '-'.repeat(72))
  for (const r of rows) {
    console.log(
      '  ' + r.route.padEnd(16) + r.file.padEnd(22) + `${(r.bytes / 1024).toFixed(1)} KB`.padEnd(12) +
      String(r.textLen).padEnd(10) + (r.titleOk ? '✓' : '✗ 未替换')
    )
  }
  console.log('\n  正文样例：' + rows[1]?.bodyPreview + '…')
  console.log('  提示：SPA 主脚本仍在 body 末尾，浏览器加载后会 hydration 接管。\n')

  if (rows.some((r) => !r.titleOk)) {
    console.error('✗ 有路由的 <title> 未被替换，请检查 src/config/seo.ts 与 index.html 的 seo 标记。')
    process.exit(1)
  }
  if (rows.some((r) => r.textLen < 100)) {
    console.error('✗ 有路由渲染出的正文字符过少，可能是渲染失败（空壳）。')
    process.exit(1)
  }
}

main().catch((err) => {
  console.error('✗ 预渲染失败：')
  console.error(err)
  process.exit(1)
})
