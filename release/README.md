# release/

本地打包产物目录（`*.tar.gz` 已 gitignore，不提交）。

| 说明 | 文档 |
|------|------|
| 如何打包、包内清单、部署步骤 | [`../docs/PACKAGING.md`](../docs/PACKAGING.md) |
| 发版日志 | [`../docs/release/CHANGELOG.md`](../docs/release/CHANGELOG.md) |
| 最近一次打包 | [`../docs/release/LATEST.md`](../docs/release/LATEST.md) |

```bash
bash scripts/package-core.sh
ls -lh release/
```
