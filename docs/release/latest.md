# 当前发布产物

> 压缩包存放在服务器 `release/` 目录，不纳入 git。本文档记录最近一次打包信息。

| 项 | 值 |
|----|-----|
| 类型 | 核心平台（不含官网） |
| 版本 | 0.5.15 |
| 打包日期 | 2026-11-04 |
| 文件名 | `cenkor-admin-core-0.5.15-20261104.tar.gz` |
| 路径 | `/www/wwwroot/cenkor-admin/release/` |
| 打包命令 | `bash scripts/package-core.sh` |
| 发布页 | `https://github.com/likele001/cenkor-admin/releases/tag/v0.5.15` |
| 容器镜像 | `ghcr.io/likele001/cenkor-admin:0.5.15`（amd64 / arm64） |

详细说明见 [../packaging.md](../packaging.md)。

## 最近几个版本

| 版本 | 日期 | 主要变化 |
|------|------|----------|
| 0.5.15 | 2026-11-04 | 依赖安全加固：dompurify critical、axios 13 条、vite 6、vue-i18n 11；改写稿 Markdown 渲染；修内链建议 max_tokens |
| 0.5.14 | 2026-11-03 | CI 门禁恢复绿：AppID 占位符不再撞密钥扫描、清理 108 处 lint、isort 显式声明 |
| 0.5.13 | 2026-11-03 | 迁移规范按真实拓扑重写，废弃会自动顺延的 `rebase_closed_chain` |
| 0.5.12 | 2026-11-03 | 闭源链合流为单 head，迁移图检查改为「公开严格、闭源放宽」 |
| 0.5.11 | 2026-11-03 | 支付交易层开源：payment + commerce 随平台同 MIT 交付，不单独收费 |

## 版本号从哪儿看

单一来源是 `backend/src/cenkor_admin/VERSION`，`release.json` 里的
`version` 与它同步由 `scripts/release.sh` 保证；CI 的 Preflight 会校验
tag 与 VERSION 一致，不一致直接失败。
