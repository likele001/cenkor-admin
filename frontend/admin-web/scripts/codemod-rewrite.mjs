#!/usr/bin/env node
/**
 * codemod-rewrite.mjs v3 - 阶段 A4b 自动重写 .vue 文件
 *
 * 策略 (保守, 安全):
 *   - <template> 文本节点:   纯中文段 -> {{ t('key') }}
 *   - <template> 静态属性:   "中文" 整段 -> t('key')  (跳过含 { } 插值的)
 *   - <script> 字符串字面量:  '中文' "中文" 整段 -> t('key')  (跳过含 ${}/+连接的)
 *
 * 跳过 (不处理):
 *   - 含 JS 插值/拼接的字符串
 *   - 已存在的 t() 调用
 *   - 注释、import 路径
 *   - class/style 属性
 */
import fs from 'node:fs'
import path from 'node:path'
import url from 'node:url'

const __dirname = path.dirname(url.fileURLToPath(import.meta.url))
const ROOT = path.resolve(__dirname, '..')
const SRC_VIEWS = path.join(ROOT, 'src/views')
const LOCALES_DIR = path.join(ROOT, 'src/locales')
const EXTRACTED_DIR = path.join(LOCALES_DIR, '_extracted')

const args = process.argv.slice(2)
const APPLY = args.includes('--apply')
const TARGET = (args.find((a) => a.startsWith('--vue=')) || '').slice(6) || null

// ============================================================
// 1) 反向索引
// ============================================================

const cnToKey = new Map()
const seenSlugs = new Set()
for (const file of fs.readdirSync(EXTRACTED_DIR)) {
  if (!file.endsWith('.json') || file.startsWith('_index')) continue
  const namespace = file.replace('.json', '')
  const data = JSON.parse(fs.readFileSync(path.join(EXTRACTED_DIR, file), 'utf8'))
  for (const [slugKey, cnText] of Object.entries(data)) {
    cnToKey.set(cnText, `${namespace}.${slugKey}`)
    seenSlugs.add(slugKey)
  }
}

const pySeg = {
  加载中: 'loading', 加载失败: 'loadFailed', 保存成功: 'saveSuccess',
  保存失败: 'saveFailed', 保存中: 'saving', 确认: 'confirm', 取消: 'cancel',
  提交: 'submit', 删除: 'delete', 编辑: 'edit', 创建: 'create', 更新: 'update',
  搜索: 'search', 重置: 'reset', 返回: 'back', 下一步: 'next', 上一步: 'prev',
  关闭: 'close', 打开: 'open', 启用: 'enable', 禁用: 'disable', 导出: 'export',
  导入: 'import', 上传: 'upload', 下载: 'download', 发布: 'publish', 下线: 'archive',
  草稿: 'draft', 已发布: 'published', 已归档: 'archived', 状态: 'status',
  类型: 'type', 名称: 'name', 描述: 'description', 创建时间: 'createdAt',
  更新时间: 'updatedAt', 操作: 'actions', 首页: 'home', 产品: 'products',
  案例: 'cases', 新闻: 'news', 登录: 'login', 注册: 'register', 退出: 'logout',
  个人中心: 'profile', 忘记密码: 'forgotPassword', 重置密码: 'resetPassword',
  欢迎: 'welcome', 分类: 'category', 标签: 'tags', 用户: 'user',
  角色: 'role', 菜单: 'menu', 应用: 'app', 权限: 'permission', 成功: 'success',
  失败: 'failed', 错误: 'error', 警告: 'warning', 确定: 'ok', 是: 'yes',
  否: 'no', 时间: 'time', 日期: 'date', 内容: 'content', 标题: 'title',
  图标: 'icon', 链接: 'link', 图片: 'image', 文件: 'file', 字段: 'field',
  值: 'value', 配置: 'config', 系统: 'system', 设置: 'settings',
  管理: 'manage', 列表: 'list', 详情: 'detail', 新增: 'add', 移除: 'remove',
  复制: 'copy', 全部: 'all',
}

function fallbackSlug(text) {
  let s = text.replace(/[^\u4e00-\u9fffA-Za-z0-9_]/g, '').slice(0, 24)
  if (!s) s = 'text'
  let candidate = s
  let n = 2
  while (seenSlugs.has(candidate)) candidate = `${s}${n++}`
  seenSlugs.add(candidate)
  return candidate
}

function newKey(namespace, cnText) {
  const seg = pySeg[cnText]
  let slug = seg
  if (!slug || seenSlugs.has(slug)) slug = fallbackSlug(cnText)
  seenSlugs.add(slug)
  return `${namespace}.${slug}`
}

// ============================================================
// 2) 解析 <script> 和 <template>
// ============================================================

function splitRegions(content) {
  const regions = []
  const re = /<script\b[^>]*>[\s\S]*?<\/script>/g
  let m
  let cursor = 0
  while ((m = re.exec(content)) !== null) {
    if (m.index > cursor) regions.push({ kind: 'template', start: cursor, end: m.index })
    regions.push({ kind: 'script', start: m.index, end: m.index + m[0].length })
    cursor = m.index + m[0].length
  }
  if (cursor < content.length) regions.push({ kind: 'template', start: cursor, end: content.length })
  return regions
}

// ============================================================
// 3) <script> 中扫描 "纯中文" 字符串字面量
// ============================================================
//
// 只处理: '纯中文' 或 "纯中文" 或 `纯中文` 整段是中文
// 跳过: 含 ${} 含 + 的含拼接的

function findScriptPureStringMatches(body, bodyStart) {
  const matches = []
  // 扫描 '...' "..." (跳过 template literal 避免 ${} 干扰)
  const re = /(['"])((?:\\.|(?!\1)[\s\S])*?)\1/g
  let m
  while ((m = re.exec(body)) !== null) {
    const quote = m[1]
    const strContent = m[2]
    // 必须几乎全是中文（允许少量 ASCII 标点）
    const cnCount = (strContent.match(/[\u4e00-\u9fff]/g) || []).length
    const total = strContent.replace(/\s/g, '').length
    if (total === 0 || cnCount === 0) continue
    if (cnCount / total < 0.5) continue  // 中文占比 < 50% 跳过
    if (total > 80) continue
    // 跳过空字符串
    if (!strContent.trim()) continue
    // 跳过已经在 t() 调用里的字符串（包括 t('key', '默认值') 的第二参数）
    const lookback = body.slice(Math.max(0, m.index - 300), m.index)
    // 检查前一个引号之前是否有 t(
    if (/\bt\s*\(\s*['"`][^'"`]*['"`]\s*,\s*$/.test(lookback)) continue
    matches.push({
      strStart: bodyStart + m.index + 1,
      strEnd: bodyStart + m.index + 1 + strContent.length,
      text: strContent,
      outerQuote: quote,
    })
  }
  return matches
}

// ============================================================
// 4) <template> 文本节点
// ============================================================

function findTemplateTextMatches(content, startOffset) {
  const matches = []
  const re = />([^<]+)</g
  let m
  while ((m = re.exec(content)) !== null) {
    const text = m[1]
    const trimmed = text.trim()
    if (!trimmed) continue
    const cnCount = (trimmed.match(/[\u4e00-\u9fff]/g) || []).length
    if (cnCount === 0) continue
    if (/[{<]/.test(trimmed)) continue
    if (/<[a-z]/.test(trimmed)) continue
    if (/\n/.test(trimmed)) continue
    // 跳过 attribute 值内的中文（"..." 里含 HTML）
    // 数从 m.index 往前 200 内的 " 字符数, 奇数表示我们在某个 attr="..." 内
    const before = content.slice(Math.max(0, m.index - 200), m.index)
    // 计算引号配对: 找 attr="..." 模式, 跳过包含在 ="" 内的
    const attrOpenRe = /="[^"]*$/g
    let inAttr = false
    let am
    while ((am = attrOpenRe.exec(before)) !== null) {
      inAttr = true
      break
    }
    if (inAttr) continue
    matches.push({
      textStart: startOffset + m.index + 1 + (text.length - text.trimStart().length),
      textEnd: startOffset + m.index + 1 + text.trimEnd().length,
      text: trimmed,
    })
  }
  return matches
}

// ============================================================
// 5) <template> 静态属性字符串
// ============================================================

function findTemplateAttrMatches(content, startOffset) {
  const matches = []
  // 匹配:   attr="..."   或   :attr="..."   (跳过 v-bind, 跳过 class/style)
  // lookbehind 排除 : - @ . 等, 避免匹配 :action-label 中的 label 部分
  const re = /(?<![:.@a-zA-Z-])([a-zA-Z][a-zA-Z0-9_:-]*)="([^"]*[\u4e00-\u9fff][^"]*)"/g
  let m
  while ((m = re.exec(content)) !== null) {
    const attrName = m[1]
    if (attrName === 'class' || attrName === 'style') continue
    if (attrName.startsWith(':') || attrName.startsWith('v-bind:')) continue
    if (attrName.startsWith('v-')) continue  // v-if="..." 等不动
    const val = m[2]
    // 只处理: 纯中文（允许标点）
    const cnCount = (val.match(/[\u4e00-\u9fff]/g) || []).length
    if (cnCount === 0) continue
    if (val.length > 80) continue
    // 跳过 :title 等动态属性的复杂表达式 (本次先只处理 attr="纯中文")
    matches.push({
      attrStart: startOffset + m.index + m[0].indexOf('"') + 1,
      attrEnd: startOffset + m.index + m[0].lastIndexOf('"'),
      attrName,
      val,
    })
  }
  return matches
}

// ============================================================
// 6) 重写
// ============================================================

function namespaceFromPath(filePath) {
  const rel = path.relative(SRC_VIEWS, filePath)
  const parts = rel.split(path.sep)
  if (parts.length === 1) {
    return parts[0].replace(/View\.vue$|Page\.vue$/, '').replace(/^./, (c) => c.toLowerCase())
  }
  return parts[parts.length - 1].replace(/View\.vue$|Page\.vue$/, '').replace(/^./, (c) => c.toLowerCase())
}

function rewriteFile(filePath) {
  const orig = fs.readFileSync(filePath, 'utf8')
  const namespace = namespaceFromPath(filePath)
  const newKeys = []
  const edits = []

  const regions = splitRegions(orig)

  for (const r of regions) {
    if (r.kind === 'script') {
      const block = orig.slice(r.start, r.end)
      const bodyMatch = block.match(/<script\b[^>]*>([\s\S]*?)<\/script>/)
      if (!bodyMatch) continue
      const body = bodyMatch[1]
      const bodyOffset = r.start + block.indexOf(body)
      const matches = findScriptPureStringMatches(body, bodyOffset)
      for (const m of matches) {
        let key
        if (cnToKey.has(m.text)) key = cnToKey.get(m.text)
        else {
          key = newKey(namespace, m.text)
          cnToKey.set(m.text, key)
          newKeys.push({ key, cn: m.text })
        }
        // 如果原字符串用单引号包裹，t() 内必须用双引号（反之亦然）
        const innerQuote = m.outerQuote === "'" ? '"' : "'"
        edits.push({ start: m.strStart, end: m.strEnd, replacement: `t(${innerQuote}${key}${innerQuote})` })
      }
    } else if (r.kind === 'template') {
      const tpl = orig.slice(r.start, r.end)
      const tplStart = r.start
      for (const m of findTemplateTextMatches(tpl, tplStart)) {
        let key
        if (cnToKey.has(m.text)) key = cnToKey.get(m.text)
        else {
          key = newKey(namespace, m.text)
          cnToKey.set(m.text, key)
          newKeys.push({ key, cn: m.text })
        }
        edits.push({ start: m.textStart, end: m.textEnd, replacement: `{{ t('${key}') }}` })
      }
      for (const m of findTemplateAttrMatches(tpl, tplStart)) {
        // 跳过动态属性中含复杂表达式的（已经是 :attr="..." 我们之前的正则不会匹配这些）
        // 这里 m.val 应该是纯中文 (静态 attr="中文")
        if (!cnToKey.has(m.val) && !/[\u4e00-\u9fff]/.test(m.val)) continue
        let key
        if (cnToKey.has(m.val)) key = cnToKey.get(m.val)
        else {
          key = newKey(namespace, m.val)
          cnToKey.set(m.val, key)
          newKeys.push({ key, cn: m.val })
        }
        // 模板静态属性里的中文 -> :attr="t('key')" 形式（Vue 兼容）
        edits.push({
          start: m.attrStart - m.attrName.length - 2,  // 包含 attr="..." 整个
          end: m.attrEnd + 1,
          replacement: `:${m.attrName}="t('${key}')"`,
        })
      }
    }
  }

  if (edits.length === 0) return { file: filePath, changed: false, newKeys: [] }

  // 排序去重（按 start 升序，去掉重叠）
  edits.sort((a, b) => a.start - b.start)
  const merged = []
  for (const e of edits) {
    if (merged.length && merged[merged.length - 1].end > e.start) continue  // 跳过重叠
    merged.push(e)
  }

  let newContent = orig
  for (let i = merged.length - 1; i >= 0; i--) {
    const e = merged[i]
    newContent = newContent.slice(0, e.start) + e.replacement + newContent.slice(e.end)
  }

  // 加 useI18n
  if (!newContent.includes('useI18n') && newContent.includes("t('")) {
    if (newContent.match(/<script setup[^>]*>/)) {
      newContent = newContent.replace(
        /(<script setup[^>]*>)/,
        `$1\nimport { useI18n } from 'vue-i18n'\nconst { t } = useI18n()`,
      )
    }
  }

  if (newContent !== orig) {
    if (APPLY) fs.writeFileSync(filePath, newContent)
    return { file: filePath, changed: true, newKeys, dryRun: !APPLY }
  }
  return { file: filePath, changed: false, newKeys: [] }
}

function walk(dir, files = []) {
  for (const f of fs.readdirSync(dir)) {
    const p = path.join(dir, f)
    if (fs.statSync(p).isDirectory()) walk(p, files)
    else if (f.endsWith('.vue')) files.push(p)
  }
  return files
}

let files
if (TARGET) files = [path.resolve(TARGET)]
else files = walk(SRC_VIEWS)

const results = []
for (const f of files) results.push(rewriteFile(f))

// 合并 new keys
const allNewKeys = []
for (const r of results) for (const k of r.newKeys || []) allNewKeys.push(k)
if (allNewKeys.length) {
  for (const lang of ['zh-CN', 'en-US']) {
    const p = path.join(LOCALES_DIR, lang, 'common.json')
    const data = JSON.parse(fs.readFileSync(p, 'utf8'))
    for (const { key, cn } of allNewKeys) {
      const [ns, k] = key.split('.')
      if (!data[ns]) data[ns] = {}
      if (!data[ns][k]) data[ns][k] = cn
    }
    if (APPLY) fs.writeFileSync(p, JSON.stringify(data, null, 2) + '\n')
  }
}

const changed = results.filter((r) => r.changed)
console.log(
  `${APPLY ? '✅ APPLIED' : '🔍 DRY-RUN'}: ${changed.length}/${results.length} files would change, ${allNewKeys.length} new keys merged`,
)
for (const r of changed.slice(0, 10)) {
  console.log(`  - ${path.relative(ROOT, r.file)}: +${(r.newKeys || []).length} new keys`)
}
if (changed.length > 10) console.log(`  ... and ${changed.length - 10} more`)