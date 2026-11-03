# Cenkor Admin 系统更新日志

> **唯一事实源**：本文件顶部为最新版本。发版时在标题行下方插入新版本段，后台首页「系统更新日志」公告约 30 秒内自动同步（无需重启服务、无需人工改公告）。
>
> 版本段格式：
>
> ```markdown
> ## YYYY-MM-DD　标题（⭐ = 重点版本）
>
> **【分组名】**
>
> - 要点一
> - 要点二
> ```

## 2026-11-03　支付中心与应用交易层开源：payment / commerce 随仓交付（⭐）

**【开源范围变更】收款能力是底座，不该收在闭源里**

支付中心 `apps/payment`（支付宝官方 / 微信支付官方 / 虎皮椒聚合三通道 +
收银台 + 订单 + 通道配置，3398 行）与生态交易层 `apps/commerce`
（定价 / 订单 / 授权签发 / 云端绑定，4994 行）此前源码放在外置目录、
被 `.gitignore` 整体排除。本次一并迁回内置目录，与平台同 MIT 授权，
**不单独收费、不需要授权码**。

- 源码位置：`backend/src/apps/{payment,commerce}/`
  → `backend/src/cenkor_admin/apps/{payment,commerce}/`
- 顺带清掉 4 个历史 `.bak_*` 手工备份（本就不该跟着源码流浪）
- `static/apps/payment/plugin.js`、`docs/05-用户手册/payment_操作手册.md`
  一并入库随包交付

> 为什么不给支付单独留个授权位：`payment/manifest.py` 里它自己标着
> `builtin=True`（"删了商店/套餐/订单付不了账"）。底座不开源、却把下游应用
> 标成商业闭源，买到商业应用的用户也跑不起一笔结算 —— 逻辑上是拧着的。

**【安全】授权体系：开源 77 行签发逻辑，但私钥不入库**

`commerce/license_authority.py` 是 Ed25519 私钥生成 + 签名签发，
文件头原本写着「只部署在授权中心」。本次判断可以开源，理由记在这里：

- 私钥**不在源码里**：`get_or_create_keypair` 首次调用时现场生成，
  以密文存进 `system_settings.license.signing_key`，随部署环境走
- 客户实例只内置**公钥**（`core/licensing.DEFAULT_PUBLIC_KEY_B64`）做验签
- Ed25519 的安全性只依赖私钥保密，不依赖算法实现保密（Kerckhoffs 原则）——
  拿到全部源码但没有私钥，依然伪造不出有效授权
- 反过来，不开源会让自营部署签不出授权，商店功能是残的

**【修复】迁移图合流：公开链恢复单 head**

开源后这些迁移要进公开仓库，但它们挂在闭源链中间，父节点拿不到：

| 迁移 | 原 `down_revision` | 问题 |
|---|---|---|
| `20260922_0020_commerce` | `20260904_mes_0009` | ERP→CRM→MES 闭源链尾 |
| `20261007_0029_product_commerce` | `20260925_0027_workflow` | workflow 仍闭源 |

直接改挂到公开链尾会切断 erp/crm/mes 与主链的连接，它们变成「未应用分支」，
`upgrade heads` 会把 ERP 全部迁移重跑一遍（撞 `DuplicateTable`）。故新增
合流迁移 `20261103_1200_merge_commerce`：把公开链并行的两条分支
（`20261103_1100_cms_orphan` 与 `20261020_0035_app_publish`）并成一个点，
commerce 段挂到合流点之后，`product_commerce_0029` 改挂它真正依赖的
`20260924_0025_cloud`。

- 公开视图：59 个迁移，**单 head** `20261027_0100_app_schema`，无断链
- 完整视图：`mes_0009` / `workflow_0027` / `collect_1100` 三个 head，
  `upgrade heads` 各自独立推进
- `alembic_version` 由 `(collect, cms_orphan)` 迁移为
  `(mes_0009, workflow_0027, collect)`；实测 `upgrade heads` 零 DDL

**【校验】开工前对支付应用做了敏感信息扫描**

- 无私钥 / 证书文件（`-----BEGIN PRIVATE KEY-----` 只是配置项的 placeholder 文案）
- 无硬编码密钥、商户号（正则扫 `secret|apikey|appsecret|mch_id` 赋值，零命中）
- 配置全部走 `settings` / 环境变量，敏感值用 Fernet（密钥由 `SECRET_KEY`
  经 PBKDF2 派生）加密存储

**【文档】口径同步**

- `README.md`：许可适用范围里支付从「需单独授权」移入「已开源不收费」，
  补上 workflow / collect 两个此前漏登记的闭源项
- `CONTRIBUTING.md`：分层表格新增"改支付中心 / 应用交易层 ✅ 欢迎"一行
- `docs/packaging.md`、`docs/apps/development_guide.md`：闭源清单去掉 payment
- 代码注释 19 处 + `license_authority.py` 模块文档重写（原「闭源」定性已不成立）

---

## 2026-11-03　新增 CONTRIBUTING.md：贡献入口与提交门禁（⭐）

**【新增】根目录 `CONTRIBUTING.md`（193 行）**

把「提交前必须知道的硬约束」集中到一处，省得每个贡献者重新踩一遍：

- **分层说明**：哪些目录可以直接提 PR（核心 / 前端 / 新增 App / 驱动插件），
  哪些（ERP / CRM / MES / 支付 / 开发者门户）**不在仓库内**、提不了。
  并点明改 `apps/base.py` 的 `AppManifest` 契约会波及仓库外的商业应用，
  这类改动需在 PR 里说明兼容性影响
- **七道门禁**：与 CI 逐条对应的可复制命令（`pip check` / `ruff check` /
  `check-migration-graph.py` / `alembic upgrade heads` /
  `check-orm-drift.py` / 单元测试 / 前端 `type-check` + `build`），
  并说明 6 个集成测试需真 uvicorn + seed、本地 skip 或报错属正常
- **迁移改动**：改了 models 就必须同时有迁移，否则 alembic 不报错、单测测不到，
  只有 ORM 漂移检查会红（引用 `migrations.md` 与
  `database-migrations.md` §12.1，不重复正文）
- **提交信息**：Conventional Commits + 中文，附 6 条真实历史提交作示例；
  特别提醒「别整文件改写行尾」—— 仓库有部分 CRLF 文件，
  一个改 3 行的提交会变成 2000 行 diff
- **贡献授权**：提交 PR 即视为按 MIT 授权（inbound = outbound），
  当前**不要求签署 CLA**，将来若引入会事先在文件里说明
- **禁止提交**：密钥 / 生产数据 / 构建产物 / 闭源代码；
  并给出「密钥已误提交 → 先当它已泄漏、立刻轮换，再处理 git 历史」的处置顺序

**【入口】**

- README 顶部导航新增「🤝 参与贡献」一行，与「文档索引 / 迁移规则 / 打包交付」并列

**【核对】**

- 文档内 7 个相对链接 + 2 个代码路径**全部实测存在**，0 死链
- `check-migration-graph.py --tracked-only`（49 迁移 / 单 head）、
  `check-doc-facts.py`（33 份文档 / 260 表 / 69 路由）、
  `check-app-tracking.sh` 全绿
- README 保持 LF 行尾，diff 仅 **+1 行**；新文件为 LF

## 2026-11-03　许可证声明补齐：明确 MIT 的适用范围（⭐）

**【核对结论：确实是 MIT，且分发合规】**

- `LICENSE` 为标准 MIT 全文，`Copyright (c) 2026 李可乐`
- GitHub 识别 `spdx_id = MIT`，仓库 public
- `backend/pyproject.toml` 的 `license = "MIT"` 与之一致
- 实测 v0.5.8 发行包（1098 条目）：根目录带 `LICENSE` 且内容完整，
  **无任何闭源代码混入**，MIT 要求「所有副本附带版权声明」这一点是满足的

**【修复：两处声明缺失】**

- `frontend/admin-web`、`design-tokens`、`landing-web`、`portal-web`
  四个 `package.json` 补 `"license": "MIT"`。此前 npm 生态与 SPDX 扫描工具
  读到的是 `UNKNOWN`
- `frontend/developer-web` **刻意不加**：它是闭源资产、在 `.gitignore` 里，
  标 MIT 会与商业授权冲突
- README 许可章节新增「适用范围」：说明许可仅覆盖仓库内 git 跟踪的内容，
  ERP / CRM / MES / 支付 / 开发者门户不在仓库内、不适用本许可、需单独授权；
  并提醒混合部署场景下不要误读根目录 `LICENSE`

**【为什么补适用范围】**

MIT 只覆盖实际存在于仓库的文件，闭源代码不在仓库 → 法律上没问题。
但客户拿到「开源内核 + 商业应用」混装时，根目录的单个 `LICENSE`
容易被理解为对全部目录的授权，进而以为有权再分发商业应用。
写清边界比事后解释便宜。

## 2026-11-03　依赖门禁：CI 与升级路径双双加对账（⭐）

**【背景：上一轮的 4 条冲突是怎么漏过去的】**

出事前 `pip check` 报 4 条，但没有人在日常流程里跑它。补门禁时先做了实测，
结论比预想的更值得记一笔：

- **CI 里加 `pip check` 抓不到那次事故**。干净环境里 `boto3>=1.34.0` 没有上界，
  pip 直接解到 `boto3 1.43.117` + `aiobotocore 3.10.0` + `botocore 1.43.117`，
  三者自洽，`pip check` 输出 `No broken requirements found`
- 生产那 4 条冲突的真身是**环境漂移**：`aiobotocore` 长期停在 2023 年的 2.5.0
  （钉死 `botocore 1.29.76`），声明 `>=2.5.0` 并未被违反，所以任何只看声明的检查
  都不会报警
- **顺带查出一个更严重的隐患**：旧声明在全新环境解出的是 `aiobotocore 3.10.0`，
  而生产跑的是 2.26.x —— CI 与生产测的根本不是同一个大版本的 S3 SDK。
  v0.5.7 补的 `aiobotocore>=2.26.0,<3` 上界恰好把这处对齐了，属意外收获

**【改动】**

- `.github/workflows/ci.yml`：依赖安装后新增 `pip check` 步骤。定位是保险，
  不是主力——它能挡的是「多步安装中后一步把前一步的包降级」这类破损元数据
- `scripts/upgrade.sh`：依赖安装前存 `pip freeze` 快照到
  `$BACKUP_DIR/req-before-<时间戳>.txt`，安装后跑 `pip check` 对账。
  **漂移发生在增量升级路径上，所以真正的拦截点在这里**；冲突时逐条打印并给出
  用快照回滚依赖的确切命令
- 冲突不阻断升级（打印警告），与脚本原有的「依赖安装报错可忽略」策略保持一致

**【验证】**

- 复刻 CI 环境（py3.12 + `requirements.txt` + CI 专用工具）`pip check` 干净，
  确认新门禁不会让现有流水线变红
- 从 `upgrade.sh` 里抽出真实代码块跑了两个分支：干净环境输出「✓ 依赖自洽」；
  用 `pip install --no-deps boto3` 造出破损环境后，逐条列出 3 项缺失并打印回滚命令
- `bash -n scripts/upgrade.sh` 通过；`ci.yml` YAML 解析通过，CRLF 行尾保持

## 2026-11-03　依赖清理：pip check 归零，S3 链路升到 aiobotocore 2.26（⭐）

**【修复：4 条 pip check 冲突，根子只有一个】**

- 起因：`pip check` 报 4 条 broken requirements，看似四个独立问题
- 根因：`aiobotocore 2.5.0` 钉死 `botocore>=1.29.76,<1.29.77`（**精确到单个补丁版本**），
  而 botocore 1.29.76 又钉死 `urllib3<1.27`，于是三面撞车：
  `boto3` 要 botocore ≥1.34、`s3transfer` 要 ≥1.33.2、
  `trafilatura` / `htmldate` 要 urllib3 ≥2.8.0
- 删掉 `boto3` 声明：代码里**零引用**，唯一依赖者是 `kombu[sqs]` 的 extra，
  项目用 `celery[redis]`，从未启用
- `aiobotocore` `>=2.5.0` → `>=2.26.0,<3`，连带 `botocore 1.29.76 → 1.41.5`、
  `urllib3 1.26.20 → 2.8.0`
- 为什么 2.26 能解开 urllib3 死结：botocore 1.41 的 `urllib3<1.27` 带
  `python_version < "3.10"` 条件，本项目跑 3.13，**条件不生效**
- 上界 `<3` 是必须的：2.x 每个版本钉一个 botocore，不加上界时全新环境
  会直接解到 3.10.0（botocore 1.43.x），与现存行为差一个大版本

**【验证：先独立 venv 跑通，再动生产】**

- 目标组合（aiobotocore 2.26.0 / botocore 1.41.5 / urllib3 2.8.0 /
  trafilatura 2.3.1 / htmldate 1.11.0 / requests 2.34.2）`pip check` 无冲突
- 用项目真实 `S3CompatDriver` 跑 10 项全过：health_check / ensure_bucket /
  upload_fileobj / head_object / get_object 内容一致 / list_objects /
  presigned_put_url / presigned_get_url / copy_object / delete
- 生产真实链路（`QiniuKodoDriver` + 凭证解密）：上传、直连签名 URL 回读、
  公有 URL 回读全部 200 且内容一致
- `trafilatura` 在 urllib3 2.8.0 下 `extract` / `bare_extraction` 正常
- 后端测试与升级前**完全一致**（185 passed / 36 skipped / 1 failed / 11 errors，
  均为既有的 aiosqlite 缺失与 sqlite 方言环境问题）
- 升级后 `pip check`：**No broken requirements found**

**【顺带发现一个既有瑕疵（本轮未修）】**

- `presigned_get_url` 生成后会经 `_apply_cdn_domain` 把 host 换成 CDN 域名，
  而 CDN 不认识 S3 签名参数 → 该 URL 返回 404
- 实测同一对象：直连签名 URL **200**、公有 URL **200**、CDN 变换 URL **404**
- 私有对象的签名访问应走直连 endpoint，CDN 域名只适合公有读；单独排期修

## 2026-11-03　bcrypt 4.1+ 兼容：口令上下文收敛 + 垫片（⭐）

**【修复：passlib 版本探测告警】**

- 现象：seed 首次建管理员、或服务首次 hash/verify 口令时打印
  `(trapped) error reading bcrypt version`
- 根因：`passlib/handlers/bcrypt.py:620` 读 `bcrypt.__about__.__version__`，
  bcrypt ≥ 4.1 已删除 `__about__`；passlib 捕获后走「版本未知」分支
- 功能本就正常，但日志噪音会掩盖真实故障，且说明跑在**未声明**的版本上

**【改动】**

- 新增 `core/pwd.py`：全站唯一 `CryptContext`，导入时补回 `__about__` 垫片
- `core/security.py`、`apps/portal/auth.py` 原先**各建一份** `CryptContext`，
  改为复用同一实例——参数一旦分叉，典型症状就是「改完密码登录不了」
- 依赖约束 `bcrypt>=3.2.0,<4.0` → `bcrypt>=4.1,<5`
  （`<5` 是为规避 bcrypt 5.0 把超 72 字节口令由「静默截断」改为「抛 ValueError」）
- 新增 `tests/test_password_context.py`：垫片在位 / 单实例 / 跨模块 `$2b$` 互通

**【取 B 方案：放宽约束，而不是降级 bcrypt】**

- 备选 A（重装 3.2.x）能让告警消失，但等于把环境钉回两年前的版本，
  后续任何依赖 bcrypt 4.x 的包都会再撞一次
- 选 B：放宽声明 + 兼容垫片，环境与声明一致，且前向兼容到 4.x 任意小版本
- **哈希输出仍是 `$2b$12$`，历史口令零迁移**

**【验证】**

- 生产库实测：`auth_users` 29 条、`portal_users` 24 条，全部 `$2b$12$`，
  `pwd_context.identify()` 均返回 `bcrypt`
- 对照实验：裸 passlib 复现 `AttributeError: module 'bcrypt' has no attribute
  '__about__'`；走 `core.pwd` 则静默、哈希与校验全部正常
- ruff 全绿；`test_password_context.py` 3 条 + `test_security.py` 3 条全过

## 2026-11-03　交付文档修正：包内迁移 head 不再写死（⭐）

**【修正：PACKAGE.md 声称的 head 已过期】**

- v0.5.3 往公开链末尾补了 `20261103_1100_cms_orphan`，但 `scripts/package-core.sh`
  里 PACKAGE.md 的文案仍写死「迁移链唯一 head 为 `20261031_1600_cms_permalink`」
- 后果：每个 Release 包的说明都在告诉用户一个**过期 head**，照此核对会误以为包是旧的
- 改为打包时实算：head 取自 `check-migration-graph.py --tracked-only`，
  迁移数取自 `git ls-files`，两者一起写进 PACKAGE.md
- `docs/packaging.md` 里同样的写死示例（「44 个迁移」/旧 head）改为占位表述，
  并明确「不要在文档里写死 revision，迁移一加就会过期」

**【验证：把 Release 包真装一遍】**

- 下载 v0.5.4 的 Release 资产（`cenkor-admin-core-0.5.4-20261103.tar.gz`，4.1 MB），
  在空库上走完整路径：`alembic upgrade heads` → `seed`
- 结果：49 个迁移全部执行、head `20261103_1100_cms_orphan`、86 张基表、
  v0.5.3 补的 6 张表与 18 个字段齐全、seed 全绿
  （permissions 48 / menus 50 / roles 3 / users 1 / store listed=9 manifests=9）、
  ORM 漂移 79 张全绿、幂等复跑 no-op
- 包内无 erp / crm / mes / workflow / payment，也无 `src/apps`，闭源未泄漏

**【已知噪音，不是缺陷】**

> **已由 v0.5.6 修复**：口令上下文收敛到 `core/pwd.py` 并补 `__about__` 垫片，
> 依赖约束放宽为 `bcrypt>=4.1,<5`。以下为当时的分析，保留备查。

- seed 首次创建管理员时会打印 `(trapped) error reading bcrypt version`：
  passlib 1.7.4 读 `bcrypt.__about__.__version__`，而 bcrypt ≥ 4.1 已移除该属性。
  功能正常（passlib 内部已捕获，seed 退出码 0）。
  `requirements.txt` 已 pin `bcrypt>=3.2.0,<4.0`，按文档安装不会遇到；
  当前服务器实装 4.3.0 属「环境与声明不一致」，需单独对齐。

## 2026-11-03　漂移检查修正：ERP 视图不再误报缺表（⭐）

**【修正：20 个「缺表」其实是视图】**

- `scripts/check-orm-drift.py` 原先只用 `inspect.get_table_names()`（只返回基表），
  把 ERP 透传 MES 真表的 20 个 `erp_*` **视图**误判成「缺 20 张表」，
  于是一装 ERP 门禁就红，告警等于失效
- 实测这 20 个对象：全部可读、`pg_relation_is_updatable = 28`
  （INSERT / UPDATE / DELETE 全通）、且都带业务数据（工单 12 行、追溯 12 行、
  BOM 7 行）——ERP 一直正常在用，**不存在缺表**
- 它们由 `apps/{erp,crm,mes}/schema.sql`（方案 D）在应用启动时创建，
  对应 `AppManifest.schema_managed=True`，alembic 主链刻意不建、也不纳入 diff

**【检查逻辑加固】**

- 关系对象判定扩为「表 / 视图 / 物化视图」，视图不再被当成缺失
- 新增 `schema_managed` 应用识别：这类表缺失归入提示级
  `MISSING_SCHEMA_MANAGED`，不计为迁移责任（应用未启动过时属正常）
- 输出增加「库中基表数 / 关系对象合计 / 经视图映射 / schema.sql 托管」四项，
  一眼分清「真缺失」与「误判」
- 验证：生产库 214 张 ORM 表全绿（其中 20 张经视图映射，
  `schema.sql` 托管 107 张）；开源包等价环境 79 张仍全绿，无回归

## 2026-11-03　开源包结构完整性 + CI 门禁（⭐）

**【迁移：补齐 6 张表与 18 个字段】**

- 在「开源包全新安装」环境里做 ORM ↔ 库结构逐项比对，发现一批对象
  **任何迁移都没建过**（公开链、闭源链都没有）——生产库是历史上靠手工 SQL
  补出来的，仓库里只留 ORM 定义。这类缺口 alembic 不会报错、单元测试也测不到，
  只有真连库比对才露出来
- 补齐：`cms_kb_docs` / `cms_kb_chunks` / `cms_publish_channels` /
  `cms_publish_jobs` / `cms_entry_stats_daily` / `cms_track_events` 共 **6 张表**；
  `app_submissions`(5) / `cms_ai_generations`(4) / `cms_entries`(2) /
  `cms_forms`(2) / `cms_pages`(5) 共 **18 个字段**，外加 2 个外键
- 其中 `app_submissions` 的 5 列原先只由**闭源迁移**添加，而公开侧 seed
  （内置应用自动上架）要用它们 —— 开源版每次 `seed` 都会报
  `UndefinedColumn: schema_version`。现在公开链自备一份
- 结构全部由生产库 `pg_dump --schema-only` 导出，不凭 ORM 反推；
  重复主键会抛 `42P16 invalid_table_definition`（**不是** `duplicate_object`），
  DO 块已把四类冲突异常全收
- pgvector 缺失时 `cms_kb_chunks.vector` 降级为 `double precision[]`
  （与既有方案一致），装扩展后用 `backend/scripts/enable_pgvector.py` 升级

**【CI：迁移必须覆盖 ORM 全部定义】**

- 新增 `scripts/check-orm-drift.py`：拿 SQLAlchemy metadata 与真实库逐表逐列
  比对，`MISSING_TABLE` / `MISSING_COLUMN` 一律失败
- 接入 CI 的 `ORM ↔ 迁移 漂移检查` 步骤（在迁移执行之后、跑测试之前）
- 这才是这类问题的门禁：`alembic upgrade heads` 只要迁移图自洽就返回成功，
  它并不知道 ORM 里还有别的表

**【修复：Release 流水线已连续 3 个版本失败】**

- 根因：`scripts/build-frontends.sh` 用 `rsync -a --delete` 同步 landing 产物，
  把 `frontend/landing/` 里**不参与构建**的资产（5 个旧静态页、
  `docs-content/` 文档源、`robots.txt` 等）全删了；随后 `package-core.sh`
  用 `git ls-files | tar` 打包，撞上已不存在的文件，报
  `tar: frontend/landing/advantages.html: Cannot stat` 而中止
- 后果：v0.5.0 / v0.5.1 / v0.5.2 的 Docker 镜像都推送成功，
  但 **GitHub Release 与核心包全部没有产出**
- 修法：`rsync --delete` 配排除清单，只清理构建产物；`package-core.sh`
  增加前置检查，发现「git 跟踪但磁盘已删除」的文件时直接指明原因与恢复命令，
  不再让 tar 抛一堆 `Cannot stat`

## 2026-11-03　产品核心能力归入底座（⭐）

**【内置清单：6 个】**

- 新标记 `builtin=True`：`cms`（辰科官网 CMS，AI 内容核心）、`collect`（内容采集）、
  `cloud_storage`（云存储）、`notification`（站内通知）、`payment`（支付中心），
  连同此前的 `sso`，共 **6 个底座能力不可卸载 / 不可停用**
- 仍可装卸的 9 个：`crm` / `erp` / `mes`（商业化业务应用），
  `workflow` / `announcements` / `tickets` / `links` / `quick_notes` / `my_todo`（可选工具）
- 判定标准仍是那句：**能被卸载的是应用，不能卸载的是底座**。
  自己是做 AI CMS 的，把 CMS / 采集这类立身之本做成可卸的商业应用没有意义

**【加固：外部应用的 manifest 会被升级覆盖】**

`collect` / `payment` 在 `backend/src/apps/`（`.gitignore` 第 75 行忽略），
应用中心升级或重装会**覆盖其 `manifest.py`**，写在里面的 `builtin=True` 会丢。
为此新增 `BUILTIN_APP_KEYS` 兜底名单，`is_builtin_app()` 判定 = manifest 声明
**或** 名单命中 —— 两层保险，升级后保护不丢

**【澄清：这 7 个不需要标】**

`rbac` / `system` / `auth` / `portal` / `builder` / `comments` / `forms` 没有
`manifest.py`，不进应用中心，本来就不可能被卸载 —— 不需要也不应该标 builtin。
另 `commerce` 同理，由 `api/v1/__init__.py` 直接挂载

## 2026-11-03　统一登录归入底座能力

**【应用中心 · 内置能力】**

- `AppManifest` 新增 `builtin` 字段，立一条标准：**能被卸载的是应用，不能卸载的是底座**。
  与目录位置无关 —— 放 `apps/` 只是复用 manifest 的自动注册能力
  （路由门禁 / 权限码 / 菜单 / hook），不代表它该被商业化装卸
- 统一登录（SSO）标记 `builtin=True`：应用中心归入「内置功能」分组，排在最前，
  带「内置」徽标，**不渲染卸载 / 停用入口**；`uninstall` / `disable` 接口直接返回
  403，防止绕过 UI 直接打接口
- 启动时自动对齐内置应用状态：被手工改库或老版本 API 停用 / 卸载过的，重启即
  拉回 `installed + enabled`，不影响其他应用，不删任何业务数据

**【为什么不能可卸载】**

登录是系统入口。停用后 `/api/v1/sso/*` 会 403（后台配置页打不开），而
`/api/v1/public/sso/*` 是匿名路由、不受门禁约束（这是刻意的，否则停用后没人
能登进去把它启用回来）—— 两者叠加就是「前台还能扫码登录、后台配置页却消失」
的半死状态。与其靠注释提醒运营别点，不如从语义上禁止。

## 2026-11-03　第三方登录（⭐）

**【统一登录 · 可插拔渠道】**

- 新增「统一登录」：前台支持微信、抖音、飞书、Google、GitHub 五个渠道，
  后台保留账号密码为主、飞书可选。登录属于底座能力（`builtin=True`），
  应用中心不可卸载 / 停用，启动时自动对齐到启用态
- 加一个渠道只需在 `apps/sso/providers/` 放一个文件，不用改路由、前端、数据库 ——
  渠道用目录扫描自动发现，单个渠道加载失败只跳过不阻断启动

**【安全设计】**

- 后台**不开放第三方自助注册**：扫码进来查不到绑定一律拒绝并提示联系管理员。
  后台账号是权限载体，必须由超管创建并分配角色
- 登录成功后**不把 token 放 URL**，改为 2 分钟一次性票据，前端拿票据换 JWT ——
  避免 token 进入浏览器历史、Nginx 日志和 Referer
- state 一次性校验（防 CSRF）+ PKCE（飞书/Google/GitHub，防授权码截获）；
  微信与抖音不支持 PKCE 故关闭
- 第三方邮箱与本站账号冲突时只留空、**不自动合并**，防邮箱抢占
- 渠道密钥加密入库，后台仅回显末四位；`redirect` 参数只接受站内相对路径防开放重定向
- 微信与抖音禁止在后台开放（C 端账号体系不适合当管理入口），配置层强制拦截

**【数据】**

- 绑定表补 `raw_profile` / `last_login_at`，`auth_user_oauth` 补上
  `UNIQUE(provider, open_id)` 与外键 —— 原表注释写了唯一约束但实际从未建过，
  并发下会插重复行导致查询报错

**【后台】**

- 系统 → 登录方式：填一次回调域名，五个渠道的回调地址自动生成；
  渠道特有项（微信扫码/公众号两种模式、Google 是否申请离线访问）由后端声明下发

**【升级提示】**

- 升级后重启后端，侧栏「系统」组会出现「登录方式」入口（启动自动对齐补菜单）
- 需在后台填入各渠道 AppID/AppSecret 后才会在登录页显示按钮；
  未配置时登录页与原来完全一致，账号密码登录不受影响
- 微信需企业认证（300 元/年）、抖音需企业主体 + 网站备案，两者回调地址必须 HTTPS

## 2026-11-02　菜单入口全量补齐（8 项）

**【平台 · 修复】**

- 补回 8 个「有页面、无菜单入口」的功能：在线升级、事件推送、URL 重定向、评论管理、表单问卷、代码生成、URL 规则、页面构建
- 根因：这些页面前端路由一直都在，菜单定义却只存在于生产数据库（早年在「菜单管理」里手工加的行）。代码里的种子清单没有它们，全新部署侧边栏自然看不到入口
- 对账口径升级为「前端路由 × 生产库菜单 × 种子清单」三方比对，不再逐个发现逐个补
- 修复后全新库验证：105 张表 + seed → 菜单 49 条，「系统」组 14 项齐全，顺序按 sort 正确排列
- 老库无影响：生产库同步预演「菜单新建 0 个」，既有菜单与角色绑定保持不变
- 新增启动时自动对齐：后端启动按 app manifest + 核心种子重放菜单与权限（幂等、只补不删、不覆盖运营在菜单管理里调过的顺序），以后改菜单升级重启即生效，不必再手工跑同步脚本

## 2026-11-02　内链模块 + URL 规则体系 + 标签聚合 ⭐

**【内容运营 · 内链】**

- 内链升级为独立模块：向量召回候选文章 → 模型精选并生成锚文本与插入位置 → 编辑页一键插入正文或保存待审，支持通过 / 拒绝 / 标记已插入 / 删除
- 新增 `cms_entry_links` 表，用部分唯一索引排除 rejected，拒绝后可重新建议，不会卡死
- 内链关系可管理、可筛选、带状态计数；后续沉淀为标签资产，为标签聚合页做流量承接
- 历史文章内链回填脚本（幂等、支持 --dry-run），存量已回填 36 条

**【SEO · URL 与聚合页】**

- 栏目级 URL 规则可视化配置，支持按栏目配置文章永久链接格式与模板
- 标签聚合页上线并纳入 sitemap 收录

**【平台 · 修复】**

- 修复新装实例 14 个 AI 页面侧栏无入口：seed 与 manifest 两套菜单清单补齐「AI 内容中心」分组
- 补齐 AI 层 12 张表的建表迁移（批量生产 / 记忆 / 定价 / 质检 / 会话 / AB 测试 / 内容摘要 / 工作流编排），干净环境安装后即可用，不再报「表不存在」

**【运维】**

- CI lint 门禁转绿，修复 ruff 12 处告警
- 仓库停止跟踪前端构建产物，减少 2 万余行噪音

## 2026-11-02　全自动发布模式 + 图片转存云存储 + AI 自动配图 ⭐

**【采集应用 collect · 全链路】**

- 全自动发布模式：规则可选三档（不自动 / 自动改写转草稿 / 自动改写并发布），定时抓 → 改写 → 配图 → 发布无人值守；每轮 5 条成本护栏，失败标记跳过不重试，调度器补扫防丢
- 正文图片转存云存储：外站图自动转自有 CDN，同图缓存幂等、单图失败兜底不阻塞；含存量文章一次性回填（29 张）
- AI 自动配图：正文无图时自动生成头图，插正文首图 + 挂 SEO 社交分享封面
- 修复空壳检测误杀英文站、外链清洗误删 HTML 图片等问题
- 采集操作手册上线文档站（docs.user.023ent.net）

**【工作台首页】**

- 系统更新日志自动化：本文件为唯一事实源，公告自动同步，发版零人工
- 首页 API 统计图去噪：排除钩子事件（HOOK）与门户公开接口流量，趋势窗口修正为真实 7 天

## 2026-11-01　采集箱操作闭环 + AI 改写 / 聚合 + JS 渲染通道 ⭐

**【采集应用 collect · 全链路】**

- 可视化采集规则：数据项点选式编辑（CSS / XPath / 正则多选自动回退）+ 数据处理动作点选（替换 / 截取 / 反转义 / 填充等），试采集面板逐步 trace
- 定时采集（分钟级）+ 采集箱操作闭环：AI 改写 / AI 聚合 / 转草稿 / 发布 / 批量操作
- AI 聚合：2~8 条同主题素材融合为综述条目（新条目落箱、带溯源）
- JS 渲染采集通道（browser）：无头浏览器抓取单页应用，「渲染等待」毫秒可调
- 外链三道防线清洗：入箱清洗 / AI 改写禁链 / 转草稿兜底，正文外站超链接零残留

## 2026-10-31　采集应用（collect）开发启动

- 可视化点选式规则引擎 + 定时采集

## 2026-09-24　应用商店 / 应用中心重构 + 商业生态层落地 ⭐

- 商店公开只读接口、门户应用中心收编、搜索筛选 facets、详情页版本/权限/安装状态
- 商业生态层：定价 / 订单 / 支付 / 授权 license / 开发者收益 / 云端安装
- 可插拔应用三层机制体检通过，商店在架 12 应用全部已安装

## 2026-09-04　应用商店体系落地：MES 制造执行首个独立可插拔应用 v1.0.0 ⭐

- BOM / 工艺路线 / 生产订单 / 生产计划 / 排产派工 / 生产报工 / 车间看板
- 「上传 ZIP → 审核 → 安装」一键流程，路由 / 前端 / 迁移自动注册

## 2026-08-08　内容编辑器 + 全量移动端响应式 + 工作台更新日志 ⭐

- TipTap 富文本编辑器替换后台 9 处长文本字段，图片直传云存储
- 侧边栏抽屉化、表格横滚、grid 响应式；工作台首页直接展示更新日志

## 2026-07-02　V2 架构文档更新与重构

## 2026-06-09　通知中心 / API Key 管理 / 系统设置 / 后台增强

## 2026-06-08　项目初始化（Cenkor Admin Platform 单体仓库）
