#!/usr/bin/env node
/**
 * codemod-rewrite.mjs v4 — 阶段 A4b 自动重写 .vue 中文字面量为 t() 调用
 *
 * 相对 v3 的修复：
 *   [修复1] 死字符串：v3 只替换引号内部，产出 msg = 't("ns.保存")' 这种死字符串。
 *           v4 整体替换「带引号的字面量」'保存' → t("ns.保存")，引号一起吃掉。
 *   [修复2] 反查索引：v3 只索引 _extracted/<ns>.json 的裸 key，认不出
 *           _index.json 里的带前缀 key，导致重复造键。v4 双源合并索引。
 *   [修复3] 去重作用域：v3 的 seenSlugs 是全局 Set，跨命名空间互相顶掉。
 *           v4 改为 Map<namespace, Set<slug>>。
 *   [修复4] 扫描范围：v3 只扫 src/views。v4 覆盖 src/views + components + layouts。
 *   [修复5] 写回结构：v3 往 common.json 嵌套结构里塞。v4 写回
 *           _extracted/<ns>.json（扁平）并同步重建 _index.json 镜像。
 *
 * 用法：
 *   node scripts/codemod-rewrite.mjs                # dry-run，只报告
 *   node scripts/codemod-rewrite.mjs --apply        # 实际改写
 *   node scripts/codemod-rewrite.mjs --vue=src/x.vue --apply   # 单文件
 */
import fs from 'node:fs'
import path from 'node:path'
import url from 'node:url'

const __dirname = path.dirname(url.fileURLToPath(import.meta.url))
const ROOT = path.resolve(__dirname, '..')
const SRC = path.join(ROOT, 'src')
const LOCALES_DIR = path.join(SRC, 'locales')
const EXTRACTED_DIR = path.join(LOCALES_DIR, '_extracted')
const EN_EXTRACTED_DIR = path.join(LOCALES_DIR, 'en-US', '_extracted')

// 扫描范围（修复4）
const SCAN_DIRS = ['views', 'components', 'layouts'].map((d) => path.join(SRC, d))

const args = process.argv.slice(2)
const APPLY = args.includes('--apply')
const TARGET = (args.find((a) => a.startsWith('--vue=')) || '').slice(6) || null

// ============================================================
// 1) 反查索引（修复2 + 修复3）
// ============================================================

/** 中文文本 -> { namespace -> key }，按命名空间隔离 */
const textIndex = new Map()
/** namespace -> Set<slug>，用于去重（修复3） */
const slugsByNs = new Map()

function addIndex(namespace, slugKey, cnText) {
  if (typeof cnText !== 'string') return
  let m = textIndex.get(cnText)
  if (!m) {
    m = new Map()
    textIndex.set(cnText, m)
  }
  if (!m.has(namespace)) m.set(namespace, `${namespace}.${slugKey}`)

  let s = slugsByNs.get(namespace)
  if (!s) {
    s = new Set()
    slugsByNs.set(namespace, s)
  }
  s.add(slugKey)
}

function loadFlatDir(dir) {
  if (!fs.existsSync(dir)) return
  for (const file of fs.readdirSync(dir)) {
    if (!file.endsWith('.json') || file.startsWith('_index')) continue
    const ns = file.replace('.json', '')
    let data
    try {
      data = JSON.parse(fs.readFileSync(path.join(dir, file), 'utf8'))
    } catch {
      continue
    }
    for (const [k, v] of Object.entries(data)) addIndex(ns, k, v)
  }
}

// 双源：_extracted/<ns>.json（裸 key） + _index.json（带前缀 key）
loadFlatDir(EXTRACTED_DIR)
loadFlatDir(EN_EXTRACTED_DIR)

// _index.json 是带前缀镜像，只用于补全索引，不重复计数
for (const idxFile of [
  path.join(EXTRACTED_DIR, '_index.json'),
  path.join(EN_EXTRACTED_DIR, '_index.json'),
]) {
  if (!fs.existsSync(idxFile)) continue
  let data
  try {
    data = JSON.parse(fs.readFileSync(idxFile, 'utf8'))
  } catch {
    continue
  }
  for (const [fullKey, v] of Object.entries(data)) {
    const i = fullKey.indexOf('.')
    if (i < 0) continue
    const ns = fullKey.slice(0, i)
    const slug = fullKey.slice(i + 1)
    addIndex(ns, slug, v)
  }
}

/** 查已有 key：优先本命名空间，其次任意命名空间（减少重复造键） */
function lookup(ns, cnText) {
  const m = textIndex.get(cnText)
  if (!m) return null
  if (m.has(ns)) return m.get(ns)
  // 跨命名空间复用仅在文本足够长时允许，避免「保存」这类通用词乱串
  if (cnText.length >= 4) {
    const first = m.values().next()
    if (!first.done) return first.value
  }
  return null
}

// ============================================================
// 2) 新 key 生成（修复3：按 namespace 去重）
// ============================================================

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

/** 与 extract-i18n.mjs 完全一致的稳定 slug：前4中文字 + '_' + hash36前6位 */
function slugify(text) {
  let h = 0
  for (let i = 0; i < text.length; i++) {
    h = ((h << 5) - h + text.charCodeAt(i)) | 0
  }
  const tag = (text.match(/^[\u4e00-\u9fa5]+/)?.[0] || 'text').slice(0, 4)
  return `${tag}_${(h >>> 0).toString(36).slice(0, 6)}`
}

/** common.json 的顶层命名空间集合。
 *  _extracted/*.json 的顶层键会被 Object.assign 压到与 common.json 同一层，
 *  若某个裸 key 恰好等于这些命名空间名（如 "app" / "products"），
 *  就会把 common.json 里的整个对象覆盖成字符串，导致该命名空间下所有子键失效。
 *  这是 v4 apply 时实际踩到的坑：marketPricing.json 的 "app": "应用"
 *  干掉了 app.* 全部 17 个子键，登录页标题直接退化显示 "app.name"。 */
const RESERVED_NS = new Set()

function loadReservedNamespaces() {
  const commonPath = path.join(LOCALES_DIR, 'zh-CN', 'common.json')
  if (!fs.existsSync(commonPath)) return
  try {
    const d = JSON.parse(fs.readFileSync(commonPath, 'utf8'))
    for (const [k, v] of Object.entries(d)) {
      if (v && typeof v === 'object') RESERVED_NS.add(k)
    }
  } catch {
    /* ignore */
  }
}
loadReservedNamespaces()

function newKey(namespace, cnText) {
  const set = slugsByNs.get(namespace) || new Set()
  if (!slugsByNs.has(namespace)) slugsByNs.set(namespace, set)

  // 优先用户友好的 pySeg 名（如 loading/saveFailed），冲突时退回内容哈希
  const seg = pySeg[cnText]
  if (seg && !set.has(seg) && !RESERVED_NS.has(seg)) {
    set.add(seg)
    return `${namespace}.${seg}`
  }
  // 内容哈希是确定性的：同文本必得同 slug，天然可复用
  let slug = slugify(cnText)
  let n = 2
  while (set.has(slug) || RESERVED_NS.has(slug)) slug = `${slugify(cnText)}_${n++}`
  set.add(slug)
  return `${namespace}.${slug}`
}

// ============================================================
// 3) 区段切分
// ============================================================

function splitRegions(content) {
  const regions = []
  const re = /<script\b[^>]*>[\s\S]*?<\/script>/gi
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
// 4) <script> 字符串字面量（修复1：替换整个带引号字面量）
// ============================================================

/** 业务语义位置的字面量绝不能翻译（值比较、对象键、方法参数等） */
function isBusinessLiteral(body, strStart, quote) {
  const before = body.slice(Math.max(0, strStart - 120), strStart)
  // 已在 t() 调用里（含 t('k','默认值') 的第二参数）
  if (/\bt\s*\(\s*$/.test(before)) return true
  if (/\bt\s*\(\s*['"`][^'"`]*['"`]\s*,\s*$/.test(before)) return true
  // 相等比较 a === '中文'
  if (/[=!]==?\s*$/.test(before)) return true
  // case '中文'
  if (/\bcase\s+$/.test(before)) return true
  // includes/indexOf/startsWith/endsWith/match/test('中文')
  if (/\b(?:includes|indexOf|startsWith|endsWith|match|test)\s*\(\s*$/.test(before)) return true
  // 对象下标 obj['中文']
  if (/\[\s*$/.test(before)) return true
  // 对象字面量键 { '中文': ... }
  if (/[{,]\s*$/.test(before)) {
    const after = body.slice(strStart + 1, strStart + 400)
    const close = after.indexOf(quote)
    if (close >= 0 && /^\s*:/.test(after.slice(close + 1))) return true
  }
  // push('中文') / unshift('中文') —— 常用于收集校验消息，需人工判断，保守跳过
  if (/\b(?:push|unshift)\s*\(\s*$/.test(before)) return true
  return false
}

function findScriptLiterals(body, bodyStart, namespace, collector) {
  const edits = []
  const shadows = collectTShadows(body)
  const re = /(['"])((?:\\.|(?!\1)[\s\S])*?)\1/g
  let m
  while ((m = re.exec(body)) !== null) {
    const quote = m[1]
    const raw = m[2]
    const cnCount = (raw.match(/[\u4e00-\u9fff]/g) || []).length
    const total = raw.replace(/\s/g, '').length
    if (total === 0 || cnCount === 0) continue
    if (cnCount / total < 0.5) continue
    if (total > 80) continue
    if (!raw.trim()) continue
    if (/[\n\r]/.test(raw)) continue // 跨行字面量保守跳过

    // 绝对偏移：包含两侧引号
    const litStart = bodyStart + m.index
    const litEnd = bodyStart + m.index + m[0].length

    if (isBusinessLiteral(body, m.index, quote)) continue

    // 修复7：模块顶层立即求值会漏掉语言切换，跳过
    if (isModuleTopLevel(body, m.index)) continue

    // 修复8：t 被局部参数/变量遮蔽，跳过
    if (isTShadowed(shadows, m.index)) continue

    const key = collector(namespace, raw)
    if (!key) continue
    // 修复1 核心：把 '中文' 整个（含引号）换成 t("key")
    edits.push({ start: litStart, end: litEnd, replacement: `t(${JSON.stringify(key)})` })
  }
  return edits
}

// ============================================================
// 4a) 语义守卫（修复7）：跳过「模块顶层立即求值」的字面量
// ============================================================
//
// 形如 const LABELS = { a: '中文' } 的模块级常量，若改成 t('key')，
// t() 只在模块加载时求值一次，用户切语言后这些标签不会变。
// 这类必须保持字面量、由调用处翻译，因此跳过。

/** 判断 pos 是否处于「模块顶层求值」位置。
 *  规则：从 body 开头扫到 pos，追踪代码块深度。
 *  对象字面量 { } 不算代码块（要单独识别），只有 function/箭头函数/if/for 等代码块才算。
 *  简化实现：只要在 pos 之前出现过函数体开括号且未闭合，就视为"函数内"（安全）；
 *  否则视为顶层（需跳过）。为降低误判，额外要求：顶层声明形态 const X = {...} 也算顶层。 */
function isModuleTopLevel(body, posInBody) {
  // 收集所有可能开启函数体的 '{' 位置：在其前面 120 字符内出现 => 或 function
  const fnOpen = []
  for (let i = 0; i < posInBody; i++) {
    if (body[i] !== '{') continue
    const before = body.slice(Math.max(0, i - 160), i)
    if (/=>\s*$/.test(before) || /\bfunction\b[^(]*\([^)]*\)\s*$/.test(before) ||
        /\b(if|for|while|switch|catch)\s*\([^)]*\)\s*$/.test(before)) {
      fnOpen.push(i)
    }
  }
  if (!fnOpen.length) return true // 没有任何函数体开括号 -> 顶层

  // 判断每个 fnOpen 是否在 pos 前已闭合（配平）
  let depth = 0
  let openedAt = null
  let inFn = 0
  const set = new Set(fnOpen)
  let inStr = null
  let inTpl = false
  for (let i = 0; i < posInBody; i++) {
    const ch = body[i]
    if (inStr) {
      if (ch === '\\') i++
      else if (ch === inStr) inStr = null
      continue
    }
    if (inTpl) {
      if (ch === '\\') i++
      else if (ch === '`') inTpl = false
      continue
    }
    if (ch === '"' || ch === "'") { inStr = ch; continue }
    if (ch === '`') { inTpl = true; continue }
    if (ch === '{') {
      if (set.has(i)) inFn++
    } else if (ch === '}') {
      if (inFn > 0) inFn--
    }
  }
  // inFn > 0 表示当前在某函数体内 -> 非顶层
  return inFn === 0
}

// ============================================================
// 4c) 作用域守卫（修复8）：跳过 t 被局部变量/参数遮蔽的位置
// ============================================================
//
// 形如 async function removeTurn(t: TurnItem) { ... t("中文") ... }
// 这里的 t 是业务参数，不是 i18n 的 t。硬改成 t("key") 会变成
// 「把 TurnItem 当函数调用」，类型检查必挂、运行时必崩。

/** 收集 body 中所有「遮蔽 t」的声明：参数、const/let/var 声明、解构 */
function collectTShadows(body) {
  const shadows = []
  // 函数参数里出现 t：function f(t) / (t: TurnItem) => / (t) {
  const paramRe = /(?:function\s*\w*\s*\(([^)]*)\)|\(\s*([^()]*)\)\s*=>|\b(\w+)\s*=\s*\(([^)]*)\)\s*=>)/g
  let m
  while ((m = paramRe.exec(body)) !== null) {
    const ps = [m[1], m[2], m[4]].filter(Boolean).join(',')
    if (!ps) continue
    // 参数列表里是否有独立的 t
    const parts = ps.split(',')
    for (const p of parts) {
      const name = p.split(':')[0].split('=')[0].trim()
      if (name === 't') {
        // 记录该函数体的范围：从参数结束处的 { 开始配对
        const startBrace = body.indexOf('{', m.index + m[0].length - 1)
        if (startBrace >= 0) {
          let depth = 0
          let end = body.length
          for (let i = startBrace; i < body.length; i++) {
            if (body[i] === '{') depth++
            else if (body[i] === '}') {
              depth--
              if (depth === 0) {
                end = i
                break
              }
            }
          }
          shadows.push([startBrace, end])
        }
        break
      }
    }
  }
  // const t = ... / let t = ... / var t = ...
  const declRe = /\b(?:const|let|var)\s+t\s*(?::[^=]+)?=/g
  while ((m = declRe.exec(body)) !== null) {
    shadows.push([m.index, body.length])
  }
  return shadows
}

/** pos 是否被遮蔽 */
function isTShadowed(shadows, pos) {
  return shadows.some(([a, b]) => pos >= a && pos <= b)
}

// ============================================================
// 4b) 修复历史遗留死字符串（修复6）
// ============================================================
//
// 老版 codemod 产出过 't("ns.key")' 这种「被引号整个包裹的 t() 调用」，
// 运行时只是普通字符串，页面直接显示 t("ns.key") 这串文字。
// 这里把外层引号去掉，恢复成真正的 t() 调用。
// 仅处理 <script> 内、key 形如 ns.slug 的形态，不做猜测。

const DEAD_LITERAL = /(['"])t\(\s*(['"`])([\w\u4e00-\u9fff.\-]+)\2\s*\)\1/g

function fixDeadLiterals(content, scriptRanges) {
  const edits = []
  DEAD_LITERAL.lastIndex = 0
  let m
  while ((m = DEAD_LITERAL.exec(content)) !== null) {
    // 必须在 script 区内
    if (scriptRanges.length && !scriptRanges.some(([a, b]) => a <= m.index && m.index < b)) continue
    const key = m[3]
    const dot = key.indexOf('.')
    if (dot <= 0 || dot === key.length - 1) continue // 必须是 ns.key 形态
    edits.push({
      start: m.index,
      end: m.index + m[0].length,
      replacement: `t(${JSON.stringify(key)})`,
      dead: true,
    })
  }
  return edits
}

// ============================================================
// 5) <template> 文本节点与静态属性
// ============================================================

/** 在 HTML 属性值内使用 t()：外层是双引号，t() 内部必须用单引号 */
function tCallInAttr(key) {
  if (key.includes("'")) return `t(${JSON.stringify(key)})`
  return `t('${key}')`
}

/** 生成「掩码」：保留标签的 < 与 > 两个边界字符，只把标签名与属性抹成空格。
 *  这样：
 *    - >文本< 的边界仍然存在，可以正常匹配真实文本节点；
 *    - 属性值内部的伪标签（如 :srcdoc="'<p>中文</p>'"）被整体抹平，
 *      不会再被误认为真实文本节点。 */
function maskTags(tpl) {
  const chars = tpl.split('')
  let i = 0
  while (i < chars.length) {
    if (chars[i] !== '<') {
      i++
      continue
    }
    const next = chars[i + 1]
    if (!next || !/[a-zA-Z/!?]/.test(next)) {
      i++
      continue
    }
    // 从 i+1 扫到匹配的 >（跳过引号内内容）
    let j = i + 1
    let quote = null
    while (j < chars.length) {
      const c = chars[j]
      if (quote) {
        if (c === quote) quote = null
      } else if (c === '"' || c === "'") {
        quote = c
      } else if (c === '>') {
        break
      }
      j++
    }
    // 只抹 (i, j) 中间部分，保留 chars[i]='<' 与 chars[j]='>'
    for (let k = i + 1; k < j && k < chars.length; k++) chars[k] = ' '
    i = j + 1
  }
  return chars.join('')
}

/** 模板侧作用域守卫（修复9）：v-for / v-slot / 解构里声明了 t 时，
 *  同一元素及其子节点内的 t("中文") 会撞上循环变量。
 *  保守做法：整个 <template> 里只要出现 v-for="t in ..." / #default="t" / v-slot="t"，
 *  就直接跳过这个文件的模板部分，交人工处理。 */
function templateShadowT(tpl) {
  return (
    /\bv-for\s*=\s*["'][^"']*\bt\b\s*(?:,|\bin\b)/.test(tpl) ||
    /\bv-slot(?::[^=]*)?\s*=\s*["'][^"']*\bt\b/.test(tpl) ||
    /#\w+\s*=\s*["'][^"']*\bt\b/.test(tpl)
  )
}

function findTemplateText(tpl, tplStart, namespace, collector) {
  const edits = []
  const masked = maskTags(tpl)
  const re = />([^<>]+)</g
  let m
  while ((m = re.exec(masked)) !== null) {
    // 用原始 tpl 取真实文本（位置一致，长度已保证）
    const raw = tpl.slice(m.index, m.index + m[0].length)
    const text = raw.slice(1, -1)
    const trimmed = text.trim()
    if (!trimmed) continue
    if (!/[\u4e00-\u9fff]/.test(trimmed)) continue
    if (/[{}]/.test(trimmed)) continue // 已有插值
    if (/\n/.test(trimmed)) continue
    if (trimmed.length > 80) continue

    const lead = text.length - text.trimStart().length
    const key = collector(namespace, trimmed)
    if (!key) continue
    edits.push({
      start: tplStart + m.index + 1 + lead,
      end: tplStart + m.index + 1 + lead + trimmed.length,
      replacement: `{{ t(${JSON.stringify(key)}) }}`,
    })
  }
  return edits
}

function findTemplateAttrs(tpl, tplStart, namespace, collector) {
  const edits = []
  // 仅处理静态属性 attr="纯中文"，跳过 class/style/v-*/:/@
  const re = /(?<![-:.\w@])([a-zA-Z][a-zA-Z0-9-]*)="([^"]*[\u4e00-\u9fff][^"]*)"/g
  let m
  while ((m = re.exec(tpl)) !== null) {
    const attrName = m[1]
    if (['class', 'style', 'id', 'name', 'href', 'src', 'to', 'type'].includes(attrName)) continue
    const val = m[2]
    if (val.length > 80) continue
    // 含插值 / 单引号 / HTML 标签的属性值一律跳过：改写后极易破坏语法
    if (/[{}]/.test(val)) continue
    if (/'/.test(val)) continue
    if (/</.test(val)) continue
    // 已经带 : / v-bind 的跳过（上面正则已排除，双保险）
    if (attrName.startsWith('v-')) continue

    const key = collector(namespace, val)
    if (!key) continue
    // 外层是 HTML 双引号属性，t() 内部一律用单引号
    edits.push({
      start: tplStart + m.index,
      end: tplStart + m.index + m[0].length,
      replacement: `:${attrName}="${tCallInAttr(key)}"`,
    })
  }
  return edits
}

// ============================================================
// 6) 文件处理
// ============================================================

function namespaceFromPath(filePath) {
  const base = path.basename(filePath).replace(/\.vue$/, '')
  return base.replace(/View$|Page$/i, '').replace(/^./, (c) => c.toLowerCase())
}

function rewriteFile(filePath, pending) {
  const orig = fs.readFileSync(filePath, 'utf8')
  const namespace = namespaceFromPath(filePath)

  const collector = (ns, cnText) => {
    const hit = lookup(ns, cnText)
    if (hit) return hit
    const k = newKey(ns, cnText)
    textIndex.set(cnText, new Map([[ns, k]]))
    const [nsPart, slugPart] = [ns, k.slice(ns.length + 1)]
    pending.push({ namespace: nsPart, slug: slugPart, cn: cnText })
    return k
  }

  const edits = []
  const regions = splitRegions(orig)
  const scriptRanges = regions
    .filter((r) => r.kind === 'script')
    .map((r) => [r.start, r.end])

  // 先处理历史死字符串（这类位置后续的字面量扫描会因 isBusinessLiteral 跳过，不会冲突）
  edits.push(...fixDeadLiterals(orig, scriptRanges))

  for (const r of regions) {
    if (r.kind === 'script') {
      const block = orig.slice(r.start, r.end)
      const bm = block.match(/<script\b[^>]*>([\s\S]*?)<\/script>/i)
      if (!bm) continue
      const body = bm[1]
      const off = r.start + block.indexOf(body)
      edits.push(...findScriptLiterals(body, off, namespace, collector))
    } else {
      const tpl = orig.slice(r.start, r.end)
      // 修复9：模板里 t 被 v-for/v-slot 占用时，整个模板块跳过
      if (templateShadowT(tpl)) continue
      edits.push(...findTemplateText(tpl, r.start, namespace, collector))
      edits.push(...findTemplateAttrs(tpl, r.start, namespace, collector))
    }
  }

  if (!edits.length) return { file: filePath, changed: false, count: 0 }

  edits.sort((a, b) => a.start - b.start)
  const merged = []
  for (const e of edits) {
    if (merged.length && merged[merged.length - 1].end > e.start) continue
    merged.push(e)
  }

  let out = orig
  for (let i = merged.length - 1; i >= 0; i--) {
    const e = merged[i]
    out = out.slice(0, e.start) + e.replacement + out.slice(e.end)
  }

  // 补 useI18n（script setup 且尚未引入时）
  if (!/\buseI18n\b/.test(out) && out.includes('t(')) {
    if (/<script\s+setup[^>]*>/i.test(out)) {
      out = out.replace(
        /(<script\s+setup[^>]*>\n?)/i,
        `$1import { useI18n } from 'vue-i18n'\nconst { t } = useI18n()\n`,
      )
    }
  }

  if (out === orig) return { file: filePath, changed: false, count: 0 }
  if (APPLY) fs.writeFileSync(filePath, out)
  return { file: filePath, changed: true, count: merged.length }
}

// ============================================================
// 7) 写回 locales（修复5）
// ============================================================

function writeLocales(pending) {
  if (!pending.length) return 0

  // 按 namespace 聚合
  const byNs = new Map()
  for (const { namespace, slug, cn } of pending) {
    if (!byNs.has(namespace)) byNs.set(namespace, [])
    byNs.get(namespace).push({ slug, cn })
  }

  // 统计口径：按「逻辑新 key」计数，不按「写入次数」计数
  let written = 0
  for (const [ns, items] of byNs) {
    // 先看 zh 侧是否已存在，作为是否算「新」的依据
    const zhPath = path.join(EXTRACTED_DIR, `${ns}.json`)
    let zhData = {}
    if (fs.existsSync(zhPath)) {
      try {
        zhData = JSON.parse(fs.readFileSync(zhPath, 'utf8'))
      } catch {
        zhData = {}
      }
    }
    for (const { slug, cn } of items) {
      if (!(slug in zhData)) {
        zhData[slug] = cn
        written++
      }
    }

    for (const [dir, data] of [
      [EXTRACTED_DIR, zhData],
      [EN_EXTRACTED_DIR, null],
    ]) {
      const p = path.join(dir, `${ns}.json`)
      let target = data
      if (target === null) {
        // en 侧：只补缺失键，值先填中文，交给后续翻译流程
        target = {}
        if (fs.existsSync(p)) {
          try {
            target = JSON.parse(fs.readFileSync(p, 'utf8'))
          } catch {
            target = {}
          }
        }
        for (const { slug, cn } of items) {
          if (!(slug in target)) target[slug] = cn
        }
      }
      if (APPLY && !fs.existsSync(dir)) fs.mkdirSync(dir, { recursive: true })
      if (APPLY) fs.writeFileSync(p, JSON.stringify(target, null, 2) + '\n', 'utf8')
    }
  }

  // 重建 _index.json 镜像
  if (APPLY) {
    for (const dir of [EXTRACTED_DIR, EN_EXTRACTED_DIR]) {
      if (!fs.existsSync(dir)) continue
      const flat = {}
      for (const f of fs.readdirSync(dir).sort()) {
        if (!f.endsWith('.json') || f === '_index.json') continue
        const ns = f.replace('.json', '')
        try {
          const d = JSON.parse(fs.readFileSync(path.join(dir, f), 'utf8'))
          for (const [k, v] of Object.entries(d)) flat[`${ns}.${k}`] = v
        } catch {
          /* ignore */
        }
      }
      fs.writeFileSync(
        path.join(dir, '_index.json'),
        JSON.stringify(flat, null, 2) + '\n',
        'utf8',
      )
    }
  }
  return written
}

// ============================================================
// 8) 入口
// ============================================================

function walk(dir, out = []) {
  if (!fs.existsSync(dir)) return out
  for (const f of fs.readdirSync(dir)) {
    const p = path.join(dir, f)
    if (fs.statSync(p).isDirectory()) walk(p, out)
    else if (f.endsWith('.vue')) out.push(p)
  }
  return out
}

let files
if (TARGET) files = [path.resolve(TARGET)]
else files = SCAN_DIRS.flatMap((d) => walk(d))

const pending = []
const results = files.map((f) => rewriteFile(f, pending))
const written = writeLocales(pending)

const changed = results.filter((r) => r.changed)
console.log(
  `${APPLY ? '✅ APPLIED' : '🔍 DRY-RUN'}: ${changed.length}/${results.length} 文件改动，` +
    `${results.reduce((a, r) => a + r.count, 0)} 处替换，${written} 个新 key`,
)
for (const r of changed.slice(0, 12)) {
  console.log(`  - ${path.relative(ROOT, r.file)}: ${r.count} 处`)
}
if (changed.length > 12) console.log(`  ... 另有 ${changed.length - 12} 个文件`)