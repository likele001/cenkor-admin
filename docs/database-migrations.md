# cenkor-admin 数据库迁移规范（开发者必读）

> 状态基线：**2026-10-30 实测**。适用于 cenkor-admin（hub）后端全部开发者。
> 本文是当前唯一权威版本；`docs/migrations.md` 是 2026-10-27 的历史记录与事故复盘，冲突时以本文为准。

---

## 0. 一分钟版

```bash
cd /www/wwwroot/cenkor-admin/backend
PY=/www/server/pyporject_evn/cenkor/bin/python3

$PY -m alembic heads                      # 必须只出 1 个 head
$PY ../scripts/check-migration-graph.py   # 工作区全量：无断链/无重复/单 head
$PY ../scripts/check-migration-graph.py --tracked-only   # 公开仓库视图：同样必须通过
```

三条铁律：

1. **公开迁移的 `down_revision` 只能指向公开 revision**（否则开源仓库断链）。
2. **闭源链的挂载点必须跟随公开 head**（每加一条公开迁移，顺延一次）。
3. **提交前两套视图各只有一个 head**，`check-migration-graph.py` 两种模式都要绿。

---

## 1. 现状（先看清事实，再看规则）

### 1.1 文件分布

`backend/alembic/versions/` 按应用分 6 个子目录，`alembic.ini` 用 `version_locations` 全部挂进来：

| 目录 | 迁移数 | 入库(git) | 归属 |
|---|---|---|---|
| `core/` | 31 | 全部 31 | 平台核心（cms/auth/rbac/portal/app store/i18n…） |
| `ext/` | 13 | 9 | 平台扩展（cloud_storage / codegen / upgrade / inventory / ai_video_jobs…） |
| `commerce/` | 9 | 3（白名单） | 交易层（定价/订单/授权/结算），大部分闭源 |
| `erp/` | 19 | 0 | ERP 应用（闭源） |
| `crm/` | 6 | 0 | CRM 应用（闭源） |
| `mes/` | 9 | 0 | MES 应用（闭源） |
| **合计** | **87** | **43** | |

```
/web 版本目录不是「一个目录一棵树」，而是 6 个目录里的 87 个 revision
被跨目录的 down_revision 串成【一条线】，只有 1 个 base、1 个 head。
```

### 1.2 两个 head，取决于你站在哪个视图

| 视图 | 文件数 | head | 说明 |
|---|---|---|---|
| 完整工作区（服务器 / 有闭源代码的开发者） | 87 | `20261027_0100_app_schema` | 闭源链末端 |
| git 跟踪视图（公开仓库 / CI / 新克隆） | 43 | `20261031_1310_cms_ai_tables` | 公开链末端 = 挂载点的父 |

### 1.3 真实链路

```
公开/基础链（43 个，进公开仓库）
  20260107_0001_initial
    → 0002_auth_rbac → 0003_media_news_audit → 0004_platform_apps
    → 20260108_0001_website_url → 20260608_0001_notif → 20260608_0002_apikey
    → 20260610_0001_content_engine → 20260610_1211_portaltv → 20260610_1215_pwdrst
    → 20260610_1220_app_perms → 20260611_1300_portal_register_ip
    → 20260611_1400_app_tables → 20260611_1500_app_store
    → 20260612_0400_add_has_frontend → 20260612_0500_my_todo_items
    → 20260612_0600 → 20260612_0700 → 043ba4506897
    → 20260806_2000 → 20260807_1347 → e0b1bc517b5f → …（i18n/评论/表单/webhook 共 8 条）
    → 20260925_0026_app_enabled
    → 20261007_0028_product_axis → 20261009_0030_app_intro → 20261010_0031_dev_method
    → 20261015_0032_codegen_runs → 20261015_0033_upgrade_runs → 20261018_0034_upgrade_notes
    → 20261014_124126_gen_inventory → 20261014_124200_schema_versions
    → 20261029_1500_ai_video_jobs
    → 20261031_1100_cms_templates（CMS 主题模板表）
    → 20261031_1300_cms_multisite（多站点地基，接管原 001/002/005 SQL）
    → 20261031_1310_cms_ai_tables（AI 五表，接管原 003/004/006 SQL）  ← 公开 head
                    │
                    │  挂载点（闭源、不入库）
                    ▼
  20261020_0035_app_publish（app_submissions 上架/撤回 + manifest 快照）
                    ▼
闭源链（44 个，全部 .gitignore）
  erp_init(20260831_0001) → … erp 19 条 … → 20260903_0019_deepen
    → crm_0001 … crm_0006
    → mes_0001 … mes_0009
    → 20260922_0020_commerce → payment → marketplace → payout → promo → cloud
    → workflow(0027) → product_commerce(0029)
    → 20261027_0100_app_schema            ← 完整工作区 head
```

> 注意两个「反直觉」的地方：
> 1. **日期不单调**：erp 的 revision 是 2026-08-31 建的，但它挂在 2026-10-20 的 `0035_app_publish` 之后——因为是先写了 ERP，后来才把闭源链整体挂到公开链末端（挂载点会随公开 head 顺延，见 §3）。
> 2. **目录与先后无关**：`erp/` 里的文件可能排在 `crm/` 之前，`ext/` 里的文件可能排在 `erp/` 之后。判断顺序只看 `down_revision`，不要看目录、不要看文件名日期。

---

## 2. 目录与配置

### 2.1 `backend/alembic.ini`

```ini
[alembic]
script_location = alembic
prepend_sys_path = src
version_path_separator = space
version_locations = %(here)s/alembic/versions/core
                   %(here)s/alembic/versions/erp
                   %(here)s/alembic/versions/crm
                   %(here)s/alembic/versions/mes
                   %(here)s/alembic/versions/commerce
                   %(here)s/alembic/versions/ext
file_template = %%(year)d%%(month).2d%%(day).2d_%%(hour).2d%%(minute).2d_%%(rev)s_%%(slug)s
```

- 新增目录 = 同时改 `version_locations`，否则该目录下的迁移**不会被 alembic 看见**。
- `sqlalchemy.url` 只是占位，真实连接串由 `alembic/env.py` 从 `backend/.env` 的 `DATABASE_URL_SYNC` 注入；临时演练可用环境变量 `CENKOR_DATABASE_URL` 覆盖目标库。
- 文件名模板决定 revision 形如 `20261030_1530_ab12cd34_add_xxx`，**revision 字符串长度上限 32**（`alembic_version.version_num` 是 VARCHAR(32)），超长会在执行时才炸，`check-migration-graph.py` 会提前拦。

### 2.2 `backend/alembic/env.py` 做了四件额外的事

| 机制 | 位置 | 作用 |
|---|---|---|
| 全量模型加载 | `core/model_loader.py` | 把内置 + 外置 app 的 ORM 全并入 `Base.metadata`；与体检脚本共用同一份逻辑 |
| diff 过滤 | `core/schema_filters.py` | 排除「视图托管表」和「无 ORM 的遗留表」，防止 autogenerate 误删 |
| DDL 幂等层 | `core/migration_idempotent.py` | 给 `create_table/add_column/create_index…` 装「已存在就跳过」 |
| 日志保护 | `env.py` | `fileConfig(..., disable_existing_loggers=False)`，否则 uvicorn 的 `hub.log` 会被禁用 |

---

## 3. 三条硬规则

### 规则一：公开链不依赖闭源

公开（git 跟踪）迁移的 `down_revision` **只能指向公开 revision**。指向闭源 revision 的后果：

- 开源仓库里父迁移不存在 → `KeyError: 'xxxx'` / 启动即报 `Can't locate revision`；
- 或者凭空多出一个 head → `alembic upgrade head` 直接 `MultipleHeads`，一条都不执行；
- 对外表现为「容器全 healthy，数据库一张表都没建」。

> 2026-10-26 门户应用中心整页 500 就是这个：`0035_app_publish` 没顺延挂载点。

### 规则二：挂载点跟随公开 head

当前挂载点 = `20261020_0035_app_publish`（闭源链第一环），它的 `down_revision` **必须等于最新公开 revision**（现在是 `20261031_1310_cms_ai_tables`）。

> 每新增一条公开迁移，就要把挂载点的 `down_revision` 顺延到它。**先执行、后顺延**，顺序见 §4.1。

### 规则三：两种视图都只能有一个 head

- 完整工作区：head = 闭源链末端（当前 `20261027_0100_app_schema`）
- git 跟踪视图：head = 公开链末端（当前 `20261031_1310_cms_ai_tables`）

### 规则四：所有 DDL 必须走 alembic，禁止另开 SQL 迁移目录

2026-10-31 之前，`backend/migrations/` 下躺着 6 个旁路 SQL（多站点、embedding 维度、
pgvector、提示词表）。**没有任何脚本执行它们**：不入 docker entrypoint、不入
bootstrap、不入 CI —— 只有当初手工跑过一次。后果是开源用户 clone 之后
`cms_sites` / `cms_ai_prompts` 这两张地基表根本不存在，而线上老库因为早建好了，
一切正常 —— 最容易被忽略的那类问题。

现在已全部并入 alembic：

| 原文件 | 现迁移 |
|---|---|
| `001_multisite.sql` + `002_multisite_tags.sql` + `005_page_form_site.sql` | `20261031_1300_cms_multisite` |
| `003_embed_dims.sql` + `004_vector_pgvector.sql` + `006_ai_prompts.sql` + `apps/cms/ai/schema.sql` | `20261031_1310_cms_ai_tables` |

两条硬要求：

1. **新表 / 新列一律写 alembic 迁移**。不要再建 `*.sql` 迁移目录；也不要往
   `apps/*/schema.sql` 里加 DDL（那是闭源应用的方案 D 专用，见 §8）。
2. **依赖可选扩展的迁移必须能降级**。`cms_ai_tables` 对 pgvector 的处理是范例：
   扩展能建就用 `vector(1024)` + HNSW，建不了（CI / docker 的 `postgres:16-alpine`
   没有 pgvector，应用账号通常也没权限建扩展）就退回 `double precision[]`
   并打一条带处理指引的告警，**绝不让迁移失败**。
   装好扩展后跑 `backend/scripts/enable_pgvector.py` 把列升级上去。

> 自查方法：按 §6 在空库跑一遍「git 跟踪视图」的 `upgrade head`。
> 线上能跑通不代表新装能跑通 —— 这是本次两个事故的共同成因。

### 规则五：收口挂载点之后要清理 `alembic_version` 的多余行

§4.1 的流程有一个隐蔽副作用：中间态「2 个 head」时执行 `upgrade heads`，
`alembic_version` 会记 **2 行**；挂载点顺延让其中一个变成另一个的祖先之后，
alembic 只是「显示上」合并（`alembic current` 只打 head），表里那行脏数据还在。

后果是 `check_alembic_drift.py` 直接炸在 `scalar_one()`：

```
sqlalchemy.exc.MultipleResultsFound: Multiple rows were found when exactly one was required
```

收口后固定查一次：

```bash
$PY -c "from sqlalchemy import create_engine,text; from cenkor_admin.core.config import get_settings; \
        print([r[0] for r in create_engine(get_settings().DATABASE_URL_SYNC).connect() \
               .execute(text('select version_num from alembic_version'))])"
# 必须只有 1 行；多出来的那行是祖先 revision，删掉即可
```

> `alembic stamp <head>` **不会**帮你删掉这行 —— 它认为目标已达成，直接 no-op。
> 必须显式 `DELETE FROM alembic_version WHERE version_num = '<祖先 revision>'`，
> 且删之前先确认它确实出现在 head 的祖先链里（2026-10-31 就是这么处理的）。

---

## 4. 新增迁移的正确做法

### 4.1 新增「平台/公开」迁移

```bash
cd /www/wwwroot/cenkor-admin/backend
PY=/www/server/pyporject_evn/cenkor/bin/python3

# 1) 生成到 core/（平台核心）或 ext/（平台扩展），文件名带业务语义
$PY -m alembic revision --autogenerate -m "add_xxx_table" --version-path alembic/versions/core
```

打开生成的文件，**手工确认 `down_revision`**：

- 必须是当前**公开 head**（现在是 `20261031_1100_cms_templates`）；
- **不能**是 `alembic heads` 打出来的闭源 head（`20261027_0100_app_schema`）——autogenerate 默认就取它；
- **不能**是挂载点 `0035_app_publish`（那会变成挂载点之后的第二个 head）。

```bash
# 2) 先让线上库真正执行（此刻图上有 2 个 head 是正常中间态）
$PY -m alembic upgrade heads
#    ⚠️ 演练想指到别的库，不能用环境变量：
#    get_settings() 会用 .env 强行覆盖（core/config.py:233「覆盖可能继承的旧环境变量」），
#    `DATABASE_URL_SYNC=xxx $PY -m alembic ...` 会静默连回 .env 里那个库。
#    正确做法：在一个临时工作目录放 .env（_find_env_file 第一候选是 Path.cwd()/.env），
#    并在该目录用 `-c` 指定 alembic.ini 运行。

# 3) 验证对象真的建出来了（表/列/索引），再动挂载点
#    新建表看一眼： psql -c '\d+ new_table'

# 4) 顺延挂载点：改 0035_app_publish 的 down_revision 为新 revision
$PY -m alembic heads                      # 回到 1 个 head

# 5) 两套视图都自检
$PY ../scripts/check-migration-graph.py --tracked-only
$PY ../scripts/check-migration-graph.py

# 6) 「新迁移 + 挂载点改动」一起提交
```

> **顺序反了会静默失败**：先顺延、后执行，新迁移在拓扑上变成闭源 head 的祖先，alembic 认为「已应用」，`upgrade` 直接跳过——不报错，直到代码查那张表才 500。

### 4.2 新增「闭源/商业应用」迁移

```bash
# 放进对应应用目录，且确认被 .gitignore 命中（输出非空才安全）
$PY -m alembic revision --autogenerate -m "crm_add_xxx" --version-path alembic/versions/crm
git check-ignore -v backend/alembic/versions/crm/2026xxxx_xxxx_crm_add_xxx.py
```

- `down_revision` 取**完整工作区当前 head**（`alembic heads` 的结果，现在是 `app_schema`）。
- `ext/` 是混合目录：闭源迁移必须**逐个加到 .gitignore**（见 §7.2），否则 `git add -A` 会带进公开仓库。
- `commerce/` 同理：默认屏蔽，平台级迁移用 `!` 白名单反选。

### 4.3 两个人同时加迁移 → 多 head

```bash
$PY -m alembic heads          # 出现 2 个
$PY -m alembic merge -m "merge a/b" <head1> <head2>
```

merge 迁移的 `down_revision` 是元组 `(head1, head2)`，`upgrade()` 留空即可。合并后重新跑 §4.1 第 5 步。

> 允许出现多 head 的**唯一场景**是「公开迁移刚加、挂载点还没顺延」这个中间态，且必须在同一次提交里收掉。

---

## 5. 校验：提交前必须跑

| 命令 | 检查什么 | 什么时候跑 |
|---|---|---|
| `python3 scripts/check-migration-graph.py` | 工作区全量：断链 / 重复 revision / head 数 / revision 长度 ≤32 | 每次提交前 |
| `python3 scripts/check-migration-graph.py --tracked-only` | 公开仓库视图（等价于新克隆） | 每次提交前（CI 必跑） |
| `python3 scripts/check_alembic_drift.py` | 库里实况 vs 待跑迁移链期望（回答「能不能安全 stamp 到 head」） | 线上要 stamp / 升级报 DuplicateColumn 时 |
| `python3 scripts/check_schema_drift.py` | `Base.metadata` vs 真实库（表级差异应为 0） | 大改模型、发版前 |

pre-commit 钩子：

```bash
git config core.hooksPath .githooks     # 启用后 check-migration-graph 会在 commit 时自动跑
```

CI（`.github/workflows/ci.yml`）固定两步：

```yaml
- run: python3 scripts/check-migration-graph.py --tracked-only
- run: cd backend && alembic upgrade heads     # 在干净的 PostgreSQL 上真跑一遍
```

> CI 是「干净克隆」，只有 41 个公开迁移，跑到 `cms_templates` 为止。CI 绿 ≠ 线上闭源链没问题，闭源部分由完整工作区的自检负责。

---

## 6. 三道 autogenerate 护栏（别删）

### 6.1 护栏一：模型必须加载全（`core/model_loader.py`）

漏加载一个 app 的 models，autogenerate 就会把那个 app 的全部表判成「库里多出来的」，生成 `drop_table`。

> 2026-10 事故：`erp/models.py` 其实是**包目录**，旧扫描只认单文件 `models.py`，ERP 74 张表从未进过 metadata，一次 autogenerate 生成 **101 个 drop_table**。

非 `models` 命名的模型模块必须登记进 `EXTRA_MODEL_MODULES`（例：`apps/system/store_models.py`）。

### 6.2 护栏二：不该参与 diff 的对象要过滤（`core/schema_filters.py`）

1. **视图托管表**：ERP 侧 20 个 `erp_xxx` 在库里是**视图**，透传 MES 的 `mes_xxx` 真表。ORM 按 `erp_xxx` 映射，autogenerate 会误判「表缺失」→ `create_table`，所以运行时查出视图名一律排除。
2. **无 ORM 的遗留表**：`*_legacy`、被 `mesx_*` 取代的旧 `mes_*`、只有 DDL 没有 models 的 `inventory_*`。既不该 drop，也不该出现在 diff 里。

体检脚本与 `env.py` 必须共用这一份规则——两边各写一遍，结论迟早对不上。

### 6.3 护栏三：新功能用定向 diff

全量 `--autogenerate` 只在 `check_schema_drift.py` 表级差异为 0 时可信。日常新增一个小功能，优先手写 `op.add_column` / `op.create_table`，再跑 `check_schema_drift.py` 确认差异归零。

### 6.4 DDL 幂等层（`core/migration_idempotent.py`，2026-10-30 新增）

线上库结构可能**领先于** `alembic_version`（历史上手工补过 DDL、挂载点被反复顺延），这时重跑迁移会撞：

```
DuplicateColumn: column "schema_version" of relation "app_submissions" already exists
DuplicateTable: relation "app_orders" already exists
```

幂等层做的事：`create_table / add_column / create_index / drop_index / create_unique_constraint / drop_constraint` 执行前先查真实库，已存在就跳过（并打一条 `migration.idempotent` 日志）。

**它不是免死金牌**：幂等只能保证「不炸」，不能保证「结构对」。撞过 DuplicateColumn 之后，仍要跑 `check_alembic_drift.py` 确认待跑链里每个对象都在库里，再决定 stamp。

---

## 7. 闭源与 Git：扩展应用的数据库不进仓库

这是本项目最容易出事的边界，务必逐条读完。

### 7.1 一句话

> **crm / erp / mes 三个商业应用的代码、迁移、`schema.sql`、静态资源全部不进 git；`commerce` 和 `ext` 是混合目录，只有平台级迁移进 git。**

因此公开仓库里的迁移图是**不完整**的——这是设计，不是 bug。

### 7.2 `.gitignore` 当前规则（照抄）

```gitignore
# ===== 闭源应用迁移（2026-10-27 迁移分入子目录后新增）=====
backend/alembic/versions/crm/
backend/alembic/versions/erp/
backend/alembic/versions/mes/

# commerce 是混合目录：3 个平台级迁移公开，6 个商业模块闭源
backend/alembic/versions/commerce/*
!backend/alembic/versions/commerce/20261007_0028_product_axis.py
!backend/alembic/versions/commerce/20261009_0030_app_intro.py
!backend/alembic/versions/commerce/20261010_0031_dev_method.py

# 应用自带 schema（方案 D）同样属商业实现，双保险
backend/src/cenkor_admin/apps/*/schema.sql

# ext 是混合目录：8 个平台级迁移公开，以下 4 个闭源，逐个登记
backend/alembic/versions/ext/20260924_0025_cloud.py
backend/alembic/versions/ext/20260925_0027_workflow.py
backend/alembic/versions/ext/20261020_0035_app_publish.py
backend/alembic/versions/ext/20261027_0100_app_schema.py

# 应用代码本体
backend/src/cenkor_admin/apps/erp/
backend/src/cenkor_admin/apps/crm/
backend/src/cenkor_admin/apps/mes/
backend/src/cenkor_admin/apps/workflow/
backend/src/apps/                    # 外置应用（payment / commerce …）整体排除
```

另外 `*.db` / `*.sqlite` 也被忽略——本地开发库、扩展应用的独立库文件都不入库。

### 7.3 三个必须知道的细节

1. **`git add -A` 会带进闭源文件**。`ext/` 的闭源迁移是「逐个登记」的，新增一个闭源 ext 迁移时必须同步加规则。提交前固定跑：
   ```bash
   git status --short | grep alembic/versions    # 只应出现你有意公开的文件
   git check-ignore -v backend/alembic/versions/ext/xxx.py   # 输出为空 = 没被忽略，危险
   ```
2. **白名单是反向的**。`commerce/*` 先全屏蔽再 `!` 反选 3 个平台级文件；新增平台级 commerce 迁移要加一条 `!`，否则会被静默排除。
3. **双保险**。闭源应用的表结构除了迁移，还有 `apps/<key>/schema.sql`（方案 D，见 §8），两条路径都被忽略。

### 7.4 新克隆（公开仓库）会遇到什么

| 场景 | 结果 |
|---|---|
| `alembic heads` | 1 个：`20261031_1310_cms_ai_tables` |
| `alembic upgrade heads` | 成功，但只建平台表；crm/erp/mes 表不存在 |
| crm/erp/mes 应用 | 目录本身不在仓库里，不存在「装了但缺表」 |
| CI | 只对公开链负责，绿了不代表闭源链 OK |

### 7.5 为什么不把它们放进仓库

闭源迁移与 `apps/{crm,erp,mes}` 代码同源，属商业实现；一旦进公开仓库，等于把 ERP/CRM/MES 的完整表设计（含定价、结算、授权）开源出去。规则由 `scripts/check-migration-graph.py` 在 pre-commit / CI 双重把关。

---

## 8. 应用自带 schema（方案 D）

闭源应用除了 alembic 迁移，还有一条平行的建表路径：

| 应用 | schema 文件 | 说明 |
|---|---|---|
| erp | `apps/erp/schema.sql` | 全部 ERP 表 |
| crm | `apps/crm/schema.sql` | 全部 CRM 表 |
| mes | `apps/mes/schema.sql` | 全部 MES 表 |
| ~~cms/ai~~ | 已于 2026-10-31 迁回 alembic | AI 五表见 `20261031_1310_cms_ai_tables`，`bootstrap.py` 只做校验不再建表 |

要点：

- `AppBase` 里的 `schema_file` 标记「本 App 的表由 `schema.sql` 管理，alembic 主链不再建，也不纳入 diff」。
- 启动时由各 app 的 `bootstrap` 执行；执行结果记进 `app_schema_versions`，**带 checksum 短路**（schema.sql 没改就整段跳过）。
- 对应的 alembic 迁移保留为**空 `upgrade()`**，只为维持链完整——
  > 删掉空迁移会让后续迁移断链、`alembic_version` 无法前进。这是刻意为之，不要"清理"。
- 跨应用外键（ERP 表引用 MES 表）由 schema.sql 里的视图/约束补偿，见 `schema_filters` 的视图规则。

---

## 9. 谁在什么时候跑迁移

| 入口 | 命令/行为 | 备注 |
|---|---|---|
| 服务启动 | **不跑 alembic**（erp/crm/mes 跑 `schema.sql` bootstrap；cms/ai 只校验表存在） | `main.py` 里没有 `upgrade` 调用 |
| 后台「系统 > 在线升级」 | `git pull --ff-only` → `alembic upgrade heads` → 提示重启 | `apps/system/upgrade_service.py` |
| CI | `alembic upgrade heads`（干净 PostgreSQL） | 只看公开链 |
| 手工 | 见下 | 发版 / 排障 |

```bash
cd /www/wwwroot/cenkor-admin/backend
PY=/www/server/pyporject_evn/cenkor/bin/python3

$PY -m alembic current            # 当前 alembic_version
$PY -m alembic history | head -5  # 看链头
$PY -m alembic upgrade heads      # 用 heads，不要用 head
$PY -m alembic+head              # ← 多 head 时会 MultipleHeads，整条不执行
```

> **永远用 `upgrade heads`**：它等价于单 head 时的 `head`，但挂载点漏顺延时不会整链失败。

---

## 10. 故障对照表

| 症状 | 根因 | 处理 |
|---|---|---|
| `MultipleHeads: Multiple head revisions are present` | 多 head（并发新增 / 挂载点没顺延 / 手工改过 down_revision） | `alembic heads` → `alembic merge`，或补挂载点顺延 |
| `KeyError` / `Can't locate revision identified by 'xxxx'` | 指向了闭源 revision（公开链依赖闭源） | 改 `down_revision` 到公开 head |
| `DuplicateColumn` / `DuplicateTable` 在启动/升级时 | 库结构领先于 `alembic_version` | 幂等层会跳过；随后跑 `check_alembic_drift.py` 判断能否 stamp |
| 升级"成功"但新表不存在 | 顺序反了：先顺延挂载点、后执行迁移，被判定已应用 | 拿到真实版本号，`alembic stamp` 回退一格后重跑 upgrade |
| `StringDataRightTruncation` on `alembic_version` | revision 字符串 > 32 | 缩短 revision（文件名模板已控，手写迁移要自查） |
| autogenerate 生成大批 `drop_table` | 模型没加载全（包目录 / 非 `models.py` 命名） | 查 `model_loader`，`check_schema_drift.py` 表级差异必须为 0 |
| autogenerate 想 `create_table` 已存在的视图 | 视图托管表没过滤 | 确认走的是 `schema_filters.make_include_object` |
| 公开仓库 clone 后建表不全 | 正常：闭源迁移/代码不在仓库 | 不要试图补；闭源部署用完整工作区 |
| 提交后发现闭源迁移进了仓库 | `git add -A` | `git rm --cached` + 补 `.gitignore`，再 `check-migration-graph --tracked-only` |

---

## 11. 回退与降级

1. **优先向前修**：新增一条修正迁移（补列 / 补索引 / 补数据），生产上比 downgrade 安全。
2. `alembic downgrade -1` 只适用于**你自己刚加的、还没被业务写入依赖**的迁移。
3. 真正回退发版：代码 `git checkout <tag>` + **数据库用升级前的备份**（PostgreSQL 用 `pg_dump` 快照），不要指望 `alembic downgrade` 走完 85 个迁移。
4. stamp 有风险：`alembic stamp <rev>` 只改版本号不动结构。stamp 前必须 `check_alembic_drift.py` 全绿，否则等于把真问题藏起来。

---

## 12. 检查清单

### 12.1 提交 PR 前

- [ ] 迁移文件放在**正确的应用目录**
- [ ] `down_revision` 指向正确视图的 head（公开 → 公开 head；闭源 → 闭源 head）
- [ ] 若为公开迁移：挂载点 `0035_app_publish` 已顺延，且与迁移**同一次提交**
- [ ] 顺延后 `alembic_version` **只剩 1 行**（`clean_alembic_version_rows.py` 可查可清）
- [ ] 若为闭源迁移：`git check-ignore -v <file>` 有输出（确实被忽略）
- [ ] `upgrade()` 与 `downgrade()` 都写全（downgrade 可留最小实现，但不能 `pass` 掉 DDL）
- [ ] revision 字符串 ≤ 32
- [ ] `check-migration-graph.py` 与 `--tracked-only` 都通过
- [ ] 改动涉及模型时：`check_schema_drift.py` 表级差异 = 0

### 12.2 发版前

- [ ] 完整工作区 `alembic heads` 唯一
- [ ] 备份：`pg_dump` 全库快照（含 `alembic_version`）
- [ ] 备份后跑 `alembic upgrade heads`，确认 `alembic current` = 期望 head
- [ ] 抽查 3~5 张新表/新列确实存在
- [ ] 公开仓库侧 `check-migration-graph.py --tracked-only` 绿（发版 tag 前）

### 12.3 线上异常时

- [ ] `alembic current` 与 `alembic heads` 是否一致
- [ ] `check_alembic_drift.py`：待跑链里的对象是否都在库里
- [ ] 查看 `migration.idempotent` 日志，确认是「跳过」还是「真错」
- [ ] 需要回退 → 走备份恢复，不走 downgrade

---

## 13. 附录

### 13.1 关键常量（2026-10-31）

| 项 | 值 |
|---|---|
| 完整工作区 head | `20261027_0100_app_schema` |
| 公开仓库 head | `20261031_1310_cms_ai_tables` |
| 挂载点 | `20261020_0035_app_publish`（down → `20261031_1310_cms_ai_tables`） |
| 迁移总数 / 公开数 | 87 / 43 |
| Python 解释器 | `/www/server/pyporject_evn/cenkor/bin/python3` |
| 数据库 | 仅 PostgreSQL（`DATABASE_URL_SYNC`，psycopg2） |

### 13.2 脚本索引

| 脚本 | 用途 |
|---|---|
| `scripts/check-migration-graph.py` | 断链/重复/head 数/revision 长度；`--tracked-only` 查公开视图 |
| `backend/scripts/check_alembic_drift.py` | 待跑链期望 vs 库实况，判断能否安全 stamp |
| `backend/scripts/check_schema_drift.py` | metadata vs 库，表级差异应为 0 |
| `backend/scripts/check_hub_schema.py` | hub 关键表存在性 |
| `backend/scripts/apply_app_publish_ddl.py` | 历史事故的补 DDL 脚本（一次性，勿当常规手段） |
| `backend/scripts/enable_pgvector.py` | 扩展装晚了用它把 `cms_embeddings.vector` 升级成 pgvector |
| `backend/scripts/seed_ai_prompts.py` | 把代码里的 5 套默认提示词种进 `cms_ai_prompts`（幂等） |
| `backend/scripts/clean_alembic_version_rows.py` | 收口挂载点后清掉 `alembic_version` 里的冗余祖先行（见规则五） |
| `backend/src/cenkor_admin/codegen/builder.py::rebase_closed_chain` | codegen 内置模式：顺延闭源链入口（改挂载点的程序化版本） |

### 13.3 术语

- **公开链 / 基础链**：git 跟踪的迁移，公开仓库可见。
- **闭源链 / 商业链**：`.gitignore` 排除的迁移，仅完整工作区可见。
- **挂载点**：把闭源链挂到公开链末端的那个迁移（当前 `0035_app_publish`）。
- **视图托管表**：库里是视图、ORM 按同名表映射的对象（20 个 `erp_xxx`）。
- **方案 D**：应用自带 `schema.sql` 建表，alembic 迁移保留空实现以维持链。

---

> 本文档随迁移图变化同步更新。改 `alembic.ini` 的 `version_locations`、动挂载点、调整 `.gitignore` 白名单这三类改动，**必须**在同一提交里更新 §1、§3、§7。
