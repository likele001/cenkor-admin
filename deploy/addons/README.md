# 可选部署扩展（Addons）

核心平台见 [`docs/core_platform.md`](../../docs/core_platform.md)。  
本目录存放**非必需**的集成配置，按需复制到宝塔或 nginx。

| 目录 | 用途 | 文档 |
|------|------|------|
| [`website/`](website/) | 外部营销站 + CMS 公开 API | [`docs/addons/website_cms.md`](../../docs/addons/website_cms.md) |

新增扩展建议：`deploy/addons/<name>/` + `docs/addons/<NAME>.md`，不修改核心 `deploy/baota/` 与 `scripts/deploy-baota-static.sh`。
