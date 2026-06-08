# 发布记录

本目录用于**存放打包产物说明与发版日志**。压缩包文件本身在仓库根目录 `release/`（已 `.gitignore`，不提交 git）。

## 产物命名

```
release/cenkor-admin-core-<version>-<YYYYMMDD>.tar.gz
```

## 发版日志

### 0.1.0 · 2026-06-07

- 首次核心平台打包脚本 `scripts/package-core.sh`
- 包含：backend、admin-web/portal-web（源码 + dist）、宝塔/systemd/Docker 部署配置
- 不含：官网 addon、node_modules、生产密钥
- 文档：`docs/PACKAGING.md`、`docs/CORE_PLATFORM.md`

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
