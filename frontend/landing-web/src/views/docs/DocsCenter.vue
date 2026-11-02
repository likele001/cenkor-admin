<template>
  <div class="docs-page">
    <section class="page-hero">
      <div class="container">
        <div class="page-hero-content">
          <span class="hero-tag">文档中心</span>
          <h1>{{ currentDoc ? currentDoc.title : 'Cenkor Admin 文档' }}</h1>
          <p>用户教程 · 模板标签参考 · 二次开发指南</p>
        </div>
      </div>
    </section>

    <section class="section">
      <div class="container">
        <div class="docs-layout">
          <aside class="docs-sidebar">
            <input v-model="query" type="search" class="docs-search" placeholder="搜索文档…" />
            <nav class="docs-nav">
              <div v-for="group in visibleGroups" :key="group.key" class="docs-group">
                <div class="docs-group-title">{{ group.label }}</div>
                <router-link
                  v-for="doc in group.items"
                  :key="doc.path"
                  :to="docUrl(doc)"
                  class="docs-item"
                  :class="{ active: currentDocPath === doc.path }"
                >
                  {{ doc.title }}
                </router-link>
              </div>
              <p v-if="!visibleGroups.length" class="docs-empty">没有匹配的文档</p>
            </nav>
          </aside>

          <article class="docs-article">
            <!-- 目录首页（/docs）：分组卡片 -->
            <template v-if="!currentDocPath">
              <div v-for="group in visibleGroups" :key="group.key" class="docs-card-group">
                <h2 class="docs-card-group-title">{{ group.label }}</h2>
                <div class="docs-cards">
                  <router-link
                    v-for="doc in group.items"
                    :key="doc.path"
                    :to="docUrl(doc)"
                    class="doc-card"
                  >
                    <h3>{{ doc.title }}</h3>
                    <p v-if="doc.desc">{{ doc.desc }}</p>
                  </router-link>
                </div>
              </div>
            </template>

            <!-- 阅读页 -->
            <template v-else>
              <p v-if="loading" class="docs-state">加载中…</p>
              <div v-else-if="error" class="docs-state docs-error">
                <p>文档加载失败（{{ error }}）。</p>
                <router-link to="/docs" class="btn btn-secondary btn-small">返回文档中心</router-link>
              </div>
              <template v-else>
                <div class="markdown-body" @click="onContentClick" v-html="rendered"></div>
                <div class="docs-pager">
                  <router-link v-if="prevDoc" :to="docUrl(prevDoc)" class="docs-pager-link">
                    <span>上一篇</span>{{ prevDoc.title }}
                  </router-link>
                  <span v-else></span>
                  <router-link v-if="nextDoc" :to="docUrl(nextDoc)" class="docs-pager-link next">
                    <span>下一篇</span>{{ nextDoc.title }}
                  </router-link>
                </div>
              </template>
            </template>
          </article>
        </div>
      </div>
    </section>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useHead } from '@unhead/vue'
import MarkdownIt from 'markdown-it'
import hljs from 'highlight.js/lib/common'
import 'highlight.js/styles/github.css'
import { DOCS_GROUPS, DOCS_FLAT, type DocMeta } from '@/config/docs-manifest.generated'

const route = useRoute()
const router = useRouter()

const query = ref('')
const loading = ref(false)
const error = ref('')
const rawMd = ref('')
const rendered = ref('')

/** 当前文档相对路径（去掉 .md，'index' 表示根总览 → 视为目录首页） */
const currentDocPath = computed(() => {
  const raw = route.params.pathMatch
  const path = Array.isArray(raw) ? raw.join('/') : (raw as string | undefined) || ''
  return path === 'index' ? '' : path
})

const currentDoc = computed<DocMeta | undefined>(() =>
  DOCS_FLAT.find((d) => stripMd(d.path) === currentDocPath.value)
)

const prevDoc = computed(() => {
  const i = DOCS_FLAT.findIndex((d) => stripMd(d.path) === currentDocPath.value)
  return i > 0 ? DOCS_FLAT[i - 1] : undefined
})
const nextDoc = computed(() => {
  const i = DOCS_FLAT.findIndex((d) => stripMd(d.path) === currentDocPath.value)
  return i >= 0 && i < DOCS_FLAT.length - 1 ? DOCS_FLAT[i + 1] : undefined
})

const visibleGroups = computed(() => {
  const q = query.value.trim().toLowerCase()
  if (!q) return DOCS_GROUPS
  return DOCS_GROUPS.map((g) => ({
    ...g,
    items: g.items.filter(
      (d) => d.title.toLowerCase().includes(q) || d.desc.toLowerCase().includes(q)
    )
  })).filter((g) => g.items.length)
})

function stripMd(p: string): string {
  return p.endsWith('/index.md') || p === 'index.md'
    ? p.replace(/index\.md$/, '').replace(/\/$/, '')
    : p.replace(/\.md$/, '')
}

/** 文档链接：根总览指回 /docs 本身 */
function docUrl(doc: DocMeta): string {
  const p = stripMd(doc.path)
  return p === '' ? '/docs' : `/docs/${p}`
}

// ---------------------------------------------------------------- markdown 渲染

const md = new MarkdownIt({
  html: false,
  linkify: true,
  breaks: false,
  highlight(code: string, lang: string): string {
    if (lang && hljs.getLanguage(lang)) {
      try {
        return `<pre class="hljs"><code>${hljs.highlight(code, { language: lang }).value}</code></pre>`
      } catch {
        /* 落到转义输出 */
      }
    }
    return `<pre class="hljs"><code>${md.utils.escapeHtml(code)}</code></pre>`
  }
})

/**
 * 链接重写（在 renderer 里做，env 传当前文档目录）：
 * - .md 内链 → 解析相对路径 → /landing/docs/<path>
 * - /cenkor-admin/ 前缀（知识库风格绝对路径）→ /landing/docs/<path>
 * - 其它相对路径（指仓库源文件的 conf/yml 等）→ 降级为死链样式，点击不跳
 * - 外链 / 锚点原样
 */
function rewriteHref(href: string, dir: string): { href?: string; dead?: boolean } {
  if (/^(https?:)?\/\//.test(href) || href.startsWith('mailto:')) return { href }
  if (href.startsWith('#')) return { href }

  let h = href
  if (h.startsWith('/cenkor-admin/')) {
    h = h.slice('/cenkor-admin/'.length)
  } else if (h.startsWith('/')) {
    return { href } // 其它站内绝对路径，原样交给浏览器
  }

  const hashIdx = h.indexOf('#')
  let anchor = ''
  if (hashIdx >= 0) {
    anchor = h.slice(hashIdx)
    h = h.slice(0, hashIdx)
  }
  if (!h) return { href } // 纯页内锚点

  if (h.endsWith('.md')) {
    const parts = (dir ? dir.split('/') : [])
    for (const seg of h.split('/')) {
      if (seg === '.' || seg === '') continue
      if (seg === '..') parts.pop()
      else parts.push(seg)
    }
    const resolved = stripMd(parts.join('/'))
    return { href: `${import.meta.env.BASE_URL}docs/${resolved}${anchor}` }
  }
  return { dead: true }
}

md.renderer.rules.link_open = (tokens, idx, options, env, self) => {
  const token = tokens[idx]
  const raw = token.attrGet('href') || ''
  const r = rewriteHref(raw, (env as { dir?: string }).dir || '')
  if (r.dead) {
    token.attrJoin('class', 'docs-dead')
    token.attrSet('title', '该文件在仓库源码里，见 GitHub')
  } else if (r.href) {
    token.attrSet('href', r.href)
  }
  return self.renderToken(tokens, idx, options)
}

function renderDoc(source: string, dir: string): string {
  return md.render(source, { dir })
}

// ---------------------------------------------------------------- 加载与交互

async function loadDoc(path: string) {
  loading.value = true
  error.value = ''
  rawMd.value = ''
  rendered.value = ''
  try {
    const url =
      import.meta.env.BASE_URL +
      'docs-content/' +
      path.split('/').map(encodeURIComponent).join('/') +
      '.md'
    const res = await fetch(url)
    if (!res.ok) throw new Error(`HTTP ${res.status}`)
    rawMd.value = await res.text()
    const dir = path.includes('/') ? path.slice(0, path.lastIndexOf('/')) : ''
    rendered.value = renderDoc(rawMd.value, dir)
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e)
  } finally {
    loading.value = false
  }
}

/** markdown 里的链接：站内文档路由化，死链拦截 */
function onContentClick(e: MouseEvent) {
  const a = (e.target as HTMLElement).closest('a')
  if (!a) return
  if (a.classList.contains('docs-dead')) {
    e.preventDefault()
    return
  }
  const href = a.getAttribute('href') || ''
  const base = import.meta.env.BASE_URL
  if (href.startsWith(`${base}docs/`)) {
    e.preventDefault()
    router.push(href.slice(base.length - 1))
  }
}

useHead({
  title: computed(() =>
    currentDoc.value ? `${currentDoc.value.title} - 辰科 Cenkor Admin` : '辰科 Cenkor Admin - 文档中心'
  )
})

watch(currentDocPath, (p, old) => {
  if (p === old) return
  if (p) loadDoc(p)
  window.scrollTo({ top: 0 })
})

onMounted(() => {
  if (currentDocPath.value) loadDoc(currentDocPath.value)
})
</script>

<style scoped lang="scss">
.docs-page {
  min-height: 60vh;
}

.docs-layout {
  display: grid;
  grid-template-columns: 280px 1fr;
  gap: 40px;
  align-items: start;
}

.docs-sidebar {
  position: sticky;
  top: 90px;
  max-height: calc(100vh - 120px);
  overflow-y: auto;
  border-right: 1px solid rgba(15, 23, 42, 0.08);
  padding-right: 20px;
}

.docs-search {
  width: 100%;
  padding: 10px 14px;
  border: 1px solid rgba(15, 23, 42, 0.15);
  border-radius: 10px;
  font-size: 14px;
  margin-bottom: 16px;
  outline: none;

  &:focus {
    border-color: #10b981;
  }
}

.docs-group-title {
  font-size: 13px;
  font-weight: 700;
  color: #64748b;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  margin: 18px 0 8px;
}

.docs-item {
  display: block;
  padding: 7px 12px;
  border-radius: 8px;
  color: #334155;
  font-size: 14px;
  text-decoration: none;
  line-height: 1.4;

  &:hover {
    background: rgba(16, 185, 129, 0.08);
    color: #059669;
  }

  &.active {
    background: #10b981;
    color: #fff;
    font-weight: 600;
  }
}

.docs-empty {
  color: #94a3b8;
  font-size: 14px;
}

.docs-article {
  min-height: 400px;
  max-width: 860px;
}

.docs-state {
  color: #64748b;
  padding: 40px 0;
}

.docs-error {
  .btn {
    margin-top: 12px;
    display: inline-block;
  }
}

.docs-card-group-title {
  font-size: 20px;
  margin: 28px 0 14px;

  &:first-child {
    margin-top: 0;
  }
}

.docs-cards {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(240px, 1fr));
  gap: 14px;
}

.doc-card {
  display: block;
  border: 1px solid rgba(15, 23, 42, 0.08);
  border-radius: 12px;
  padding: 16px 18px;
  text-decoration: none;
  transition: all 0.2s ease;

  h3 {
    font-size: 15px;
    color: #0f172a;
    margin: 0 0 6px;
  }

  p {
    font-size: 13px;
    color: #64748b;
    margin: 0;
    line-height: 1.5;
    display: -webkit-box;
    -webkit-line-clamp: 2;
    -webkit-box-orient: vertical;
    overflow: hidden;
  }

  &:hover {
    border-color: #10b981;
    box-shadow: 0 4px 14px rgba(16, 185, 129, 0.12);
    transform: translateY(-1px);
  }
}

.docs-pager {
  display: flex;
  justify-content: space-between;
  gap: 16px;
  margin-top: 40px;
  padding-top: 20px;
  border-top: 1px solid rgba(15, 23, 42, 0.08);
}

.docs-pager-link {
  max-width: 48%;
  text-decoration: none;
  color: #059669;
  font-size: 14px;
  font-weight: 600;

  span {
    display: block;
    font-size: 12px;
    color: #94a3b8;
    font-weight: 400;
  }

  &.next {
    text-align: right;
  }
}

/* ---------------------------------------------------------------- 正文排版 */
.markdown-body {
  font-size: 15px;
  line-height: 1.75;
  color: #1e293b;
  word-break: break-word;

  :deep(h1) {
    font-size: 26px;
    margin: 0 0 20px;
    padding-bottom: 12px;
    border-bottom: 1px solid rgba(15, 23, 42, 0.08);
  }

  :deep(h2) {
    font-size: 21px;
    margin: 32px 0 14px;
  }

  :deep(h3) {
    font-size: 17px;
    margin: 24px 0 10px;
  }

  :deep(p) {
    margin: 10px 0;
  }

  :deep(a) {
    color: #059669;
    text-decoration: none;

    &:hover {
      text-decoration: underline;
    }

    &.docs-dead {
      color: #94a3b8;
      cursor: help;
      text-decoration: underline dotted;
    }
  }

  :deep(ul),
  :deep(ol) {
    padding-left: 24px;
    margin: 10px 0;
  }

  :deep(li) {
    margin: 4px 0;
  }

  :deep(blockquote) {
    margin: 14px 0;
    padding: 10px 16px;
    border-left: 3px solid #10b981;
    background: rgba(16, 185, 129, 0.06);
    border-radius: 0 8px 8px 0;
    color: #475569;
  }

  :deep(code) {
    font-family: 'SFMono-Regular', Consolas, 'Liberation Mono', Menlo, monospace;
    font-size: 0.88em;
    background: rgba(15, 23, 42, 0.06);
    padding: 2px 6px;
    border-radius: 5px;
  }

  :deep(pre.hljs) {
    background: #f8fafc;
    border: 1px solid rgba(15, 23, 42, 0.08);
    border-radius: 10px;
    padding: 16px;
    overflow-x: auto;
    font-size: 13px;
    line-height: 1.6;

    code {
      background: none;
      padding: 0;
      font-size: inherit;
    }
  }

  :deep(table) {
    width: 100%;
    border-collapse: collapse;
    margin: 14px 0;
    font-size: 14px;
    display: block;
    overflow-x: auto;

    th,
    td {
      border: 1px solid rgba(15, 23, 42, 0.1);
      padding: 8px 12px;
      text-align: left;
    }

    th {
      background: rgba(15, 23, 42, 0.04);
      font-weight: 600;
    }

    tr:nth-child(2n) td {
      background: rgba(15, 23, 42, 0.015);
    }
  }

  :deep(hr) {
    border: none;
    border-top: 1px solid rgba(15, 23, 42, 0.08);
    margin: 28px 0;
  }
}

@media (max-width: 900px) {
  .docs-layout {
    grid-template-columns: 1fr;
  }

  /* 手机端文章区排到侧栏前面：单列布局下侧栏 45 条列表占两三屏，
     路由切换后 scrollTo(top:0) 滚回页顶，文章在两屏之外 —— 看起来就是「点了没反应」。
     文章优先后，滚回顶部正好是正文开头；/docs 目录页也变成卡片优先。 */
  .docs-article {
    order: -1;
  }

  .docs-sidebar {
    position: static;
    max-height: none;
    border-right: none;
    border-bottom: none;
    border-top: 1px solid rgba(15, 23, 42, 0.08);
    padding-bottom: 16px;
    padding-right: 0;
    margin-top: 28px;
  }
}
</style>
