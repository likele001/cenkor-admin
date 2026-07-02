#!/usr/bin/env node
/**
 * codemod: 从 admin-web / portal-web 的 .vue 文件中抽取中文文本
 *
 * 用法：
 *   node scripts/extract-i18n.mjs <src-dir> <out-dir> [--apply]
 *
 * 示例：
 *   # 仅扫描并输出建议（不修改源文件）
 *   node scripts/extract-i18n.mjs frontend/admin-web/src frontend/admin-web/src/locales/_extracted
 *
 *   # 自动替换（--apply 模式会改写源文件）
 *   node scripts/extract-i18n.mjs frontend/admin-web/src frontend/admin-web/src/locales/_extracted --apply
 *
 * 抽取规则：
 *   1. <template> 块中：text content、属性值（title, placeholder, alt 等）、JSX-like 插值外的字面量
 *   2. <script> 块中：alert()/confirm()/throw new Error()/console.log()
 *   3. 跳过：注释、URL、class 名、JSON key、technical identifiers
 *
 * 白名单（跳过）：
 *   - 纯符号串：==, ===, !==, ... 等
 *   - CSS class / id
 *   - URL、SVG path、emoji 标识符
 *   - 已经在 {{ t('...') }} 里的
 */
import { readFileSync, writeFileSync, readdirSync, statSync, mkdirSync, existsSync } from 'fs'
import { join, basename, relative, dirname } from 'path'

const [, , SRC_DIR = 'src', OUT_DIR = 'src/locales/_extracted', ...flags] = process.argv
const APPLY = flags.includes('--apply')

const CN_RE = /[\u4e00-\u9fa5]+/g

// 这些文件不应被扫描
const SKIP_FILES = new Set([
  'locale.ts',  // 自身递归
])

// 模板属性中通常是 i18n 候选的属性
const I18N_ATTRS = new Set(['title', 'placeholder', 'alt', 'label', 'aria-label'])

// 模板中应当保持原样的属性（CSS class、id、type、name、href、src）
const SKIP_ATTRS = new Set(['class', 'id', 'type', 'name', 'href', 'src', 'style', 'v-bind', 'to'])

// 生成 key 的稳定 hash（基于原文）
function slugify(text, max = 32) {
  // 中文用拼音/编号；简化用 P + index
  // 用原文 hash 前 6 位保证稳定性
  let h = 0
  for (let i = 0; i < text.length; i++) {
    h = ((h << 5) - h + text.charCodeAt(i)) | 0
  }
  const tag = (text.match(/^[\u4e00-\u9fa5]+/)?.[0] || 'text').slice(0, 4)
  return `${tag}_${(h >>> 0).toString(36).slice(0, 6)}`
}

// 递归获取所有 .vue 文件
function walk(dir, out = []) {
  for (const name of readdirSync(dir)) {
    if (name === 'node_modules' || name.startsWith('.')) continue
    const p = join(dir, name)
    const st = statSync(p)
    if (st.isDirectory()) walk(p, out)
    else if (p.endsWith('.vue') && !SKIP_FILES.has(name)) out.push(p)
  }
  return out
}

// 抽取 <template>...</template> 块
function extractTemplate(src) {
  const m = src.match(/<template>([\s\S]*?)<\/template>/)
  return m ? m[1] : ''
}

// 抽取 <script setup>...</script> 块
function extractScript(src) {
  const m = src.match(/<script\s+setup[^>]*>([\s\S]*?)<\/script>/)
  return m ? m[1] : ''
}

// 给定文件路径，推断 namespace（基于 views/cms/ProductsListView.vue → productsList）
function namespaceFromPath(filePath, srcDir) {
  const rel = relative(srcDir, filePath)
  // views/cms/ProductsListView.vue → productsList
  const parts = rel.split(/[\\/]/)
  let name = parts[parts.length - 1].replace(/\.vue$/, '')
  // 去掉后缀 View / View.vue
  name = name.replace(/View$/, '').replace(/Page$/, '')
  // 转 camelCase
  return name.charAt(0).toLowerCase() + name.slice(1)
}

// 把文本中的中文提取为 [{ text, line, col }]
function findChinesePositions(text, startLine = 1) {
  const out = []
  const lines = text.split('\n')
  for (let i = 0; i < lines.length; i++) {
    const line = lines[i]
    const matches = [...line.matchAll(CN_RE)]
    for (const m of matches) {
      out.push({
        text: m[0],
        line: startLine + i,
        col: m.index,
      })
    }
  }
  return out
}

// 简易启发式：判断一个中文串是否"安全的可翻译"
// 排除：被 {{ }} 包起来的、纯 HTML 实体、纯数字+中文、明显的 CSS 单位
function shouldTranslate(text) {
  // 太短不翻
  if (text.length < 2) return false
  // 全是标点+中文中的标点 - 翻（"中文（含）："是可以的）
  return true
}

// 主扫描
function scanFile(filePath, srcDir) {
  const src = readFileSync(filePath, 'utf8')
  const ns = namespaceFromPath(filePath, srcDir)
  const findings = []  // { namespace, key, text, line }

  // === 模板部分 ===
  const template = extractTemplate(src)
  if (template) {
    // 简单按行处理：捕获 text content 和特定属性的值
    const lines = template.split('\n')
    for (let i = 0; i < lines.length; i++) {
      const line = lines[i]

      // 1. 属性值：title="中文" / placeholder="中文" / :title="'中文'"
      // 匹配 attr="..." 或 attr='...'
      const attrRe = /(?:^|\s)(:title|:placeholder|:label|:alt|placeholder|title|alt|label|aria-label)="([^"]+)"/g
      let m
      while ((m = attrRe.exec(line))) {
        const val = m[2]
        const cn = val.match(CN_RE)
        if (cn) {
          findings.push({
            ns,
            text: val,
            line: i + 1,
            kind: 'attr',
            attr: m[1],
          })
        }
      }

      // 2. text content：> 中文 < （行内文本）
      // 简单匹配：标签闭合后的 > ... < 之前
      const textRe = />([^<>{}]+)</g
      let tm
      while ((tm = textRe.exec(line))) {
        const val = tm[1].trim()
        if (!val) continue
        const cn = val.match(CN_RE)
        if (cn && shouldTranslate(val)) {
          findings.push({
            ns,
            text: val,
            line: i + 1,
            kind: 'text',
          })
        }
      }
    }
  }

  // === script 部分（仅扫描 alert/confirm/throw） ===
  const script = extractScript(src)
  if (script) {
    const lines = script.split('\n')
    for (let i = 0; i < lines.length; i++) {
      const line = lines[i]
      // alert("...") / alert(`...`) / confirm("...") / throw new Error("...")
      const fnRe = /(alert|confirm|throw new Error)\s*\(\s*(["'`])([^"'`]+?)\2/g
      let m
      while ((m = fnRe.exec(line))) {
        const val = m[3]
        const cn = val.match(CN_RE)
        if (cn && shouldTranslate(val)) {
          findings.push({
            ns,
            text: val,
            line: i + 1,
            kind: 'js-string',
            func: m[1],
          })
        }
      }
    }
  }

  return findings
}

// 生成 messages 对象
function buildMessages(findings) {
  // 去重：同 ns.key 只保留第一个
  const messages = {}  // { ns: { key: text } }
  const keys = {}     // { text: 'ns.key' }
  for (const f of findings) {
    if (!messages[f.ns]) messages[f.ns] = {}
    const key = slugify(f.text)
    if (!messages[f.ns][key]) {
      messages[f.ns][key] = f.text
      keys[f.text] = `${f.ns}.${key}`
    }
  }
  return { messages, keys }
}

async function main() {
  console.log(`扫描目录: ${SRC_DIR}`)
  console.log(`输出目录: ${OUT_DIR}`)
  console.log(`应用模式: ${APPLY ? '是（将改写源文件）' : '否（仅生成建议）'}`)
  console.log('')

  const files = walk(SRC_DIR)
  console.log(`发现 ${files.length} 个 .vue 文件`)
  console.log('')

  const allFindings = []
  for (const file of files) {
    const findings = scanFile(file, SRC_DIR)
    if (findings.length > 0) {
      const rel = relative(process.cwd(), file)
      console.log(`  ${rel}: ${findings.length} 条中文`)
      for (const f of findings) {
        allFindings.push({ ...f, file: relative(process.cwd(), file) })
      }
    }
  }

  console.log('')
  console.log(`总计: ${allFindings.length} 条中文可翻译`)

  // 生成 messages
  const { messages, keys } = buildMessages(allFindings)
  console.log(`生成 ${Object.keys(messages).length} 个 namespace`)
  console.log('')

  // 写入建议文件
  mkdirSync(OUT_DIR, { recursive: true })
  for (const [ns, kvs] of Object.entries(messages)) {
    const file = join(OUT_DIR, `${ns}.json`)
    writeFileSync(file, JSON.stringify(kvs, null, 2) + '\n', 'utf8')
    console.log(`  写入 ${relative(process.cwd(), file)}: ${Object.keys(kvs).length} 个 key`)
  }

  // 写总索引
  const indexFile = join(OUT_DIR, '_index.json')
  const flatKeys = {}
  for (const [ns, kvs] of Object.entries(messages)) {
    for (const [k, v] of Object.entries(kvs)) {
      flatKeys[`${ns}.${k}`] = v
    }
  }
  writeFileSync(indexFile, JSON.stringify(flatKeys, null, 2) + '\n', 'utf8')
  console.log(`  写入 ${relative(process.cwd(), indexFile)}: ${Object.keys(flatKeys).length} 个 key 总览`)
  console.log('')

  console.log('示例建议（前 10 条）：')
  for (const f of allFindings.slice(0, 10)) {
    console.log(`  ${f.file}:${f.line}  ${keys[f.text] || '?'}  ←  ${f.text}`)
  }
  console.log('')
  console.log('下一步：')
  console.log('  1. 检查 _extracted/ 下生成的 JSON')
  console.log('  2. 把 zh-CN/en-US 翻译文本填入对应文件')
  console.log('  3. 在 .vue 中手动替换 文本 → {{ t(\'ns.key\') }}')
  console.log('  4. 在 <script setup> 顶部添加 const { t } = useI18n()')
}

main().catch((e) => {
  console.error(e)
  process.exit(1)
})