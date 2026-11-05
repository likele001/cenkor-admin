# 当前发布产物

> 压缩包存放在服务器 `release/` 目录，不纳入 git。本文档记录最近一次打包信息。

| 项 | 值 |
|----|-----|
| 类型 | 核心平台（不含官网） |
| 版本 | 0.5.21 |
| 打包日期 | 2026-11-05 |
| 文件名 | `cenkor-admin-core-0.5.21-20261105.tar.gz` |
| 路径 | `/www/wwwroot/cenkor-admin/release/`（与 GitHub Release 附件同一份） |
| 打包命令 | CI 自动（`scripts/package-core.sh`，tag 触发） |
| 发布页 | `https://github.com/likele001/cenkor-admin/releases/tag/v0.5.21` |
| 容器镜像 | `ghcr.io/likele001/cenkor-admin:0.5.21`（amd64 / arm64） |
| SHA256 | `d9e2c290c445ad16912eeea1c0f682ac2f0dccaffdfdb96108e5a40ec0fc24b5` |

详细说明见 [../packaging.md](../packaging.md)。

> **包内声明已对齐**：0.5.21 的包内 `VERSION` 与 `release.json` 均为 `0.5.21`。
> 0.5.20 曾出现「包内 `release.json` 落后一版」的瑕疵，根因是 `release.sh` 在版本未变时
> 直接退出；该缺陷已修（新增 `sync` / `check`），CI Preflight 也会在打包前拦住漂移。

## 最近几个版本

| 版本 | 日期 | 主要变化 |
|------|------|----------|
| 0.5.21 | 2026-11-05 | 发版链路加固：`release.sh` 补 `sync`/`check` 并容忍 CRLF，CI 增加 `release.json` ↔ `VERSION` 一致性闸门；修复发布页 Docker 镜像名缺 owner；模板市场提交限定门户账号、后台已安装列表 Tab 串页修复；新增宝塔 Nginx 反代与伪静态配置说明 |
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
