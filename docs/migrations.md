# 迁移事故复盘与历史（2026-08 ~ 2026-11）

> 🔴 **这篇不是规范，是病历。**
>
> 需要照着做事时，看 [**database-migrations.md**](./database-migrations.md) —— 那是唯一权威规范。
> 本文只回答一个问题：**「以前出过什么事，为什么现在要这样规定」**。
>
> 里面的 revision 名、表名、行数都是**当时**的事实。要查现在的真实状态，永远跑命令，
> 不要抄本文的数字：
>
> ```bash
> cd /www/wwwroot/cenkor-admin
> PYTHONPATH=backend/src python3 scripts/check-migration-graph.py                # 全量视图
> PYTHONPATH=backend/src python3 scripts/check-migration-graph.py --tracked-only # 公开视图
> ```

## 目录

1. [2026-10-26 门户应用中心整页 500](#1-2026-10-26-门户应用中心整页-500)
2. [2026-10-27 一次 autogenerate 生成 101 个 drop_table](#2-2026-10-27-一次-autogenerate-生成-101-个-drop_table)
3. [2026-10-27 CI 全红的真正原因：GitHub 账号被账单锁定](#3-2026-10-27-ci-全红的真正原因github-账号被账单锁定)
4. [2026-10-28 `Can't locate revision`：merge 迁移只删了文件](#4-2026-10-28-cant-locate-revisionmerge-迁移只删了文件)
5. [2026-10-31 六份旁路 SQL 从未被执行](#5-2026-10-31-六份旁路-sql-从未被执行)
6. [2026-11-03 闭源迁移一度暴露在 `git add -A` 范围内](#6-2026-11-03-闭源迁移一度暴露在-git-add-a-范围内)
7. [2026-11-28 `cms_sites` 缺失：版本戳领先于真实结构](#7-2026-11-28-cms_sites-缺失版本戳领先于真实结构)
8. [这些事故共同的形状](#8-这些事故共同的形状)

---

## 1. 2026-10-26 门户应用中心整页 500

**现象**：`https://portal.cenkor.cn/apps` 显示「加载应用列表失败」，统计全 0。

**直接原因**：`app_submissions` 缺 `schema_version / min_core_version / changelog /
published_at / yanked_at` 五列，`GET /api/v1/store/apps` 抛 `UndefinedColumnError`。

**根因链条**（这是最有价值的部分）：

1. `0035_app_publish` 合入时，闭源挂载点仍指向 `0034` → 公开链与闭源链各留一个 head；
2. hub 启动时的 `alembic upgrade head`（单数）抛 `MultipleHeads`，**一条都不执行**；
3. 该异常被 `try/except` 吞成一行 structlog error，且**没进 `logs/hub.log`**；
4. 于是「容器全 healthy，数据库一张表都没建」——监控完全看不出来；
5. `0035` 从未执行，但拓扑上它「已在路径中」，后续 `upgrade` 也不会补。

**修复**：

1. 挂载点顺延到 `0035`，图恢复单 head（这是**旧模型**的做法，v0.5.11 起已改为锚点固定，别照做）；
2. 启动与在线升级改用 `alembic upgrade heads`（复数）——单 head 时等价，多 head 时不再整链失败；
3. 线上库因拓扑已被视为「0035 已应用」，用 `backend/scripts/apply_app_publish_ddl.py --apply`
   幂等补齐列/索引并回填 `published_at`；
4. `scripts/check_hub_schema.py` 复核。

**教训**：**拓扑检查只保证图是通的，不保证线上真的执行过。**

> 这条教训在 2026-11-28 又应验了一次，见 §7。

---

## 2. 2026-10-27 一次 autogenerate 生成 101 个 drop_table

**现象**：`alembic revision --autogenerate` 生成的迁移里有 **101 个 `drop_table`**，
全是 `app_developers` / `crm_api_keys` / `erp_products` 这种在用的真表。谁执行谁删库。

**根因**：`alembic/env.py` 的模型加载循环只认单文件 `<app>/models.py`，
而实际有四种形态并存：

| 形态 | 例子 | 旧循环是否认 |
|---|---|---|
| `<app>/models.py` | `cms/models.py` | ✅ |
| `<app>/models/` 包 | `erp/models/__init__.py` | ❌ **ERP 74 张表全漏** |
| `<app>/<sub>/models.py` | `crm/integration/models.py` | ❌ 漏 5 张 |
| 不叫 models 的模型文件 | `system/store_models.py` | ❌ 漏 3 张 |

漏加载的表被 autogenerate 判成「库里多出来的」，于是生成 drop。

**放大器**：加载失败时静默 `pass`。少加载了没人知道，直到有人跑 autogenerate。

**现在的护栏**（详见权威文档 §6）：三种形态都认、递归跳过 `routers/`/`tests/`/`schemas/`、
非 models 命名的用 `EXTRA_MODEL_MODULES` 显式登记、**导入失败打到 stderr**。

**教训**：`--autogenerate` 是全库最危险的命令。跑之前先 `check_schema_drift.py`，
表级差异不为 0 就说明 models 没加载全，此时生成的任何 drop 都不可信。

---

## 3. 2026-10-27 CI 全红的真正原因：GitHub 账号被账单锁定

**现象**：CI 全红，但本地跑测试全绿。日志里是各种不相干的失败。

**根因**：GitHub 账号因账单问题被锁定，Actions 无法拉取 runner 镜像。
**它不报「账号被锁」，只表现为一堆看起来像代码问题的失败。**

**教训**：**CI 只在本地绿、远端红**时，先确认账号/额度/配额，再怀疑代码。
这类基础设施故障会伪装成代码 bug，浪费一整天。

---

## 4. 2026-10-28 `Can't locate revision`：merge 迁移只删了文件

**现象**：`alembic current` 报
`Can't locate revision identified by '20261021_0036_merge_heads'`，整条迁移链彻底不可用——
`current` / `heads` / `upgrade` 三条命令全部失效。

**根因**：`0036_merge_heads` 是当时误判「双 head」写的纯拓扑合并迁移。
后来发现 `gen_inventory` 重挂之后图本来就是单链，于是**把文件删了，但
`alembic_version` 里的记录没回退**。alembic 找不到这个 revision，直接瘫掉。

**处置**：把 `alembic_version` 对齐到代码里真实的 head，之后三条命令才恢复。

**教训**：**merge 迁移只能整体撤销，不能只删文件。** 真要撤掉一条 merge，
必须同时把库里的 `alembic_version` 改回它合并前的某个 head。

> 这条和 §7 是同一个病理：**数据库里的版本戳与代码里的迁移图是两个独立事实，
> 删代码不会自动改库。**

---

## 5. 2026-10-31 六份旁路 SQL 从未被执行

**现象**：开源用户 `git clone` 之后建库，`cms_sites` / `cms_ai_prompts` 这类地基表根本不存在，
应用起不来。而线上老库一切正常。

**根因**：`backend/migrations/` 下躺着 6 个旁路 SQL（多站点、embedding 维度、pgvector、
提示词表等）。**没有任何脚本执行它们**——不入 docker entrypoint、不入 bootstrap、不入 CI，
只有当初手工跑过一次。于是只有「当初那台机器」是对的。

**处置**：全部迁回 alembic，旁路 SQL 目录废弃。

**教训**：**DDL 只能有一个执行入口。** 任何「手工跑过的 SQL」都是定时炸弹——
它在你的机器上生效，在别人的机器上不存在，而且没有任何检查会发现。
这条现在是权威文档的规则四。

---

## 6. 2026-11-03 闭源迁移一度暴露在 `git add -A` 范围内

**现象**：40 个闭源迁移（含完整 ERP/MES/CRM 表结构）重新进入 git 扫描范围，
一次 `git add -A` 就是商业实现外泄。

**根因**：迁移文件按应用移入子目录（`versions/mes/` 等）后，原有规则失效了：

```gitignore
backend/alembic/versions/2026*_mes_*.py   # 扁平布局时代的写法，文件移进 mes/ 后匹配不到
```

**处置**：改为整目录屏蔽（`versions/crm/`、`erp/`、`mes/`、`collect/`），
`ext/` 这种混合目录逐个文件登记。

**教训**：**移动文件会静默废掉 `gitignore` 规则**，而 `git status` 不会报警——
它只会高高兴兴地把这些文件列成「未跟踪」。改目录结构后必须 `git status` 逐个核对。

规则现状见权威文档 §7。

---

## 7. 2026-11-28 `cms_sites` 缺失：版本戳领先于真实结构

**现象**：升级到 `20261127_1200_cms_site_plans` 时报

```
UndefinedTable: relation "cms_sites" does not exist
```

但 `alembic_version` 明明说已经在 `cms_sites` 之后了。

**根因**：2026-11 给 `merge_commerce` 追加 `cms_orphan` 作为**第二父节点**时，
那些「早就越过合流点」的老库只改了版本戳，CMS 分支的 DDL 从未执行过。
alembic 判定「已应用」**只看 DAG 位置，从不检查真实表是否存在**。

**关键点**：这次**迁移图本身是自洽的**。全新库 `alembic upgrade heads` 一次成功，
39 条迁移逐条审计也没有未保护的破坏性操作。问题纯粹在**库的版本戳**里。

**处置**：

1. `20261127_1200_cms_site_plans.py` 的 `upgrade()` 开头加 `_require_cms_sites()`，
   把裸 `UndefinedTable` 换成带修复指引的 `RuntimeError`；
2. 新增 `scripts/repair-cms-branch.py`：把版本戳退回到合流点、补跑 CMS 分支、
   再还原原版本戳（失败自动回滚）。

**实测**（四种源库全部通过，零数据丢失）：

| 源库状态 | 起点 revision | 补跑结果 | `upgrade heads` |
|---|---|---|---|
| 完全缺 4 张表 | `product_commerce` | 255 张表 | rc=0 |
| 缺 4 张表 | `app_schema` | 108 张表 | rc=0 |
| **部分缺**（有 sites/embeddings，缺 templates/entry_links） | `app_schema` | 精确补齐，已有的不重建 | rc=0 |
| 全新库 | — | 121 张表 | rc=0 |

数据无损：`audit_logs` 4215、`login_logs` 480、`app_orders` 54、`cms_news` 49、
`cms_entries` 25，全部与源库一致。重复执行幂等（输出「无需修复」）。

**教训**：**「迁移图正确」和「数据库结构正确」是两件事。**

alembic 用 DAG 位置判断「是否已应用」，这个判断在正常情况下够用，
但一旦有人手工改过 `alembic_version`、或给已合流的迁移追加过父节点，
两者就会分叉——而且**分叉后不报错，直到某段代码真的去查那张表**。

> 这和 §1 是同一个病理的不同变体。§1 是「拓扑说执行了，实际没执行」，
> 这里是「版本戳说越过了，实际没跑过」。共同结论：
> **凡涉及 DDL，必须直接查 `pg_class` / `pg_attribute`，不能只信版本号。**
>
> 具体诊断 SQL 与两条修复路径见权威文档 §10.1。

---

## 8. 这些事故共同的形状

七次事故，可以归成三类，每类都对应一条现在的硬规则：

| 类型 | 事故 | 现在怎么防 |
|---|---|---|
| **DAG 与真实库分叉** | §1、§4、§7 | DDL 前查 `pg_class`；`_require_xxx()` 显式判存；`repair-cms-branch.py` 可修 |
| **模型加载不全 → autogenerate 删表** | §2 | 三种 models 形态都认；导入失败打 stderr；`check_schema_drift.py` 表级差异必须为 0 |
| **DDL 有多个执行入口 / 无入口** | §5、§6 | 全部走 alembic；闭源迁移整目录 gitignore |

还有一条横跨所有事故的元教训：

> **这些故障全部表现为「服务健康、接口 500」。**
> 容器 healthy、进程在、端口通 —— 但某张表不存在。
> 所以「启动成功」和「环境健康」都不能证明迁移跑对了，
> 唯一的证据是**去库里查那个对象**。