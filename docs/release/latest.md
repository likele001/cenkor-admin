# 当前发布产物

> 压缩包存放在服务器 `release/` 目录，不纳入 git。本文档记录最近一次打包信息。

| 项 | 值 |
|----|-----|
| 类型 | 核心平台（不含官网） |
| 版本 | 0.5.20 |
| 打包日期 | 2026-11-04 |
| 文件名 | `cenkor-admin-core-0.5.20-20261104.tar.gz` |
| 路径 | `/www/wwwroot/cenkor-admin/release/`（与 GitHub Release 附件同一份） |
| 打包命令 | CI 自动（`scripts/package-core.sh`，tag 触发） |
| 发布页 | `https://github.com/likele001/cenkor-admin/releases/tag/v0.5.20` |
| 容器镜像 | `ghcr.io/likele001/cenkor-admin:0.5.20`（amd64 / arm64） |
| SHA256 | `04ae9b80873014ceb965ff50d811dc5caf58f06dd438afa87faf95bd50bfc089` |

详细说明见 [../packaging.md](../packaging.md)。

> **已知瑕疵**：0.5.20 的包内 `release.json` 仍是 `0.5.19`。当时 `release.sh` 在「VERSION
> 已是目标版本」时直接退出，声明文件没同步；打包发生在修正之前。包内 `VERSION` 是正确的
> `0.5.20`，安装后以站点 `VERSION` 为准。该缺陷已在 `release.sh` 修复，下个版本起包内声明
> 不再落后，CI Preflight 也会拦住漂移。

## 最近几个版本

| 版本 | 日期 | 主要变化 |
|------|------|----------|
| 0.5.20 | 2026-11-04 | 模板市场：商店新增 `theme` 商品类型 + `theme.json` 包规范与校验器；后台「内容管理 → 模板市场」浏览官方目录并一键安装；开发者门户补「发布主题模板」入口与主题开发文档；官方样例主题 墨痕 Inkwell / 青云 Qingyun |
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
`version` 与它同步由 `scripts/release.sh` 保证。

```
bash scripts/release.sh check    # 只检查，漂移退出码 1（CI 也跑这个）
bash scripts/release.sh sync     # 按当前 VERSION 对齐 release.json（修漂移）
bash scripts/release.sh patch    # 正常发版：抬版本 + 同步声明
```

CI 的 Preflight 会同时校验三处一致：tag、`VERSION`、`release.json` 的 `version`。
任何一处不一致直接失败，不会再出现「tag 打了、声明没跟」的半成品发版。
