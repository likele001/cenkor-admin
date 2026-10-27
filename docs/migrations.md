# 数据库迁移：两条链、一个挂载点

> 适用：cenkor-admin（hub）后端。开源基础框架与商业应用共用同一套 Alembic 迁移目录，
> 但两张迁移图必须**各自保持单 head，再通过挂载点串成一条**。
> 违反这条规则曾导致 2026-10-26 门户应用中心整页 500，见 §6。

## 1. 三条硬规则

1. **公开链不依赖闭源**：公开（git 跟踪）迁移的 `down_revision` 只能指向公开 revision。
   否则开源仓库里会出现「找不到父迁移」的断链。
2. **挂载点跟随公开 head**：闭源链的挂载迁移 `20261014_124126_create_inventory`
   （revision `20261014_124126_gen_inventory`，下称 `gen_inventory`）的 `down_revision`
   必须等于**最新的公开迁移**。公开链每加一条，就要把它顺延一次。
3. **两种视图都只能有一个 head**：
   - 完整工作区（公开 + 闭源）：head = 闭源链末端；
   - `git` 跟踪视图（开源仓库的样子）：head = `gen_inventory`。

## 2. 两张图长什么样

```
公开/基础链（git 跟踪）
  0001_initial → … → 0028_product_axis → 0030_app_intro → 0031_dev_method
  → 0032_codegen_runs → 0033_upgrade_runs → 0034_upgrade_notes
  → 0035_app_publish → gen_inventory          ← 公开视图 head（挂载点）
                            │
商业应用闭源链（.gitignore，不进开源仓库）
                            └→ erp_init → … → mes_0009 → 0020_commerce
                               → … → 0029_product_commerce   ← 完整部署 head
```

- 开源使用者只有上半段：单 head，`alembic upgrade heads` 即可，无需关心挂载点。
- 闭源部署两段都有：`alembic_version` 里只有一行（闭源 head），迁移仍然是一条线。
- 挂载点为什么要存在：闭源迁移不能出现在开源仓库，又必须排在公开迁移之后，
  所以把闭源子链「挂」在公开链的末端，而不是让它成为第二个 head。

## 3. 新增一条公开迁移（最容易踩的顺序陷阱）

假设当前公开迁移是 `0035`、挂载点是 `gen_inventory → 0035`，要加 `0036`：

1. **新建迁移**，`down_revision` 填当前挂载点的父（现在 `0035`）。
   注意：`alembic revision --autogenerate` 默认把 `down_revision` 设成脚本目录的当前
   head——闭源部署里那是闭源 head `0029`，必须手工改成公开 revision，否则公开迁移
   就挂到闭源链上了。也不要挂到 `gen_inventory` 上——那会变成挂载点之后的第二个 head。
   此时 `alembic heads` 会显示两个（`0036` 与 `0029`），属正常中间态。
2. **先让线上库执行**：`alembic upgrade heads`（重启 hub 也会自动做）。
   此刻 `0036` 还不是闭源 head 的祖先，alembic 会真正执行它。
3. **验证对象真的建出来了**（新表/新列/索引），再往下走。
4. **顺延挂载点**：把 `gen_inventory.down_revision` 从 `0035` 改成 `0036`，
   图恢复单 head。
5. `scripts/check-migration-graph.py` 两种模式都通过后，
   把「新迁移 + 挂载点改动」**一起提交**。

> 反了会怎样：先顺延、后执行，`0036` 在拓扑上变成闭源 head 的祖先，
> alembic 会认为它「已应用」，`upgrade` 静默跳过——不报错，直到代码查那张表/列才 500。
> 2026-10-26 的 0035 就是这一步没做（当时连挂载点都没顺延）。

> 忘了顺延会怎样：双 head，但 hub 启动与在线升级现在都用 `alembic upgrade heads`，
> 新迁移照样执行，不会整链卡死；`check-migration-graph.py` 会报错，补上顺延即可。
> （历史版本用 `upgrade head`，遇到双 head 直接 MultipleHeads，一条都不执行。）

> 闭源应用（erp / crm / commerce / mes 等）的新迁移方向相反：挂在**当前闭源 head**
> （现在 `0029`）之后，不要碰公开链，也不要动挂载点。判断依据只有一个：
> 这个迁移文件会不会进开源仓库——会，就插在挂载点之前；不会，就接在闭源 head 之后。

## 4. 校验清单

在仓库根目录（`backend/` 下执行 alembic 命令）：

```bash
cd backend
alembic heads            # 完整部署：1 个；新增迁移的中间态：2 个
alembic current          # 线上库当前版本（应为闭源 head）
alembic history | head   # 确认 0035 → gen_inventory → erp_init 的串联顺序
cd ..
python3 scripts/check-migration-graph.py                # 完整工作区：必须 1 head
python3 scripts/check-migration-graph.py --tracked-only # 开源视图：必须 1 head
```

对象级体检（可选，只读）：`backend/scripts/check_hub_schema.py`
——核对 `alembic_version` 与 0030–0035 实际创建的表/列/索引。

## 5. 开源仓库 / 闭源部署的差异

### 5.1 两条链的关系（2026-10-27 校正）

仓库被切成两半：**公开链**（进 git）和**闭源链**（不进 git，只在完整部署里有）。

```
公开链 39 个：0001_initial → … → 0034_upgrade_notes → gen_inventory
                                                            ↓
                                    20261014_124200_schema_versions（公开 head）
                                                            ↓
闭源链 44 个：                                      0035_app_publish
                                                            ↓
                                            erp_init → … → 0029_product_commerce
                                                            ↓
                                   20261027_0100_app_schema（全集 head，空实现）
```

**核心规则：公开迁移绝对不能依赖闭源 revision。**

之前的错误做法是把挂载点「顺延」—— 让公开的 `gen_inventory` 挂到闭源的
`0035_app_publish` 上。这样两条链确实串成一条，但**开源版单独拿出来就断链**：

```
KeyError: '20261020_0035_app_publish'
```

而且 `docker/fullstack/entrypoint.sh` 写的是
`alembic upgrade heads || echo "[entrypoint] 迁移未成功，交由应用内 lifespan 重试"`
—— 报错被吞、服务照常启动，然后所有接口 500。**别人 clone 下来会以为装好了，实际一张表都没建。**

同一个坑当天踩了第二次：`20261027_0100_app_schema` 最初把父节点设成闭源的
`0029_product_commerce`，又造出一次「公开迁移依赖闭源」。是
`scripts/check-migration-graph.py --tracked-only` 当场把它拦下来的。
**建在闭源链尾的公开迁移，等于没建 —— 开源仓库里看不到它。**

### 5.2 正确做法：公开链自己闭合，闭源挂在公开 head 之后

| 文件 | down_revision | 归属 |
|---|---|---|
| `ext/20261014_124126_create_inventory.py` | `20261018_0034_upgrade_notes` | 公开 |
| `core/20261014_124200_schema_versions.py` | `20261014_124126_gen_inventory` | **公开 head**，建 `app_schema_versions` |
| `ext/20261020_0035_app_publish.py` | `20261014_124200_schema_versions` | 闭源挂载点，顺延到这里 |
| `erp/20260831_0001_erp_init.py` | `20261020_0035_app_publish` | 闭源 |

`app_schema_versions` 为什么必须在公开链：它是 `core/app_schema.py`（方案 D）的记账表，
属于平台核心，开源部署同样要用（`sync_builtin_apps()` 直接读写它）。

`ext/20261027_0100_app_schema.py` 已改为**空实现** —— 它当初建的正是这张表，
前移到公开链之后，这里只保留 revision 占位。已部署环境的 `alembic_version` 指向它，
删掉会报「未知 revision」。空实现对任何环境都无副作用：
新装时公开链已建好表，已部署的环境早已执行过、不会重跑。

以后**新增公开迁移**：接在 `20261014_124200_schema_versions` 后面，然后把这个新 revision
填进 `0035_app_publish.down_revision`（顺延的是**闭源的挂载点**，不是公开的）。

以后**新增闭源迁移**：正常接在当前闭源 head 后面，不用动公开链。

> 判断标准只有一条：**这个迁移要不要出现在开源仓库里？** 要 → 挂公开 head；
> 不要 → 挂闭源 head。别靠目录名判断，目录只是分类，不决定归属。

### 5.3 实测验证（2026-10-27，从 GitHub 公开地址 clone 后真装）

| 场景 | 迁移数 | head | 建表数 | 结果 |
|---|---:|---|---:|---|
| 只有公开链（`git clone` 公开仓库） | 39 | `20261014_124200_schema_versions` | **59** | ✅ 退出码 0，闭源表 **0 张** |
| 公开 + 闭源（完整部署） | 83 | `0100_app_schema` | 81 核心 + 107 应用 + 20 视图 | ✅ 单 head |

公开链 39 个 = 原有 38 个 + `20261014_124200_schema_versions`。

开源版建出的 59 张表全是平台核心：`auth_*` / `rbac_*` / `cms_*` / `portal_*` /
`notifications` / `cloud_storage_*` / `app_*`（商店）/ `codegen_runs` / `inventory_*` /
`links` / `my_todo_items` / `app_schema_versions`。

复现命令：

```bash
git clone https://github.com/likele001/cenkor-admin /tmp/x && cd /tmp/x/backend
CENKOR_DATABASE_URL="postgresql+psycopg2://cenkor:PW@127.0.0.1:5432/testdb" \
  PYTHONPATH=src python -m alembic upgrade head     # 39 步，59 张表
```

`alembic.ini` 的 `version_locations` 列了 6 个目录，公开仓库里只有
`core` / `commerce` / `ext` 三个 —— **alembic 对不存在的版本目录不报错**（已实测），
不需要为缺目录做特殊处理。

### 5.4 命令

| 场景 | 命令 | 说明 |
|---|---|---|
| 只用开源基础框架 | `alembic upgrade head` | 单 head，`heads` 也等价 |
| 闭源完整部署 | `alembic upgrade head` | 挂载点正确时单 head |
| 全新装库 | `alembic upgrade head` | 顺序由拓扑决定 |
| 已有库补跑漏掉的公开迁移 | 手工幂等 DDL + 校验 | 见 §6；`upgrade` 是 no-op |

> 用 `head` 而不是 `heads`：`heads` 会在多 head 时静默只跑一部分，
> 而多 head 本身就该当成错误处理（见 §4 校验清单）。

## 6. 事故复盘：2026-10-26 门户 500

- 现象：`https://portal.cenkor.cn/apps` 显示「加载应用列表失败」，统计全 0。
- 直接原因：`app_submissions` 缺 `schema_version/min_core_version/changelog/published_at/yanked_at`，
  `GET /api/v1/store/apps` 抛 `UndefinedColumnError`。
- 根因：`0035_app_publish` 合入时挂载点仍指向 `0034`，公开链与闭源链各留一个 head；
  hub 启动的 `alembic upgrade head` 抛 `MultipleHeads`，被 try/except 吞成一行
  structlog error（未进 `logs/hub.log`），0035 从未执行。
- 修复：
  1. 挂载点顺延到 `0035`，图恢复单 head；
  2. 启动与在线升级改用 `alembic upgrade heads`（单 head 时等价，双 head 时不再整链失败）；
  3. 线上库因拓扑已被视为「0035 已应用」，用
     `backend/scripts/apply_app_publish_ddl.py --apply` 幂等补齐列/索引并回填 `published_at`；
  4. `scripts/check_hub_schema.py` 复核。
- 教训：**拓扑检查只保证图是通的，不保证线上真的执行过**；新增公开迁移必须
  「先执行、再顺延、后提交」。

## 7. 症状对照

| 症状 | 大概率原因 | 处理 |
|---|---|---|
| 接口 500 `column ... does not exist` | 迁移没执行 / 版本停在旧 head | `alembic current`、对象体检、按 §3 补跑 |
| 启动日志无 `migration.ok`，或出现 MultipleHeads | 挂载点漏顺延 | 顺延挂载点；本次起 `heads` 已兜底 |
| `alembic upgrade` 无任何 revision 输出，但代码报缺列 | 先顺延后执行，迁移被静默跳过 | 手工幂等 DDL + 校验（见 §6） |
| `--tracked-only` 报断链 | 新公开迁移未加入 git / 公开迁移挂了闭源 revision | 与新迁移一起提交；改回公开父节点 |

## 8. 回退与降级

- 回退公开迁移在闭源部署上**不要用 `alembic downgrade -1`**：当前版本是闭源 head，
  `-1` 回退的是闭源迁移。
- 正确顺序：先把挂载点退回该迁移的父修订 → 再针对该迁移执行其 `downgrade()`
  中定义的 DDL（删列/删表前先备份；`downgrade <rev>` 会连带回退途经的闭源迁移，
  生产上不要直接跑）。
- 回退后同样跑一遍 §4 的校验清单，确保两种视图都恢复单 head。

## 9. 相关脚本

| 脚本 | 用途 |
|---|---|
| `scripts/check-migration-graph.py` | 迁移图自检（断链 / 重复 / head 数量 / revision 长度），可挂 pre-commit |
| `backend/scripts/check_hub_schema.py` | 只读体检：版本号 vs 实际表/列/索引 |
| `backend/scripts/check_schema_drift.py` | **全量双向 diff**：ORM 声明的结构 vs 线上真实库，按业务域汇总（见 §10） |
| `backend/scripts/apply_app_publish_ddl.py` | 幂等补齐 0035 的列（预演 / `--apply`），仅用于本次事故收尾 |
| `scripts/migrate-and-seed-host.sh` | 宿主机模式迁移 + 播种 |

## 10. autogenerate 的三道护栏（2026-10-27 补齐）

`alembic revision --autogenerate` 在这套库里曾经是**最危险的一条命令**。

2026-10 之前 `alembic/env.py` 的模型加载循环只认单文件 `<app>/models.py`，
而实际情况是三种形态并存：

| 形态 | 例子 | 旧循环是否认 |
|---|---|---|
| `<app>/models.py` | `cms/models.py` | ✅ |
| `<app>/models/` 包 | `erp/models/__init__.py` | ❌ **ERP 74 张表全漏** |
| `<app>/<sub>/models.py` | `crm/integration/models.py` | ❌ 漏 5 张 |
| 不叫 models 的模型文件 | `system/store_models.py` | ❌ 漏 3 张 |

漏加载的后果不是「少几个检查项」，而是 autogenerate 把它们判成「库里多出来的表」。
实测那一次生成 **101 个 `drop_table`**，全是 `app_developers` / `crm_api_keys` /
`erp_products` 这种在用的真表 —— 谁执行谁删库。

### 10.1 护栏一：模型必须加载全

`alembic/env.py` 的 `_load_app_models()` 现在：

- 三种形态都认（`models.py` / `models/__init__.py` / 递归 `<sub>/models.py`）；
- 递归时跳过 `routers/`、`tests/`、`schemas/` —— `crm/routers/models.py` 是 API 层定义，
  与真模型重名，加载会抛 `Table 'crm_customers' is already defined`；
- 非 models 命名的模型文件用 `_EXTRA_MODEL_MODULES` 显式登记；
- **导入失败打到 stderr 而不是静默 `pass`** —— 静默是这次事故的放大器：
  少加载了没人知道，直到有人跑 autogenerate。

### 10.2 护栏二：不该参与 diff 的对象要过滤

规则集中在 `core/schema_filters.py`，`env.py` 与体检脚本共用同一份
（两边各写一份的话，体检结论和 autogenerate 结论迟早对不上）：

- **视图托管表**：20 个 `erp_xxx` 在库里是视图，透传到 MES 的 `mes_xxx` 真表。
  ORM 按 `erp_xxx` 映射，autogenerate 会误判「表缺失 → create_table」。
  运行时查 `information_schema.views` 动态排除，不维护硬编码名单。
- **无 ORM 的遗留表**：`*_legacy`（改名前的备份）、`mes_*` 老结构（已被 `mesx_*`
  取代，但 erp 视图仍指向它们）、只有 DDL 没 models 的 `inventory_*`。
  清单见 `LEGACY_UNMAPPED_TABLES`，新增前先确认真的是「代码不写、历史要读」。

### 10.3 护栏三：新功能用定向 diff，别全量

历史积累的列级漂移（NOT NULL 声明、列注释、索引命名）共 516 处，
全量 autogenerate 会产出 3000+ 行与本次改动无关的内容，根本没法 review。

开发新表/新列时指定范围：

```bash
cd backend
ALEMBIC_SCOPE_TABLES=my_new_table alembic revision --autogenerate -m "feat: add my_new_table"
ALEMBIC_SCOPE_TABLES=orders,order_items alembic revision --autogenerate -m "feat: ..."
```

生成的迁移只含这些表的变更，删掉无关行后按 §3 的顺序（先执行、再顺延挂载点、后提交）走。

### 10.4 体检命令

```bash
cd backend
python3 scripts/check_schema_drift.py          # 汇总（按业务域）
python3 scripts/check_schema_drift.py -v       # 逐条列出 516 处
python3 scripts/check_schema_drift.py --json   # CI 存档

# 2026-10-27 基线（改动后实测）
#   metadata 187 表 / 视图托管 20 个（已排除）
#   表级差异 0        ← 关键指标，非 0 说明有 models 没加载上
#   列属性 333 / 索引 115 / 约束 36 / 其他 32
```

退出码：`0` = 表级一致；`1` = 存在表级漂移（有表在库不在 metadata，或反之）。
**表级差异一旦变成非 0，先查 models 加载，不要去看 autogenerate 的输出。**

### 10.5 那次故障是怎么被发现的

`alembic current` 报 `Can't locate revision identified by '20261021_0036_merge_heads'` ——
0036 是当时误判「双 head」写的纯拓扑合并迁移，后来发现 `gen_inventory` 重挂之后
图本来就是单链，文件被删了但 `alembic_version` 没回退，于是整条迁移链彻底不可用。

处置：把 `alembic_version` 对齐到代码里真实的 head（`20261007_0029_product_commerce`），
之后 `current` / `heads` / `upgrade` 三条命令才恢复正常。

> 教训：**merge 迁移只能删文件不能只删一半**。真要撤掉一条 merge，必须同时
> 把库里的 `alembic_version` 改回它合并前的某个 head，否则 alembic 直接瘫。

---

## 11. 迁移目录按应用分区（2026-10-27）

### 11.1 目录结构

81 个迁移已按应用移入子目录，`down_revision` 一个字没改 —— **执行顺序仍是原来那条单链**，
这里只是工程分类，不是分支隔离。

```
backend/alembic/versions/
├── core/       28  平台核心（auth / rbac / cms / portal / 通知 / 云存储 / 应用商店）
├── erp/        19  ERP
├── crm/         6  CRM
├── mes/         9  MES
├── commerce/    9  商业化（定价 / 订单 / 授权 / 支付 / 结算 / 分销 / 促销）
└── ext/        10  平台扩展（云存储 / 工作流 / 库存 / 代码生成 / 升级 / 应用发布）
```

`alembic.ini` 里用 `version_locations` 把这 6 个目录全部纳入扫描：

```ini
version_path_separator = space
version_locations = %(here)s/alembic/versions/core %(here)s/alembic/versions/erp %(here)s/alembic/versions/crm %(here)s/alembic/versions/mes %(here)s/alembic/versions/commerce %(here)s/alembic/versions/ext
```

### 11.2 新增迁移必须指定目录

不指定 `--version-path` 时，alembic 会把文件生成到 `version_locations` 里某个不确定的位置
（实测会落到 `commerce/`，与业务无关）。**养成显式指定的习惯：**

```bash
cd backend

# 平台核心
ALEMBIC_SCOPE_TABLES=my_table alembic revision --autogenerate -m "feat: add my_table" \
  --version-path alembic/versions/core

# MES
ALEMBIC_SCOPE_TABLES=mes_xxx alembic revision --autogenerate -m "mes: xxx" \
  --version-path alembic/versions/mes

# ERP / CRM / 商业化 / 扩展同理
```

### 11.3 分区之后仍然做不到的事

目录分区解决的是「找文件、review、归类」，**不解决「基础版不该建 MES 表」**。

原因：81 个迁移仍然是一条链，`alembic upgrade head` 会从 `0001_initial` 一路跑到
`0029_product_commerce`，中间 ERP 19 步、MES 9 步、CRM 6 步、商业化 9 步一个都跳不过。

另外 `branch_labels = ("crm_app",)` 全项目只写过一次（在 `20260903_crm_0001.py`），
但 alembic 的分支名沿链继承 —— 结果 **81 个节点全被打上 `crm_app`**，连最老的
`0001_initial` 都是。所以 `alembic upgrade crm_app@head` 升的不是 CRM，是全部。

要实现「装什么应用建什么表」，需要方案 D：应用自带 schema，见下一节。

> **2026-10-27 补注**：方案 D 已落地（见 §12）。上面这段描述的是 A 做完、D 还没做时的状态。
> 现在 34 个 crm/erp/mes 迁移已是空实现，`alembic upgrade head` 只建 81 张核心表，
> 应用表由 `apps/<key>/schema.sql` 在启动时按 `CENKOR_APPS` 创建。


### 11.4 相关脚本已同步

`scripts/check-migration-graph.py` 的 `collect()` 原先只 `os.listdir` 一层，
迁移移入子目录后一个文件都扫不到，已改为 `os.walk` 递归。

```bash
python3 scripts/check-migration-graph.py          # 全量：81 文件 / 81 revision / 单 head
```

## 12. 应用自带 schema：方案 D（2026-10-27）

§11 的目录分区解决了「文件归类」，但没解决「基础版不该建 MES 表」。方案 D 把**应用表的建表权**
从 alembic 手里拿走，交给应用自己。

### 12.1 一句话原理

> alembic 只建**平台核心表**；应用（crm / erp / mes）的表由 `apps/<key>/schema.sql`
> 在后端启动时自动建，幂等执行、带版本指纹、缺视图自动补。

### 12.2 三层改动

| 层 | 文件 | 作用 |
|---|---|---|
| 迁移链 | 34 个 crm/erp/mes 迁移改成空实现 | 保留 revision 维持链完整，不再建表 |
| 执行器 | `src/cenkor_admin/core/app_schema.py` | 读 schema.sql → 比对版本指纹 → 执行 → 记账 |
| 启动钩子 | `src/cenkor_admin/main.py` | alembic 跑完后调 `sync_builtin_apps()` |

配套还有：
- `core/schema_filters.py` 新增 `APP_SCHEMA_PREFIXES` / `is_app_managed_table()`，
  让 autogenerate 和漂移体检都不再管应用表（127 张表被正确排除）
- `apps/base.py` 的 AppManifest 新增 `schema_managed: bool` / `schema_file: str`
- 每个应用目录下放 `schema.sql` + 在 MANIFEST 里置 `schema_managed=True`
- 新迁移 `20261027_0100_app_schema` 建记账表 `app_schema_versions`

### 12.3 记账表

```sql
CREATE TABLE IF NOT EXISTS app_schema_versions (
    app_key    VARCHAR(64) PRIMARY KEY,
    version    VARCHAR(32) NOT NULL,   -- 取自 MANIFEST 的 version
    checksum   VARCHAR(64) NOT NULL,   -- schema.sql 内容 sha256
    applied_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

「版本 + 校验和」双维度判等：版本号没变但 SQL 改了（改内容不改 MANIFEST）也会重跑，
避免手工改 schema.sql 后不生效。

### 12.4 双轮执行：视图补偿

ERP 有 20 个 `erp_xxx` 在库里是**视图**，透传到 `mes_xxx` 真表。
按目录名字母序 `crm → erp → mes`，第一轮跑 ERP 时 MES 表还不存在，视图建不出来。

所以 `sync_builtin_apps()` 跑两轮：

```
第一轮：建所有应用的表（视图缺失的算「已执行」，继续往下走）
第二轮：回头检查每个应用缺哪些视图，缺就重跑该应用 schema.sql
```

日志里会出现 `app.schema.views_retry key=erp missing=20`。

### 12.5 跨应用外键

应用之间的依赖是真实存在的：

```
 7  REFERENCES public.auth_users       ← 三个应用都依赖平台核心
15  REFERENCES public.mes_*            ← ERP 依赖 MES
 4  REFERENCES public.crm_*            ← ERP 依赖 CRM
```

单个应用文件里 `ALTER TABLE ... ADD CONSTRAINT` 如果目标表不存在会**整份失败回滚**。
所以生成 schema.sql 时给每条跨应用外键加了守卫：

```sql
DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'erp_attachments_uploader_id_fkey')
     AND to_regclass('public.auth_users') IS NOT NULL THEN
    ALTER TABLE ONLY public.erp_attachments
        ADD CONSTRAINT erp_attachments_uploader_id_fkey
        FOREIGN KEY (uploader_id) REFERENCES public.auth_users(id) ON DELETE SET NULL;
  END IF;
END $$;
```

装 ERP 不装 MES 时，那 15 个外键静默跳过，不阻断建表。后续补装 MES 后重启，
因为 `pg_constraint` 里仍不存在该约束，会自动补上。

### 12.6 三个应用 schema.sql 的体量

| 应用 | 语句数 | 行数 | 内容 |
|---|---:|---:|---|
| crm | 150 | 850 | 17 表 / 17 序列 / 56 索引 / 43 约束 |
| erp | 487 | 3456 | 54 表 / 74 序列 / 66 索引 / 202 约束 / **20 视图** |
| mes | 278 | 1611 | 36 表 / 16 序列 / 33 索引 / 96 约束 |

由 `tmp/gen_schema.py` 从 pg_dump 输出自动转换生成，规则：
- `CREATE TABLE` → `CREATE TABLE IF NOT EXISTS`
- `ALTER TABLE ADD CONSTRAINT` → 包 `DO $$ ... pg_constraint 存在性检查 ... $$`
- `setval(...)` **全部丢弃**（否则新库的序列起点会和已有数据主键冲突）
- 过滤 `\restrict` / `\unrestrict`（pg_dump 17+ 注入的 psql 元命令）
- 过滤 `*_legacy` / `*_bak_*` 历史备份表

### 12.7 终极验证结果（2026-10-27）

空库从零跑一遍完整链路：

```
[1] 重建空库 cenkor_fresh_test
[2] alembic upgrade head
      已执行迁移步数: 82
      版本: 20261027_0100_app_schema
      对象: 81 表 / 0 视图        ← 只有核心表
      应用表: 0                    ← 全量剥离成功
[3] 执行三个应用的 schema.sql
      crm OK   erp OK   mes OK
[4] 视图补偿第二轮 → 188 表 / 20 视图
[5] 与生产库逐项对比（排除 *_legacy / *_bak_*）
```

| 项 | 生产 | 新库 | 差异 |
|---|---:|---:|---:|
| 表 | 188 | 188 | **0** |
| 视图 | 20 | 20 | **0** |
| 索引 | 583 | 583 | **0** |
| 外键 | 142 | 142 | **0** |
| 主键/唯一约束 | 372 | 372 | **0** |
| 列（名/类型/长度/可空/默认值） | 2703 | 2703 | **0** |

幂等性另外单测：在已有 188 表的库上连跑 3 轮 `sync_builtin_apps()` ——
第 1 轮 `applied` 无报错，第 2、3 轮全部 `skipped`，对象数一个没变。

### 12.8 两条升级路径

**A. 老库（表已存在，`app_schema_versions` 为空）**

```
alembic upgrade head   → 已在 head，无操作
启动                   → app_schema_versions 空 → 三份 schema.sql 全量执行
                         因为全是 IF NOT EXISTS，实际只补了缺的视图
                       → 写入 3 条版本记录
```
这是生产库重启后会走的路径，已在 fresh_test 上等价验证（第 1 轮 applied 无报错）。

**B. 新环境从零安装**

```
alembic upgrade head   → 建 81 张核心表
启动                   → 建 107 张应用表 + 20 视图
```

### 12.9 顺手修掉的一个致命 bug

给 `alembic/env.py` 加「查视图名」的 SQL 时踩了 SQLAlchemy 2.0 的坑：

> 执行任何 SQL 都会**隐式开启事务**；alembic 的 `begin_transaction()` 检测到
> `connection.in_transaction()` 为 True 时，会退化成 `nullcontext()`、**不 commit**。
> 结果：所有迁移的 DDL 和 `alembic_version` 更新在连接关闭时被整体 rollback，
> 而命令照样打印 `Running upgrade`。

这就是之前 `alembic_version` 一直卡在 `20261007_0029_product_commerce`、
`0030~0035` 永远不生效的真正原因。修法是在 `context.configure()` 之前加：

```python
connection.rollback()
```

同一次还补了 `import os`（`env.py` 里用 `os.environ` 却漏了这个导入，
导致 `alembic` 直接 `NameError` 退出，而验证脚本用 `grep | wc -l` 把报错吞了，
显示成「跑了 0 步」）。

### 12.10 换库验证的正确姿势

`get_settings()` 会用 `.env` 里的值**强制覆盖** `DATABASE_URL_SYNC` 环境变量
（设计如此，防止 shell 残留变量污染生产）。所以想临时换库只能用它没覆盖的变量：

```bash
export CENKOR_DATABASE_URL="postgresql+psycopg2://cenkor:口令@127.0.0.1:5432/测试库"
```

`alembic/env.py` 和 `core/app_schema.py` 都优先读这个变量。

### 12.11 还做不到的事

- **应用之间的解耦只做了一半**：建表能分开，但 ERP 的 15 个外键仍指向 `mes_*`。
  真正做到「ERP 独立可装」需要改数据模型把这些跨应用外键拆掉，属独立任务。
- **回滚（downgrade）没做**：34 个空实现的 `downgrade()` 也是空的，
  意味着回退到旧版本不会删应用表。这是有意的 —— 删数据比不删危险。
- **`pay_channels_bak_leakfix20260925`** 是 2026-09 一次泄漏修复留下的手工备份表，
  还躺在生产库里，与本次改造无关，观察期后单独清理。

---

## 13. 闭源隔离：.gitignore 规则（2026-10-27）

迁移按应用分入子目录后，原有的一条规则失效了：

```gitignore
backend/alembic/versions/2026*_mes_*.py   # 老的扁平布局，文件移进 mes/ 后匹配不到
```

结果 40 个闭源迁移重新暴露在 `git add -A` 的扫描范围内 —— 这些文件含完整的
ERP / MES / CRM 表结构，一次误提交就是商业实现外泄。

### 13.1 当前规则

```gitignore
# 整目录闭源
backend/alembic/versions/crm/
backend/alembic/versions/erp/
backend/alembic/versions/mes/

# 混合目录：默认屏蔽，! 反选回平台级公开迁移
backend/alembic/versions/commerce/*
!backend/alembic/versions/commerce/20261007_0028_product_axis.py
!backend/alembic/versions/commerce/20261009_0030_app_intro.py
!backend/alembic/versions/commerce/20261010_0031_dev_method.py

# ext/ 逐个登记（7 公开 : 4 闭源）
backend/alembic/versions/ext/20260924_0025_cloud.py
backend/alembic/versions/ext/20260925_0027_workflow.py
backend/alembic/versions/ext/20261020_0035_app_publish.py
backend/alembic/versions/ext/20261027_0100_app_schema.py

# 应用自带 schema，双保险
backend/src/cenkor_admin/apps/*/schema.sql
```

`apps/{crm,erp,mes}/` 整目录在更早的规则里已经屏蔽（第 67、68、83 行），无需重复。

### 13.2 三个必须知道的细节

**1. `.gitignore` 对已跟踪文件无效。**

```bash
git add -f <file>              # 强制加入，忽略规则形同虚设
git rm -r --cached <path>      # 已经进过索引的，必须先这样退出索引
```

`git ls-tree -r HEAD` 里的文件不受任何 ignore 规则约束。判断有没有闭源文件已经被
跟踪，用这一条：

```bash
git ls-tree -r HEAD --name-only | while read f; do
  git check-ignore -q "$f" && echo "已跟踪却被忽略: $f"
done
```

输出为空才安全。

**2. 目录被整体排除时，`!` 反选不生效。**

```gitignore
backend/alembic/versions/commerce/      # ✗ 父目录被排除，下面的 ! 全部失效
!backend/alembic/versions/commerce/xxx.py
```

必须写成 `commerce/*`（排除目录内的条目，但目录本身仍可进入），反选才起作用。

**3. `--tracked-only` 自检是技术兜底，不是替代品。**

`.githooks/pre-commit` 会跑 `scripts/check-migration-graph.py --tracked-only`，
校验的是**暂存区**里的迁移能否闭合。它能抓住「公开迁移依赖闭源 revision」
（表现为 `✗ 断链：xxx 缺失的 down = yyy`），但抓不住「闭源迁移被误提交且拓扑自洽」。

所以两类机制要同时存在：`.gitignore` 负责堵源头，自检负责兜语义。

### 13.3 新增迁移时怎么做

| 类型 | 操作 |
|---|---|
| 公开迁移 | 直接放在 `core/` 或 `ext/`（`commerce/` 需确认不在屏蔽名单） |
| 闭源迁移 | 放 `crm/` `erp/` `mes/` 自动屏蔽；放 `ext/` 必须往 `.gitignore` 追加一行 |

提交前自查：

```bash
git add -A --dry-run | grep -E 'versions/(crm|erp|mes|commerce)/|schema\.sql'
# 输出为空才提交
```

### 13.4 实测记录

| 检查项 | 结果 |
|---|---|
| 46 个闭源文件中被忽略 | 43 个（另 3 个是公开的 commerce 迁移，符合预期） |
| HEAD 已跟踪文件误中忽略规则 | 0 |
| `git add -A` 在迁移目录的产出 | 0 |
| 从 GitHub clone 后 `apps/{crm,erp,mes}` 目录数 | 0 |
| 从 GitHub clone 后 `versions/{crm,erp,mes}` 目录数 | 0 |
| 从 GitHub clone 后 `commerce/` 文件数 | 3（全部公开） |
| 从 GitHub clone 后 `ext/` 文件数 | 7（全部公开） |
| 模拟新增 `versions/erp/fake.py` 后 `git add -A` | 零产出 |
| 公开链 head | `20261014_124200_schema_versions`（唯一） |
