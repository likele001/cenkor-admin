# 发布记录

本目录用于**存放打包产物说明与发版日志**。压缩包文件本身在仓库根目录 `release/`（已 `.gitignore`，不提交 git）。

## 产物命名

```
release/cenkor-admin-core-<version>-<YYYYMMDD>.tar.gz
```

## 发版日志

### 0.5.18 · 2026-11-04

- 新增 widget 组件沙箱（模板市场第四期）：模板可以把交互部分做成组件，跑在没有同源权限的 iframe 里 —— 开放交互但**不需要信任模板作者**
- 三层防护各自独立：`iframe sandbox="allow-scripts"`（无 `allow-same-origin`）、宿主页响应头 `sandbox allow-scripts`（地址栏直开也受限）、子文档 CSP `default-src 'none'` + `connect-src 'none'`
- 组件脚本用 sha256 哈希白名单放行，不用 `'self'`：opaque origin 下 `'self'` 匹配不到任何东西，外链脚本会被静默拦下
- 新增 `GET /public/theme-widgets/{theme}/{name}` 宿主页路由；刻意不发 `X-Frame-Options`（`SAMEORIGIN` 在 opaque origin 下会把 iframe 直接拒掉）
- `theme.json` 新增 `widgets` 声明（name / title / height / description），组件文件为 `widgets/<name>.html` + 可选 `.js`
- 新增模板函数 `widget(name, args, height=, title=)`；参数走 URL（base64url JSON），不依赖父页面脚本
- 新增配置 `CMS_THEME_ALLOW_JS`（默认 `false`）：同源脚本与站点同权，需要显式开启；关闭时 `script()` 只留一句 HTML 注释，不静默失败
- 内置 `corporate` 主题新增 `stats` 数字统计组件（1.1.0）作为官方样板，作者可 `init --from corporate` 直接取用
- 包校验：声明了组件却缺 `widgets/<name>.html` 拒包；`asset_kinds` 比对改为只看 `assets/` 下的文件（此前任何 `.js` 都被算进 `js` 资源，等于逼作者为换个轮播图声明整站同权）
- 修 `cenkor-theme init --from` 只拷 `widgets/*.html` 不拷声明，作者一 lint 就被告知「组件没声明」
- 无数据库迁移；需重启服务
- 产物：`release/cenkor-admin-core-0.5.18-20261104.tar.gz`
### 0.5.17 · 2026-11-04

- 新增公开页严格 CSP：`script-src 'self'`、`frame-ancestors 'self'`、`base-uri 'self'`、`form-action 'self'`；5 处 HTML 出口统一走 `csp.html_response()`
- 补齐全仓此前完全缺失的 clickjacking 防护（`X-Frame-Options: SAMEORIGIN` + `X-Content-Type-Options: nosniff` + `Referrer-Policy`）
- 新增主题资源路由 `GET /public/theme-assets/{theme}/assets/{file}`，只服务 css/js，HTML 与 SVG 一律 404
- 模板校验拦截内联 `<script>`、内联事件属性、`javascript:` 伪协议，validate / 保存 / 导入三处统一口径
- 新增 `theme.json` 包规范（schema_version=1）：版本 / 作者 / 许可 / 依赖 / `asset_kinds` / `settings` 声明；`validate_package()` 成为后台导入、商店提交、CLI lint 共用的唯一校验入口
- 内置主题拆为 4 个模块：`default` / `blog` 墨读 / `corporate` 企业官网 / `landing` 落地页，只存差异文件，其余回落到 default
- 新增主题配置：`GET/PUT /cms/templates/themes/{theme}/settings` + 后台「主题配置」弹窗，按 `settings` 声明自动渲染控件，值存 `Site.settings`（不建表、不迁移）
- 新增打包 CLI `scripts/cenkor-theme.py`：`init` / `lint` / `pack` / `list`
- 修 Jinja 模板缓存串主题：`auto_reload=False` 下缓存 key 不含主题，换肤后 `layout.html` 仍命中上一个主题的编译结果；改 `cache_size=0`，编译缓存交给 `_compile`（key = 名字 + 源码 sha1）
- 修 `clear_template_cache()` 在 `cache_size=0` 时的 `AttributeError`（异常发生在「保存后清理」环节，表面看像保存失败）
- 修 `theme_documents()` 合并漏本主题，导出非默认主题时 `layout.html` 是 default 的
- 修用户主题（DB）的 `theme.json` 读不到，从 zip 导入的主题配置页永远空着
- 模板上下文注入 `is_home`：列表页 `kind` 一律为 `"list"`，模板此前无法区分首页
- 闭源链迁移 `20261104_1200_merge_closed_cms`：纯拓扑合流、无 DDL，`alembic_version` 由两行收敛为一行（开源包不含，公开子图仍是单 head）
- 后端改动需重启服务；有迁移的部署执行 `alembic upgrade heads`
- 产物：`release/cenkor-admin-core-0.5.17-20261104.tar.gz`

### 0.5.16 · 2026-11-04

- 新增稿件版本对比：`GET /cms/entries/{id}/versions/diff` + 后台双栏对照弹窗，审核人能看到「改了什么」
- 新增站内搜索词日志：`cms_search_logs` 表、`/public/search` 旁路记录、`GET /cms/ai/search-terms`，选题缺口页接入真实搜索词
- 官网构建产物移出 git（`frontend/landing/` 70 个文件），改由打包脚本从磁盘收集，仓库不再随每次构建变大
- 数据库迁移：`20261104_1100_cms_search_logs`（down_revision 挂公开 head，开源版链路完整）
- 后端改动 + 迁移，需重启服务并 `alembic upgrade head`
- 新增 AI 事实溯源：`POST /cms/ai/entries/{id}/fact-check`，规则层比对 + 模型逐句判定，只告警不阻断
- 修打包漏文件：`build-frontends.sh` 的 rsync 曾把 `docs-content/` 与 `public/` 下的 favicon / robots / sitemap 误当静态资产排除，产物移出 git 后官网文档中心整目录缺席
- 新增打包自检：landing 文件数不达标直接中止，避免「包能打出来、装上缺内容」
- 产物：`release/cenkor-admin-core-0.5.16-20261104.tar.gz`

### 0.5.15 · 2026-11-04

- 依赖安全加固：`dompurify` 3.4.13 → 3.4.17 修 critical 级 SAFE_FOR_TEMPLATES 绕过，`axios` 等 20+ 个包同步升级
- `vite` 5.4.21 → 6.4.5（vite 5 已 EOL，安全回补只在 6.4.4+）、`@vitejs/plugin-vue` 5.2.4、`vue-i18n` 9.x → 11.x
- 删除两份幽灵 lock（landing-web 的 package-lock、admin-web 的 pnpm-lock），Dependabot 告警由 100+ 降到 7（全 medium/low）
- 新增改写稿 Markdown 渲染：`src/lib/markdown.ts` + `RichTextContent format="markdown"`
- 修内链建议 `max_tokens` 4000 → 16000，推理模型下不再必然返回空正文
- 后台欢迎语对齐 AI CMS 定位
- 无数据库迁移；后端 `max_tokens` 改动需重启服务生效
- 产物：`release/cenkor-admin-core-0.5.15-20261104.tar.gz`

### 0.5.14 · 2026-11-03

- CI 门禁恢复绿：payment 驱动的微信 AppID 占位符改为不撞 GitHub 密钥扫描规则的写法
- 清理 payment / commerce 开源入仓后暴露的 108 处 ruff 告警（等价重写）
- `pyproject.toml` 显式声明 `known-first-party`，消除本地绿 / CI 红的判定漂移
- 纯后台改动，不涉及数据库迁移，不需要重启服务
- 产物：`release/cenkor-admin-core-0.5.14-20261103.tar.gz`

### 0.5.13 · 2026-11-03

- `database-migrations.md` / `migrations.md` 按合流后的真实拓扑整体重写
- 废弃 `codegen/builder.py` 的 `rebase_closed_chain`：它会让新迁移被静默跳过
- 产物：`release/cenkor-admin-core-0.5.13-20261103.tar.gz`

### 0.5.12 · 2026-11-03

- 新增闭源合流迁移 `20261103_1300_merge_closed`，三条闭源支线收成一个 head
- `check-migration-graph.py` 改为「公开子图严格单 head、全量允许多 head 但须能回到公开 head」
- 删除 `backend/scripts/check-migration-graph.py`（自 v0.3.0 起分叉的孤立副本）
- 产物：`release/cenkor-admin-core-0.5.12-20261103.tar.gz`

### 0.5.11 · 2026-11-03

- **支付交易层开源**：payment（13 py / 3398 行）+ commerce（9 py / 4994 行）移入主仓库，同 MIT
- 收款能力是平台底座，不再作为商业闭源项单独收费
- 迁移图重构：payment / commerce 的迁移改挂公开 head，不再依赖闭源 revision
- 产物：`release/cenkor-admin-core-0.5.11-20261103.tar.gz`

### 0.5.10 · 2026-11-03

- 补齐 6 张表与 18 个字段（生产库手工补过、迁移里从没建过的那些）
- 新增 `scripts/check-orm-drift.py`，CI 里卡「迁移必须覆盖 ORM 全部定义」
- 产物：`release/cenkor-admin-core-0.5.10-20261103.tar.gz`

### 0.1.0 · 2026-06-07

- 首次核心平台打包脚本 `scripts/package-core.sh`
- 包含：backend、admin-web/portal-web（源码 + dist）、宝塔/systemd/Docker 部署配置
- 不含：官网 addon、node_modules、生产密钥
- 文档：`docs/packaging.md`、`docs/core_platform.md`

---

## 如何追加记录

发版后在此文件顶部（最新在上）追加：

```markdown
### x.y.z · YYYY-MM-DD

- 变更摘要
- 产物：release/cenkor-admin-core-x.y.z-YYYYMMDD.tar.gz
```

并执行：

```bash
bash scripts/package-core.sh
cp release/cenkor-admin-core-*.tar.gz /你的备份路径/
```

> 完整变更说明见 [CHANGELOG.md](../CHANGELOG.md)；本文档只记「哪一版打了什么包」。
