# 文档索引

Cenkor Admin 文档目录。按用途选择：

| 文档 | 用途 |
|------|------|
| [**PLATFORM_V2_ROADMAP.md**](PLATFORM_V2_ROADMAP.md) | **V2 改造路线图**（内容引擎 / 用户拆分 / App 中心 / Liquid 模板） |
| [**DEV_GUIDE.md**](DEV_GUIDE.md) | **开发者指南**（如何创建 App、字段定义、模板开发、部署） |
| [**CORE_PLATFORM.md**](CORE_PLATFORM.md) | 核心平台架构、模块、域名规划 |
| [**PACKAGING.md**](PACKAGING.md) | **打包交付**（产物清单、命令、解压部署） |
| [**BAOTA_STATIC_DEPLOY.md**](BAOTA_STATIC_DEPLOY.md) | **宝塔面板完整部署**（推荐，含 Python 项目 / Docker 双方案） |
| [**NATIVE_DEPLOY.md**](NATIVE_DEPLOY.md) | 裸机 systemd 部署 |
| [**release/**](release/) | 发布记录与产物说明 |
| [**addons/WEBSITE_CMS.md**](addons/WEBSITE_CMS.md) | 可选：外部官网 CMS 对接 |

## 推荐阅读顺序

1. 了解 V2 改造计划 → `PLATFORM_V2_ROADMAP.md`
2. 了解 V2 架构 → `ARCHITECTURE.md`
3. 了解产品 → `CORE_PLATFORM.md`
4. 新开发者 → `DEV_GUIDE.md`（如何创建 App / 字段 / 模板）
5. 打包给别人 → `PACKAGING.md`
6. 自己上线 → `BAOTA_STATIC_DEPLOY.md` 或 `NATIVE_DEPLOY.md`
7. 接官网 → `addons/WEBSITE_CMS.md`

## 脚本对照

| 脚本 | 文档 |
|------|------|
| `scripts/package-core.sh` | [PACKAGING.md](PACKAGING.md) |
| `scripts/deploy-baota-static.sh` | [BAOTA_STATIC_DEPLOY.md](BAOTA_STATIC_DEPLOY.md) |
| `scripts/install-native.sh` | [NATIVE_DEPLOY.md](NATIVE_DEPLOY.md) |
| `scripts/gen-secrets.sh` | [PACKAGING.md](PACKAGING.md) |
| `scripts/restart-backend-host.sh` | [BAOTA_STATIC_DEPLOY.md](BAOTA_STATIC_DEPLOY.md) |
| `scripts/migrate-and-seed-host.sh` | [BAOTA_STATIC_DEPLOY.md#625-迁移首次--升级](BAOTA_STATIC_DEPLOY.md) |
