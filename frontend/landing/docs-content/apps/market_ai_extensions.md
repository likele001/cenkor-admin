# AI 体系扩展应用 · 上架说明（cenkormes）

> **给谁看**：在 hub（cenkor-admin）这一侧做发布、定价、发卡、排查商店展示的人。
> 实例侧（CenkorMES）的安装/更新/卸载语义与运维口径不在这里重复，见 cenkormes 仓
> `docs/EXTENSIONS.md` §9。

首批三个 AI 扩展已于 **2026-10-17** 走完整链路：打包 → 首发 → 审核通过 → 商店富介绍 →
定价 → 发卡 → 实例安装 → 冒烟与卸载回归。当前在售版本 **1.0.3**（chat 与向量分网关），AI 知识库已到 **1.0.4**（问答留痕记模型）。


## 一、在售清单（hub 库实查，2026-10-17）

| app_key | 名称 | 版本 | `app_submissions.id` | 状态 | `file_hash` 前 12 位 |
|---------|------|------|---------------------|------|---------------------|
| `ai_scene_reports` | AI 场景文书 | **1.0.3** | 100 | approved | `9cbc4e5e383b` |
| `ai_insight` | AI 深度洞察 | **1.0.3** | 101 | approved | `fd4eec2f5d7d` |
| `ai_knowledge` | AI 知识库 | **1.0.4** | 103 | approved | `8869f75ed31d` |
| `ai_knowledge` | AI 知识库 | 1.0.3 | 102 | approved | `0d3cafb939b5` |

三个 key 的 1.0.0 / 1.0.1 历史行也都留在 `app_submissions`（同 `(product, app_key, version)` 唯一键，
可并存，实例侧只取最新 approved。1.0.2（id 97 / 98 / 99）为上一版，1.0.3 逐包改动见 `mes-extensions/<key>/README.md` 变更记录）。产品轴统一 `product='cenkormes'`，`category=ai`，`vendor=Cenkor`。

定价（`app_pricing`，唯一键 `(product, app_key)`）：

| 字段 | 值 | 说明 |
|------|-----|------|
| `model` | `one_time` | 买断 |
| `price_cents` / `currency` | `99` / `CNY` | **0.99 元** |
| `list_price_cents` | `0` | 划线价填 0 才不打折标签；填成与售价相同会打出难看的「X 折」 |
| `promo_price_cents` | `0` | 该列 **NOT NULL**，不打促销必须显式写 0 |
| `period_days` / `trial_days` / `min_seats` | `365` / `0` / `1` | |
| `developer_id` / `platform_fee_bp` | `1` / `0` | |

已发授权（manual 通道，`status=paid` 订单 + 真 token）：
`CKA-7M8J-6W5R-9BCU-GED5`（scene_reports）、`CKA-YX7H-ZQYE-SF7T-UVVR`（insight）、
`CKA-SRR4-FY76-BFZ3-6A3D`（knowledge），归属实例 `ins_f8vfn823j5mn` / `portal_user_id=21`。

## 二、发布链路（命令逐条，都在 `cenkor-admin/backend` 下执行）

```bash
# 0) 闸门：包结构与前端注册协议体检（27 个包全过才算绿）
python /www/wwwroot/mes-extensions/_selftest/manifest_check.py

# 1) 打包：--check 只校验，--build 才出 <key>-<version>.zip
python /www/wwwroot/mes-extensions/pack.py --check
python /www/wwwroot/mes-extensions/pack.py --build --keys ai_scene_reports ai_insight ai_knowledge

# 2) 发布：先干跑看 PLANNED，确认无误再 --apply
python scripts/publish_extension.py --keys ai_scene_reports ai_insight ai_knowledge
python scripts/publish_extension.py --keys ai_scene_reports ai_insight ai_knowledge --apply
#    全新 app_key 首次发布必须加 --allow-new（可选 --developer-id，默认沿用同产品最近一条历史行）

# 3) 商店富介绍（幂等，必跑，否则卡片摘要会兜底成整条 description）
PYTHONPATH=src python scripts/seed_app_intros.py

# 4) 手动发卡（dry-run 默认，--apply 才落库）
PYTHONPATH=src python scripts/grant_manual_license.py \
  --keys ai_scene_reports ai_insight ai_knowledge --product cenkormes --apply
```

产物落 `src/uploads/apps/<key>-<version>.zip`；`--apply` 写 `app_submissions` 并把 sha256 记进
`file_hash`。**发布后 hub 进程不需要重启** —— 商店与分发接口每次请求都现读库。

## 三、商店展示的取数优先级（踩过的坑）

列表与详情页的 `summary` 按这条链取值（`src/cenkor_admin/apps/system/store_router.py:289`）：

```
app_intros.summary  →  manifest.summary  →  SHOWCASE.summary  →  description 整条兜底
```

新包没有 `app_intros` 行时，卡片摘要会变成整条 description（实测 373 / 511 / 534 字顶在摘要位，
`tags` 为空）。正规做法是往 `scripts/seed_app_intros.py` 的 `INTROS` 字典补条目
（summary 约 45 字 + 5 个 tags + 5 条 highlights + long_description）再跑一遍 —— 不要直接改库。
补完实测：摘要 41 / 44 / 42 字，tags 各 5 个，详情页 highlights 5 条、long_description 371 / 405 / 433 字。

## 四、首发会卡的三处（都已在脚本里解决，记录成因）

1. **`publish_extension.py` 对全新 key 一律 SKIP**：它是增量发布器，`baseline_row()` 要先查到同
   `(product, app_key)` 的旧行来继承 `developer_id / dev_method / name / icon / category`。
   `pack.py --check` 全绿也救不了它 —— 首发得走 `--allow-new`，字段改从 manifest 取。
2. **`promo_price_cents` NOT NULL**：定价写库时必须显式给 0。
3. **`list_price_cents` 等于售价会打出折扣标签**：`<= 0` 才不打。

## 五、分发与授权校验

实例侧下载走 `GET /api/v1/store/cloud/packages/{app_key}?license_key=`
（`src/apps/commerce/commerce_router.py:1324`）。实例的市场页只列 `approved` 版本，
「已购买 / 最新版本」由 `_purchases_for(db, portal_user_id, product=...)` 现算 ——
所以改完库在实例点一次刷新授权即可看到新版本，不用重启 hub，也不用重启实例后端
（扩展是热挂载，单进程 uvicorn 下即时生效）。

## 六、更新与回滚

- **更新**：改 `manifest.json` 的 `version` → `pack.py --build` → `publish_extension.py --apply`
  （同 key 新版本是 INSERT，不是覆盖，历史版本可追溯）。
- **打包会把包目录里的文件全收进去**：改代码时随手留的备份（`router.py.102bak` 这种）会混进 zip，
  1.0.3 首发就中过一次。备份一律移出包目录（现存 `lightmes/.local-backups/ext-staging/102bak/`），
  `pack.py` 的排除规则也已补上 `\.\d+bak$`。
- 同一步要发布**已存在的版本行**时（改内容重发同一 version），走的是 UPDATE，会同步刷新
  `file_path`/`file_hash`/`manifest_data`；只要确认还没人装过这个版本，重发没有副作用。
- **回滚**：没有独立的 unpublish 步骤，`approve` 即上架。要撤下某版本，把该 `app_submissions.id`
  的 `status` 改回 `pending`/`rejected`；实例端已装的不会被远程卸载（fail-open，心跳只同步快照）。
- **包内 sha 一致性**：`--apply` 后务必双校 —— 库里 `file_hash` vs 磁盘 zip 的 sha256，
  再看 zip 成员（成员路径是包内相对路径 `frontend/plugin.js`，不是 `<key>/frontend/plugin.js`）。

## 七、产品边界（商店详情页与 README 都写明了）

- 知识库文档解析**仅支持在线粘贴与 `.txt` / `.md`**，**不支持 docx / pdf**
  （实例未装 `python-docx` / `pymupdf`，本批不新增依赖），不支持图片 OCR / URL 抓取 / 批量导入。
- 单篇正文 20 ~ 200000 字符。
- AI 网关未配置时全部降级可用（规则层出结论、检索走关键词），不报错、不空页。
- 向量通道已在真实网关下端到端跑通（2026-10-17，火山方舟 `doubao-embedding-vision`，2048 维）：
  建文档即向量化、近义问法命中 `mode=vector` 且正确文档排第一、删文档不留孤儿向量。
  配置需**两处配齐**（平台「AI 网关/模型」+ 本扩展「参数设置 → embedding 模型」），
  只配一处会静默降级；实例侧完整口径见 cenkormes `docs/EXTENSIONS.md` §九·1。
- **1.0.3 起 chat 与向量分网关**：三个应用的「参数设置」都有**对话模型标识**，AI 知识库另有
  **向量模型标识**，填平台「AI 网关/模型」里模型行的**标识（code）**，留空=跟随平台默认模型。
  这样向量模型占着默认也不影响问答/文书/洞察走 MiniMax 等对话网关（反之亦然）。
  ⚠️ 标识填错宿主会**静默回落到默认模型**，保存后要看应用回显的「当前生效模型」确认。
  同时 1.0.3 把向量维度记进配置与集合 metadata，换模型/换维度会**拒写并给出可读原因**
  （处理入口：批量重建索引 + 勾选「重建集合」），`/status` 的 `llm_ready` 也不再是恒真。
- 三个包只读写自己的 `ext_ai_*` 表与自己的向量目录，不触碰任何核心业务表。

## 八、交付验证清单（本轮实测结果）

| 项 | 结果 |
|----|------|
| `pack.py --check` | 27 个包，0 个不通过 |
| `manifest_check.py` 闸门 | ✅（含 4 条前端硬校验：渲染函数 / locales / 组件 name / 迁移形态） |
| 包外自测（须在实例 `backend` 目录下跑） | 33 / 39 / **61** 项，失败 0（1.0.4 新增降级文案与留痕记模型 11 条） |
| HTTP 冒烟（1.0.2，21 项） | 全绿，含三条「拿返回 id 立刻回读详情」回归位 |
| 卸载回归（`ai_knowledge` 三轮快照） | 只有该变的变了；表、参数、授权、向量目录原样 |
| 向量通道端到端（真实 embedding） | 13 项断言全绿：`vectorized=1`、`vector_id` 回填、`chroma_vectors` 0→2→0、`mode=vector` 命中正确文档 |
| hub 库 sha 双校 | 10 行全 √（1.0.1 / 1.0.2 / 1.0.3 × 3 + ai_knowledge 1.0.4），每包 zip 成员 5 个（无备份文件） |
| 商店接口价格 | `price.unit_price="0.99"`、`is_discounted=false`、`discount_label=null` |
