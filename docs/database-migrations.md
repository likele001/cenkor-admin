# cenkor-admin 数据库迁移规范（开发者必读）

> 状态基线：**2026-11-03 实测（v0.5.12）**。适用于 cenkor-admin（hub）后端全部开发者。
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
2. **公开子图必须单根、单 head**，开源版要能 `alembic upgrade head` 一把建库。
3. **新增公开迁移只改自己的 `down_revision`，不碰任何闭源文件。**
   闭源侧是三条锚点固定的支线，不需要（也绝不能）"顺延" —— 自动顺延会让新迁移
   进入闭源合流点的祖先闭包，`upgrade heads` 静默跳过它，见 §4.1 的警告。

---

## 1. 现状（先看清事实，再看规则）

### 1.1 文件分布

`backend/alembic/versions/` 按应用分 7 个子目录，`alembic.ini` 用 `version_locations` 全部挂进来。

> 📌 **下表是 2026-11-03 的快照，数字一定会变。把它当"形状"看，不要当"事实"用** ——
> 真实数字用一条命令拿（本文所有数字类断言都遵循这个原则）：
>
> ```bash
> cd backend/alembic/versions
> for d in core ext commerce erp crm mes collect; do
>   printf '%-10s %s\n' "$d" "$(ls $d/*.py 2>/dev/null | grep -v __init__ | wc -l)"
> done
> cd /www/wwwroot/cenkor-admin && git ls-files 'backend/alembic/versions/*.py' | grep -v __init__ | wc -l
> ```

| 目录 | 迁移数 | 入库(git) | 归属 |
|---|---:|---:|---|
| `core/` | 36 | 36 | 平台核心（cms/auth/rbac/portal/app store/i18n…） |
| `ext/` | 15 | 13 | 平台扩展（cloud_storage / codegen / upgrade / inventory / cms_*…）；闭源仅 `0027_workflow` 与合流文件 `1300_merge_closed` |
| `commerce/` | 10 | 10 | 交易层（定价/订单/授权/结算）；**v0.5.11 起整体开源** |
| `erp/` | 19 | 0 | ERP 应用（闭源） |
| `crm/` | 6 | 0 | CRM 应用（闭源） |
| `mes/` | 9 | 0 | MES 应用（闭源） |
| `collect/` | 5 | 0 | 内容采集（闭源） |

> **全量 100 个迁移，公开 59 个。**

```
/web 版本目录不是「一个目录一棵树」，而是 7 个目录里的全部 revision
被跨目录的 down_revision 串成【一张图】：1 个 base，全量 1 个 head；
公开子图另有一个 head（被闭源支线过滤掉之后的形态）。
```

### 1.2 两个 head，取决于你站在哪个视图

| 视图 | head | 说明 |
|---|---|---|
| 完整工作区（服务器 / 有闭源代码的开发者） | 闭源合流点 | 三条闭源支线汇成一个点，`alembic heads` 只出 1 行 |
| git 跟踪视图（公开仓库 / CI / 新克隆） | 公开链 head | 闭源支线被过滤后剩下的那个端点 |

> ⚠️ 这里**故意不写具体 revision 名**：head 会随迁移增减而变。
> 2026-11-03 的值是：全量 `20261103_1300_merge_closed`、公开 `20261027_0100_app_schema`。
> 查当前值：
>
> ```bash
> cd /www/wwwroot/cenkor-admin
> PYTHONPATH=backend/src python3 scripts/check-migration-graph.py                # 完整工作区 head
> PYTHONPATH=backend/src python3 scripts/check-migration-graph.py --tracked-only # 公开视图 head
> ```

### 1.3 真实链路

```
公开链（59 个，git 跟踪，单根单 head）
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
    → 20261029_1500_ai_video_jobs → 20261031_1100_cms_templates
    → 20261031_1300_cms_multisite → 20261031_1310_cms_ai_tables
    → 20261031_1600_cms_permalink                 ← 公开链在这里分叉
            ├─→ 20261020_0035_app_publish ─────────────────────┐
            └─→ 20261102_1210_cms_cat_url_tpl                  │
                      → 20261102_1215_cms_entry_links           │
                      → 20261102_2140_cms_ai_missing            │
                      → 20261103_0930_sso_bindings              │
                      → 20261103_1100_cms_orphan ───────────────┤
                                                                ▼
                                    20261103_1200_merge_commerce   ← 公开合流点
                                                                ▼
                                                    20260922_0020_commerce
                                                                ▼
                        20260922_0021_payment → 0022_marketplace → 0023_payout
                                                                ▼
                        20260923_0024_promo → 20260924_0025_cloud
                                                                ▼
                                              20261007_0029_product_commerce
                                                                ▼
                                        20261027_0100_app_schema  ← 公开 head

闭源支线（41 个，.gitignore，只在完整部署里）
  锚 0035_app_publish → 20260831_0001_erp_init → …（erp 19 + crm 6 + mes 9）
                                                    → 20260904_mes_0009 ─────┐
  锚 0025_cloud      → 20260925_0027_workflow（仅此一条）───────────────────┤
  锚 0100_app_schema → 20261101_1430_collect → …（collect 5）
                                                    → 20261102_1100_collect ┤
                                                                             ▼
                                        20261103_1300_merge_closed  ← 全量 head
```

> 三个「反直觉」的地方：
>
> 1. **锚点固定，不顺延**：三条闭源支线分别锚在 `0035_app_publish` / `0025_cloud` /
>    `0100_app_schema` 上，位置不再随公开链增长而变化。公开链在它们之后继续长，
>    不影响任何一条支线。
> 2. **日期不单调**：`erp_init` 是 2026-08-31 建的，却排在 2026-10-20 的
>    `0035_app_publish` 之后——拓扑只看 `down_revision`，不看文件名日期。
> 3. **目录与先后无关**：`ext/` 里的迁移可能排在 `erp/` 之前，也可能之后。

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

> 2026-10-26 门户应用中心整页 500 就是这个：`0035_app_publish` 当时没顺延挂载点。
> （那是旧模型的做法；v0.5.12 起锚点固定、不再顺延任何东西，见规则二。）

### 规则二：闭源支线的锚点固定，不随公开链顺延

闭源侧不是「一条挂在公开链末端的链」，而是**三条锚点固定的独立支线**：

| 支线 | 规模 | 锚在哪个公开 revision |
|---|---:|---|
| erp / crm / mes | 34 | `20261020_0035_app_publish` |
| workflow | 1 | `20260924_0025_cloud` |
| collect | 5 | `20261027_0100_app_schema`（恰好是公开 head） |

三条线最后在 `20261103_1300_merge_closed`（闭源合流点，纯拓扑、零 DDL）汇成一个 head。

**新增公开迁移不需要动任何锚点。** 公开链往前长，三条支线原地不动——这是 v0.5.11
之后相对旧模型最大的简化。旧规则「挂载点跟随公开 head，每加一条迁移顺延一次」已作废。

> 🔴 **不要「顺延」锚点，尤其是别用自动工具。** v0.5.12 之前
> `codegen/builder.py::rebase_closed_chain` 会把「`down_revision` 恰好等于公开 head 的
> 闭源迁移」改挂到新迁移下面。现在 collect 支线的锚点**就是**公开 head，一旦触发：
>
> 1. collect 支线被拖到新迁移之下；
> 2. 新迁移因此进入闭源合流点 `merge_closed` 的**祖先闭包**；
> 3. 已部署库跑 `upgrade heads` 判定它「已应用」——**不报错、不建表**，
>    直到代码查那张表才 500。
>
> 这个函数已在 v0.5.12 废弃（恒返回空列表），`scripts/gen-app.py` 也不再调用它。

### 规则三：两种视图各自闭合

| 视图 | 硬要求 |
|---|---|
| 公开子图（`--tracked-only`，pre-commit + CI 必跑） | **恰好 1 个 head、无断链、单根** |
| 全量（`check-migration-graph.py`） | 允许 1 个以上 head，但每个都必须能沿 `down_revision` 回到公开链；公开子图自身必须完整 |

全量视图允许「新增公开迁移后的 2 head」这个中间态（`merge_closed` + 新公开 head），
`upgrade heads` 会把两者都升到位。这不是错误，别为了「看起来整齐」去改闭源文件。

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

### 规则五：合流之后要清理 `alembic_version` 的多余行

`alembic_version` 是**多行**的：每个 head 一行。执行 `upgrade heads` 或 `alembic merge`
让两个 head 合成一个之后，被合并掉的那个 head **仍然留在表里**——alembic 只是
「显示上」认新的 head（`alembic current` 只打一个），脏行不会自动消失。

v0.5.12 实测：迁移图合流前，生产库 `alembic_version` 是 3 行
（`20260904_mes_0009` / `20260925_0027_workflow` / `20261102_1100_collect`）；
合流后 `heads` 变成 1 个，但这 3 行不会自己变成 1 行。

后果是 `check_alembic_drift.py` 直接炸在 `scalar_one()`：

```
sqlalchemy.exc.MultipleResultsFound: Multiple rows were found when exactly one was required
```

收口后固定查一次：

```bash
$PY -c "from sqlalchemy import create_engine,text; from cenkor_admin.core.config import get_settings; \
        print([r[0] for r in create_engine(get_settings().DATABASE_URL_SYNC).connect() \
               .execute(text('select version_num from alembic_version'))])"
# 必须只有 1 行；多出来的那些是祖先 revision，删掉即可
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

- 必须是当前**公开 head**（11-03 是 `20261027_0100_app_schema`）；
- **不能**是全量 head（`20261103_1300_merge_closed`）——autogenerate 默认就取它，
  那是闭源合流点，公开仓库里根本不存在；
- **不能**是任何一个锚点（`0035_app_publish` / `0025_cloud`），那会在锚点处造出分支。

查当前公开 head 不要翻文档（天天变）：

```bash
PYTHONPATH=backend/src python3 ../scripts/check-migration-graph.py --tracked-only | grep -i head
```

```bash
# 2) 让线上库执行（全量图此刻变成 2 个 head，正常）
$PY -m alembic upgrade heads

#    ⚠️ 演练要指到别的库，用 env.py 单独支持的 CENKOR_DATABASE_URL：
CENKOR_DATABASE_URL="postgresql+psycopg2://user:pw@127.0.0.1:5432/testdb" \
  PYTHONPATH=src $PY -m alembic upgrade heads
#    两个注意点：
#    · 必须 postgresql+psycopg2://（同步驱动）。塞 asyncpg 会 MissingGreenlet。
#    · 别只设 DATABASE_URL_SYNC —— get_settings() 会用 .env 覆盖环境变量
#      （core/config.py:233），静默连回 .env 里那个库。CENKOR_DATABASE_URL 是
#      alembic/env.py 里独立的覆盖口，优先级高于 get_settings()，用它。

# 3) 验证对象真的建出来了（表/列/索引）
#    新建表看一眼： psql -c '\d+ new_table'

# 4) 两套视图自检
$PY ../scripts/check-migration-graph.py --tracked-only
$PY ../scripts/check-migration-graph.py

# 5) 提交：只有一个迁移文件，不需要改任何闭源文件
```

> 🔴 **绝对不要自动「顺延」闭源链入口。** 新拓扑下 collect 支线的锚点**就是**公开 head，
> 一旦顺延，新迁移会进入闭源合流点 `merge_closed` 的祖先闭包，已部署库
> `upgrade heads` 判定它「已应用」→ **静默跳过，不建表，不报错**。
> `builder.rebase_closed_chain()` 已在 v0.5.12 废弃，`gen-app.py` 不再调用。

> 另一种静默失败：先改父节点、后执行。新迁移在拓扑上成了某个已应用 revision 的
> 祖先，alembic 认为「已应用」，`upgrade` 直接跳过——不报错，直到代码查那张表才 500。

### 4.2 新增「闭源/商业应用」迁移

```bash
# 放进对应应用目录，且确认被 .gitignore 命中（输出非空才安全）
$PY -m alembic revision --autogenerate -m "crm_add_xxx" --version-path alembic/versions/crm
git check-ignore -v backend/alembic/versions/crm/2026xxxx_xxxx_crm_add_xxx.py
```

- `down_revision` 取**自己那条支线的 head**，不要接别的应用：

  | 支线 | 接在谁后面（2026-11-03） |
  |---|---|
  | erp / crm / mes | `20260904_mes_0009` |
  | workflow | `20260925_0027_workflow` |
  | collect | `20261102_1100_collect` |

- **不要接在合流点 `merge_closed` 上**——它已经收拢三条支线，往上接会重新分裂出 head。
- 跨支线挂会把两条独立线缝成一条，将来任何一方调整都牵连另一方。
- `commerce/` 现在全部公开，不用考虑忽略规则。`ext/` 是混合目录（13 公开 / 2 闭源）：
  确实要放闭源迁移时**必须逐个加 `.gitignore`**（见 §7.2），否则 `git add -A` 会带进公开仓库。

### 4.3 多 head 的两种来源

| 来源 | 处理 |
|---|---|
| 新增了一条公开迁移，`merge_closed` 还没收拢它 | **不用管**。全量 2 head 是合流模型的正常状态，`upgrade heads` 两个都会升 |
| 两个人同时加了迁移（同一父节点两个子节点） | **要收口**：`alembic merge` |

```bash
$PY -m alembic heads          # 看到 2 个
$PY -m alembic merge -m "merge a/b" <head1> <head2>
```

merge 迁移的 `down_revision` 是元组 `(head1, head2)`，`upgrade()` 留空即可。
合并后重新跑 §4.1 第 4 步，并按规则五清理 `alembic_version` 的冗余行。

> 公开子图（`--tracked-only`）**永远**只能有 1 个 head。开源版只有一条线，
> 多 head 就是出了 bug，必须当场收掉 —— 这一点不因为全量视图放宽而放松。

---

## 5. 校验：提交前必须跑

2026-11-03（v0.5.12）的预期结果：

| 模式 | 迁移数 | head | 硬要求 |
|---|---:|---|---|
| `--tracked-only` | 59 | `20261027_0100_app_schema` | 恰好 1 个 head，无断链 |
| 全量 | 100 | `20261103_1300_merge_closed` | 允许 1 个以上 head，但每个都须可达公开链 |

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

> **erp / crm / mes / workflow / collect 五个商业应用的代码、迁移、`schema.sql`、静态资源全部不进 git。**
> `commerce/` 自 v0.5.11 起**整体开源**（支付中心与交易层不单独收费）；
> `ext/` 是混合目录——15 个迁移里 13 个公开，只有 `0027_workflow` 和合流文件 `1300_merge_closed` 闭源。

因此公开仓库里的迁移图是**不完整**的——这是设计，不是 bug。

### 7.2 `.gitignore` 当前规则（照抄）

```gitignore
# ===== 闭源应用迁移：整目录屏蔽，对应四条支线 =====
backend/alembic/versions/crm/
backend/alembic/versions/erp/
backend/alembic/versions/mes/
backend/alembic/versions/collect/

# ext 是混合目录：15 个里 13 个公开，以下 2 个闭源，逐个登记
backend/alembic/versions/ext/20260925_0027_workflow.py
backend/alembic/versions/ext/20261103_1300_merge_closed.py

# commerce 自 v0.5.11 起整体开源，不再有 commerce 专属忽略规则
# （此前是「先全屏蔽再 ! 反选 3 个平台级迁移」的白名单写法，已全部移除）

# 应用自带 schema（方案 D）同样属商业实现，双保险
backend/src/cenkor_admin/apps/*/schema.sql

# 应用代码本体
backend/src/cenkor_admin/apps/erp/
backend/src/cenkor_admin/apps/crm/
backend/src/cenkor_admin/apps/mes/
backend/src/cenkor_admin/apps/workflow/
backend/src/apps/                    # 外置应用目录，现仅剩 collect
```

另外 `*.db` / `*.sqlite` 也被忽略——本地开发库、扩展应用的独立库文件都不入库。

### 7.3 三个必须知道的细节

1. **`git add -A` 会带进闭源文件**。`ext/` 的闭源迁移是「逐个登记」的，新增一个闭源 ext 迁移时必须同步加规则。提交前固定跑：
   ```bash
   git status --short | grep alembic/versions    # 只应出现你有意公开的文件
   git check-ignore -v backend/alembic/versions/ext/xxx.py   # 输出为空 = 没被忽略，危险
   ```
2. **`commerce/` 已经不用白名单了**（v0.5.11 整体开源）。但 `ext/` 仍然是「逐个登记」——新增一个闭源 `ext/` 迁移必须同步加规则，否则 `git add -A` 会把它带进公开仓库。
3. **双保险**。闭源应用的表结构除了迁移，还有 `apps/<key>/schema.sql`（方案 D，见 §8），两条路径都被忽略。

### 7.4 新克隆（公开仓库）会遇到什么

| 场景 | 结果 |
|---|---|
| `alembic heads` | 1 个（= 最新公开 head，名字会随新增迁移变化，别写死在脚本里） |
| `alembic upgrade heads` | 成功。实测：59 个迁移建 **101 张表**、闭源表 **0 张**、退出码 0 |
| crm/erp/mes/workflow/collect 应用 | 目录本身不在仓库里，不存在「装了但缺表」 |
| `inventory_items` 等 ERP 表 | 不存在。它们由应用自带 `schema.sql`（方案 D）在运行时建，开源版没这个应用 |
| CI | 只对公开链负责，绿了不代表闭源链 OK |

### 7.5 为什么不把它们放进仓库

闭源迁移与 `apps/{crm,erp,mes,workflow}`、`src/apps/collect` 代码同源，属商业实现；一旦进公开仓库，等于把 ERP / CRM / MES / 工作流 / 内容采集的完整表设计开源出去。规则由 `scripts/check-migration-graph.py` 在 pre-commit / CI 双重把关。

> 定价、结算、授权这三块表原属 commerce，自 v0.5.11 起 commerce 整体开源，不再是闭源理由。

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

> **永远用 `upgrade heads`**：它等价于单 head 时的 `head`，但在多 head 时不会整链失败
> （新增公开迁移后，全量图常态就是 2 个 head，见规则三）。

---

## 10. 故障对照表

| 症状 | 根因 | 处理 |
|---|---|---|
| `MultipleHeads: Multiple head revisions are present` | 多 head（并发新增 / 手工改过 down_revision） | `alembic heads` → `alembic merge` 收口；公开子图多 head 一律算 bug |
| `KeyError` / `Can't locate revision identified by 'xxxx'` | 指向了闭源 revision（公开链依赖闭源） | 改 `down_revision` 到公开 head |
| `DuplicateColumn` / `DuplicateTable` 在启动/升级时 | 库结构领先于 `alembic_version` | 幂等层会跳过；随后跑 `check_alembic_drift.py` 判断能否 stamp |
| 升级"成功"但新表不存在 | 新迁移的父节点写成了闭源 revision（多是被自动顺延过），拓扑上被判定「已应用」 | 把父节点改回公开 head，从 `alembic_version` 清掉对应行后重跑 upgrade |
| `StringDataRightTruncation` on `alembic_version` | revision 字符串 > 32 | 缩短 revision（文件名模板已控，手写迁移要自查） |
| autogenerate 生成大批 `drop_table` | 模型没加载全（包目录 / 非 `models.py` 命名） | 查 `model_loader`，`check_schema_drift.py` 表级差异必须为 0 |
| autogenerate 想 `create_table` 已存在的视图 | 视图托管表没过滤 | 确认走的是 `schema_filters.make_include_object` |
| 公开仓库 clone 后建表不全 | 正常：闭源迁移/代码不在仓库（公开版 101 表 vs 完整版 241 表） | 不要试图补；闭源部署用完整工作区 |
| 提交后发现闭源迁移进了仓库 | `git add -A` | `git rm --cached` + 补 `.gitignore`，再 `check-migration-graph --tracked-only` |

---

## 11. 回退与降级

1. **优先向前修**：新增一条修正迁移（补列 / 补索引 / 补数据），生产上比 downgrade 安全。
2. `alembic downgrade -1` 只适用于**你自己刚加的、还没被业务写入依赖**的迁移。
3. 真正回退发版：代码 `git checkout <tag>` + **数据库用升级前的备份**（PostgreSQL 用 `pg_dump` 快照），不要指望 `alembic downgrade` 一条条走完整条链（现在 100 个迁移，且途中会穿过三条闭源支线）。
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

### 13.1 关键常量

> 🔴 **这张表是本文件最容易过时的地方。** 下面「值」一列只写**稳定的**东西；
> 会变的东西（head 名、迁移数）写成**查法**。任何一次新增迁移都别指望回来改这张表。

| 项 | 值 / 查法 |
|---|---|
| 完整工作区 head | `PYTHONPATH=backend/src python3 scripts/check-migration-graph.py \| grep head` |
| 公开仓库 head | `PYTHONPATH=backend/src python3 scripts/check-migration-graph.py --tracked-only \| grep head` |
| 闭源支线锚点（固定不变） | erp/crm/mes → `20261020_0035_app_publish`；workflow → `20260924_0025_cloud`；collect → `20261027_0100_app_schema` |
| 闭源合流点 | `20261103_1300_merge_closed`（`ext/`，**不进公开仓库**，已登记 `.gitignore`） |
| 迁移总数 / 公开数 | 见 §1.1 顶部的统计命令 |
| Python 解释器 | `/www/server/pyporject_evn/cenkor/bin/python3` |
| 数据库 | 仅 PostgreSQL（`DATABASE_URL_SYNC`，psycopg2） |

<details>
<summary>2026-11-03 实测快照（v0.5.12，仅供对照，会变）</summary>

| 项 | 值 |
|---|---|
| 完整工作区 | 100 个迁移，head = `20261103_1300_merge_closed` |
| 公开视图 | 59 个迁移，head = `20261027_0100_app_schema` |
| 公开链建库（空库实测） | 101 张表，闭源表 0 张，退出码 0 |
| 生产库 | 241 张表 |

</details>

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
| `backend/src/cenkor_admin/codegen/builder.py::rebase_closed_chain` | **已废弃（v0.5.12）**：旧的自动顺延入口，恒返回空列表。别重新启用，理由见规则二 |

### 13.3 术语

- **公开链 / 基础链**：git 跟踪的迁移，公开仓库可见。
- **闭源链 / 商业链**：`.gitignore` 排除的迁移，仅完整工作区可见。
- **锚点（旧称挂载点）**：闭源支线接在公开链上的那个父 revision。现有三个，位置固定。
- **合流点**：`alembic merge` 的产物，把多条 head 收成一个。公开侧 `merge_commerce`、
  闭源侧 `merge_closed`，两者都是纯拓扑、零 DDL。
- **视图托管表**：库里是视图、ORM 按同名表映射的对象（20 个 `erp_xxx`）。
- **方案 D**：应用自带 `schema.sql` 建表，alembic 迁移保留空实现以维持链。

---

> 本文档随迁移图变化同步更新。改 `alembic.ini` 的 `version_locations`、动锚点或合流点、调整 `.gitignore` 忽略规则这三类改动，**必须**在同一提交里更新 §1、§3、§7。
