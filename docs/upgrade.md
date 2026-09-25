# 升级指南（UPGRADE）

本文说明 **Cenkor Admin 核心平台** 发布新版本后，不同部署方式如何升级，以及维护者如何发版。

> 先分清两层"升级"：
> - **可插拔应用**（ERP / MES / CRM 等）：在后台「应用中心 / 应用商店」用授权码一键 OTA 升级，**免重启**。见 [dev_guide.md](dev_guide.md)。
> - **核心平台**（backend + admin-web + portal-web）：本文主题。核心改动涉及进程本身、数据库结构、前端产物，需"换代码 → 迁移 → 重启"。

---

## 一、我怎么知道有新版本？

- 升级到最新版后，平台会向官方中心查询最新版本（`GET /api/v1/release/latest`），与本地版本比较。
- 有新版本时，**管理后台工作台**顶部会出现"🆙 发现新版本 x.y.z"横幅，附「查看升级方式」「更新日志」链接。
- 检查逻辑：由环境变量 `RELEASE_CHECK_URL`（留空回退 `CENKOR_CLOUD_URL`）指向官方云；两者都留空 = 本机即中心，不联网检查。结果缓存 6 小时（`RELEASE_CHECK_TTL_HOURS`）。
- 关闭某版本提示后，同一版本不再打扰；有新版本号会再次提示。

---

## 二、用户升级：按部署方式选择

> 本机生产用的是 **B. 宿主机 / 宝塔 venv 部署**。A（Docker）留给交付环境。

### A. Docker 部署（交付环境用）

```bash
docker compose -f docker-compose.baota.yml pull      # 拉取最新镜像（:latest 或指定版本 tag）
docker compose -f docker-compose.baota.yml up -d      # 滚动更新，启动时自动 alembic upgrade head
```

回滚：把镜像 tag 换回旧版本号再 `up -d` 即可。

### B. 宿主机 / 宝塔 venv 部署（**本机生产用的是这种**）

```bash
# 方式 1：从 GitHub Release 下载核心包升级（<date> 为发版日期，如 20260924）
bash scripts/upgrade.sh --url https://github.com/likele001/cenkor-admin/releases/download/v0.2.0/cenkor-admin-core-0.2.0-<date>.tar.gz

# 方式 2：已有核心包
bash scripts/upgrade.sh --tar /path/to/cenkor-admin-core-0.2.0.tar.gz

# 方式 3：Git 仓库用户
bash scripts/upgrade.sh --git
```

脚本流程：**备份数据库 → 覆盖代码（保留 .env / uploads / logs）→ pip 安装依赖 → alembic 迁移 → 重启后端 → 健康检查**。任一步失败即中止并提示回滚用的备份文件路径。

常用参数：`--skip-backup`（跳过备份）、`--python <路径>`（指定 venv python）。

### C. 手动升级（进阶）

```bash
# 1. 备份
bash scripts/backup.sh
# 2. 更新代码（git pull 或解压核心包覆盖，保留 .env）
# 3. 依赖
cd backend && pip install -r requirements.txt
# 4. 迁移（其实重启后端时 lifespan 会自动 upgrade head）
PYTHONPATH=src alembic upgrade head
# 5. 重启
bash scripts/restart-backend-host.sh
```

---

## 三、版本号从哪来？

- **单一来源**：`backend/src/cenkor_admin/VERSION` 文件。
- 后端 `__version__`、`config.APP_VERSION`、打包脚本 `package-core.sh`、镜像脚本 `build-multiarch.sh` 全部读它，不再各写各的。
- 可用环境变量 `APP_VERSION` 临时覆盖。

---

## 四、维护者发版流程

```bash
# 1. 抬版本号 + 更新中心声明文件 release.json（version / released_at / notes）
bash scripts/release.sh 0.2.0 --notes "修复 xxx；新增 yyy"
#    也可自动递增：bash scripts/release.sh patch | minor | major

# 2. 提交并打 tag —— 推送 tag 即触发 CI 自动发版（见下）
git add -A && git commit -m "release: v0.2.0" && git tag v0.2.0 && git push --follow-tags

# 3. 打核心包（供裸机用户 --url/--tar 升级）
bash scripts/package-core.sh            # → release/cenkor-admin-core-0.2.0-*.tar.gz

# 4. 构建并推送多架构镜像到 GitHub 容器镜像库（ghcr.io，供 Docker 用户 pull）
#    先登录一次：echo $GITHUB_TOKEN | docker login ghcr.io -u likele001 --password-stdin
REGISTRY=ghcr.io/likele001 bash docker/fullstack/build-multiarch.sh --push

# 5. 把新的 release.json 部署到官方云（hub），并把核心包上传到 GitHub Release
#    —— spoke 实例即可在工作台检测到 v0.2.0
```

发版后别忘了同步更新后台「系统更新日志」置顶公告（工作台展示的就是它）。

### 自动发版（推荐）

仓库已配置 `.github/workflows/release.yml`：**只要 push 以 `v` 开头的 tag（如 `v0.2.0`），CI 会自动完成上面的 3~5 步**：

1. 校验 tag 与 `VERSION` 文件一致（不一致直接失败，防止误发）；
2. 跑 `package-core.sh` 打核心包并上传为 GitHub Release 附件；
3. `build-multiarch.sh --push` 构建 amd64/arm64 多架构镜像推送到 `ghcr.io/<你的用户名>`；
4. 自动创建带说明的 GitHub Release。

所以日常发版只需两条命令：

```bash
bash scripts/release.sh 0.2.0 --notes "修复 xxx；新增 yyy"
git push && git push --tags
```

> 前置条件：仓库 Settings → Actions → General 里 Workflow permissions 选 **Read and write permissions**（GITHUB_TOKEN 需 `packages:write` / `contents:write` 推 ghcr 和建 Release，本文件顶部已声明）。首次推送的 ghcr 包默认私有，需在包设置里改为 Public，外部用户才能免登录 `docker pull`。

### 手动发版（不想用 / 暂不能用 CI 的备选）

GitHub 对 Actions 账号有付款验证要求（公开仓库本身免费，但需绑卡验证身份，可把消费上限设为 $0）。若账号被账单锁定或不想碰信用卡，可全程手动，效果与 CI 完全一致：

```bash
# 1. 抬版本（同自动流程）
bash scripts/release.sh 0.2.0 --notes "修复 xxx；新增 yyy"

# 2. 本地打核心包（不需要 GitHub 账号，纯本地操作）
bash scripts/package-core.sh        # → release/cenkor-admin-core-0.2.0-<date>.tar.gz

# 3. 本地构建多架构镜像并推送到 ghcr（只需 Docker，不占 Actions）
#    需先建一个带 write:packages 权限的 token（Fine-grained → Packages: Read/Write）
echo <token> | docker login ghcr.io -u likele001 --password-stdin
REGISTRY=ghcr.io/likele001 bash docker/fullstack/build-multiarch.sh --push

# 4. 上传核心包 + 建 Release：网页操作最稳
#    github.com/likele001/cenkor-admin/releases → Draft a new release
#    tag 选/输入 v0.2.0，把第 2 步的 tar.gz 拖进附件区，发布

# 5. 最后再推 tag（本地已有 v0.2.0 的话）
git push --tags
```

注意事项：

- 手动路径依赖本机有 Docker + buildx（arm64 交叉构建首次执行 `docker run --privileged --rm tonistiigi/binfmt --install all` 启用 QEMU）。
- 推 tag 仍会触发一次 Release 工作流；账号未解锁前它会秒失败，**不影响已手动完成的发版**，忽略即可。
- ghcr 首次推送的包默认私有：网页进入 ghcr.io/likele001/<包名> → Package settings → Change visibility → Public，否则用户 `docker pull` 会报 unauthorized。
- 账单修好后无需任何迁移：继续用 tag 自动发版即可，两条路径产物格式一致。

---

## 五、回滚

| 部署 | 回滚方式 |
|------|----------|
| **宿主机 / 宝塔（本机）** | 换回旧代码 + 恢复数据库备份，在宝塔面板重启 Python 项目 `cenkor` |
| Docker | `docker compose ... up -d` 指定旧镜像 tag |
| 裸机 | 用 `upgrade.sh` 打印的备份 `pg_*.sql.gz` 恢复数据库，再用旧核心包 `--tar` 重装并重启 |

数据库恢复示例：

```bash
gunzip -c /www/backup/cenkor-admin/pg_<STAMP>.sql.gz | \
  PGPASSWORD=<pwd> psql -h 127.0.0.1 -p 5432 -U cenkor -d cenkor
# 本机生产的 PostgreSQL 在宿主机 5432（不是容器 5433）
```

---

## 六、注意事项

- **迁移只前进**：核心发版的 alembic 迁移务必向后兼容或提供 downgrade；升级前一定先备份。
- **不要手改 VERSION / release.json 不一致**：统一用 `scripts/release.sh`。
- **开源版无 commerce 模块**：`/store` 定价/授权/分成等闭源能力缺失时会自动静默跳过，不影响升级与启动。
- 生产环境 `RELEASE_CHECK_ENABLED` 可按需关闭横幅检查。
