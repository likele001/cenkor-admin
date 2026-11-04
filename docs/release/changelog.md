# 发布记录

本目录用于**存放打包产物说明与发版日志**。压缩包文件本身在仓库根目录 `release/`（已 `.gitignore`，不提交 git）。

## 产物命名

```
release/cenkor-admin-core-<version>-<YYYYMMDD>.tar.gz
```

## 发版日志

### 0.5.16 · 2026-11-04

- 新增稿件版本对比：`GET /cms/entries/{id}/versions/diff` + 后台双栏对照弹窗，审核人能看到「改了什么」
- 新增站内搜索词日志：`cms_search_logs` 表、`/public/search` 旁路记录、`GET /cms/ai/search-terms`，选题缺口页接入真实搜索词
- 官网构建产物移出 git（`frontend/landing/` 70 个文件），改由打包脚本从磁盘收集，仓库不再随每次构建变大
- 数据库迁移：`20261104_1100_cms_search_logs`（down_revision 挂公开 head，开源版链路完整）
- 后端改动 + 迁移，需重启服务并 `alembic upgrade head`
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
