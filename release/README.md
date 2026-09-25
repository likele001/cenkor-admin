# release/

本地打包产物目录（`*.tar.gz` 已 gitignore，不提交）。

| 说明 | 文档 |
|------|------|
| 如何打包、包内清单、部署步骤 | [`../docs/packaging.md`](../docs/packaging.md) |
| 发版日志 | [`../docs/release/changelog.md`](../docs/release/changelog.md) |
| 最近一次打包 | [`../docs/release/latest.md`](../docs/release/latest.md) |

```bash
bash scripts/package-core.sh
ls -lh release/
```
