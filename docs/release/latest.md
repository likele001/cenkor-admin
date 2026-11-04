# 当前发布产物

> 压缩包存放在服务器 `release/` 目录，不纳入 git。本文档记录最近一次打包信息。

| 项 | 值 |
|----|-----|
| 类型 | 核心平台（不含官网） |
| 版本 | 0.5.19 |
| 打包日期 | 2026-11-04 |
| 文件名 | `cenkor-admin-core-0.5.19-20261104.tar.gz` |
| 路径 | `/www/wwwroot/cenkor-admin/release/` |
| 打包命令 | `bash scripts/package-core.sh` |
| 发布页 | `https://github.com/likele001/cenkor-admin/releases/tag/v0.5.19` |
| 容器镜像 | `ghcr.io/likele001/cenkor-admin:0.5.19`（amd64 / arm64） |

详细说明见 [../packaging.md](../packaging.md)。

## 最近几个版本

| 版本 | 日期 | 主要变化 |
|------|------|----------|
| 0.5.19 | 2026-11-04 | 修 corporate 主题 Hero 在真实页面从未显示（分页字段名对不上）；`build_pagination` 增加 `current` 别名；后台预览补齐 theme / is_home / 组件声明 |
| 0.5.18 | 2026-11-04 | widget 组件沙箱：模板可带交互组件，跑在 opaque origin 的 iframe 里，开放交互但不需要同源权限；内置 corporate 加 stats 组件样板 |
| 0.5.17 | 2026-11-04 | 公开页严格 CSP + 主题资源路由 + 内联脚本拦截；`theme.json` 包规范、3 个官方样板主题、主题配置表单、打包 CLI |
| 0.5.16 | 2026-11-04 | 稿件版本对比；站内搜索词日志（新表 + 选题真实信号）；AI 事实溯源（只告警不阻断）；官网产物移出 git、修打包漏文档中心 |
| 0.5.15 | 2026-11-04 | 依赖安全加固：dompurify critical、axios 13 条、vite 6、vue-i18n 11；改写稿 Markdown 渲染；修内链建议 max_tokens |
| 0.5.14 | 2026-11-03 | CI 门禁恢复绿：AppID 占位符不再撞密钥扫描、清理 108 处 lint、isort 显式声明 |
| 0.5.13 | 2026-11-03 | 迁移规范按真实拓扑重写，废弃会自动顺延的 `rebase_closed_chain` |
| 0.5.12 | 2026-11-03 | 闭源链合流为单 head，迁移图检查改为「公开严格、闭源放宽」 |
| 0.5.11 | 2026-11-03 | 支付交易层开源：payment + commerce 随平台同 MIT 交付，不单独收费 |

## 版本号从哪儿看

单一来源是 `backend/src/cenkor_admin/VERSION`，`release.json` 里的
`version` 与它同步由 `scripts/release.sh` 保证；CI 的 Preflight 会校验
tag 与 VERSION 一致，不一致直接失败。
