/**
 * 生成官网的 llms.txt（给 AI 爬虫的站点索引）。
 *
 * 为什么需要：/landing/llms.txt 此前不存在，nginx 的 SPA fallback 会返回
 * index.html（Content-Type: text/html），爬虫把 HTML 当 llms.txt 解析必然失败。
 * 现在产出真实文件：public/ → dist → frontend/landing/，并在 nginx 加精确匹配。
 *
 * 数据来源（不手写，避免漂移）：
 *   - 官网页面：src/config/seo.ts 的 SEO 表（title / description）
 *   - 文档中心：public/docs-content/ 下实际的 .md 文件 + docs-manifest 的 title
 *
 * 用法：node scripts/gen-llms-txt.mjs
 * 产物：public/llms.txt
 */
import { readFileSync, writeFileSync, existsSync, readdirSync, statSync } from 'node:fs'
import { join, dirname, relative } from 'node:path'
import { fileURLToPath } from 'node:url'

const WEB_ROOT = join(dirname(fileURLToPath(import.meta.url)), '..')
const SEO = join(WEB_ROOT, 'src/config/seo.ts')
const MANIFEST = join(WEB_ROOT, 'src/config/docs-manifest.generated.ts')
const DOCS_DIR = join(WEB_ROOT, 'public/docs-content')
const OUT = join(WEB_ROOT, 'public/llms.txt')

const SITE = 'https://admin.cenkor.cn'
const LANDING = `${SITE}/landing`
const DOCS = `${LANDING}/docs-content`

/**
 * 从 seo.ts 抽取 SEO 表。
 *
 * 不能简单正则整块抓 `'/x': { ... }`：description 存在跨行字符串拼接
 * （`'...' + '...'`），块匹配会截断。改为按行状态机：
 * 遇到 `'/path': {` 记下 key，之后累积 title / description 直到下一个 key。
 */
function parseSeo(src) {
  const lines = src.split('\n')
  const out = []
  let cur = null
  let field = null // 当前正在累积的字段：'title' | 'desc'

  const flush = () => {
    if (cur && cur.title) {
      out.push({
        path: cur.path,
        title: cur.title.replace(/\s+/g, ' ').trim(),
        desc: (cur.desc || '').replace(/\s+/g, ' ').trim()
      })
    }
    cur = null
    field = null
  }

  for (const raw of lines) {
    const line = raw.trim()

    // 新条目：'/path': {
    const mKey = line.match(/^['"](\/[a-z0-9/-]*)['"]\s*:\s*\{/)
    if (mKey) {
      flush()
      cur = { path: mKey[1], title: '', desc: '' }
      continue
    }
    if (!cur) continue

    if (/^title\s*:/.test(line)) { field = 'title'; }
    else if (/^description\s*:/.test(line)) { field = 'desc'; }

    // 抽取本行所有单/双引号字符串字面量，拼到当前字段
    if (field) {
      const strs = [...line.matchAll(/'([^']*)'|"([^"]*)"/g)].map((x) => x[1] ?? x[2] ?? '')
      if (strs.length) {
        const joined = strs.join(' ')
        if (field === 'title') cur.title += joined
        else cur.desc += joined
      }
      // 行尾有 `},` 或 `,` 表示该字段结束
      if (/^},?\s*$/.test(line) || /^}\s*$/.test(line)) flush()
    }
  }
  flush()
  return out
}

/** 文档中心：读 manifest 的 title，配 public/docs-content 里实际存在的文件。 */
function parseDocs() {
  if (!existsSync(MANIFEST)) return []
  const src = readFileSync(MANIFEST, 'utf-8')
  // ⚠️ manifest 里 DOCS_GROUPS 和 DOCS_FLAT 是同一批文档的两份表达
  //    （分组视图 / 扁平视图），整文件正则会把每篇抓两遍。
  //    只解析 DOCS_FLAT 段，它是唯一清单。
  const flatIdx = src.indexOf('export const DOCS_FLAT')
  const seg = flatIdx >= 0 ? src.slice(flatIdx) : src
  const entries = []
  const re = /"path":\s*"([^"]+)"\s*,\s*\n\s*"title":\s*"([^"]*)"/g
  let m
  while ((m = re.exec(seg)) !== null) {
    const rel = m[1]
    // 只收录真实存在的文件，避免清单里有过期条目
    if (!existsSync(join(DOCS_DIR, rel))) continue
    entries.push({ path: rel, title: m[2].replace(/\\"/g, '"') })
  }
  return entries
}

const seoSrc = existsSync(SEO) ? readFileSync(SEO, 'utf-8') : ''
const pages = parseSeo(seoSrc)
const docs = parseDocs()

if (!pages.length) {
  console.error('✗ 未能从 seo.ts 解析出任何页面，拒绝生成空的 llms.txt')
  console.error('  检查 src/config/seo.ts 里 SEO 表的结构是否变化')
  process.exit(1)
}

const date = new Date().toISOString().slice(0, 10)
const lines = [
  '# 辰科 Cenkor Admin',
  '',
  '> 企业级后台管理平台：FastAPI + Vue3，内置应用中心、RBAC 权限、通用内容引擎、',
  '> 用户中心与审计日志；应用按需安装，支持私有化部署与 AI CMS。',
  '',
  `- 官网：${LANDING}/`,
  // ⚠️ 文档中心是 landing 的「文件路由」docs.html，不是目录：
  //    `/landing/docs`  → 200（try_files 命中 docs.html）
  //    `/landing/docs/` → 403（被当成目录，实际无 index.html）
  //    尾斜杠会让 AI 爬虫拿到 403，这里必须不带
  `- 文档中心：${LANDING}/docs`,
  // ⚠️ 原始 Markdown（docs-content/*.md）按篇列在下方「技术文档中心」，
  //    但**不要**给目录 URL：目录无索引文件，nginx 直接 403。要放只能放具体 .md。
  '- 语言：zh-CN',
  `- 更新：${date}`,
  '',
  '## 官网页面',
  ''
]

for (const p of pages) {
  const url = p.path === '/' ? `${LANDING}/` : `${LANDING}${p.path}`
  lines.push(`- [${p.title}](${url})${p.desc ? '：' + p.desc : ''}`)
}

if (docs.length) {
  lines.push('', '## 技术文档中心', '', `共 ${docs.length} 篇：`, '')
  // 按目录分组，根级在前
  const byDir = new Map()
  for (const d of docs) {
    const dir = d.path.includes('/') ? d.path.slice(0, d.path.lastIndexOf('/')) : ''
    if (!byDir.has(dir)) byDir.set(dir, [])
    byDir.get(dir).push(d)
  }
  const dirs = [...byDir.keys()].sort((a, b) => (a === '' ? -1 : b === '' ? 1 : a.localeCompare(b)))
  for (const dir of dirs) {
    if (dir) lines.push(`### ${dir}`, '')
    for (const d of byDir.get(dir)) {
      lines.push(`- [${d.title}](${DOCS}/${d.path})`)
    }
    lines.push('')
  }
}

lines.push('')
writeFileSync(OUT, lines.join('\n'), 'utf-8')
console.log(`[llms.txt] 已生成：${pages.length} 个官网页面 + ${docs.length} 篇文档 → public/llms.txt`)
if (docs.length === 0) {
  console.warn('  ⚠️ 文档中心为空（public/docs-content 不存在或无匹配），仅输出了官网页面')
}