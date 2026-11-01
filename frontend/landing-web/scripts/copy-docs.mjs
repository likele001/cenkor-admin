#!/usr/bin/env node
/**
 * 文档中心数据同步：仓库 docs/ → landing-web
 *
 *   docs 下的全部 .md →  public/docs-content/   （vite 构建时原样带进 dist，线上可 fetch）
 *                     →  src/config/docs-manifest.generated.ts（目录清单，构建期 import，SSR 可用）
 *
 * 为什么不直接 import 仓库 docs/：
 *   vite 的 glob 对项目外目录的 dev/server 行为不可靠，且 public/ 是最省心的静态下发方式；
 *   manifest 生成成 .ts 而不是 .json，是为了免掉 tsconfig 的 resolveJsonModule 和类型体操。
 *
 * 排除：archive/（历史归档）、*.bak*、隐藏文件。
 * 重复执行安全：每次全量重建 public/docs-content 与 manifest。
 */
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const __dirname = path.dirname(fileURLToPath(import.meta.url))
const WEB_ROOT = path.resolve(__dirname, '..')
const REPO_ROOT = path.resolve(WEB_ROOT, '..', '..')
const SRC = path.join(REPO_ROOT, 'docs')
const DEST = path.join(WEB_ROOT, 'public', 'docs-content')
const MANIFEST_TS = path.join(WEB_ROOT, 'src', 'config', 'docs-manifest.generated.ts')

// 侧栏分组显示名；未登记的目录直接显示原目录名
const DIR_LABELS = {
  '05-用户手册': '用户手册',
  template: '模板标签参考',
  apps: '应用开发',
  addons: '插件与扩展',
  release: '发布记录'
}
const ROOT_LABEL = '总览与指南'
const EXCLUDE_DIRS = new Set(['archive', '_bak'])

function walk(dir, base) {
  const out = []
  for (const name of fs.readdirSync(dir).sort()) {
    if (name.startsWith('.') || name.endsWith('.bak') || name.includes('.bak-')) continue
    const full = path.join(dir, name)
    const rel = path.join(base, name)
    const st = fs.statSync(full)
    if (st.isDirectory()) {
      if (EXCLUDE_DIRS.has(name)) continue
      out.push(...walk(full, rel))
    } else if (name.endsWith('.md')) {
      out.push(rel)
    }
  }
  return out
}

/** 从 md 提取标题与首段描述 */
function metaOf(rel) {
  const text = fs.readFileSync(path.join(SRC, rel), 'utf-8')
  const lines = text.split('\n')
  let title = ''
  let desc = ''
  for (const line of lines.slice(0, 40)) {
    const t = line.trim()
    if (!title && t.startsWith('# ') && !t.startsWith('#!')) {
      title = t.replace(/^#\s+/, '').trim()
      continue
    }
    if (title && !desc && t && !t.startsWith('#') && !t.startsWith('|') && !t.startsWith('```')
      && !t.startsWith('<') && !t.startsWith('![')) {
      desc = t.replace(/[*_`>[\]()#]/g, '').replace(/\s+/g, ' ').trim().slice(0, 80)
      break
    }
  }
  if (!title) title = path.basename(rel, '.md')
  return { title, desc }
}

if (!fs.existsSync(SRC)) {
  console.error(`✗ 找不到文档源目录: ${SRC}`)
  process.exit(1)
}

const files = walk(SRC, '')
if (!files.length) {
  console.error('✗ docs/ 下没有任何 .md，拒绝生成空目录')
  process.exit(1)
}

fs.rmSync(DEST, { recursive: true, force: true })
fs.mkdirSync(DEST, { recursive: true })

const manifest = []
for (const rel of files) {
  const norm = rel.split(path.sep).join('/')
  fs.mkdirSync(path.dirname(path.join(DEST, norm)), { recursive: true })
  fs.copyFileSync(path.join(SRC, rel), path.join(DEST, norm))
  const { title, desc } = metaOf(rel)
  const dir = norm.includes('/') ? norm.slice(0, norm.lastIndexOf('/')) : ''
  manifest.push({ path: norm, title, desc, dir })
}

// 分组：根级在前，其余按显示名排序
const groups = []
const byDir = new Map()
for (const doc of manifest) {
  const key = doc.dir
  if (!byDir.has(key)) byDir.set(key, [])
  byDir.get(key).push(doc)
}
const dirKeys = [...byDir.keys()].sort((a, b) => {
  if (a === '') return -1
  if (b === '') return 1
  return (DIR_LABELS[a] ?? a).localeCompare(DIR_LABELS[b] ?? b, 'zh-CN')
})
for (const key of dirKeys) {
  const items = byDir.get(key).sort((a, b) => a.path.localeCompare(b.path, 'zh-CN'))
  groups.push({ key, label: key === '' ? ROOT_LABEL : (DIR_LABELS[key] ?? key), items })
}

fs.writeFileSync(
  MANIFEST_TS,
  `// ⚠️ 本文件由 scripts/copy-docs.mjs 生成，不要手改；重跑构建即可更新。\n`
  + `// 数据源：仓库 docs/（${files.length} 份，生成时间见 git log）。\n\n`
  + `export interface DocMeta {\n  path: string\n  title: string\n  desc: string\n  dir: string\n}\n\n`
  + `export interface DocGroup {\n  key: string\n  label: string\n  items: DocMeta[]\n}\n\n`
  + `export const DOCS_GROUPS: DocGroup[] = ${JSON.stringify(groups, null, 2)}\n\n`
  + `export const DOCS_FLAT: DocMeta[] = ${JSON.stringify(manifest, null, 2)}\n`,
  'utf-8'
)

console.log(`✓ 文档同步完成：${files.length} 份 md → public/docs-content/，manifest → src/config/docs-manifest.generated.ts`)
for (const g of groups) console.log(`    ${g.label}: ${g.items.length} 份`)
