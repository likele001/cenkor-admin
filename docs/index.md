# 文档索引

Cenkor Admin 文档目录。按用途选择。

## 主线（本机生产正在用的）

| 文档 | 用途 |
|------|------|
| [**deploy.md**](deploy.md) | **部署方案（权威）** —— 架构拓扑 · 端口台账 · 配置五落点与优先级 · 依赖服务 · 发布 · 验证 · 备份回滚 · 排障手册 |
| [**dev_guide.md**](dev_guide.md) | **开发者指南** —— 创建 App、字段定义、模板开发 |
| [**apps/development_guide.md**](apps/development_guide.md) | 应用开发规范（结构 / 字段类型 / 路由 / 迁移 / 打包 / 安全） |
| [**core_platform.md**](core_platform.md) | 核心平台组成 · 域名规划 · 宝塔建站 |
| [**architecture.md**](../architecture.md) | V2 架构设计（内容引擎 / 双用户体系 / 模板引擎 / App 中心 / 安全） |
| [**roadmap.md**](roadmap.md) | 路线图与规划（V2 改造 / 平台重构 / 平台升级 三合一） |
| [**upgrade.md**](upgrade.md) | 版本升级（用户升级 / 维护者发版 / 回滚） |
| [**packaging.md**](packaging.md) | 打包交付（产物清单 / 命令 / 接收方部署） |
| [**domain_setup.md**](domain_setup.md) | 域名绑定 + SSL |
| [**release/**](release/) | 发布记录与产物说明 |
| [**addons/website_cms.md**](addons/website_cms.md) | 可选：外部官网 CMS 对接 |

## 面向使用者（给「用系统的人」看）

| 文档 | 用途 |
|------|------|
| [**05-用户手册/workflow_操作手册.md**](05-用户手册/workflow_操作手册.md) | **工作流审批** —— 发起单据 · 审批 · 画流程 · 条件分支 · 委托代理 · 权限对照 · 常见问题 |

> **每个应用都必须配一份用户手册**，放在 `docs/05-用户手册/<应用 key>_操作手册.md`。
> 新增应用时在这里补一行。规范见 [apps/development_guide.md](apps/development_guide.md) §7.3。

## 可选路径（本机生产**未采用**）

本机生产是**纯宿主机 + 宝塔**，以下方案仅在「交付给别人」或「换环境验证」时使用。

| 文档 | 用途 |
|------|------|
| [**fullstack_deploy.md**](fullstack_deploy.md) | Docker 全栈部署（一条命令起全栈，**交付演示用**） |
| [**native_deploy.md**](native_deploy.md) | 裸机 systemd 部署（替代宝塔守护） |
| [**baota_static_deploy.md**](baota_static_deploy.md) | 宝塔 + Docker 混合部署（**历史方案**，已被 deploy.md 取代） |
| [**admin_system_comparison.md**](../admin_system_comparison.md) | 同类系统架构对比 |

## 推荐阅读顺序

1. **要部署 / 排障** → `deploy.md`（先读它，再读别的）
2. 了解平台组成与域名 → `core_platform.md`
3. 了解 V2 架构设计 → `architecture.md`
4. 了解下一步要做什么 → `roadmap.md`
5. 新开发者 → `dev_guide.md` + `apps/development_guide.md`
6. 打包给别人 → `packaging.md`
7. 发版 / 升级 → `upgrade.md`
8. 接官网 → `addons/website_cms.md`
9. **要上手用某个应用（发起 / 审批单据）** → `05-用户手册/` 里挑对应那份

## 文档维护约定

- **端口、路径、域名只在 `deploy.md` 里维护**，其他文档引用它，不要各写一份。
- 站点版（<https://docs.user.023ent.net/cenkor-admin/>）由脚本从本目录同步，**不要直接改站点上的文件**。
- 同步命令：`bash scripts/sync-docs-to-knowledge.sh`
- **新增应用必须配用户手册**：`docs/05-用户手册/<key>_操作手册.md`，
  规范见 [apps/development_guide.md](apps/development_guide.md) §7.3。
  ⚠️ **只能放这个数字前缀目录** —— 放 `docs/` 根级会被侧栏的关键词过滤**静默丢掉**。

## 脚本对照

| 脚本 | 用途 | 文档 |
|------|------|------|
| `scripts/backup.sh` | 备份 | [deploy.md](deploy.md) |
| `scripts/restart-backend-host.sh` | 重启后端（无面板时） | [deploy.md](deploy.md) |
| `scripts/migrate-and-seed-host.sh` | 宿主机模式迁移 + 播种 | [deploy.md](deploy.md) |
| `scripts/sync-docs-to-knowledge.sh` | 文档同步到知识库站点 | 本文档 |
| `scripts/build-frontends.sh` | 构建全部前端 dist | [deploy.md](deploy.md) |
| `scripts/package-core.sh` | 打核心平台包 | [packaging.md](packaging.md) |
| `scripts/package-app.sh` | 打单个应用包 | [apps/development_guide.md](apps/development_guide.md) |
| `scripts/gen-secrets.sh` | 生成 `.env.prod` | [packaging.md](packaging.md) |
| `scripts/release.sh` | 维护者发版 | [upgrade.md](upgrade.md) |
| `scripts/upgrade.sh` | 升级 | [upgrade.md](upgrade.md) |
| `scripts/deploy.sh` | Docker 部署（`--mode docker\|baota\|baota-static`） | [fullstack_deploy.md](fullstack_deploy.md) |
| `scripts/install-native.sh` | systemd 安装 | [native_deploy.md](native_deploy.md) |
| `scripts/setup-domain.sh` | 域名与证书辅助 | [domain_setup.md](domain_setup.md) |
